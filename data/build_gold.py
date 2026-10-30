"""Step 5 of the data pipeline: build gold deterministically. No LLM touches any field.

- `gold_evidence`: the line ranges in the FROZEN version of each changed source
  file that the fix modified or deleted. A hunk that only adds lines points at
  the nearest existing line above it (`anchor_for_insert`). Hunks that only change
  whitespace or comments are ignored.
- `gold_answer`: a template filled from the test output and the diff.
- `category`: computed from the issue text and the diff.

Also writes `data/questions_all.jsonl`, `data/dropped.jsonl` and `data/mining_report.md`.

Usage: python data/build_gold.py
"""

from __future__ import annotations

import ast
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import REPO_ROOT, load_config  # noqa: E402
from core.jsonl import read_jsonl, write_jsonl  # noqa: E402
from data import freeze  # noqa: E402
from data.patch import Hunk, parse_hunks, split_files, split_patch  # noqa: E402
from data.schema import Question  # noqa: E402

DOCS_RE = re.compile(r"\b(docs?|documentation|docstrings?)\b", re.IGNORECASE)
MENTION_RE = re.compile(r"(?<![\w/.-])@[A-Za-z0-9][A-Za-z0-9-]*")
MAX_QUESTION_CHARS = 6000


def _is_code(line: str) -> bool:
    s = line.strip()
    return bool(s) and not s.startswith("#")


def evidence_from_hunks(path: str, hunks: list[Hunk]) -> list[dict[str, Any]]:
    """Frozen-side line ranges a fix touched. Consecutive lines are merged into one range."""
    items: list[tuple[int, str]] = []
    for h in hunks:
        old = [ln.strip() for ln in h.old_lines if _is_code(ln)]
        new = [ln.strip() for ln in h.new_lines if _is_code(ln)]
        if old == new:
            continue  # whitespace or comments only
        code_lines = [h.old_start + i for i, ln in enumerate(h.old_lines) if _is_code(ln)]
        if code_lines:
            kind = "changed" if h.new_lines else "deleted"
            items += [(ln, kind) for ln in code_lines]
        else:
            # Only added lines (or a comment replaced by code). With -U0 the old start is the line above.
            items.append((max(h.old_start, 1), "anchor_for_insert"))
    out: list[dict[str, Any]] = []
    for line, kind in sorted(set(items)):
        if out and out[-1]["kind"] == kind and line == out[-1]["line_end"] + 1:
            out[-1]["line_end"] = line
        else:
            out.append({"path": path, "line_start": line, "line_end": line, "kind": kind})
    return out


def docstrings(source: str) -> list[str | None]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    nodes = [tree] + [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
    return [ast.get_docstring(n) for n in nodes]


def category(issue_text: str, docs_paths: list[str], docstring_changed: bool, n_source_files: int) -> str:
    if DOCS_RE.search(issue_text) or docs_paths or docstring_changed:
        return "doc_related"
    return "spread_across_files" if n_source_files > 1 else "single_location"


def clean_question(title: str, body: str) -> str:
    """Issue title plus opening post only, never comments (they often hold the answer).

    HTML comments of issue templates are removed; @usernames are replaced
    (proposal §12: usernames are removed from the released dataset).
    """
    body = re.sub(r"<!--.*?-->", "", body or "", flags=re.DOTALL).strip()
    text = f"{title.strip()}\n\n{body}".strip()
    text = MENTION_RE.sub("@user", text)
    return text[:MAX_QUESTION_CHARS] + (" [truncated]" if len(text) > MAX_QUESTION_CHARS else "")


def format_ranges(evidence: list[dict[str, Any]]) -> str:
    return "; ".join(f"`{e['path']}` lines {e['line_start']}-{e['line_end']}" for e in evidence)


def gold_answer(fail: dict[str, Any], evidence: list[dict[str, Any]], pr_number: int) -> str:
    message = " ".join((fail.get("message") or "").split())
    return (f"On the frozen version, `{fail['test']}` fails: {message}. The behaviour is decided in "
            f"{format_ranges(evidence)}, which the merged fix (PR #{pr_number}) changed.")


def build_question(v: dict[str, Any], config: dict[str, Any]) -> dict[str, Any] | str:
    """A validated pair -> a Question dict, or the reason it has no gold."""
    repo = freeze.repo_path(v["library"], config)
    commit, merge = v["frozen_commit"], v["merge_commit"]
    diff_u0 = freeze.git(repo, "diff", "-U0", "--no-renames", commit, merge)
    parts = split_patch(diff_u0, v["package"], v["tests_dir"])
    evidence: list[dict[str, Any]] = []
    source_py: list[str] = []
    added = removed = 0
    doc_changed = False
    for path, text in split_files(parts.source):
        hunks = parse_hunks(text)
        added += sum(len(h.new_lines) for h in hunks)
        removed += sum(len(h.old_lines) for h in hunks)
        if not path.endswith(".py"):
            continue
        ev = evidence_from_hunks(path, hunks)
        if ev:
            source_py.append(path)
            evidence += ev
        old = freeze.git(repo, "show", f"{commit}:{path}", check=False)
        new = freeze.git(repo, "show", f"{merge}:{path}", check=False)
        doc_changed |= docstrings(old) != docstrings(new)
    if not evidence:
        return "no_gold_evidence_only_comments_or_whitespace"
    text = clean_question(v["issue_title"], v["issue_body"])
    if re.search(rf"(pull/|#){v['pr_number']}\b", text):
        return "question_text_names_the_fix_pr"
    q = Question(
        qid=f"{v['library']}-{v['issue_number']}", library=v["library"], issue_url=v["issue_url"],
        issue_number=v["issue_number"], created_at=v["created_at"], question_text=text, fix_pr_url=v["pr_url"],
        fix_pr_number=v["pr_number"], fix_merge_commit=merge, frozen_commit=commit, fail_to_pass=v["fail_to_pass"],
        observed_before=v["observed_before"], observed_after=v["observed_after"], gold_evidence=evidence,
        fix_source_files=source_py, fix_diff_stats={"files": len(parts.source_paths), "lines_added": added,
                                                    "lines_removed": removed},
        gold_answer=gold_answer(v["observed_before"][0], evidence, v["pr_number"]),
        category=category(f"{v['issue_title']}\n{v['issue_body']}", v.get("docs_paths", []), doc_changed,
                          len(source_py)))
    return q.model_dump()


FUNNEL = [("closed_prs", "closed PRs listed"), ("merged_prs_all_time", "merged, any date"),
          ("merged_prs", "merged since cutoff"), ("linked_issue", "linked to an issue"),
          ("issue_not_bot", "issue not by a bot"), ("source_and_test", "changes source AND tests"),
          ("candidates", "at most N source files (candidates)")]


def write_report(path: Path, counts: dict, validation: list[dict], questions: list[dict], dropped: list[dict],
                 cfg: dict) -> None:
    libs = list(counts)
    lines = ["# Mining report", "",
             "Generated by `data/build_gold.py` from real GitHub and sandbox runs. Every dropped item, with its "
             "reason, is in `data/dropped.jsonl`.", "",
             f"Cutoff: merged on or after {cfg['data']['merged_since']}; at most {cfg['data']['max_source_files']} "
             "source files per PR.", "", "## Funnel", "",
             "| Step | " + " | ".join(libs) + " | total |", "|---|" + "---|" * (len(libs) + 1)]
    for key, label in FUNNEL:
        vals = [counts[lib].get(key, 0) for lib in libs]
        lines.append(f"| {label} | " + " | ".join(map(str, vals)) + f" | {sum(vals)} |")
    per = lambda rows: Counter(r["library"] for r in rows)  # noqa: E731
    for label, rows in (("validated: test fails before, passes after", [r for r in validation if r.get("valid")]),
                        ("gold built, unique issue (questions)", questions)):
        c = per(rows)
        lines.append(f"| {label} | " + " | ".join(str(c.get(lib, 0)) for lib in libs) + f" | {sum(c.values())} |")
    lines += ["", "## Drop reasons", "", "| Stage | Reason | " + " | ".join(libs) + " | total |",
              "|---|---|" + "---|" * (len(libs) + 1)]
    keyed = Counter((d.get("stage", "?"), d["reason"], d["library"]) for d in dropped)
    for stage, reason in sorted({k[:2] for k in keyed}):
        vals = [keyed.get((stage, reason, lib), 0) for lib in libs]
        lines.append(f"| {stage} | {reason} | " + " | ".join(map(str, vals)) + f" | {sum(vals)} |")
    lines += ["", "## Questions by library and category", "", "| Library | doc_related | spread_across_files | "
              "single_location | total |", "|---|---|---|---|---|"]
    for lib in libs:
        rows = [q for q in questions if q["library"] == lib]
        c = Counter(q["category"] for q in rows)
        lines.append(f"| {lib} | {c.get('doc_related', 0)} | {c.get('spread_across_files', 0)} | "
                     f"{c.get('single_location', 0)} | {len(rows)} |")
    c = Counter(q["category"] for q in questions)
    lines.append(f"| total | {c.get('doc_related', 0)} | {c.get('spread_across_files', 0)} | "
                 f"{c.get('single_location', 0)} | {len(questions)} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    cfg = load_config()
    cache = REPO_ROOT / cfg["paths"]["cache_dir"]
    mined = json.loads((cache / "candidates.json").read_text(encoding="utf-8"))
    validation = read_jsonl(cache / "validation.jsonl")
    dropped = list(mined["dropped"]) + [{k: r.get(k) for k in ("library", "pr", "issue", "stage", "reason", "detail")}
                                        for r in validation if not r.get("valid")]
    questions: list[dict[str, Any]] = []
    seen: set[str] = set()
    # Oldest merged fix first: if several PRs fixed one issue, the first fix is the one that answers it.
    for v in sorted((r for r in validation if r.get("valid")), key=lambda r: r["merged_at"]):
        qid = f"{v['library']}-{v['issue_number']}"
        result = build_question(v, cfg)
        if isinstance(result, str):
            dropped.append({"library": v["library"], "pr": v["pr"], "issue": v["issue"], "stage": "gold", "reason": result})
        elif qid in seen:
            dropped.append({"library": v["library"], "pr": v["pr"], "issue": v["issue"], "stage": "gold",
                            "reason": "duplicate_issue_later_fix"})
        else:
            seen.add(qid)
            questions.append(result)
    questions.sort(key=lambda q: q["qid"])
    data_dir = REPO_ROOT / "data"
    write_jsonl(data_dir / "questions_all.jsonl", questions)
    write_jsonl(data_dir / "dropped.jsonl", dropped)
    write_report(data_dir / "mining_report.md", mined["counts"], validation, questions, dropped, cfg)
    print(f"{len(questions)} questions, {len(dropped)} dropped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
