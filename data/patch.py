"""Step 3 of the data pipeline: split a fix's diff into its test and source parts.

Test part: files under the library's tests directory. Source part: files inside
the package. Everything else (changelog, docs) is ignored for gold evidence but
recorded, because editing `docs/` makes a question `doc_related`.

Validation applies the test part alone to the frozen tree (the new test should
fail), then the source part as well (the new test should pass).
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

_HEADER = re.compile(r"^diff --git a/(.+?) b/(.+)$", re.MULTILINE)
_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


@dataclass
class PatchParts:
    test: str = ""
    source: str = ""
    test_paths: list[str] = field(default_factory=list)
    source_paths: list[str] = field(default_factory=list)
    docs_paths: list[str] = field(default_factory=list)
    other_paths: list[str] = field(default_factory=list)


@dataclass
class Hunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    old_lines: list[str] = field(default_factory=list)
    new_lines: list[str] = field(default_factory=list)


def split_files(diff_text: str) -> list[tuple[str, str]]:
    """[(path, diff text of that file)] in diff order. A deleted file is listed under its old path."""
    starts = list(_HEADER.finditer(diff_text))
    out = []
    for i, m in enumerate(starts):
        end = starts[i + 1].start() if i + 1 < len(starts) else len(diff_text)
        out.append((m.group(2), diff_text[m.start():end]))
    return out


def split_patch(diff_text: str, package: str, tests_dir: str) -> PatchParts:
    parts = PatchParts()
    tests, source = [], []
    for path, text in split_files(diff_text):
        if path.startswith((f"src/{package}/", f"{package}/")):
            source.append(text)
            parts.source_paths.append(path)
        elif path.startswith(f"{tests_dir}/"):
            tests.append(text)
            parts.test_paths.append(path)
        elif path.startswith("docs/"):
            parts.docs_paths.append(path)
        else:
            parts.other_paths.append(path)
    parts.test = "".join(tests)
    parts.source = "".join(source)
    return parts


def parse_hunks(file_diff: str) -> list[Hunk]:
    """The hunks of one file's diff, with the removed and added line texts."""
    hunks: list[Hunk] = []
    current: Hunk | None = None
    for line in file_diff.splitlines():
        m = _HUNK.match(line)
        if m:
            current = Hunk(int(m.group(1)), int(m.group(2) or 1), int(m.group(3)), int(m.group(4) or 1))
            hunks.append(current)
        elif current is not None:
            if line.startswith("-"):
                current.old_lines.append(line[1:])
            elif line.startswith("+"):
                current.new_lines.append(line[1:])
    return hunks


def apply_patch(tree: str | Path, patch_text: str) -> None:
    """Apply a patch to a plain directory. Raises RuntimeError if it does not apply cleanly.

    GIT_CEILING_DIRECTORIES stops git from discovering an enclosing repository:
    inside one, `git apply` silently skips paths outside the current directory.
    """
    if not patch_text.strip():
        return
    tree = Path(tree)
    env = {**os.environ, "GIT_CEILING_DIRECTORIES": str(tree.parent)}
    p = subprocess.run(["git", "apply", "--whitespace=nowarn", "-"], cwd=tree, input=patch_text.encode("utf-8"),
                       capture_output=True, env=env, timeout=120)
    if p.returncode != 0:
        raise RuntimeError(f"patch did not apply: {p.stderr.decode('utf-8', 'replace')[-300:]}")
