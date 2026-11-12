"""Gate G1, step 3: apply the members' spot-check verdicts to the dataset.

Reads `annotation/spotcheck_<member>_done.jsonl` (exported by spotcheck.html),
checks them against `annotation/sample_manifest.json`, and then:

- removes every question a member marked invalid (any of the three answers "no")
  from `data/questions_all.jsonl`, logging each removal in `data/dropped.jsonl`
  (stage `spot_check`) with the member's notes;
- records `spot_check: {checked_by, valid, reason}` on the questions that passed;
- writes the disagreement rate (how often the humans disagreed with the automatic
  gold) into a "Spot check" section of `data/mining_report.md`.

Why idempotent: `data/build_gold.py` rebuilds the dataset files from scratch.
The verdict files are the record, so re-running this script after any rebuild
gives the same result, and running it twice changes nothing.

After the G2 lock (2026-11-07) the split is NOT rebuilt: `data/questions_{dev,test}.jsonl` and the test file's
SHA-256 stay as locked. The removals logged here (stage `spot_check`) are excluded from every system's results by
`analysis/make_all.py` (PREREGISTRATION.md, locked values and Deviations).

Usage: python annotation/apply_spotcheck.py [--allow-missing]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import REPO_ROOT  # noqa: E402
from core.jsonl import read_jsonl, write_jsonl  # noqa: E402

CRITERIA = ("genuine_question", "test_captures_behaviour", "gold_lines_decide")
SECTION = "## Spot check (gate G1)"


class Verdict(BaseModel):
    """One member's verdict on one question, as the page exports it."""
    model_config = ConfigDict(extra="ignore")
    qid: str
    member: str
    genuine_question: bool
    test_captures_behaviour: bool
    gold_lines_decide: bool
    genuine_question_note: str = ""
    test_captures_behaviour_note: str = ""
    gold_lines_decide_note: str = ""
    valid: bool
    checked_at: str = ""

    @model_validator(mode="after")
    def _valid_means_all_yes(self) -> "Verdict":
        if self.valid != all(getattr(self, c) for c in CRITERIA):
            raise ValueError("`valid` must be true exactly when all three answers are yes")
        return self

    def failed(self) -> list[str]:
        return [c for c in CRITERIA if not getattr(self, c)]

    def reason(self) -> str:
        parts = []
        for c in self.failed():
            note = getattr(self, f"{c}_note").strip()
            parts.append(f"{c}: no" + (f" ({note})" if note else ""))
        return "; ".join(parts)


def load_verdicts(directory: Path, manifest: dict[str, Any], allow_missing: bool) -> tuple[list[Verdict], list[str]]:
    """All verdicts, checked against the manifest. Returns (verdicts, problems); problems block the apply."""
    owner = {qid: m for m, qids in manifest["assignment"].items() for qid in qids}
    verdicts: list[Verdict] = []
    problems: list[str] = []
    seen: set[str] = set()
    for path in sorted(directory.glob("spotcheck_*_done.jsonl")):
        for i, row in enumerate(read_jsonl(path), 1):
            try:
                v = Verdict.model_validate(row)
            except ValidationError as exc:
                problems.append(f"{path.name} line {i}: {exc.errors()[0]['msg']}")
                continue
            if v.qid not in owner:
                problems.append(f"{path.name}: {v.qid} is not in the sample")
            elif owner[v.qid] != v.member:
                problems.append(f"{path.name}: {v.qid} was assigned to {owner[v.qid]}, not {v.member}")
            elif v.qid in seen:
                problems.append(f"{path.name}: {v.qid} has more than one verdict")
            else:
                seen.add(v.qid)
                verdicts.append(v)
    missing = sorted(set(owner) - seen)
    if missing and not allow_missing:
        problems.append(f"{len(missing)} sampled questions have no verdict yet: " + ", ".join(missing))
    return verdicts, problems


def apply(questions: list[dict[str, Any]], dropped: list[dict[str, Any]],
          verdicts: list[Verdict]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Pure: the new question list and drop log. Running it on its own output changes nothing."""
    by_qid = {v.qid: v for v in verdicts}
    logged = {d.get("qid") for d in dropped if d.get("stage") == "spot_check"}
    kept: list[dict[str, Any]] = []
    new_dropped = list(dropped)
    for q in questions:
        v = by_qid.get(q["qid"])
        if v is None:
            kept.append(q)
        elif v.valid:
            kept.append({**q, "spot_check": {"checked_by": v.member, "valid": True, "reason": None}})
        elif q["qid"] not in logged:
            new_dropped.append({"library": q["library"], "pr": q["fix_pr_number"], "issue": q["issue_number"],
                                "qid": q["qid"], "stage": "spot_check", "reason": "spot_check_invalid",
                                "detail": v.reason(), "checked_by": v.member})
            logged.add(q["qid"])
    return kept, new_dropped


def disagreement(verdicts: list[Verdict]) -> dict[str, Any]:
    """How often the humans disagreed with the automatic gold.

    Per question: the share of the three checks answered "no". Overall: the share
    of checked questions with at least one "no" (these are removed), and the rate
    of "no" for each check.
    """
    n = len(verdicts)
    per_question = {v.qid: round(len(v.failed()) / len(CRITERIA), 3) for v in verdicts}
    return {"checked": n, "invalid": sum(not v.valid for v in verdicts),
            "overall_rate": round(sum(not v.valid for v in verdicts) / n, 3) if n else None,
            "per_criterion": {c: round(sum(not getattr(v, c) for v in verdicts) / n, 3) if n else None for c in CRITERIA},
            "per_question": per_question}


def report_section(stats: dict[str, Any], verdicts: list[Verdict]) -> str:
    lines = [SECTION, "",
             "Written by `annotation/apply_spotcheck.py` from the members' verdicts. One member checked each sampled "
             "question; disagreement means the member answered no to a check of the automatic gold.", ""]
    if not stats["checked"]:
        return "\n".join(lines + ["No verdicts yet.", ""])
    lines += [f"- Checked: {stats['checked']}; marked invalid and removed: {stats['invalid']} "
              f"(overall disagreement rate {stats['overall_rate']:.1%}).", "",
              "| Check | Rate of no |", "|---|---|"]
    lines += [f"| {c} | {stats['per_criterion'][c]:.1%} |" for c in CRITERIA]
    bad = [v for v in verdicts if not v.valid]
    if bad:
        lines += ["", "| Question | Checked by | Share of checks failed | Reason |", "|---|---|---|---|"]
        for v in sorted(bad, key=lambda v: v.qid):
            reason = v.reason().replace("|", "\\|").replace("\n", " ")
            lines.append(f"| {v.qid} | {v.member} | {stats['per_question'][v.qid]:.0%} | {reason} |")
    return "\n".join(lines) + "\n"


def write_section(report: Path, section: str) -> None:
    """Replace the spot-check section of the mining report, or append it."""
    text = report.read_text(encoding="utf-8") if report.exists() else ""
    pattern = re.compile(re.escape(SECTION) + r".*?(?=^## |\Z)", re.DOTALL | re.MULTILINE)
    if pattern.search(text):
        text = pattern.sub(lambda m: section + "\n", text, count=1)
    else:
        text = text.rstrip("\n") + "\n\n" + section
    report.write_text(text.rstrip("\n") + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--allow-missing", action="store_true", help="apply the verdicts that exist, even if some are missing")
    ap.add_argument("--annotation-dir", default=str(REPO_ROOT / "annotation"))
    ap.add_argument("--data-dir", default=str(REPO_ROOT / "data"))
    args = ap.parse_args(argv)
    ann, data = Path(args.annotation_dir), Path(args.data_dir)
    manifest = json.loads((ann / "sample_manifest.json").read_text(encoding="utf-8"))
    verdicts, problems = load_verdicts(ann, manifest, args.allow_missing)
    if problems:
        print("Not applied. Fix these first:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 1
    questions = read_jsonl(data / "questions_all.jsonl")
    dropped = read_jsonl(data / "dropped.jsonl") if (data / "dropped.jsonl").exists() else []
    kept, new_dropped = apply(questions, dropped, verdicts)
    write_jsonl(data / "questions_all.jsonl", kept)
    write_jsonl(data / "dropped.jsonl", new_dropped)
    stats = disagreement(verdicts)
    write_section(data / "mining_report.md", report_section(stats, verdicts))
    print(f"{stats['checked']} verdicts; {stats['invalid']} invalid; {len(questions) - len(kept)} removed now; "
          f"{len(kept)} questions remain.\nThe test set is locked: do not rebuild the split. Re-run the analysis, which "
          f"excludes these questions: python -m analysis.make_all --run-id main --split test")
    return 0


if __name__ == "__main__":
    sys.exit(main())
