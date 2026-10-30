"""Check the import rule: every prefix of the push order passes its own tests.

Bundles are merged in the order Sunil, Ameya, Aditya, Sourav (CLAUDE.md §3).
For each prefix (Sunil; Sunil+Ameya; ...) this copies only those members'
files into a temporary git checkout and runs the unit tests there. A failure
means some bundle imports, at module level, code from a bundle pushed later.

Usage: python scripts/check_bundle_order.py [--docker]
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.make_bundles import REPO_ROOT, load_ownership, owner_of, repo_files  # noqa: E402


def check_prefix(members: list[str], files: list[str], ownership: dict, marker: str) -> tuple[bool, str]:
    with tempfile.TemporaryDirectory(prefix="rtci-order-") as tmp:
        root = Path(tmp)
        for f in files:
            if owner_of(f, ownership) in members:
                dest = root / f
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(REPO_ROOT / f, dest)
        # A git checkout, like a member's clone (some tests list files with git).
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(["git", "add", "-A"], cwd=root, check=True)
        p = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-m", marker],
                           cwd=root, capture_output=True, text=True, timeout=1800)
        tail = (p.stdout + p.stderr).strip().splitlines()[-1:] or [""]
        # Exit code 5 = no tests matched this marker in this prefix (e.g. no Docker tests yet): fine.
        return p.returncode in (0, 5), tail[0]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--docker", action="store_true", help="also run the Docker tests for each prefix")
    args = ap.parse_args(argv)
    ownership = load_ownership()
    order = ownership["push_order"]
    files = repo_files()
    markers = ["not docker and not live"] + (["docker"] if args.docker else [])
    ok_all = True
    for k in range(1, len(order) + 1):
        prefix = order[:k]
        for marker in markers:
            ok, summary = check_prefix(prefix, files, ownership, marker)
            ok_all &= ok
            print(f"[{'OK ' if ok else 'FAIL'}] {' + '.join(prefix):32s} -m {marker!r}: {summary}")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
