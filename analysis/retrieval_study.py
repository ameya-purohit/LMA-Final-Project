"""Retrieval study R1-R5 (exploratory extension): which retrieval finds the code the developer's fix changed?

No LLM is involved, so it runs on every test question at no quota cost. For each question, each mode retrieves the
top 10 code chunks for the question text; a chunk is *relevant* if it overlaps a `gold_evidence` range.

Modes: R1 bm25 · R2 dense · R3 rrf (BM25 + dense) · R4 rerank (R3 + cross-encoder) · R5 graph (R4 + call-graph
expansion). Metrics per K in (1, 5, 10): hit@K (a relevant chunk in the top K), Recall@K (share of the relevant chunks
in the top K), Precision@K, MRR@K. Paired comparisons: exact McNemar on hit@5 and a paired bootstrap on MRR@10.

Resumable: each question's ranks are written to `results/ext_retrieval/<qid>.json` as soon as they are computed.
Usage: python -m analysis.retrieval_study [--split test] [--limit N]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from statistics import mean
from typing import Any

from core.config import REPO_ROOT, load_config
from core.jsonl import read_jsonl

MODES = {"R1": "bm25", "R2": "dense", "R3": "rrf", "R4": "rerank", "R5": "graph"}
KS = (1, 5, 10)
COMPARISONS = [("R2", "R1"), ("R3", "R1"), ("R4", "R1"), ("R4", "R3"), ("R5", "R4")]


def relevant(chunk_path: str, start: int, end: int, gold: list[dict[str, Any]]) -> bool:
    from eval.metrics import path_matches
    return any(path_matches(chunk_path, g["path"]) and start <= g["line_end"] and g["line_start"] <= end for g in gold)


def per_question_metrics(flags: list[bool], n_relevant: int) -> dict[str, float]:
    """flags[i] = whether the i-th retrieved chunk is relevant."""
    out: dict[str, float] = {}
    first = next((i + 1 for i, f in enumerate(flags) if f), None)
    for k in KS:
        top = flags[:k]
        out[f"hit@{k}"] = float(any(top))
        out[f"recall@{k}"] = sum(top) / n_relevant if n_relevant else 0.0
        out[f"precision@{k}"] = sum(top) / k
        out[f"mrr@{k}"] = 1.0 / first if first and first <= k else 0.0
    return out


def run_question(q: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    from codegraph.graph import CodeGraph
    from retrieval.hybrid import HybridIndex
    from tools.workspace import Workspace
    ws = Workspace.for_question(q, cfg)
    graph = CodeGraph(ws.tree, ws.package, ws.source_root)
    index = HybridIndex(ws.index, cfg, graph=graph)
    gold = q["gold_evidence"]
    n_rel = sum(relevant(c.path, c.line_start, c.line_end, gold) for c in ws.index.code.chunks)
    row: dict[str, Any] = {"qid": q["qid"], "library": q["library"], "n_relevant": n_rel, "modes": {}}
    for name, mode in MODES.items():
        hits = index.search(q["question_text"], 10, kind="code", mode=mode)
        flags = [relevant(h.chunk.path, h.chunk.line_start, h.chunk.line_end, gold) for h in hits]
        row["modes"][name] = {"flags": flags, "top": [f"{h.chunk.path}:{h.chunk.line_start}" for h in hits],
                              **per_question_metrics(flags, n_rel)}
    return row


def summarize(rows: list[dict[str, Any]], cfg: dict[str, Any]) -> dict[str, Any]:
    from eval.stats import mcnemar_exact, paired_bootstrap
    rows = [r for r in rows if r["n_relevant"] > 0]
    ev = cfg["eval"]
    table = {name: {m: mean(r["modes"][name][m] for r in rows) for m in rows[0]["modes"][name] if "@" in m}
             for name in MODES} if rows else {}
    comps = {}
    for a, b in COMPARISONS:
        ha = [bool(r["modes"][a]["hit@5"]) for r in rows]
        hb = [bool(r["modes"][b]["hit@5"]) for r in rows]
        ma = [r["modes"][a]["mrr@10"] for r in rows]
        mb = [r["modes"][b]["mrr@10"] for r in rows]
        comps[f"{a} vs {b}"] = {"hit@5": {**mcnemar_exact(ha, hb), **paired_bootstrap(ha, hb, resamples=ev["bootstrap_resamples"], seed=ev["bootstrap_seed"])},
                                "mrr@10": paired_bootstrap(ma, mb, resamples=ev["bootstrap_resamples"], seed=ev["bootstrap_seed"])}
    by_lib = {lib: {name: mean(r["modes"][name]["hit@5"] for r in rows if r["library"] == lib) for name in MODES}
              for lib in sorted({r["library"] for r in rows})}
    return {"n_questions": len(rows), "table": table, "comparisons": comps, "hit5_by_library": by_lib}


def report(res: dict[str, Any], n_skipped: int) -> str:
    lines = ["# Retrieval study (exploratory extension, no LLM)", "",
             f"Test questions with at least one relevant code chunk: {res['n_questions']} "
             f"(skipped {n_skipped} whose fix lines fall in no code chunk, e.g. only new files).", "",
             "| Mode | hit@1 | hit@5 | hit@10 | Recall@5 | Recall@10 | Precision@5 | MRR@10 |", "|---|---|---|---|---|---|---|---|"]
    names = {"R1": "R1 BM25", "R2": "R2 dense", "R3": "R3 BM25+dense (RRF)", "R4": "R4 RRF + rerank", "R5": "R5 R4 + call graph"}
    for k, t in res["table"].items():
        lines.append(f"| {names[k]} | {t['hit@1']:.1%} | {t['hit@5']:.1%} | {t['hit@10']:.1%} | {t['recall@5']:.1%} | "
                     f"{t['recall@10']:.1%} | {t['precision@5']:.1%} | {t['mrr@10']:.3f} |")
    lines += ["", "Paired comparisons (hit@5: exact McNemar and bootstrap 95% CI of the difference; MRR@10: bootstrap CI).", "",
              "| Comparison | hit@5 diff | 95% CI | p | MRR@10 diff | 95% CI |", "|---|---|---|---|---|---|"]
    for name, c in res["comparisons"].items():
        h, m = c["hit@5"], c["mrr@10"]
        lines.append(f"| {name} | {h['diff'] * 100:+.1f} pts | [{h['ci_low'] * 100:+.1f}, {h['ci_high'] * 100:+.1f}] | "
                     f"{h['p_value']:.3f} | {m['diff']:+.3f} | [{m['ci_low']:+.3f}, {m['ci_high']:+.3f}] |")
    lines += ["", "hit@5 by library: " + "; ".join(f"{lib}: " + ", ".join(f"{k} {v:.0%}" for k, v in t.items())
                                                  for lib, t in res["hit5_by_library"].items())]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", default="test")
    ap.add_argument("--limit", type=int)
    args = ap.parse_args(argv)
    cfg = load_config()
    from analysis.make_all import spot_check_exclusions
    removed = spot_check_exclusions(REPO_ROOT / "data" / "dropped.jsonl")
    questions = [q for q in read_jsonl(REPO_ROOT / "data" / f"questions_{args.split}.jsonl") if q["qid"] not in removed]
    questions = questions[: args.limit]
    out_dir = REPO_ROOT / "results" / "ext_retrieval"
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for i, q in enumerate(questions, 1):
        path = out_dir / f"{q['qid']}.json"
        if path.exists():
            rows.append(json.loads(path.read_text()))
            continue
        t = time.time()
        row = run_question(q, cfg)
        path.write_text(json.dumps(row), encoding="utf-8")
        rows.append(row)
        print(f"{q['qid']}: hit@5 " + " ".join(f"{k}={int(v['hit@5'])}" for k, v in row["modes"].items())
              + f" ({time.time() - t:.0f}s, {i}/{len(questions)})", flush=True)
    res = summarize(rows, cfg)
    skipped = sum(r["n_relevant"] == 0 for r in rows)
    summary = REPO_ROOT / "results" / "summary"
    (summary / "retrieval_study.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    (summary / "retrieval_study.md").write_text(report(res, skipped), encoding="utf-8")
    print(report(res, skipped))
    return 0


if __name__ == "__main__":
    sys.exit(main())
