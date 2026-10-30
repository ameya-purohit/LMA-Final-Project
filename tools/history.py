"""`git_log` and `git_blame`, run on the bare clone AT the frozen commit.

Both name the commit explicitly, so no history after the question can appear:
the later fix is invisible.
"""

from __future__ import annotations

import subprocess

from tools.workspace import Workspace


def _git(ws: Workspace, *args: str) -> str:
    if ws.repo is None or ws.commit is None:
        return "No git history is available for this repository."
    p = subprocess.run(["git", "-C", str(ws.repo), *args], capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip()[-200:] or "git failed")
    return p.stdout.strip()


def _checked(ws: Workspace, path: str) -> str:
    ws.resolve(path)  # raises if it escapes the tree
    if path.startswith("-"):
        raise ValueError(f"bad path {path!r}")
    return path


def git_log(ws: Workspace, path: str, n: int = 10) -> str:
    n = max(1, min(n, 30))
    out = _git(ws, "log", f"-n{n}", "--date=short", "--format=%h %ad %s", ws.commit or "HEAD", "--", _checked(ws, path))
    return out or f"No history for {path} at the frozen commit."


def git_blame(ws: Workspace, path: str, start: int, end: int) -> str:
    start = max(1, start)
    end = min(max(start, end), start + 100)
    return _git(ws, "blame", "--date=short", "-s", f"-L{start},{end}", ws.commit or "HEAD", "--", _checked(ws, path))
