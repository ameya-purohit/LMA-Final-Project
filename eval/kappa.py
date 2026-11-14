"""Cohen's kappa, and gate G3's agreement report: humans against each other and against the judge.

If human-judge kappa is below 0.6, the primary comparison uses human labels (§6.11).
The rule is applied per label kind: answer correctness and citation labels each
have their own kappa (both three-class, consensus against judge), and each kind
whose kappa is below the threshold switches to human labels (D-48).

Consensus of the two labellers: their shared label where they agree; where they
disagree, the more conservative one (incorrect < partial < correct;
irrelevant < on_topic < causal). Deterministic, and it never credits a system
with more than both humans gave it.

Usage: python -m eval.kappa --run-id main
Reads results/<run>/human/{key.json, labels_<a>_done.jsonl, labels_<b>_done.jsonl} and the judgements;
writes results/<run>/human/{agreement.json, agreement.md, consensus.jsonl}.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Hashable, Sequence

ANSWER_ORDER = ("incorrect", "partial", "correct")
CITATION_ORDER = ("irrelevant", "on_topic", "causal")


def cohens_kappa(a: Sequence[Hashable], b: Sequence[Hashable]) -> float:
    if len(a) != len(b) or not a:
        raise ValueError("kappa needs two non-empty label lists of the same length")
    n = len(a)
    observed = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    expected = sum(ca[k] * cb.get(k, 0) for k in ca) / (n * n)
    if expected == 1.0:
        return 1.0 if observed == 1.0 else 0.0
    return (observed - expected) / (1 - expected)


def conservative(x: str, y: str, order: Sequence[str]) -> str:
    return x if x == y else order[min(order.index(x), order.index(y))]


def pairs(a: dict[str, dict], b: dict[str, dict], items: list[str], kind: str) -> tuple[list[str], list[str]]:
    """Aligned label lists over `items` for 'answer' (one per item) or 'citation' (one per cited line)."""
    xs, ys = [], []
    for it in items:
        if kind == "answer":
            xs.append(a[it]["correctness"]), ys.append(b[it]["correctness"])
        else:
            ca, cb = a[it]["citations"], b[it]["citations"]
            for x, y in zip(ca, cb):
                xs.append(x), ys.append(y)
    return xs, ys


def kappa_or_none(xs: list[str], ys: list[str]) -> float | None:
    return round(cohens_kappa(xs, ys), 3) if xs else None


def agreement(labels: dict[str, dict[str, dict]], judge: dict[str, dict], threshold: float) -> dict[str, Any]:
    """`labels`: labeller -> item -> {correctness, citations}; `judge`: item -> the same shape."""
    who = sorted(labels)
    if len(who) != 2:
        raise ValueError(f"need exactly two labellers, found {who}")
    a, b = labels[who[0]], labels[who[1]]
    both = sorted(set(a) & set(b))
    consensus = {it: {"correctness": conservative(a[it]["correctness"], b[it]["correctness"], ANSWER_ORDER),
                      "citations": [conservative(x, y, CITATION_ORDER) for x, y in zip(a[it]["citations"], b[it]["citations"])]}
                 for it in both}
    judged = [it for it in both if it in judge and len(judge[it]["citations"]) == len(consensus[it]["citations"])]
    out: dict[str, Any] = {"labellers": who, "items_labelled_by_both": len(both), "items_with_judgement": len(judged),
                           "threshold": threshold, "kappa": {}}
    for kind in ("answer", "citation"):
        k = out["kappa"][kind] = {
            "human_human": kappa_or_none(*pairs(a, b, both, kind)),
            f"{who[0]}_judge": kappa_or_none(*pairs(a, judge, judged, kind)),
            f"{who[1]}_judge": kappa_or_none(*pairs(b, judge, judged, kind)),
            "consensus_judge": kappa_or_none(*pairs(consensus, judge, judged, kind)),
            "n": len(pairs(consensus, judge, judged, kind)[0]),
        }
        k["use_human_labels"] = k["consensus_judge"] is not None and k["consensus_judge"] < threshold
    out["consensus"] = consensus
    return out


def report_md(result: dict[str, Any]) -> str:
    who = result["labellers"]
    lines = [f"# G3 agreement ({who[0]} and {who[1]})", "",
             f"Items labelled by both: {result['items_labelled_by_both']}; with a judgement: {result['items_with_judgement']}. "
             f"Kappa rule threshold: {result['threshold']}.", "",
             "| Labels | n | human-human | " + f"{who[0]}-judge | {who[1]}-judge | consensus-judge | primary uses |",
             "|---|---|---|---|---|---|---|"]
    f = lambda x: "n/a" if x is None else f"{x:.3f}"  # noqa: E731
    for kind, name in (("answer", "answer correctness"), ("citation", "citation labels")):
        k = result["kappa"][kind]
        lines.append(f"| {name} | {k['n']} | {f(k['human_human'])} | {f(k[who[0] + '_judge'])} | {f(k[who[1] + '_judge'])} | "
                     f"{f(k['consensus_judge'])} | {'human labels' if k['use_human_labels'] else 'judge labels'} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    from core.config import REPO_ROOT, load_config
    from core.jsonl import read_jsonl, write_jsonl
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-id", required=True)
    args = ap.parse_args(argv)
    cfg = load_config()
    root = REPO_ROOT / cfg["paths"]["results_dir"] / args.run_id
    human = root / "human"
    key = {k["item"]: k for k in json.loads((human / "key.json").read_text(encoding="utf-8"))}
    labels = {}
    for path in sorted(human.glob("labels_*_done.jsonl")):
        rows = read_jsonl(path)
        if rows:
            labels[rows[0]["labeller"]] = {r["item"]: r for r in rows}
    judge = {}
    for item, k in key.items():
        jp = root / "judgements" / k["system"] / f"{k['qid']}.json"
        if jp.exists():
            j = json.loads(jp.read_text(encoding="utf-8"))
            judge[item] = {"correctness": j["correctness"], "citations": j.get("citations", [])}
    result = agreement(labels, judge, cfg["eval"]["kappa_threshold"])
    write_jsonl(human / "consensus.jsonl", [{"item": it, **key[it], **lab} for it, lab in sorted(result["consensus"].items())])
    (human / "agreement.json").write_text(json.dumps({k: v for k, v in result.items() if k != "consensus"}, indent=1),
                                          encoding="utf-8")
    md = report_md(result)
    (human / "agreement.md").write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
