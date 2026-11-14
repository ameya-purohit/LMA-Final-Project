"""Tables for the exploratory multi-agent extension (E0-E6, B2) on the 47 `sub50` test questions.

Reads stored answers only (no LLM): E0 = `results/sub50/ours`, B2 = `results/sub50/b2`, E1-E6 = `results/ext/e*`.
Writes `results/summary/extension.json` and `results/summary/extension.md`.

Usage: python -m analysis.extension [--run-id ext]
"""

from __future__ import annotations

import argparse
import json
import sys
from statistics import mean
from typing import Any

from core.config import REPO_ROOT, load_config
from core.jsonl import read_jsonl

SOURCES = {"E0": ("sub50", "ours"), "B2": ("sub50", "b2"), "E1": ("ext", "e1"), "E2": ("ext", "e2"),
           "E3": ("ext", "e3"), "E4": ("ext", "e4"), "E5": ("ext", "e5"), "E6": ("ext", "e6")}
COMPARISONS = [("E1", "E0"), ("E1", "B2"), ("E2", "E1"), ("E3", "E2"), ("E4", "E3"), ("E5", "E4"), ("E6", "E5"),
               ("E5", "E0"), ("E2", "E0"), ("E2", "B2")]
LOC_KEYS = ["line_top1", "line_top3", "line_mrr", "line_precision", "line_recall", "line_f1",
            "fn_top1", "fn_top3", "fn_mrr", "fn_precision", "fn_recall", "fn_f1"]


def function_lookup(question: dict[str, Any], cache: dict[str, Any]):
    """(path, line) -> qualified function name in the frozen tree, or None (module level / unknown)."""
    from codegraph.graph import CodeGraph
    from tools.workspace import detect_source_root
    key = f"{question['library']}/{question['frozen_commit']}"
    if key not in cache:
        cache.clear()   # keep one graph in memory at a time (the run machine has ~1 GB free)
        cfg = load_config()
        tree = REPO_ROOT / cfg["paths"]["trees_dir"] / question["library"] / question["frozen_commit"]
        pkg = cfg["data"]["libraries"][question["library"]]["package"]
        try:
            cache[key] = CodeGraph(tree, pkg, detect_source_root(tree, pkg))
        except FileNotFoundError:
            cache[key] = None
    g = cache[key]

    def of(path: str, line: int):
        if g is None:
            return None
        f = g.function_at(path, line)
        return f.qualname if f else None
    return of


def load_answers(run_id: str, qids: set[str]) -> dict[str, dict[str, dict[str, Any]]]:
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for name, (default_run, system) in SOURCES.items():
        run = run_id if default_run == "ext" else default_run
        d = REPO_ROOT / "results" / run / system
        if not d.is_dir():
            continue
        rows = {p.stem: json.loads(p.read_text()) for p in d.glob("*.json") if p.stem in qids}
        if rows:
            jd = REPO_ROOT / "results" / run / "judgements" / system
            for qid, a in rows.items():
                j = jd / f"{qid}.json"
                a["_judgement"] = json.loads(j.read_text()) if j.exists() else None
            out[name] = rows
    return out


def per_question(answers: dict[str, dict[str, dict]], questions: dict[str, dict]) -> dict[str, dict[str, dict]]:
    from eval.localization import ranked_locations, score_locations, verification_counts
    cache: dict[str, Any] = {}
    out: dict[str, dict[str, dict]] = {}
    for name, rows in answers.items():
        out[name] = {}
        for qid, a in sorted(rows.items(), key=lambda kv: questions[kv[0]]["frozen_commit"]):
            q = questions[qid]
            s = score_locations(ranked_locations(a), q["gold_evidence"], function_lookup(q, cache))
            s.update(verification_counts(a, q["gold_evidence"]))
            j = a.get("_judgement")
            s["correct"] = None if not j else j.get("correctness") == "correct"
            s.update({"requests": a.get("requests", 0), "api_requests": a.get("api_requests", 0),
                      "tokens": a.get("tokens", {}).get("total", 0), "mutant_runs": a.get("mutant_runs", 0),
                      "probe_runs": a.get("probe_runs", 0), "wall_seconds": a.get("wall_seconds", 0.0),
                      "flagged": bool(a.get("flagged_uncertain")), "abstained": bool(a.get("abstained")),
                      "patch_validated": (a.get("patch_validation") or {}).get("validated")})
            s["ranking_len"], s["gold_class"], s["gold_rank"] = ranking_diagnosis(a, q["gold_evidence"])
            out[name][qid] = s
    return out


def ranking_diagnosis(answer: dict[str, Any], gold: list[dict[str, Any]]) -> tuple[int | None, str | None, int | None]:
    """For E1-E6: (length of the final ranking, verdict class of the first gold line in it, its 1-based rank).
    Explains rank changes between configurations: a gold line the mutation check rejected sorts below every
    inconclusive or untested line, so it only stays in the top 3 when the ranking is short."""
    from eval.localization import range_index
    if answer.get("ranking") is None:
        return None, None, None
    for i, r in enumerate(answer["ranking"]):
        if range_index(r["path"], int(r["line"]), gold) is not None:
            return len(answer["ranking"]), r.get("class"), i + 1
    return len(answer["ranking"]), None, None


def summarize(scores: dict[str, dict[str, dict]], common: list[str]) -> dict[str, Any]:
    from eval.stats import mcnemar_exact, paired_bootstrap
    cfg = load_config()["eval"]
    table, groups, verif = {}, {}, {}
    for name, rows in scores.items():
        rs = [rows[q] for q in common if q in rows]
        if not rs:
            continue
        t = {k: mean(r[k] for r in rs) for k in LOC_KEYS if k in rs[0]}
        judged = [r for r in rs if r["correct"] is not None]
        t["correct"] = mean(r["correct"] for r in judged) if judged else None
        t["n_judged"] = len(judged)
        for k in ("requests", "api_requests", "tokens", "mutant_runs", "probe_runs", "wall_seconds"):
            t[k] = mean(r[k] for r in rs)
        t["coverage"] = mean(not r["flagged"] and not r["abstained"] for r in rs)
        pv = [r["patch_validated"] for r in rs if r["patch_validated"] is not None]
        t["patch_validated"] = (sum(pv) / len(pv)) if pv else None
        t["n_patches"] = len(pv)
        t["n"] = len(rs)
        table[name] = t
        groups[name] = {g: {"n": len(sub), "line_top3": mean(r["line_top3"] for r in sub),
                            "fn_top3": mean(r.get("fn_top3", 0) for r in sub),
                            **({"multi_found": mean(r["multi_found"] for r in sub)} if g == "multi" else {})}
                        for g, sub in (("single", [r for r in rs if not r["multi"]]), ("multi", [r for r in rs if r["multi"]]))
                        if sub}
        tot = {k: sum(r[k] for r in rs) for k in ("tested", "tested_gold", "accepted_gold", "tested_other",
                                                   "accepted_other", "inconclusive")}
        verif[name] = {**tot,
                       "acceptance_on_gold": tot["accepted_gold"] / tot["tested_gold"] if tot["tested_gold"] else None,
                       "acceptance_on_other": tot["accepted_other"] / tot["tested_other"] if tot["tested_other"] else None,
                       "inconclusive_rate": tot["inconclusive"] / tot["tested"] if tot["tested"] else None}
    comps = {}
    for a, b in COMPARISONS:
        if a not in scores or b not in scores:
            continue
        qs = [q for q in common if q in scores[a] and q in scores[b]]
        xa = [bool(scores[a][q]["line_top3"]) for q in qs]
        xb = [bool(scores[b][q]["line_top3"]) for q in qs]
        ma = [scores[a][q]["line_mrr"] for q in qs]
        mb = [scores[b][q]["line_mrr"] for q in qs]
        fa = [bool(scores[a][q].get("fn_top3")) for q in qs]
        fb = [bool(scores[b][q].get("fn_top3")) for q in qs]
        kw = {"resamples": cfg["bootstrap_resamples"], "seed": cfg["bootstrap_seed"]}
        comps[f"{a} vs {b}"] = {"n": len(qs), "line_top3": {**mcnemar_exact(xa, xb), **paired_bootstrap(xa, xb, **kw)},
                                "fn_top3": {**mcnemar_exact(fa, fb), **paired_bootstrap(fa, fb, **kw)},
                                "line_mrr": paired_bootstrap(ma, mb, **kw)}
        # Judged correctness, on the questions both systems have a judgement for.
        jq = [q for q in qs if scores[a][q]["correct"] is not None and scores[b][q]["correct"] is not None]
        ca = [bool(scores[a][q]["correct"]) for q in jq]
        cb = [bool(scores[b][q]["correct"]) for q in jq]
        comps[f"{a} vs {b}"]["correct"] = {"n": len(jq), **mcnemar_exact(ca, cb), **paired_bootstrap(ca, cb, **kw)}
    diag = {}
    for name, rows in scores.items():
        rs = [rows[q] for q in common if q in rows and rows[q].get("ranking_len") is not None]
        if not rs:
            continue
        top3 = [r for r in rs if r["gold_rank"] is not None and r["gold_rank"] <= 3]
        classes: dict[str, int] = {}
        for r in top3:
            classes[r["gold_class"]] = classes.get(r["gold_class"], 0) + 1
        diag[name] = {"mean_ranking_len": mean(r["ranking_len"] for r in rs), "top3_gold_classes": classes,
                      "gold_absent": sum(r["gold_rank"] is None for r in rs)}
    return {"n_common": len(common), "table": table, "by_fault": groups, "verification": verif, "comparisons": comps,
            "ranking_diagnosis": diag}


def pct(x: float | None) -> str:
    return "–" if x is None else f"{x:.1%}"


def report(res: dict[str, Any]) -> str:
    t = res["table"]
    names = [n for n in SOURCES if n in t]
    L = ["# Exploratory extension: multi-agent localization (not pre-registered as a primary result)", "",
         f"Questions answered by every system shown: {res['n_common']} (of the 47 `sub50` test questions). "
         "Gold = lines the developer's fix changed; every rate is a lower bound (a causal line outside the fix counts as a miss).", "",
         "## Localization", "",
         "| System | Line Top-1 | Line Top-3 | Line MRR | Line P / R / F1 | Fn Top-1 | Fn Top-3 | Fn MRR | Fn F1 |",
         "|---|---|---|---|---|---|---|---|---|"]
    for n in names:
        r = t[n]
        L.append(f"| {n} | {pct(r['line_top1'])} | {pct(r['line_top3'])} | {r['line_mrr']:.3f} | "
                 f"{pct(r['line_precision'])} / {pct(r['line_recall'])} / {pct(r['line_f1'])} | {pct(r.get('fn_top1'))} | "
                 f"{pct(r.get('fn_top3'))} | {r.get('fn_mrr', 0):.3f} | {pct(r.get('fn_f1'))} |")
    L += ["", "## Single-location vs multi-location faults", "",
          "| System | Single: n, line Top-3, fn Top-3 | Multi: n, line Top-3, fn Top-3, ≥2 gold ranges in top 5 |", "|---|---|---|"]
    for n in names:
        g = res["by_fault"][n]
        s, m = g.get("single"), g.get("multi")
        L.append(f"| {n} | " + (f"{s['n']}, {pct(s['line_top3'])}, {pct(s['fn_top3'])}" if s else "–") + " | "
                 + (f"{m['n']}, {pct(m['line_top3'])}, {pct(m['fn_top3'])}, {pct(m['multi_found'])}" if m else "–") + " |")
    L += ["", "## Causal verification (mutation-checked lines)", "",
          "| System | Lines tested | Acceptance on fix lines | Acceptance on other lines (upper bound on false acceptance) | Inconclusive |",
          "|---|---|---|---|---|"]
    for n in names:
        v = res["verification"][n]
        L.append(f"| {n} | {v['tested']} | {pct(v['acceptance_on_gold'])} ({v['accepted_gold']}/{v['tested_gold']}) | "
                 f"{pct(v['acceptance_on_other'])} ({v['accepted_other']}/{v['tested_other']}) | {pct(v['inconclusive_rate'])} |")
    L += ["", "E0 records yes/no verdicts; its 'no' includes flips that also changed a control, which E1-E6 call "
          "inconclusive, so E0's inconclusive rate counts only untestable lines.", "",
          "## Correctness (judge) and cost per question", "",
          "| System | Correct (judged) | Coverage | Requests | Tokens | Mutant runs | Probe runs | Wall s | Patch validated |",
          "|---|---|---|---|---|---|---|---|---|"]
    for n in names:
        r = t[n]
        L.append(f"| {n} | {pct(r['correct'])} (n={r['n_judged']}) | {pct(r['coverage'])} | {r['requests']:.1f} | "
                 f"{r['tokens']:,.0f} | {r['mutant_runs']:.1f} | {r['probe_runs']:.1f} | {r['wall_seconds']:.0f} | "
                 f"{pct(r['patch_validated'])} (n={r['n_patches']}) |")
    L += ["", "## Paired comparisons", "",
          "| Comparison | n | Line Top-3 diff [95% CI], McNemar p | Fn Top-3 diff [95% CI], p | Line MRR diff [95% CI] "
          "| Correct (judged) diff [95% CI], p |",
          "|---|---|---|---|---|---|"]
    for k, c in res["comparisons"].items():
        a, f, m = c["line_top3"], c["fn_top3"], c["line_mrr"]
        L.append(f"| {k} | {c['n']} | {a['diff'] * 100:+.1f} [{a['ci_low'] * 100:+.1f}, {a['ci_high'] * 100:+.1f}], "
                 f"p={a['p_value']:.3f} | {f['diff'] * 100:+.1f} [{f['ci_low'] * 100:+.1f}, {f['ci_high'] * 100:+.1f}], "
                 f"p={f['p_value']:.3f} | {m['diff']:+.3f} [{m['ci_low']:+.3f}, {m['ci_high']:+.3f}] | {_corr(c.get('correct'))} |")
    if res.get("ranking_diagnosis"):
        L += ["", "## Ranking diagnosis (E1-E6)", "",
              "Final rankings sort lines by verdict: accepted, accepted pair, cited, inconclusive, untested, rejected. "
              "A gold line the mutation check rejected therefore reaches the top 3 only when few lines are ranked.", "",
              "| System | Mean lines ranked | Gold line in top 3, by its verdict class | Gold line not ranked |",
              "|---|---|---|---|"]
        for n, d in res["ranking_diagnosis"].items():
            cl = ", ".join(f"{k} {v}" for k, v in sorted(d["top3_gold_classes"].items(), key=lambda kv: -kv[1])) or "–"
            L.append(f"| {n} | {d['mean_ranking_len']:.1f} | {cl} | {d['gold_absent']} |")
    return "\n".join(L) + "\n"


def _corr(c: dict | None) -> str:
    if not c or not c["n"]:
        return "–"
    return f"{c['diff'] * 100:+.1f} [{c['ci_low'] * 100:+.1f}, {c['ci_high'] * 100:+.1f}], p={c['p_value']:.3f} (n={c['n']})"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-id", default="ext")
    args = ap.parse_args(argv)
    qids = {x.strip() for x in (REPO_ROOT / "data" / "ext_qids.txt").read_text().splitlines() if x.strip()}
    questions = {q["qid"]: q for q in read_jsonl(REPO_ROOT / "data" / "questions_test.jsonl") if q["qid"] in qids}
    answers = load_answers(args.run_id, qids)
    scores = per_question(answers, questions)
    common = sorted(set.intersection(*[set(r) for r in scores.values()])) if scores else []
    res = summarize(scores, common)
    res["n_by_system"] = {n: len(r) for n, r in scores.items()}
    out = REPO_ROOT / "results" / "summary"
    (out / "extension.json").write_text(json.dumps({**res, "per_question": scores}, indent=1, default=str), encoding="utf-8")
    (out / "extension.md").write_text(report(res), encoding="utf-8")
    print(report(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
