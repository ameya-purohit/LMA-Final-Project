"""Split a frozen tree into searchable chunks, each with its path and line range.

Code chunks come from the AST: module-level functions, methods, class headers
(the class up to its first method) and runs of top-level statements (constants
and assignments often decide behaviour). Doc chunks are `.rst`/`.md` sections
split at headings, plus docstrings.

Why the AST and not fixed-size windows: a chunk that is one whole function gives
the model a complete, citable unit, and its line range is exact.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

MAX_CHUNK_LINES = 120
_MD_HEADING = re.compile(r"^#{1,6}\s")
_RST_UNDERLINE = re.compile(r"^([=\-~^\"'`*+#])\1{2,}\s*$")


@dataclass
class Chunk:
    kind: str          # "code" or "doc"
    path: str          # relative to the tree root
    line_start: int
    line_end: int
    symbol: str
    text: str


def _slice(lines: list[str], start: int, end: int) -> str:
    return "\n".join(lines[start - 1: min(end, start + MAX_CHUNK_LINES - 1)])


def chunk_python(source: str, rel_path: str) -> tuple[list[Chunk], list[Chunk]]:
    """(code chunks, docstring chunks) of one Python file. A file that does not parse gives none."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return [], []
    lines = source.splitlines()
    code: list[Chunk] = []
    docs: list[Chunk] = []

    def add_doc(node: ast.AST, symbol: str) -> None:
        text = ast.get_docstring(node)
        if text and node.body:  # type: ignore[attr-defined]
            first = node.body[0]  # type: ignore[attr-defined]
            docs.append(Chunk("doc", rel_path, first.lineno, first.end_lineno, symbol, text))

    def first_line(node: ast.AST) -> int:
        decos = getattr(node, "decorator_list", [])
        return min([d.lineno for d in decos] + [node.lineno])  # type: ignore[attr-defined]

    def add_function(node: ast.AST, symbol: str) -> None:
        start = first_line(node)
        code.append(Chunk("code", rel_path, start, node.end_lineno, symbol,  # type: ignore[attr-defined]
                          _slice(lines, start, node.end_lineno)))  # type: ignore[attr-defined]
        add_doc(node, symbol)

    add_doc(tree, rel_path)
    pending: list[ast.stmt] = []

    def flush() -> None:
        if pending:
            start, end = pending[0].lineno, pending[-1].end_lineno
            code.append(Chunk("code", rel_path, start, end, "<module>", _slice(lines, start, end)))
            pending.clear()

    for stmt in tree.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            flush()
            add_function(stmt, stmt.name)
        elif isinstance(stmt, ast.ClassDef):
            flush()
            methods = [n for n in stmt.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            start = first_line(stmt)
            end = first_line(methods[0]) - 1 if methods else stmt.end_lineno
            code.append(Chunk("code", rel_path, start, end, stmt.name, _slice(lines, start, end)))
            add_doc(stmt, stmt.name)
            for m in methods:
                add_function(m, f"{stmt.name}.{m.name}")
        elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
            continue  # the module docstring
        else:
            pending.append(stmt)
    flush()
    return code, docs


def chunk_markup(text: str, rel_path: str) -> list[Chunk]:
    """Sections of an .rst or .md file, split at headings."""
    lines = text.splitlines()
    starts = [0]
    for i, line in enumerate(lines):
        if _MD_HEADING.match(line) and rel_path.endswith(".md"):
            starts.append(i)
        elif i > 0 and _RST_UNDERLINE.match(line) and lines[i - 1].strip() and rel_path.endswith(".rst"):
            starts.append(i - 1)
    starts = sorted(set(starts))
    out = []
    for a, b in zip(starts, starts[1:] + [len(lines)]):
        body = "\n".join(lines[a:min(b, a + MAX_CHUNK_LINES)]).strip()
        if body:
            out.append(Chunk("doc", rel_path, a + 1, b, lines[a].strip()[:80], body))
    return out


def chunk_tree(tree: str | Path, package: str, source_root: str = ".") -> list[Chunk]:
    """All chunks of a frozen tree: package code and docstrings, then docs and top-level markup files."""
    tree = Path(tree)
    chunks: list[Chunk] = []
    pkg = tree / source_root / package
    for path in sorted(pkg.rglob("*.py")):
        rel = path.relative_to(tree).as_posix()
        code, docs = chunk_python(path.read_text(encoding="utf-8", errors="replace"), rel)
        chunks += code + docs
    markup = sorted(tree.glob("*.rst")) + sorted(tree.glob("*.md"))
    if (tree / "docs").is_dir():
        markup += sorted((tree / "docs").rglob("*.rst")) + sorted((tree / "docs").rglob("*.md"))
    for path in markup:
        rel = path.relative_to(tree).as_posix()
        chunks += chunk_markup(path.read_text(encoding="utf-8", errors="replace"), rel)
    return chunks
