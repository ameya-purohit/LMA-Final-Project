"""Turn stored answers and judgements into summary tables (results/summary/).

Usage: python -m eval.report --run-id mid --split dev
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from core.config import REPO_ROOT, load_config
from core.jsonl import read_jsonl
from eval.metrics import score_question, summarize
from eval.stats import mcnemar_exact, paired_bootstrap

ORDER = ["b0", "b1", "b2", "b2plus", "b3", "ours", "a1", "a2", "a3", "a4", "a5", "a7", "a8", "a10none", "a10oracle", "a11"]


def load_scores(run_root: Path, questions: dict[str, dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for system_dir in sorted(p for p in run_root.iterdir() if p.is_dir() and p.name not in ("judgements", "human")):
        rows = []
        for path in sorted(system_dir.glob("*.json")):
            answer = json.loads(path.read_text(encoding="utf-8"))
            q = questions.get(answer["qid"])
            if q is None:
                continue
            jpath = run_root / "judgements" / system_dir.name / path.name
            judgement = json.loads(jpath.read_text(encoding="utf-8")) if jpath.exists() else None
            rows.append(score_question(answer, q, judgement))
        out[system_dir.name] = rows
    return out


def common_questions(scores: dict[str, list[dict[str, Any]]]) -> tuple[list[str], list[str]]:
    """(questions every system answered, the subset every system also has a judgement for).

    If quota stops a run early, systems cover different questions, and comparing rates over different
    questions would be unfair. Every comparison therefore uses only these common sets.
    """
    if not scores:
        return [], []
    answered = [{s["qid"] for s in rows} for rows in scores.values()]
    judged = [{s["qid"] for s in rows if s["judged"]} for rows in scores.values()]
    return sorted(set.intersection(*answered)), sorted(set.intersection(*judged))


def restrict(rows: list[dict[str, Any]], common: list[str], judged_common: list[str]) -> list[dict[str, Any]]:
    """Keep common questions only. A judgement outside the judged-common set is not counted."""
    out = []
    for s in rows:
        if s["qid"] in common:
            if s["qid"] not in judged_common:
                s = {**s, "judged": False, "label": None, "correct": False, "partial": False, "wrong": False,
                     "confident_error": False, "causally_supported": False}
            out.append(s)
    return out


def pct(x: float | None) -> str:
    return "pending" if x is None else f"{100 * x:.1f}%"


def num(x: float | None, digits: int = 1) -> str:
    return "pending" if x is None else f"{x:.{digits}f}"


def markdown_table(summaries: dict[str, dict[str, Any]]) -> str:
    head = ("| System | n run | n judged | Correct | Partial | Correctness | Causally supported | Fix-location recall | "
            "Confident errors | Confident-error rate | Coverage | Requests/q (mean) | Requests/q (max) | Tokens/q (mean) | "
            "Probe runs/q | Mutant runs/q |")
    rows = [head, "|" + "---|" * 16]
    for s in [k for k in ORDER if k in summaries]:
        m = summaries[s]
        rows.append(f"| {s} | {m['n']} | {m['n_judged']} | {m['n_correct']} | {m['n_partial']} | {pct(m['correctness'])} | "
                    f"{pct(m['causally_supported'])} | {pct(m['fix_location_recall'])} | {m['n_confident_errors']} | "
                    f"{pct(m['confident_error_rate'])} | {pct(m['coverage'])} | {num(m['requests_mean'])} | {m['requests_max']} | "
                    f"{num(m['tokens_mean'], 0)} | {num(m['probe_runs_mean'])} | {num(m['mutant_runs_mean'])} |")
    return "\n".join(rows)


def paired_comparison(a: list[dict], b: list[dict], key: str, cfg: dict[str, Any]) -> dict[str, Any] | None:
    """`a` minus `b` on questions both systems answered and the judge graded."""
    ba = {s["qid"]: s for s in a if s["judged"]}
    bb = {s["qid"]: s for s in b if s["judged"]}
    common = sorted(set(ba) & set(bb))
    if not common:
        return None
    x, y = [ba[q][key] for q in common], [bb[q][key] for q in common]
    return {"n": len(common), **mcnemar_exact(x, y),
            **paired_bootstrap(x, y, resamples=cfg["eval"]["bootstrap_resamples"], seed=cfg["eval"]["bootstrap_seed"])}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default="mid")
    ap.add_argument("--split", default="dev")
    args = ap.parse_args(argv)
    cfg = load_config()
    root = REPO_ROOT / cfg["paths"]["results_dir"] / args.run_id
    questions = {q["qid"]: q for q in read_jsonl(REPO_ROOT / "data" / f"questions_{args.split}.jsonl")}
    all_scores = load_scores(root, questions)
    common, judged_common = common_questions(all_scores)
    scores = {s: restrict(rows, common, judged_common) for s, rows in all_scores.items()}
    summaries = {s: summarize(rows) for s, rows in scores.items()}
    # Each system on its own judged part of the common questions; used when the judge's quota stopped it early.
    by_system = {s: summarize(restrict(rows, common, common)) for s, rows in all_scores.items()}
    completed = {s: len(rows) for s, rows in all_scores.items()}
    comparisons = {}
    # Pairwise: within the questions all systems completed, every question both of the two have a judgement for.
    pairable = {s: restrict(rows, common, common) for s, rows in all_scores.items()}
    for other in ("b2", "a1", "a2", "a3", "b1", "b0"):
        if "ours" in pairable and other in pairable:
            for key in ("correct", "causally_supported", "confident_error", "fix_location_hit"):
                comparisons[f"ours_minus_{other}:{key}"] = paired_comparison(pairable["ours"], pairable[other], key, cfg)
    out = REPO_ROOT / "results" / "summary"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{args.run_id}_{args.split}.json").write_text(
        json.dumps({"completed_per_system": completed, "common_questions": common, "judged_common_questions": judged_common,
                    "summaries": summaries, "summaries_all_judged_of_common": by_system, "comparisons": comparisons, "per_question": scores}, indent=1), encoding="utf-8")
    header = (f"Questions completed per system: {completed}. All systems are compared only on the {len(common)} questions "
              f"every one of them completed; judge-based columns use the {len(judged_common)} of those judged for every system.")
    table = header + "\n\n" + markdown_table(summaries)
    if len(judged_common) != len(common):
        table += (f"\n\nEach system on every one of the {len(common)} common questions it has a judgement for "
                  "(n judged differs by system, so compare rows with care):\n\n" + markdown_table(by_system))
    (out / f"{args.run_id}_{args.split}.md").write_text(table + "\n", encoding="utf-8")
    print(table)
    return 0


if __name__ == "__main__":
    sys.exit(main())
