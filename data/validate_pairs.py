"""Step 4 of the data pipeline: validate each issue-fix pair by running its tests.

Inside the sandbox:
  1. frozen tree + test part only: the tests the PR added or changed run; at
     least one must fail. Those are `fail_to_pass`; their failure messages are
     `observed_before`, the actual old behaviour.
  2. frozen tree + test part + source part: every `fail_to_pass` test must pass.

A pair that cannot be validated (a missing test dependency, a timeout, a
condition not met) is dropped with a reason; nothing is ever edited by hand or
by a model. Results are appended as they finish, so an interrupted run resumes.

Usage: python data/validate_pairs.py [--workers 6] [--limit N]
"""

from __future__ import annotations

import argparse
import ast
import json
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import REPO_ROOT, load_config  # noqa: E402
from core.jsonl import append_jsonl, read_jsonl  # noqa: E402
from data import freeze  # noqa: E402
from data.patch import apply_patch, parse_hunks, split_files, split_patch  # noqa: E402
from sandbox.session import SandboxError, SandboxSession  # noqa: E402

FAIL_STATES = ("failed", "error")


def find_test_ranges(source: str) -> list[tuple[str, int, int]]:
    """(qualified test name, first line, last line) for every test function, decorators included."""
    tree = ast.parse(source)
    out: list[tuple[str, int, int]] = []

    def visit(node: ast.AST, prefix: str) -> None:
        for child in getattr(node, "body", []):
            if isinstance(child, ast.ClassDef):
                visit(child, f"{prefix}{child.name}::")
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name.startswith("test"):
                first = min([d.lineno for d in child.decorator_list] + [child.lineno])
                out.append((f"{prefix}{child.name}", first, child.end_lineno))

    visit(tree, "")
    return out


def changed_test_names(file_diff: str, new_source: str) -> set[str] | None:
    """Tests a file's diff touches (by new-side line numbers).

    Returns None if the diff touches only code outside tests (a fixture or a
    helper): every test in the file is then treated as changed.
    """
    ranges = find_test_ranges(new_source)
    touched: set[str] = set()
    for hunk in parse_hunks(file_diff):
        lines = range(hunk.new_start, hunk.new_start + max(hunk.new_count, 1))
        for name, first, last in ranges:
            if any(first <= ln <= last for ln in lines):
                touched.add(name)
    return touched or None


def node_name(node_id: str) -> tuple[str, str]:
    """('tests/test_x.py', 'Class::test_y') from 'tests/test_x.py::Class::test_y[param]'."""
    path, _, rest = node_id.partition("::")
    return path, rest.split("[", 1)[0]


def select_changed(tests: dict[str, dict[str, str]], changed: dict[str, set[str] | None]) -> dict[str, dict[str, str]]:
    out = {}
    for node, entry in tests.items():
        path, name = node_name(node)
        if path in changed and name and (changed[path] is None or name in changed[path]):
            out[node] = entry
    return out


def decide(before: dict[str, dict[str, str]], after: dict[str, dict[str, str]],
           changed: dict[str, set[str] | None]) -> dict[str, Any]:
    """Pure rule: given per-node results of both runs, is the pair valid?

    Returns {"valid": True, "fail_to_pass", "observed_before", "observed_after"} or
    {"valid": False, "reason", ...}. A collection error before the fix (the new test
    imports something the frozen code lacks) counts as a failure of the file's changed tests.
    """
    for path in changed:
        if path in after and after[path]["status"] == "error":
            return {"valid": False, "reason": "test_error_with_fix_applied",
                    "detail": after[path]["message"][-300:]}
    changed_after = select_changed(after, changed)
    changed_before = select_changed(before, changed)
    failing: dict[str, str] = {n: e["message"] for n, e in changed_before.items() if e["status"] in FAIL_STATES}
    for path in changed:
        if path in before and before[path]["status"] == "error":
            for node in changed_after:
                if node_name(node)[0] == path:
                    failing.setdefault(node, before[path]["message"])
    if not changed_after and not changed_before:
        return {"valid": False, "reason": "no_changed_tests_collected"}
    if not failing:
        return {"valid": False, "reason": "no_test_fails_before_fix"}
    not_passing = [n for n in failing if changed_after.get(n, {}).get("status") != "passed"]
    if not_passing:
        return {"valid": False, "reason": "fail_to_pass_test_not_passing_after_fix",
                "detail": ", ".join(not_passing)[:300]}
    names = sorted(failing)
    return {"valid": True, "fail_to_pass": names,
            "observed_before": [{"test": n, "status": before.get(n, {"status": "error"})["status"],
                                 "message": failing[n]} for n in names],
            "observed_after": [{"test": n, "status": after[n]["status"]} for n in names]}


def validate_one(pair: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """Validate one candidate; never raises. Returns the pair plus a verdict."""
    lib, pr = pair["library"], pair["pr_number"]
    base = {"library": lib, "pr": pr, "issue": pair["issue_number"]}
    repo = freeze.repo_path(lib, config)

    def bad(reason: str, **extra: Any) -> dict[str, Any]:
        return {**base, "valid": False, "stage": "validation", "reason": reason, **extra}

    merge = pair["merge_commit"]
    if not freeze.commit_exists(repo, merge):
        return bad("merge_commit_not_in_clone")
    pr_files = set(pair["source_files"]) | set(pair["test_files"])
    commit = freeze.frozen_commit(repo, merge, pr_files, pair.get("pr_commits"))
    if commit is None:
        return bad("cannot_determine_frozen_commit")
    if not freeze.is_ancestor(repo, commit, merge):
        return bad("frozen_commit_not_ancestor")
    diff = freeze.git(repo, "diff", "--binary", "--no-renames", commit, merge)
    parts = split_patch(diff, pair["package"], pair["tests_dir"])
    if not parts.test or not parts.source:
        return bad("diff_has_no_source_or_test_part")
    tree = freeze.export_tree(repo, commit, freeze.tree_path(lib, commit, config))
    try:
        session = SandboxSession(tree, pair["package"], dist_name=pair["library"], config=config)
    except SandboxError as exc:
        return bad("package_not_found_in_frozen_tree", detail=str(exc)[:200])
    try:
        session.start()
        before_dir = session.scratch / "before"
        shutil.copytree(tree, before_dir)
        try:
            apply_patch(before_dir, parts.test)
        except RuntimeError as exc:
            return bad("test_patch_did_not_apply", detail=str(exc)[:200])
        changed: dict[str, set[str] | None] = {}
        files_to_run = []
        for path, text in split_files(parts.test):
            new_file = before_dir / path
            if path.endswith(".py") and new_file.is_file() and Path(path).name.startswith("test"):
                try:
                    changed[path] = changed_test_names(text, new_file.read_text(encoding="utf-8"))
                except SyntaxError:
                    return bad("test_file_syntax_error_on_py310", detail=path)
                files_to_run.append(path)
        if not files_to_run:
            return bad("no_runnable_test_file_changed")
        after_dir = session.scratch / "after"
        shutil.copytree(before_dir, after_dir)
        try:
            apply_patch(after_dir, parts.source)
        except RuntimeError as exc:
            return bad("source_patch_did_not_apply", detail=str(exc)[:200])
        for d in (before_dir, after_dir):
            for p in [d, *d.rglob("*")]:
                if not p.is_symlink():
                    p.chmod(0o755 if p.is_dir() else 0o644)
        out_before = session.run_pytest(files_to_run, lib_root=session.to_inner(before_dir))
        out_after = session.run_pytest(files_to_run, lib_root=session.to_inner(after_dir))
        for out in (out_before, out_after):
            if out.get("kind") != "pytest":
                reason = "timeout" if out.get("type") == "JobTimeout" else "sandbox_runner_error"
                return bad(reason, detail=str(out.get("msg"))[:200])
        verdict = decide(out_before["tests"], out_after["tests"], changed)
        if not verdict["valid"]:
            return {**base, "stage": "validation", **verdict}
        return {**pair, **base, "stage": "validation", **verdict, "frozen_commit": commit,
                "docs_paths": parts.docs_paths}
    except Exception as exc:  # a drop with a reason, never a crash of the whole batch
        return bad("sandbox_failure", detail=f"{type(exc).__name__}: {exc}"[:300])
    finally:
        session.cleanup()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--limit", type=int)
    args = ap.parse_args(argv)
    cfg = load_config()
    cache = REPO_ROOT / cfg["paths"]["cache_dir"]
    pairs = json.loads((cache / "candidates.json").read_text(encoding="utf-8"))["pairs"]
    out_path = cache / "validation.jsonl"
    done = {(r["library"], r["pr"]) for r in read_jsonl(out_path)} if out_path.exists() else set()
    todo = [p for p in pairs if (p["library"], p["pr_number"]) not in done][: args.limit]
    print(f"{len(pairs)} candidates, {len(done)} done, {len(todo)} to validate", flush=True)

    def work(pair: dict[str, Any]) -> None:
        result = validate_one(pair, cfg)
        append_jsonl(out_path, result)
        print(f"{pair['library']}#{pair['pr_number']}: {'VALID' if result.get('valid') else result.get('reason')}",
              flush=True)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(work, todo))
    return 0


if __name__ == "__main__":
    sys.exit(main())
