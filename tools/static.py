"""`find_definition` (jedi) and `find_references` (word-boundary search).

jedi parses code without importing or running it, so looking up a name the
model supplied is safe on the host. `find_references` is a plain word-boundary
search on purpose (D-32): it also finds uses through aliases and dynamic
attribute access that a type-aware search would miss, it is fast, and every
result is easy to explain.
"""

from __future__ import annotations

import ast
import re

import jedi

from tools.workspace import Workspace

MAX_DEFINITIONS = 10
MAX_REFERENCES = 40


def find_definition(ws: Workspace, symbol: str) -> str:
    """Where a name is defined. `Class.method` searches for `method`, then prefers that class."""
    name = symbol.split(".")[-1].strip()
    if not name.isidentifier():
        raise ValueError(f"{symbol!r} is not a Python name")
    project = jedi.Project(path=str(ws.tree), added_sys_path=[str(ws.tree / ws.source_root)], smart_sys_path=False,
                           load_unsafe_extensions=False)
    found: list[str] = []
    try:
        for d in project.search(name, all_scopes=True):
            if d.module_path is None or d.line is None or not str(d.module_path).startswith(str(ws.tree)):
                continue
            # rel = str(d.module_path)[len(str(ws.tree)) + 1:]
            rel = str(d.module_path)[len(str(ws.tree)) + 1:].replace("\\", "/")
            if rel.startswith(ws.tests_dir + "/"):
                continue
            line = (d.description or "").strip()
            full = d.full_name or name
            entry = f"{rel}:{d.line}  {full}  ({line[:80]})"
            if symbol in full or "." not in symbol:
                found.insert(0, entry)
            else:
                found.append(entry)
    except Exception:  # jedi has internal bugs (a TypeError searching for `__init__`, seen on click): use the AST
        found = _definitions_from_ast(ws, symbol)
    if not found:
        return f"No definition of {symbol!r} found in the repository."
    return "\n".join(found[:MAX_DEFINITIONS])


def _definitions_from_ast(ws: Workspace, symbol: str) -> list[str]:
    """Definitions of a name by walking package ASTs; `Class.method` keeps only that class's method."""
    name = symbol.split(".")[-1]
    owner = symbol.split(".")[-2] if "." in symbol else None
    out: list[str] = []

    def visit(node: ast.AST, prefix: str, rel: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if child.name == name and (owner is None or prefix.endswith(f"{owner}.")):
                    out.append(f"{rel}:{child.lineno}  {prefix}{child.name}")
                visit(child, f"{prefix}{child.name}.", rel)

    for path in sorted((ws.tree / ws.source_root / ws.package).rglob("*.py")):
        try:
            visit(ast.parse(path.read_text(encoding="utf-8", errors="replace")), "", path.relative_to(ws.tree).as_posix())
        except SyntaxError:
            continue
    return out


def find_references(ws: Workspace, symbol: str) -> str:
    """Every line of package code that mentions the name, as a whole word."""
    name = symbol.split(".")[-1].strip()
    if not name.isidentifier():
        raise ValueError(f"{symbol!r} is not a Python name")
    pattern = re.compile(rf"\b{re.escape(name)}\b")
    out: list[str] = []
    total = 0
    for path in sorted((ws.tree / ws.source_root / ws.package).rglob("*.py")):
        rel = path.relative_to(ws.tree).as_posix()
        for i, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if pattern.search(line):
                total += 1
                if len(out) < MAX_REFERENCES:
                    out.append(f"{rel}:{i}  {line.strip()[:100]}")
    if not out:
        return f"No references to {symbol!r} in the package code."
    extra = f"\n... and {total - len(out)} more" if total > len(out) else ""
    return "\n".join(out) + extra


def enclosing_def(source: str, line: int) -> str | None:
    """Name of the innermost function or class containing `line`, or None."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    best: str | None = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.lineno <= line <= node.end_lineno:
                best = node.name
    return best
