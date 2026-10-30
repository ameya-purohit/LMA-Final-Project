"""Check a question file: schema, unique ids, no leakage in the question text,
and (when the frozen tree is available) gold lines that really exist.

Usage: python data/validate_questions.py [path ...]
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import REPO_ROOT, load_config  # noqa: E402
from core.jsonl import read_jsonl  # noqa: E402
from data import freeze  # noqa: E402
from data.schema import Question  # noqa: E402


def check_questions(rows: list[dict[str, Any]], config: dict[str, Any] | None = None) -> list[str]:
    """Return a list of problems (empty = valid)."""
    problems: list[str] = []
    seen: set[str] = set()
    for row in rows:
        try:
            q = Question.model_validate(row)
        except Exception as exc:
            problems.append(f"{row.get('qid')}: schema: {str(exc)[:200]}")
            continue
        if q.qid in seen:
            problems.append(f"{q.qid}: duplicate qid")
        seen.add(q.qid)
        if not q.fail_to_pass or not q.gold_evidence:
            problems.append(f"{q.qid}: empty fail_to_pass or gold_evidence")
        if f"pull/{q.fix_pr_number}" in q.question_text or q.fix_merge_commit in q.question_text:
            problems.append(f"{q.qid}: question text names the fix")
        if q.frozen_commit == q.fix_merge_commit:
            problems.append(f"{q.qid}: frozen commit equals the merge commit")
        if config is not None:
            tree = freeze.tree_path(q.library, q.frozen_commit, config)
            for ev in q.gold_evidence:
                f = tree / ev.path
                if tree.exists() and f.exists():
                    n = len(f.read_text(encoding="utf-8", errors="replace").splitlines())
                    if not (1 <= ev.line_start <= ev.line_end <= max(n, 1)):
                        problems.append(f"{q.qid}: gold range {ev.path}:{ev.line_start}-{ev.line_end} outside file ({n} lines)")
    return problems


def main(argv: list[str] | None = None) -> int:
    paths = (argv if argv is not None else sys.argv[1:]) or [str(REPO_ROOT / "data" / "questions_all.jsonl")]
    cfg = load_config()
    failed = 0
    for path in paths:
        rows = read_jsonl(path)
        problems = check_questions(rows, cfg)
        print(f"{path}: {len(rows)} questions, {len(problems)} problems")
        for p in problems[:20]:
            print("  " + p)
        failed += bool(problems)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
