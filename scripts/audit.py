"""One command that re-checks the project's hard rules, for the team's cross-check.

Each check prints PASS, FAIL or SKIP with a one-line reason. It reads the repo,
git and the dataset; it makes no API call. Exit code 1 if anything FAILs.

Checks:
- unit tests (and Docker tests with --docker); every file has an owner;
- no key-shaped strings in tracked files, `.env` not tracked;
- no AI attribution in any commit message (CLAUDE.md §2.6);
- dataset: questions valid, dev and test disjoint, every question in exactly one
  split, no question once in dev now in test (D-44), the test file's SHA-256
  matches PREREGISTRATION.md once it is LOCKED;
- the agent's workspace cannot see gold fields (it is tested, and the test must exist).

Usage: python scripts/audit.py [--docker] [--quick]   (--quick skips the test suites)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEY_RE = r"AIza[0-9A-Za-z_-]{20,}|gsk_[0-9A-Za-z]{20,}|ghp_[0-9A-Za-z]{20,}|github_pat_[0-9A-Za-z_]{20,}|sk-[0-9A-Za-z]{32,}"
ATTRIBUTION_RE = re.compile(r"co-authored-by|generated with|🤖", re.IGNORECASE)

results: list[tuple[str, str, str]] = []


def record(name: str, ok: bool | None, detail: str) -> None:
    results.append((name, "SKIP" if ok is None else "PASS" if ok else "FAIL", detail))


def run(cmd: list[str], timeout: int = 1800) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    return p.returncode, (p.stdout + p.stderr).strip()


def last_line(text: str) -> str:
    lines = [l for l in text.splitlines() if l.strip()]
    return lines[-1][:160] if lines else ""


def read_qids(path: Path) -> list[str]:
    return [json.loads(l)["qid"] for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def check_tests(docker: bool) -> None:
    code, out = run([sys.executable, "-m", "pytest", "-q"])
    record("unit tests", code == 0, last_line(out))
    if docker:
        code, out = run([sys.executable, "-m", "pytest", "-q", "-m", "docker"])
        record("docker tests", code == 0, last_line(out))
    else:
        record("docker tests", None, "run with --docker")


def check_ownership() -> None:
    code, out = run([sys.executable, "scripts/make_bundles.py", "--check"], timeout=120)
    record("every file has an owner", code == 0, last_line(out))


def check_secrets() -> None:
    code, out = run(["git", "grep", "-nIE", KEY_RE])
    hits = [l.split(":")[0] for l in out.splitlines()] if code == 0 else []
    record("no keys in tracked files", not hits, f"{len(hits)} hit(s) in {sorted(set(hits))}" if hits else "none found")
    _, tracked = run(["git", "ls-files"])
    env = [f for f in tracked.splitlines() if f == ".env" or f.endswith("/.env")]
    record(".env not tracked", not env, "tracked: " + ", ".join(env) if env else "not tracked")


def check_attribution() -> None:
    _, log = run(["git", "log", "--format=%H%x00%B%x01"])
    bad = []
    for entry in log.split("\x01"):
        if "\x00" in entry:
            sha, body = entry.split("\x00", 1)
            if ATTRIBUTION_RE.search(body):
                bad.append(sha.strip()[:8])
    record("no AI attribution in commits", not bad, f"commits: {bad}" if bad else "all commit messages clean")


def check_dataset() -> None:
    data = ROOT / "data"
    code, out = run([sys.executable, "data/validate_questions.py"], timeout=300)
    record("questions valid", code == 0 and "0 problems" in out, last_line(out))
    all_ids = read_qids(data / "questions_all.jsonl")
    dev, test = read_qids(data / "questions_dev.jsonl"), read_qids(data / "questions_test.jsonl")
    record("dev and test disjoint", not set(dev) & set(test), f"dev {len(dev)}, test {len(test)}")
    # After the G2 lock the split is never rebuilt: a question removed by the spot check (G1) leaves
    # questions_all.jsonl but stays in its split file, and the analysis excludes it. So the splits must equal the
    # remaining questions plus the logged spot-check removals.
    dropped = data / "dropped.jsonl"
    removed = {json.loads(l)["qid"] for l in dropped.read_text(encoding="utf-8").splitlines()
               if l.strip() and json.loads(l).get("stage") == "spot_check"} if dropped.exists() else set()
    record("split covers every question once", sorted(dev + test) == sorted(set(all_ids) | (removed & set(dev + test)))
           and len(dev + test) == len(set(dev + test)) and not set(all_ids) & removed,
           f"{len(all_ids)} questions + {len(removed & set(dev + test))} removed by the spot check = {len(dev) + len(test)} in splits")
    history = data / "dev_history.txt"
    ever = {l.strip() for l in history.read_text().splitlines() if l.strip()} if history.exists() else set()
    leaked = sorted(ever & set(test))
    record("no former dev question in test (D-44)", not leaked, f"leaked: {leaked}" if leaked else f"{len(ever)} in history")
    prereg = (ROOT / "PREREGISTRATION.md").read_text(encoding="utf-8")
    sha = hashlib.sha256((data / "questions_test.jsonl").read_bytes()).hexdigest()
    if "**Status: LOCKED" in prereg:
        record("test SHA-256 matches the lock", sha in prereg, f"test file {sha[:12]}…")
    else:
        record("test SHA-256 matches the lock", None, f"not locked yet (test file {sha[:12]}…)")


def check_isolation() -> None:
    """The unit tests run them; this only checks they still exist (deleting them would hide a leak)."""
    path = ROOT / "tests" / "tools" / "test_tools.py"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    ok = "def test_workspace_cannot_hold_gold" in text and "Tripwire" in text
    record("tests guard the workspace against gold fields", ok,
           "test_workspace_cannot_hold_gold and the question tripwire exist" if ok else "guard tests missing")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--docker", action="store_true", help="also run the Docker tests")
    ap.add_argument("--quick", action="store_true", help="skip the test suites")
    args = ap.parse_args(argv)
    if not args.quick:
        check_tests(args.docker)
    check_ownership()
    check_secrets()
    check_attribution()
    check_dataset()
    check_isolation()
    width = max(len(n) for n, _, _ in results)
    for name, status, detail in results:
        print(f"[{status}] {name.ljust(width)}  {detail}")
    failed = [n for n, s, _ in results if s == "FAIL"]
    print(f"\n{len(results) - len(failed)} of {len(results)} checks did not fail" + (f"; FAILED: {failed}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
