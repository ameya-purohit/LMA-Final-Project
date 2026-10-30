"""Step 2 of the data pipeline: freeze the library at the commit before the fix.

`frozen_commit` is the PR's base commit (SWE-bench's convention, D-28): the
first parent of the merge commit. For squash and rebase merges, it is the
parent of the first fix commit on the branch. No system can then see the fix.

The frozen tree is exported with `git archive | tar -x` into
`.cache/trees/<lib>/<commit>/`. `git log` and `git blame` run against the bare
clone at the frozen commit, so history can never reach past it.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from core.config import REPO_ROOT


def git(repo: str | Path, *args: str, check: bool = True, text: bool = True) -> str:
    p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=text, timeout=600)
    if check and p.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {p.stderr[-500:]}")
    return p.stdout


def bare_clone(url: str, dest: str | Path) -> Path:
    """Clone once, then only fetch (also keeps PR merge commits of side branches)."""
    dest = Path(dest)
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    subprocess.run(["git", "clone", "--bare", "--quiet", url, str(tmp)], check=True, timeout=3600)
    tmp.rename(dest)
    return dest


def repo_path(lib: str, config: dict) -> Path:
    return REPO_ROOT / config["paths"]["repos_dir"] / f"{lib}.git"


def commit_exists(repo: str | Path, sha: str) -> bool:
    return bool(sha) and subprocess.run(["git", "-C", str(repo), "cat-file", "-e", f"{sha}^{{commit}}"],
                                        capture_output=True).returncode == 0


def parents(repo: str | Path, sha: str) -> list[str]:
    return git(repo, "rev-list", "--parents", "-n", "1", sha).split()[1:]


def changed_paths(repo: str | Path, a: str, b: str) -> set[str]:
    return set(git(repo, "diff", "--name-only", "--no-renames", a, b).split("\n")) - {""}


def is_ancestor(repo: str | Path, a: str, b: str) -> bool:
    return subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", a, b],
                          capture_output=True).returncode == 0


def frozen_commit(repo: str | Path, merge_commit: str, pr_files: set[str], pr_commits: int | None) -> str | None:
    """The commit just before the fix landed, or None if it cannot be determined.

    Two parents: a true merge, so the first parent. One parent: a squash (the
    single commit holds all the PR's files) or a rebase (walk back over the PR's
    commits and take the parent of the first).
    """
    ps = parents(repo, merge_commit)
    if len(ps) >= 2:
        return ps[0]
    if len(ps) == 0:
        return None
    if pr_files <= changed_paths(repo, ps[0], merge_commit) or not pr_commits or pr_commits <= 1:
        return ps[0]
    current = merge_commit
    for _ in range(pr_commits):
        up = parents(repo, current)
        if len(up) != 1:
            return None
        current = up[0]
    return current if pr_files <= changed_paths(repo, current, merge_commit) else ps[0]


def tree_path(lib: str, commit: str, config: dict) -> Path:
    return REPO_ROOT / config["paths"]["trees_dir"] / lib / commit


def export_tree(repo: str | Path, commit: str, dest: str | Path) -> Path:
    """Materialize `commit` as plain files. Idempotent."""
    dest = Path(dest)
    if (dest / ".frozen").exists():
        return dest
    dest.mkdir(parents=True, exist_ok=True)
    archive = subprocess.Popen(["git", "-C", str(repo), "archive", commit], stdout=subprocess.PIPE)
    subprocess.run(["tar", "-x", "-C", str(dest)], stdin=archive.stdout, check=True, timeout=300)
    archive.stdout.close()
    if archive.wait(timeout=300) != 0:
        raise RuntimeError(f"git archive {commit} failed")
    (dest / ".frozen").write_text(commit + "\n")
    return dest
