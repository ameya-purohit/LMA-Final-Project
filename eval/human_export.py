"""Gate G3: the blinded labelling sample for the two human labellers.

Human labels check the judge (kappa rule, §6.11) and give H3 its human-judged
citation precision. The sample is drawn by *question*: a seeded random set of
questions, stratified by library, and for each one the answer of every system
in the run. So the labelled answers are paired across systems, and every
citation from ours and A2 on those questions is labelled (H3, RQ2).

Labellers see exactly what the judge sees (question, gold answer, the failing
test's message, the source part of the fix, each cited snippet), never which
system wrote an answer. Items are shuffled with a fixed seed and get opaque ids
(A001, ...); the key that maps them back is written separately.

Writes results/<run>/human/:
  labels_<labeller>.jsonl  one per labeller, identical items (both label everything)
  key.json                 item -> (qid, system); not for the labellers
  sample.json              how the sample was drawn
Labellers open eval/label.html and export labels_<labeller>_done.jsonl into the same folder.

Usage: python -m eval.human_export --run-id main --split test [--questions 12] [--labellers a b]
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

from core.config import REPO_ROOT, load_config
from core.jsonl import read_jsonl, write_jsonl

CITATION_LABELS = ("causal", "on_topic", "irrelevant")
ANSWER_LABELS = ("correct", "partial", "incorrect")


def sample_questions(qids_by_library: dict[str, list[str]], n: int, seed: int) -> list[str]:
    """`n` questions, each library in proportion to its size (largest remainder), seeded."""
    rng = random.Random(seed)
    pools = {lib: sorted(q) for lib, q in qids_by_library.items()}
    for lib in sorted(pools):
        rng.shuffle(pools[lib])
    total = sum(len(v) for v in pools.values())
    n = min(n, total)
    quota = {lib: n * len(v) / total for lib, v in pools.items()} if total else {}
    take = {lib: int(q) for lib, q in quota.items()}
    for lib in sorted(quota, key=lambda l: (-(quota[l] - take[l]), l))[: n - sum(take.values())]:
        take[lib] += 1
    return sorted(q for lib in sorted(pools) for q in pools[lib][: take[lib]])


def build_items(answers: list[dict[str, Any]], questions: dict[str, dict[str, Any]], seed: int,
                diff_fn: Callable[[dict[str, Any]], str], snippet_fn: Callable[[dict[str, Any], str, int], str]
                ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(blinded items, key). One item per answer, carrying all its citations; shuffled with the seed."""
    from eval.judge import citation_list
    ordered = sorted(answers, key=lambda a: (a["qid"], a["system"]))
    random.Random(seed).shuffle(ordered)
    items, key, diffs = [], [], {}
    for i, a in enumerate(ordered):
        q = questions[a["qid"]]
        item = f"A{i + 1:03d}"
        key.append({"item": item, "qid": a["qid"], "system": a["system"]})
        if a["qid"] not in diffs:
            diffs[a["qid"]] = diff_fn(q)
        items.append({
            "item": item, "question": q["question_text"], "gold_answer": q["gold_answer"],
            "observed_before": [{"test": o["test"], "status": o["status"], "message": (o.get("message") or "")[:1500]}
                                for o in q["observed_before"][:5]],
            "fix_diff": diffs[a["qid"]], "answer": a.get("answer_text") or "(empty answer)",
            "citations": [{"n": j + 1, "path": c["path"], "line": c["line"], "claim": c["claim"],
                           "snippet": snippet_fn(q, c["path"], c["line"])} for j, c in enumerate(citation_list(a))],
        })
    return items, key


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--split", default="test")
    ap.add_argument("--questions", type=int, default=12, help="questions to sample; every system's answer to each is labelled")
    ap.add_argument("--systems", nargs="*", help="default: every system in the run")
    ap.add_argument("--labellers", nargs=2, default=["labeller1", "labeller2"])
    args = ap.parse_args(argv)
    cfg = load_config()
    from eval.judge import fix_diff, snippet
    from data.freeze import export_tree, repo_path, tree_path
    root = REPO_ROOT / cfg["paths"]["results_dir"] / args.run_id
    questions = {q["qid"]: q for q in read_jsonl(REPO_ROOT / "data" / f"questions_{args.split}.jsonl")}
    systems = args.systems or sorted(p.name for p in root.iterdir() if p.is_dir() and p.name not in ("judgements", "human"))
    answered = [{p.stem for p in (root / s).glob("*.json")} for s in systems]
    common = sorted(set.intersection(*answered) & set(questions)) if answered else []
    by_lib: dict[str, list[str]] = defaultdict(list)
    for qid in common:
        by_lib[questions[qid]["library"]].append(qid)
    chosen = sample_questions(by_lib, args.questions, cfg["eval"]["bootstrap_seed"])
    answers = [json.loads((root / s / f"{qid}.json").read_text(encoding="utf-8")) for qid in chosen for s in systems]

    def snip(q: dict[str, Any], path: str, line: int) -> str:
        tree = export_tree(repo_path(q["library"], cfg), q["frozen_commit"], tree_path(q["library"], q["frozen_commit"], cfg))
        return snippet(tree, path, line, context=5)

    items, key = build_items(answers, questions, cfg["eval"]["bootstrap_seed"], lambda q: fix_diff(q, cfg), snip)
    out = root / "human"
    out.mkdir(parents=True, exist_ok=True)
    for who in args.labellers:
        write_jsonl(out / f"labels_{who}.jsonl", [{**it, "labeller": who} for it in items])
    (out / "key.json").write_text(json.dumps(key, indent=1), encoding="utf-8")
    (out / "sample.json").write_text(json.dumps({"run_id": args.run_id, "split": args.split, "systems": systems,
                                                 "questions": chosen, "labellers": args.labellers,
                                                 "seed": cfg["eval"]["bootstrap_seed"]}, indent=1), encoding="utf-8")
    n_cites = sum(len(it["citations"]) for it in items)
    print(f"{len(chosen)} questions x {len(systems)} systems = {len(items)} answers, {n_cites} citations; "
          f"files for {', '.join(args.labellers)} in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
