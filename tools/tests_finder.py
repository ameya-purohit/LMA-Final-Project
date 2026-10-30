"""`find_tests`: where a symbol appears in the repository's own tests at the frozen commit."""

from __future__ import annotations

import re

from tools.static import enclosing_def
from tools.workspace import Workspace

MAX_RESULTS = 30


def find_tests(ws: Workspace, symbol: str) -> str:
    """Lines in test files naming the symbol, with the test they are in and its node id form."""
    name = symbol.split(".")[-1].strip()
    if not name.isidentifier():
        raise ValueError(f"{symbol!r} is not a Python name")
    tests_root = ws.tree / ws.tests_dir
    if not tests_root.is_dir():
        return f"This repository has no {ws.tests_dir}/ directory."
    pattern = re.compile(rf"\b{re.escape(name)}\b")
    out: list[str] = []
    for path in sorted(tests_root.rglob("*.py")):
        text = path.read_text(encoding="utf-8", errors="replace")
        rel = path.relative_to(ws.tree).as_posix()
        for i, line in enumerate(text.splitlines(), 1):
            if pattern.search(line):
                owner = enclosing_def(text, i)
                where = f"{rel}::{owner}" if owner else rel
                out.append(f"{where} (line {i})  {line.strip()[:90]}")
                if len(out) >= MAX_RESULTS:
                    return "\n".join(out) + "\n... more results not shown"
    return "\n".join(out) if out else f"No test mentions {symbol!r}."
