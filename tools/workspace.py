"""What a system may see for one question: the frozen tree and nothing else.

`Workspace` deliberately has `__slots__`, and is built from the library and the
frozen commit only. The fix, the PR, the `fail_to_pass` test names and the gold
fields cannot reach it, so no system can leak the answer key by accident
(CLAUDE.md §6.9). A test asserts this.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from core.config import REPO_ROOT


def detect_source_root(tree: Path, package: str) -> str:
    for cand in ("src", "."):
        if (tree / cand / package / "__init__.py").is_file():
            return cand
    raise FileNotFoundError(f"{package}/__init__.py not found under {tree}")


class Workspace:
    __slots__ = ("library", "package", "tree", "repo", "commit", "tests_dir", "source_root", "config",
                 "_index", "_session", "_session_factory")

    FORBIDDEN = ("fail_to_pass", "gold_answer", "gold_evidence", "observed_before", "observed_after",
                 "fix_pr_url", "fix_pr_number", "fix_merge_commit", "fix_source_files", "fix_diff_stats")

    def __init__(self, library: str, package: str, tree: str | Path, *, repo: str | Path | None = None,
                 commit: str | None = None, tests_dir: str = "tests", config: dict[str, Any] | None = None,
                 session_factory: Callable[["Workspace"], Any] | None = None):
        self.library = library
        self.package = package
        self.tree = Path(tree).resolve()
        self.repo = Path(repo) if repo else None
        self.commit = commit
        self.tests_dir = tests_dir
        self.source_root = detect_source_root(self.tree, package)
        self.config = config or {}
        self._index = None
        self._session = None
        self._session_factory = session_factory

    @classmethod
    def for_question(cls, question: dict[str, Any], config: dict[str, Any],
                     session_factory: Callable[["Workspace"], Any] | None = None) -> "Workspace":
        """Reads only `library` and `frozen_commit` from the question record."""
        lib = question["library"]
        commit = question["frozen_commit"]
        spec = config["data"]["libraries"][lib]
        tree = REPO_ROOT / config["paths"]["trees_dir"] / lib / commit
        repo = REPO_ROOT / config["paths"]["repos_dir"] / f"{lib}.git"
        if not tree.is_dir():
            from data.freeze import export_tree
            export_tree(repo, commit, tree)
        return cls(lib, spec["package"], tree, repo=repo, commit=commit, tests_dir=spec["tests_dir"], config=config,
                   session_factory=session_factory)

    @property
    def index(self):
        if self._index is None:
            from retrieval.index import load_or_build
            cache = None
            if self.commit and self.config.get("paths"):
                cache = REPO_ROOT / self.config["paths"]["index_dir"] / self.library / f"{self.commit}.pkl"
            self._index = load_or_build(self.tree, self.package, self.source_root, cache)
        return self._index

    @property
    def session(self):
        """The sandbox session, started on first use and shared by every tool for this question."""
        if self._session is None:
            if self._session_factory is None:
                raise RuntimeError("this workspace has no sandbox")
            self._session = self._session_factory(self)
        return self._session

    def resolve(self, rel_path: str) -> Path:
        """A path inside the frozen tree. Raises ValueError if it escapes."""
        p = (self.tree / rel_path.lstrip("/")).resolve()
        if not p.is_relative_to(self.tree):
            raise ValueError(f"{rel_path!r} is outside the repository")
        return p

    def close(self) -> None:
        if self._session is not None:
            cleanup = getattr(self._session, "cleanup", None)
            if cleanup:
                cleanup()
            self._session = None


def docker_session_factory(workspace: Workspace) -> Any:
    """Start a locked-down Docker session for this workspace. All LLM-written code runs here."""
    from sandbox.session import SandboxSession
    session = SandboxSession(workspace.tree, workspace.package, dist_name=workspace.library, config=workspace.config)
    session.start()
    return session
