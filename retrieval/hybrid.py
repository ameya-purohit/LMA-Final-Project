"""Hybrid retrieval: BM25 + dense embeddings, fused with RRF, then reranked by a cross-encoder (extension, E2+).

The existing BM25 index (`retrieval/index.py`) stays exactly as it was; this module adds, per frozen tree:
- a **dense** index: each chunk embedded by a small embedding model and searched by cosine similarity with FAISS;
- **RRF** (reciprocal rank fusion) of the BM25 and dense rankings, which needs no score calibration;
- a **cross-encoder** that re-scores the top fused candidates by reading query and chunk together;
- optional **graph expansion** (R5): callers and callees of the top hits, from the code graph, fused in by RRF.

Retrieval modes, also the retrieval study's configurations: bm25 (R1), dense (R2), rrf (R3), rerank (R4), graph (R5).

Models run locally through `fastembed` (ONNX, no PyTorch), so nothing is sent to an API and no quota is used. They
are small on purpose: this laptop has about 1 GB of free memory, and a chunk's text is cut to 800 characters
(measured: 1,500 characters took twice as long to embed). Test functions get BM25 only. Embeddings are cached on disk by a hash of the
model and the chunk text, so a function that is identical across many frozen commits is embedded once.
Chunking is the existing AST chunker (one function or method per chunk), so every hit is a complete, citable unit.
"""

from __future__ import annotations

import hashlib
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from codegraph.rank import rrf
from retrieval.chunker import Chunk, chunk_python
from retrieval.index import Hit, Index, RepoIndex

MODES = ("bm25", "dense", "rrf", "rerank", "graph")
DEFAULTS = {"dense_model": "BAAI/bge-small-en-v1.5", "rerank_model": "Xenova/ms-marco-MiniLM-L-6-v2",
            "rrf_k": 60, "fuse_depth": 50, "rerank_depth": 30, "max_chars": 800, "batch_size": 8}


def chunk_text(c: Chunk, max_chars: int) -> str:
    """What the models read for a chunk: where it is, its name, and the start of its text."""
    return f"{c.path} {c.symbol}\n{c.text[:max_chars]}"


class EmbeddingCache:
    """SQLite store of embeddings keyed by sha256(model, text). Thread-safe enough for one process."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.execute("CREATE TABLE IF NOT EXISTS emb (k TEXT PRIMARY KEY, v BLOB)")
        self._lock = threading.Lock()

    @staticmethod
    def key(model: str, text: str) -> str:
        return hashlib.sha256(f"{model}\0{text}".encode()).hexdigest()

    def get_many(self, keys: list[str]) -> dict[str, np.ndarray]:
        out: dict[str, np.ndarray] = {}
        with self._lock:
            for i in range(0, len(keys), 500):
                part = keys[i:i + 500]
                rows = self._db.execute(f"SELECT k, v FROM emb WHERE k IN ({','.join('?' * len(part))})", part)
                out.update({k: np.frombuffer(v, dtype=np.float32) for k, v in rows})
        return out

    def put_many(self, items: dict[str, np.ndarray]) -> None:
        with self._lock:
            self._db.executemany("INSERT OR REPLACE INTO emb VALUES (?, ?)",
                                 [(k, v.astype(np.float32).tobytes()) for k, v in items.items()])
            self._db.commit()


class Models:
    """The embedding model and the cross-encoder, loaded once per process (they take a few seconds)."""

    _instance: "Models | None" = None

    def __init__(self, dense_model: str, rerank_model: str, cache_dir: Path, emb_cache: EmbeddingCache):
        from fastembed import TextEmbedding
        from fastembed.rerank.cross_encoder import TextCrossEncoder
        self.dense_name, self.rerank_name = dense_model, rerank_model
        self.dense = TextEmbedding(dense_model, cache_dir=str(cache_dir))
        self.reranker = TextCrossEncoder(rerank_model, cache_dir=str(cache_dir))
        self.cache = emb_cache
        self.batch_size = 8

    @classmethod
    def get(cls, config: dict[str, Any]) -> "Models":
        from core.config import REPO_ROOT
        h = {**DEFAULTS, **config.get("retrieval", {}).get("hybrid", {})}
        if cls._instance is None or cls._instance.dense_name != h["dense_model"]:
            cache = REPO_ROOT / config["paths"]["cache_dir"]
            cls._instance = cls(h["dense_model"], h["rerank_model"], cache / "models",
                                EmbeddingCache(cache / "embeddings.sqlite"))
        return cls._instance

    def embed(self, texts: list[str]) -> np.ndarray:
        keys = [EmbeddingCache.key(self.dense_name, t) for t in texts]
        have = self.cache.get_many(keys)
        missing = [(k, t) for k, t in zip(keys, texts) if k not in have]
        if missing:
            vecs = list(self.dense.embed([t for _, t in missing], batch_size=self.batch_size))
            new = {k: np.asarray(v, dtype=np.float32) for (k, _), v in zip(missing, vecs)}
            self.cache.put_many(new)
            have.update(new)
        mat = np.stack([have[k] for k in keys]) if keys else np.zeros((0, 1), dtype=np.float32)
        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        return mat / np.maximum(norms, 1e-12)

    def rerank(self, query: str, texts: list[str]) -> list[float]:
        return [float(s) for s in self.reranker.rerank(query, texts)] if texts else []


class DenseIndex:
    """FAISS inner-product index over normalized embeddings (= cosine similarity)."""

    def __init__(self, chunks: list[Chunk], models: Models, max_chars: int):
        import faiss
        self.chunks = chunks
        self.models = models
        self.max_chars = max_chars
        vecs = models.embed([chunk_text(c, max_chars) for c in chunks]) if chunks else None
        self.index = None
        if vecs is not None and len(vecs):
            self.index = faiss.IndexFlatIP(vecs.shape[1])
            self.index.add(vecs)

    def search(self, query: str, k: int) -> list[Hit]:
        if self.index is None:
            return []
        q = self.models.embed([query])
        scores, ids = self.index.search(q, min(k, len(self.chunks)))
        return [Hit(self.chunks[i], float(s)) for s, i in zip(scores[0], ids[0]) if i >= 0]


@dataclass
class _Kind:
    bm25: Index
    dense: DenseIndex | None  # None for tests: BM25 only (embedding them doubled the build time on this laptop)


class HybridIndex:
    """BM25 + dense + RRF + cross-encoder over the code, doc and test chunks of one frozen tree."""

    def __init__(self, base: RepoIndex, config: dict[str, Any], *, tests: list[Chunk] | None = None,
                 graph: Any = None, models: Models | None = None):
        self.h = {**DEFAULTS, **config.get("retrieval", {}).get("hybrid", {})}
        self.models = models or Models.get(config)
        self.graph = graph
        self.kinds = {
            "code": _Kind(base.code, DenseIndex(base.code.chunks, self.models, self.h["max_chars"])),
            "doc": _Kind(base.docs, DenseIndex(base.docs.chunks, self.models, self.h["max_chars"])),
        }
        if tests:
            self.kinds["test"] = _Kind(Index(tests), None)

    def search(self, query: str, k: int = 5, *, kind: str = "code", mode: str = "rerank") -> list[Hit]:
        if mode not in MODES:
            raise ValueError(f"unknown retrieval mode {mode!r}")
        idx = self.kinds.get(kind)
        if idx is None:
            return []
        depth = self.h["fuse_depth"]
        if mode == "bm25" or idx.dense is None:
            return idx.bm25.search(query, k)
        if mode == "dense":
            return idx.dense.search(query, k)
        bm = idx.bm25.search(query, depth)
        de = idx.dense.search(query, depth)
        key = lambda h: (h.chunk.path, h.chunk.line_start, h.chunk.symbol)  # noqa: E731
        by_key = {key(h): h.chunk for h in bm + de}
        fused = [by_key[x] for x in rrf([[key(h) for h in bm], [key(h) for h in de]], k=self.h["rrf_k"])]
        if mode == "rrf":
            return [Hit(c, 0.0) for c in fused[:k]]
        top = fused[: self.h["rerank_depth"]]
        scores = self.models.rerank(query, [chunk_text(c, self.h["max_chars"]) for c in top])
        reranked = [c for _, c in sorted(zip(scores, top), key=lambda x: -x[0])]
        if mode == "rerank" or self.graph is None or kind != "code":
            return [Hit(c, s) for c, s in zip(reranked[:k], sorted(scores, reverse=True))]
        return [Hit(c, 0.0) for c in self._expand(reranked)[:k]]

    def _expand(self, ranked: list[Chunk]) -> list[Chunk]:
        """R5: fuse in the callers and callees of the top three hits (one hop in the call graph)."""
        chunks = self.kinds["code"].bm25.chunks
        by_fn: dict[tuple[str, int], Chunk] = {(c.path, c.line_start): c for c in chunks}
        neighbours: list[Chunk] = []
        for c in ranked[:3]:
            f = self.graph.function_at(c.path, c.line_start)
            if f is None:
                continue
            callers, callees = self.graph.neighbours(f.qualname)
            for q in callees + callers:
                g = self.graph.functions[q]
                hit = by_fn.get((g.path, g.start))
                if hit is not None and hit not in neighbours:
                    neighbours.append(hit)
        if not neighbours:
            return ranked
        ident = {id(c): c for c in ranked + neighbours}
        return [ident[i] for i in rrf([[id(c) for c in ranked], [id(c) for c in neighbours]], k=self.h["rrf_k"],
                                      weights=[1.0, 0.5])]

    def starting_material(self, query: str, code_k: int = 5, doc_k: int = 3, mode: str = "rerank") -> tuple[list[Hit], list[Hit]]:
        return (self.search(query, code_k, kind="code", mode=mode),
                self.search(query, doc_k, kind="doc", mode="rerank" if mode == "graph" else mode))


def test_chunks(tree: str | Path, tests_dir: str = "tests") -> list[Chunk]:
    """The repository's own test functions as chunks (kind "test"), for the `search_tests` tool."""
    root = Path(tree)
    out: list[Chunk] = []
    for path in sorted((root / tests_dir).rglob("test_*.py")) if (root / tests_dir).is_dir() else []:
        code, _ = chunk_python(path.read_text(encoding="utf-8", errors="replace"), path.relative_to(root).as_posix())
        out += [Chunk("test", c.path, c.line_start, c.line_end, c.symbol, c.text) for c in code if c.symbol != "<module>"]
    return out
