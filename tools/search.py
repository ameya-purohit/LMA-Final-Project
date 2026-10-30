"""`search_code` and `search_docs`: BM25 over the frozen tree, code and docs kept separate."""

from __future__ import annotations

from retrieval.index import format_hit
from tools.workspace import Workspace


def _search(index, query: str, k: int, label: str) -> str:
    hits = index.search(query, k)
    if not hits:
        return f"No {label} matched {query!r}. Try different words."
    return "\n\n".join(format_hit(h, 40) for h in hits)


def search_code(ws: Workspace, query: str, k: int = 5) -> str:
    return _search(ws.index.code, query, k, "code")


def search_docs(ws: Workspace, query: str, k: int = 5) -> str:
    return _search(ws.index.docs, query, k, "documentation")
