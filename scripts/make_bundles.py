"""Build per-member zip bundles from `bundles/ownership.yaml` (CLAUDE.md §3).

Why bundles at all: the course checks that every member pushed code from
their own account. Code is built in one local folder, so we split it by owner
into zips; each member unzips theirs into a fresh clone, runs its tests and
opens a pull request. Nothing is pushed from the build folder itself.

Usage:
    python scripts/make_bundles.py --check
    python scripts/make_bundles.py --member sunil --name sunil_scaffold
    python scripts/make_bundles.py --member ameya --name ameya_update_1 --since <git-rev>
"""

from __future__ import annotations

import argparse
import fnmatch
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
OWNERSHIP = REPO_ROOT / "bundles" / "ownership.yaml"
REPO_URL = "https://github.com/ameya-purohit/LMA-Final-Project"


def load_ownership(path: Path = OWNERSHIP) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def owner_of(rel_path: str, ownership: dict[str, Any]) -> str | None:
    """First matching rule wins. `fnmatch`'s `*` also matches `/`, so `llm/**`
    covers every file below `llm/`."""
    for rule in ownership["rules"]:
        if fnmatch.fnmatchcase(rel_path, rule["pattern"]):
            return rule["owner"]
    return None


def repo_files(root: Path = REPO_ROOT) -> list[str]:
    """Tracked plus untracked-but-not-ignored files, so .env and caches never ship."""
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=root, check=True, capture_output=True, text=True,
    ).stdout
    return sorted(p for p in out.splitlines() if p and (root / p).is_file())


def changed_since(rev: str, root: Path = REPO_ROOT) -> tuple[set[str], set[str]]:
    """(changed_or_added, deleted) paths between `rev` and the working tree."""
    out = subprocess.run(
        ["git", "diff", "--name-status", "--no-renames", rev],
        cwd=root, check=True, capture_output=True, text=True,
    ).stdout
    changed, deleted = set(), set()
    for line in out.splitlines():
        status, path = line.split("\t", 1)
        (deleted if status.startswith("D") else changed).add(path)
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=root, check=True, capture_output=True, text=True,
    ).stdout.split()
    changed.update(untracked)
    return changed, deleted


def check_all_owned(files: list[str], ownership: dict[str, Any]) -> list[str]:
    """Return the files no rule covers (should be empty)."""
    return [f for f in files if owner_of(f, ownership) is None]


def test_dirs(files: list[str]) -> list[str]:
    """The `tests/<area>` directories present in a bundle, for its test command."""
    dirs = sorted({"/".join(f.split("/")[:2]) for f in files
                   if f.startswith("tests/") and f.count("/") >= 2 and not f.startswith("tests/fixtures/")})
    return dirs


def push_md(member: str, bundle: str, files: list[str], deleted: list[str],
            ownership: dict[str, Any]) -> str:
    """The step-by-step instructions shipped inside every zip."""
    info = ownership["members"][member]
    order = ownership["push_order"]
    # Branch is `<member>-<area>`; update rounds add a suffix so branches never collide.
    suffix = bundle.split("_", 1)[1] if "_" in bundle else ""
    branch = f"{member}-{info['area']}"
    if suffix not in ("", "scaffold", "mid"):
        branch += "-" + suffix.replace("_", "-")
    tdirs = test_dirs(files)
    test_cmd = f'python -m pytest -m "not docker and not live" {" ".join(tdirs)}' if tdirs else "# (this bundle has no tests)"
    earlier = order[: order.index(member)]
    wait_line = (
        "Before you start, make sure the pull requests of "
        + ", ".join(ownership["members"][m]["name"] for m in earlier)
        + " for this round are merged into `main` (bundles must land in the order Sunil, Ameya, Aditya, Sourav)."
        if earlier else "You go first in each round: the other members' bundles build on yours."
    )
    rm_block = ""
    if deleted:
        rm_block = "\nThis update also deletes files. After unzipping, run:\n\n```bash\ngit rm " + " ".join(deleted) + "\n```\n"
    listing = "\n".join(f"- `{f}`" for f in files)
    return f"""# PUSH.md: {bundle}.zip ({info['name']}, GitHub `{info['github']}`)

{wait_line}

Read your explainers in `docs/explainers/` first: in the viva you must be able
to explain every file in this bundle.

## Steps

1. **Accept the collaborator invite** (it arrives by email, or open
   {REPO_URL}/invitations while logged in as `{info['github']}`).

2. **Clone the repo** (or `git pull` on `main` if you already have it):

   ```bash
   git clone {REPO_URL}.git
   cd LMA-Final-Project
   git checkout main && git pull
   ```

3. **Set your own identity** so the commit is credited to you. Use the email
   on your GitHub account (GitHub -> Settings -> Emails), or the
   `...@users.noreply.github.com` address shown on that page:

   ```bash
   git config user.name "{info['name']}"
   git config user.email "<your GitHub email or no-reply address>"
   ```

4. **Create your branch:**

   ```bash
   git checkout -b {branch}
   ```

5. **Unzip the bundle at the repo root** (skip this PUSH.md so it is not committed):

   ```bash
   unzip -o /path/to/{bundle}.zip -x PUSH.md
   ```
{rm_block}
6. **Run this bundle's tests** (Python 3.10 or newer):

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate        # Windows (PowerShell): .venv\\Scripts\\Activate.ps1
   pip install -r requirements.txt
   {test_cmd}
   ```

   All tests must pass before you commit. If one fails, tell Ameya; do not edit the code to make it pass.
   `.venv/` is git-ignored, so it is never committed; the README explains the full setup.

7. **Commit** (plain message, no co-author lines):

   ```bash
   git add -A
   git status                       # only the files listed below should appear
   git commit -m "{bundle.replace('_', ' ')}: {info['area']} code from {info['name']}"
   ```

8. **Push and open a pull request into `main`:**

   ```bash
   git push -u origin {branch}
   ```

   Then open {REPO_URL}/pull/new/{branch}, and ask Ameya to merge it.

## Files in this bundle ({len(files)})

{listing}
"""


def build(member: str, name: str, since: str | None = None, out_dir: Path | None = None,
          root: Path = REPO_ROOT) -> Path:
    ownership = load_ownership(root / "bundles" / "ownership.yaml")
    if member not in ownership["members"]:
        raise SystemExit(f"unknown member {member!r}")
    files = repo_files(root)
    unowned = check_all_owned(files, ownership)
    if unowned:
        raise SystemExit("files with no owner in bundles/ownership.yaml:\n  " + "\n  ".join(unowned))
    deleted: list[str] = []
    if since:
        changed, gone = changed_since(since, root)
        files = [f for f in files if f in changed]
        deleted = sorted(f for f in gone if owner_of(f, ownership) == member)
    mine = [f for f in files if owner_of(f, ownership) == member]
    if not mine and not deleted:
        raise SystemExit(f"{name}: no files for {member}")
    out_dir = out_dir or root / "bundles"
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_dir / f"{name}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for f in mine:
            zf.write(root / f, f)
        zf.writestr("PUSH.md", push_md(member, name, mine, deleted, ownership))
    return zip_path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--member")
    ap.add_argument("--name", help="bundle name, e.g. sunil_scaffold")
    ap.add_argument("--since", help="git rev; include only files changed since it")
    ap.add_argument("--check", action="store_true", help="only check that every file has an owner")
    args = ap.parse_args(argv)
    ownership = load_ownership()
    if args.check:
        unowned = check_all_owned(repo_files(), ownership)
        for f in unowned:
            print(f"UNOWNED {f}")
        print("ownership OK" if not unowned else f"{len(unowned)} unowned file(s)")
        return 1 if unowned else 0
    if not (args.member and args.name):
        ap.error("--member and --name are required unless --check")
    path = build(args.member, args.name, args.since)
    with zipfile.ZipFile(path) as zf:
        n = len(zf.namelist()) - 1
    print(f"wrote {path.relative_to(REPO_ROOT)} ({n} files + PUSH.md)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
