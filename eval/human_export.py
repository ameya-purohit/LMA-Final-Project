"""Blinded labelling sample for gate G3: a shuffled CSV, with a key kept separately.

Human labellers see the question, the answer and its citations, never the system
that produced them. Usage: python -m eval.human_export --run-id mid --split dev --n 40
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from pathlib import Path
from typing import Any

from core.config import REPO_ROOT, load_config
from core.jsonl import read_jsonl


def build_rows(answers: list[dict[str, Any]], questions: dict[str, dict[str, Any]], n: int, seed: int) -> tuple[list[dict], list[dict]]:
    """(blinded rows, key). One row per answer, plus one per citation, in shuffled order."""
    rng = random.Random(seed)
    chosen = sorted(answers, key=lambda a: (a["qid"], a["system"]))
    rng.shuffle(chosen)
    chosen = chosen[:n]
    rows, key = [], []
    for i, a in enumerate(chosen):
        item = f"A{i + 1:03d}"
        key.append({"item": item, "qid": a["qid"], "system": a["system"]})
        q = questions[a["qid"]]
        rows.append({"item": item, "kind": "answer", "question": q["question_text"], "gold_answer": q["gold_answer"],
                     "text": a.get("answer_text", ""), "path": "", "line": "", "label": ""})
        for claim in a.get("claims", []):
            for c in claim.get("citations", []):
                rows.append({"item": item, "kind": "citation", "question": "", "gold_answer": "", "text": claim.get("text", ""),
                             "path": c["path"], "line": c["line"], "label": ""})
    return rows, key


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default="mid")
    ap.add_argument("--split", default="dev")
    ap.add_argument("--n", type=int, default=40)
    args = ap.parse_args(argv)
    cfg = load_config()
    root = REPO_ROOT / cfg["paths"]["results_dir"] / args.run_id
    questions = {q["qid"]: q for q in read_jsonl(REPO_ROOT / "data" / f"questions_{args.split}.jsonl")}
    answers = [json.loads(p.read_text(encoding="utf-8")) for s in root.iterdir() if s.is_dir() and s.name != "judgements"
               for p in s.glob("*.json")]
    rows, key = build_rows(answers, questions, args.n, cfg["eval"]["bootstrap_seed"])
    out = root / "human"
    out.mkdir(exist_ok=True)
    with open(out / "labels.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["item", "kind", "question", "gold_answer", "text", "path", "line", "label"])
        w.writeheader()
        w.writerows(rows)
    (out / "key.json").write_text(json.dumps(key, indent=1), encoding="utf-8")
    print(f"wrote {len(rows)} rows for {len(key)} answers to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
