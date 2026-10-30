"""BM25 indexes over one frozen tree, with code and docs kept apart.

Separate indexes let the agent know which kind of source it is reading, which
is the whole point of the project: a statement from the docs is a weaker kind
of evidence than the code. Embeddings are left out of the must-have tier
(a logged deviation from the proposal).

Starting material (top 5 code + top 3 doc chunks) is computed here and is
identical for every system.
"""

from __future__ import annotations

import pickle
import re
from dataclasses import dataclass
from pathlib import Path

from rank_bm25 import BM25Okapi

from retrieval.chunker import Chunk, chunk_tree

_WORD = re.compile(r"[A-Za-z0-9]+")
_CAMEL = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")


def tokenize(text: str) -> list[str]:
    """Lower-cased words; snake_case and camelCase are split, and the whole identifier is kept too.

    So `is_eager` matches both the query "eager" and the query "is_eager".
    """
    out: list[str] = []
    for token in re.findall(r"[A-Za-z0-9_]+", text):
        parts = [p for w in token.split("_") if w for p in _CAMEL.findall(w)]
        out.extend(p.lower() for p in parts)
        if len(parts) > 1:
            out.append(token.lower())
    return out


@dataclass
class Hit:
    chunk: Chunk
    score: float


class Index:
    """One BM25 index over a list of chunks."""

    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        self._tokens = [tokenize(c.text + " " + c.symbol) or ["_"] for c in chunks]
        self._sets = [set(t) for t in self._tokens]
        self._bm25 = BM25Okapi(self._tokens) if chunks else None

    def search(self, query: str, k: int = 5) -> list[Hit]:
        if self._bm25 is None:
            return []
        terms = tokenize(query) or ["_"]
        scores = self._bm25.get_scores(terms)
        # A chunk qualifies if it shares a query word. Its BM25 score alone cannot decide this: on a small
        # corpus, a word in half the chunks gets an IDF of exactly zero, though the chunk does match.
        overlap = [len(self._sets[i].intersection(terms)) for i in range(len(self.chunks))]
        order = sorted((i for i in range(len(self.chunks)) if overlap[i]), key=lambda i: (-scores[i], -overlap[i], i))
        return [Hit(self.chunks[i], float(scores[i])) for i in order[:k]]


class RepoIndex:
    """The code index and the doc index of one (library, commit)."""

    def __init__(self, chunks: list[Chunk]):
        self.code = Index([c for c in chunks if c.kind == "code"])
        self.docs = Index([c for c in chunks if c.kind == "doc"])

    def starting_material(self, query: str, code_k: int = 5, doc_k: int = 3) -> tuple[list[Hit], list[Hit]]:
        return self.code.search(query, code_k), self.docs.search(query, doc_k)


def load_or_build(tree: str | Path, package: str, source_root: str, cache_file: str | Path | None = None) -> RepoIndex:
    """Indexes are cached per (library, commit), because a frozen tree never changes."""
    if cache_file and Path(cache_file).exists():
        with open(cache_file, "rb") as fh:
            return pickle.load(fh)
    index = RepoIndex(chunk_tree(tree, package, source_root))
    if cache_file:
        Path(cache_file).parent.mkdir(parents=True, exist_ok=True)
        with open(cache_file, "wb") as fh:
            pickle.dump(index, fh)
    return index


def format_hit(hit: Hit, max_lines: int = 60) -> str:
    """A chunk as text for the model, with real line numbers so it can cite them."""
    c = hit.chunk
    body = c.text.splitlines()
    numbered = body[:max_lines]
    if c.kind == "code":
        numbered = [f"{c.line_start + i:5d}  {ln}" for i, ln in enumerate(numbered)]
    tail = [f"... ({len(body) - max_lines} more lines; use open_file)"] if len(body) > max_lines else []
    return "\n".join([f"[{c.kind}] {c.path}:{c.line_start}-{c.line_end} ({c.symbol})"] + numbered + tail)


def format_starting_material(code_hits: list[Hit], doc_hits: list[Hit]) -> str:
    """The text every system receives as its starting material."""
    parts = ["## Code retrieved for this question"] + [format_hit(h) for h in code_hits]
    parts += ["## Documentation retrieved for this question"] + [format_hit(h, 30) for h in doc_hits]
    return "\n\n".join(parts)
