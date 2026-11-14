"""retrieval.hybrid with fake models (no downloads): RRF fusion, reranking, graph expansion, mode checks."""

import numpy as np
import pytest

pytest.importorskip("faiss")
from retrieval.chunker import Chunk  # noqa: E402
from retrieval.hybrid import HybridIndex, chunk_text  # noqa: E402
from retrieval.index import RepoIndex  # noqa: E402

WORDS = ["parse", "default", "option", "help", "prompt", "error"]


class FakeModels:
    """Embeds by word counts over a tiny vocabulary; reranks by the count of 'prompt'."""

    def embed(self, texts):
        m = np.array([[t.lower().count(w) + 0.01 for w in WORDS] for t in texts], dtype=np.float32)
        return m / np.linalg.norm(m, axis=1, keepdims=True)

    def rerank(self, query, texts):
        return [float(t.count("prompt")) for t in texts]


def chunks():
    mk = lambda i, sym, text: Chunk("code", "src/p/m.py", i * 10 + 1, i * 10 + 9, sym, text)  # noqa: E731
    return [mk(0, "parse_args", "def parse_args(): parse parse option"),
            mk(1, "get_default", "def get_default(): default default value"),
            mk(2, "prompt_user", "def prompt_user(): prompt prompt default"),
            mk(3, "show_help", "def show_help(): help text option"),
            Chunk("doc", "docs/x.rst", 1, 5, "Options", "option default documented")]


@pytest.fixture
def index():
    return HybridIndex(RepoIndex(chunks()), {"retrieval": {"hybrid": {"rerank_depth": 10}}}, models=FakeModels())


def test_modes(index):
    assert index.search("default", 1, mode="bm25")[0].chunk.symbol == "get_default"
    assert index.search("default", 1, mode="dense")[0].chunk.symbol == "get_default"
    assert {h.chunk.symbol for h in index.search("default", 3, mode="rrf")} >= {"get_default", "prompt_user"}
    assert index.search("default", 1, mode="rerank")[0].chunk.symbol == "prompt_user", "the fake reranker favours 'prompt'"
    assert index.search("option default", 1, kind="doc", mode="rrf")[0].chunk.kind == "doc"
    with pytest.raises(ValueError):
        index.search("x", mode="nope")


def test_graph_expansion_adds_callees():
    class G:
        functions = {"m.show_help": type("F", (), {"path": "src/p/m.py", "start": 31})()}

        def function_at(self, path, line):
            return type("F", (), {"qualname": "m.prompt_user"})() if line == 21 else None

        def neighbours(self, q):
            return ([], ["m.show_help"]) if q == "m.prompt_user" else ([], [])
    idx = HybridIndex(RepoIndex(chunks()), {}, models=FakeModels(), graph=G())
    syms = [h.chunk.symbol for h in idx.search("default", 4, mode="graph")]
    assert "show_help" in syms


def test_chunk_text_is_cut():
    c = chunks()[0]
    assert chunk_text(c, 10).startswith("src/p/m.py parse_args\n") and len(chunk_text(c, 10)) < 40
