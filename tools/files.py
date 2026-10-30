"""`open_file`: show numbered lines of a file in the frozen tree (read-only, at most 200 lines)."""

from __future__ import annotations

from tools.workspace import Workspace

MAX_LINES = 200


def open_file(ws: Workspace, path: str, start: int = 1, end: int = 0) -> str:
    """Line numbers are the real ones, so the model can cite them. `end=0` means start + 199."""
    target = ws.resolve(path)
    if not target.is_file():
        raise FileNotFoundError(f"{path!r} does not exist in the frozen repository")
    lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    start = max(start, 1)
    end = end if end >= start else start + MAX_LINES - 1
    end = min(end, start + MAX_LINES - 1, len(lines))
    if start > len(lines):
        return f"{path} has only {len(lines)} lines."
    body = "\n".join(f"{i:5d}  {lines[i - 1]}" for i in range(start, end + 1))
    more = f"\n... file continues to line {len(lines)}" if end < len(lines) else ""
    return f"{path} lines {start}-{end}:\n{body}{more}"
