"""P12: regenerate every analysis table and figure from the stored answers, with one command.

Reads results/<run>/<system>/*.json, the judgements, the traces and (if gate G3 is
done) results/<run>/human/{consensus.jsonl, agreement.json}. Writes
results/analysis/<run>_<split>/:

  report.md          everything below, in one file (tables carry the numbers of every figure)
  analysis.json      the same numbers, machine-readable
  fig_comparisons.png  ours minus each system, with 95% CIs (primary metric and correctness)
  fig_categories.png   correctness and causal support per question category
  fig_risk_coverage.png  coverage against risk (confident-error share) per system

Sections: the pre-registered verdicts for H1-H3 (thresholds from PREREGISTRATION.md), the kappa
rule, per-category and per-library results, RQ2 (mutation rules against fix lines and human
labels), a failure taxonomy, discordant cases, tool use, and the ablation predictions against
what was observed. Every number comes from code over stored files; nothing is typed in.

Usage: python -m analysis.make_all --run-id main --split test
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from core.config import REPO_ROOT, load_config
from core.jsonl import read_jsonl

ORDER = ["ours", "b0", "b1", "b2", "b2plus", "b3", "a1", "a2", "a3", "a4", "a5", "a7", "a8", "a10none", "a10oracle", "a11"]
# Fixed colour per system (validated categorical palette, light mode): colour follows the system, never its rank.
COLOURS = {"ours": "#2a78d6", "b1": "#eb6834", "b2": "#1baf7a", "a1": "#eda100", "a2": "#e87ba4", "a3": "#008300",
           "b0": "#6250d6", "b3": "#e34948"}
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"
H1_MIN, H2_REL, H2_COVERAGE, H3_MIN = 0.08, 0.40, 0.10, 0.15
CATEGORIES = ("doc_related", "spread_across_files", "single_location")


# ----------------------------------------------------------------------------- loading
def load(run_id: str, split: str, cfg: dict[str, Any]) -> dict[str, Any]:
    from eval.report import common_questions, load_scores, restrict
    root = REPO_ROOT / cfg["paths"]["results_dir"] / run_id
    questions = {q["qid"]: q for q in read_jsonl(REPO_ROOT / "data" / f"questions_{split}.jsonl")}
    all_scores = load_scores(root, questions)
    common, _ = common_questions(all_scores)
    excluded = spot_check_exclusions(REPO_ROOT / "data" / "dropped.jsonl")
    common = [q for q in common if q not in excluded]
    scores = {s: {r["qid"]: r for r in restrict(rows, common, common)} for s, rows in all_scores.items()}
    answers = {s: {qid: json.loads((root / s / f"{qid}.json").read_text(encoding="utf-8")) for qid in common}
               for s in scores}
    judgements = {}
    for s in scores:
        jd = root / "judgements" / s
        judgements[s] = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in jd.glob("*.json")} if jd.exists() else {}
    human = root / "human"
    consensus = read_jsonl(human / "consensus.jsonl") if (human / "consensus.jsonl").exists() else []
    agreement = json.loads((human / "agreement.json").read_text()) if (human / "agreement.json").exists() else None
    trace = REPO_ROOT / cfg["paths"]["traces_dir"] / f"{run_id}_ours.jsonl"
    checks = [e for e in read_jsonl(trace) if e.get("event") == "mutation_check"] if trace.exists() else []
    return {"questions": questions, "common": common, "scores": scores, "answers": answers, "judgements": judgements,
            "consensus": consensus, "agreement": agreement, "mutation_checks": checks,
            "excluded": sorted(q for q in excluded if q in questions)}


def spot_check_exclusions(dropped_path: Path) -> set[str]:
    """Questions the team marked invalid at G1 (stage `spot_check` in data/dropped.jsonl).

    The test set was locked before G1 was applied, so these are excluded here, from every system's results, instead
    of rebuilding the split (PREREGISTRATION.md)."""
    if not dropped_path.exists():
        return set()
    return {d["qid"] for d in read_jsonl(dropped_path) if d.get("stage") == "spot_check" and d.get("qid")}


def systems_in(data: dict[str, Any]) -> list[str]:
    return [s for s in ORDER if s in data["scores"]] + sorted(s for s in data["scores"] if s not in ORDER)


# ----------------------------------------------------------------------------- statistics helpers
def paired(a: dict[str, dict], b: dict[str, dict], key: str, qids: list[str], cfg: dict[str, Any]) -> dict[str, Any] | None:
    from eval.stats import mcnemar_exact, paired_bootstrap
    qs = [q for q in qids if a[q]["judged"] and b[q]["judged"]]
    if not qs:
        return None
    x, y = [bool(a[q][key]) for q in qs], [bool(b[q][key]) for q in qs]
    return {"n": len(qs), "a_rate": sum(x) / len(qs), "b_rate": sum(y) / len(qs), **mcnemar_exact(x, y),
            **paired_bootstrap(x, y, resamples=cfg["eval"]["bootstrap_resamples"], seed=cfg["eval"]["bootstrap_seed"])}


def verdict_h1(c: dict[str, Any] | None) -> str:
    if not c:
        return "not tested (no paired judged answers)"
    if c["ci_low"] <= 0 <= c["ci_high"]:
        return "inconclusive (95% CI includes zero)"
    if c["ci_high"] < 0:
        return "not supported (the baseline is better; CI below zero)"
    return "supported" if c["diff"] >= H1_MIN else f"not supported (gain {100 * c['diff']:.1f} points, below the {100 * H1_MIN:.0f}-point threshold)"


def cluster_precision(cites: dict[str, list[bool]], qids: list[str], cfg: dict[str, Any]) -> tuple[float | None, list[float]]:
    """Pooled share of causal citations, and its bootstrap replicates over questions (cluster bootstrap)."""
    rng = np.random.default_rng(cfg["eval"]["bootstrap_seed"])
    def pooled(sample: list[str]) -> float | None:
        flat = [c for q in sample for c in cites.get(q, [])]
        return sum(flat) / len(flat) if flat else None
    point = pooled(qids)
    reps = []
    if qids:
        for _ in range(cfg["eval"]["bootstrap_resamples"]):
            reps.append(rng.integers(0, len(qids), len(qids)))
    return point, reps


def precision_diff(a: dict[str, list[bool]], b: dict[str, list[bool]], qids: list[str], cfg: dict[str, Any]) -> dict[str, Any] | None:
    """Difference in pooled causal-citation precision (a - b), paired by question, with a cluster-bootstrap 95% CI."""
    qs = [q for q in qids if a.get(q) or b.get(q)]
    if not qs:
        return None
    pa, idx = cluster_precision(a, qs, cfg)
    pb, _ = cluster_precision(b, qs, cfg)
    if pa is None or pb is None:
        return None
    diffs = []
    for ix in idx:
        sample = [qs[i] for i in ix]
        fa = [c for q in sample for c in a.get(q, [])]
        fb = [c for q in sample for c in b.get(q, [])]
        if fa and fb:
            diffs.append(sum(fa) / len(fa) - sum(fb) / len(fb))
    lo, hi = (float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))) if diffs else (float("nan"), float("nan"))
    return {"n_questions": len(qs), "a_precision": pa, "b_precision": pb, "diff": pa - pb, "ci_low": lo, "ci_high": hi,
            "a_citations": sum(len(a.get(q, [])) for q in qs), "b_citations": sum(len(b.get(q, [])) for q in qs)}


# ----------------------------------------------------------------------------- sections
def human_view(data: dict[str, Any]) -> dict[str, Any] | None:
    """If G3 is done: scores recomputed with the human consensus labels on the labelled questions (kappa rule)."""
    if not data["consensus"] or not data["agreement"]:
        return None
    from eval.metrics import in_gold
    use = {k: v["use_human_labels"] for k, v in data["agreement"]["kappa"].items()}
    by = defaultdict(dict)
    for row in data["consensus"]:
        by[row["system"]][row["qid"]] = row
    out: dict[str, dict[str, dict]] = {}
    for s, rows in by.items():
        out[s] = {}
        for qid, row in rows.items():
            q, ans = data["questions"][qid], data["answers"].get(s, {}).get(qid)
            if ans is None:
                continue
            labels = iter(row["citations"])
            per_claim = []
            for claim in ans.get("claims", []):
                flags = []
                for c in claim.get("citations", []):
                    human_causal = next(labels, None) == "causal"  # always consume, to stay aligned
                    flags.append(in_gold(c["path"], c["line"], q["gold_evidence"]) or human_causal)
                per_claim.append(flags)
            correct = row["correctness"] == "correct"
            covered = not ans.get("flagged_uncertain") and not ans.get("abstained")
            out[s][qid] = {"judged": True, "correct": correct, "causally_supported": correct and bool(per_claim) and all(any(r) for r in per_claim),
                           "confident_error": (not correct) and covered, "covered": covered}
    return {"use_human_labels": use, "scores": out, "qids": sorted({r["qid"] for r in data["consensus"]})}


def hypotheses(data: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    sc, qids = data["scores"], data["common"]
    out: dict[str, Any] = {}
    if "ours" in sc and "b2" in sc:
        h1 = paired(sc["ours"], sc["b2"], "causally_supported", qids, cfg)
        out["H1"] = {"comparison": h1, "verdict": verdict_h1(h1),
                     "decomposition_correctness": paired(sc["ours"], sc["b2"], "correct", qids, cfg)}
        if "b2plus" in sc:
            c = paired(sc["ours"], sc["b2plus"], "causally_supported", qids, cfg)
            out["H1_vs_b2plus"] = {"comparison": c, "verdict": verdict_h1(c)}
        judged = [q for q in qids if sc["ours"][q]["judged"] and sc["b2"][q]["judged"]]
        ce_o = sum(sc["ours"][q]["confident_error"] for q in judged) / len(judged) if judged else None
        ce_b = sum(sc["b2"][q]["confident_error"] for q in judged) / len(judged) if judged else None
        cov_o = sum(sc["ours"][q]["covered"] for q in qids) / len(qids) if qids else None
        cov_b = sum(sc["b2"][q]["covered"] for q in qids) / len(qids) if qids else None
        c = paired(sc["ours"], sc["b2"], "confident_error", qids, cfg)
        rel = (1 - ce_o / ce_b) if ce_b else None
        if c is None or rel is None:
            v = "not tested"
        elif c["ci_low"] <= 0 <= c["ci_high"]:
            v = "inconclusive (95% CI of the difference includes zero)"
        elif rel >= H2_REL and (cov_b - cov_o) <= H2_COVERAGE and c["diff"] < 0:
            v = "supported"
        else:
            v = "not supported"
        out["H2"] = {"confident_error_ours": ce_o, "confident_error_b2": ce_b, "relative_reduction": rel,
                     "coverage_ours": cov_o, "coverage_b2": cov_b, "comparison": c, "verdict": v}
    if "ours" in sc and "a2" in sc:
        # Human-judged precision needs G3 labels; until then the judge's labels (plus fix-line membership) stand in.
        h = human_view(data)
        if h and "ours" in h["scores"] and "a2" in h["scores"]:
            source, cites = "human consensus labels", {}
            for s in ("ours", "a2"):
                cites[s] = {}
                for row in data["consensus"]:
                    if row["system"] == s:
                        cites[s][row["qid"]] = [lab == "causal" for lab in row["citations"]]
            pool = h["qids"]
        else:
            source, cites, pool = "judge labels (provisional until G3)", {}, qids
            for s in ("ours", "a2"):
                cites[s] = {q: [lab == "causal" for lab in data["judgements"].get(s, {}).get(q, {}).get("citations", [])]
                            for q in qids}
        d = precision_diff(cites["ours"], cites["a2"], pool, cfg)
        if d is None:
            v = "not tested"
        elif d["ci_low"] <= 0 <= d["ci_high"]:
            v = "inconclusive (95% CI includes zero)"
        else:
            v = "supported" if d["diff"] >= H3_MIN and d["ci_low"] > 0 else "not supported"
        out["H3"] = {"label_source": source, "comparison": d, "verdict": v}
    return out


def by_group(data: dict[str, Any], field: str) -> dict[str, dict[str, dict[str, Any]]]:
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for s in systems_in(data):
        out[s] = {}
        groups = defaultdict(list)
        for q in data["common"]:
            groups[data["questions"][q][field]].append(data["scores"][s][q])
        for g, rows in sorted(groups.items()):
            judged = [r for r in rows if r["judged"]]
            out[s][g] = {"n": len(rows), "n_judged": len(judged),
                         "correctness": sum(r["correct"] for r in judged) / len(judged) if judged else None,
                         "causally_supported": sum(r["causally_supported"] for r in judged) / len(judged) if judged else None,
                         "confident_errors": sum(r["confident_error"] for r in judged)}
    return out


def rq2(data: dict[str, Any]) -> dict[str, Any]:
    """Each mutation acceptance rule against fix-line membership, and against human labels when they exist."""
    from eval.kappa import cohens_kappa
    from eval.metrics import in_gold
    rows = []
    for e in data["mutation_checks"]:
        q = data["questions"].get(e.get("qid"))
        if q is None or e.get("qid") not in data["common"] or len(e.get("locs", [])) != 1:
            continue
        path, line = e["locs"][0].rsplit(":", 1)
        rows.append({"qid": e["qid"], "path": path, "line": int(line), "untestable": bool(e.get("untestable")),
                     "verdicts": e.get("verdicts") or {}, "in_gold": in_gold(path, int(line), q["gold_evidence"])})
    testable = [r for r in rows if not r["untestable"] and r["verdicts"]]
    out: dict[str, Any] = {"checks": len(rows), "untestable": sum(r["untestable"] for r in rows),
                           "untestable_in_gold": sum(r["untestable"] and r["in_gold"] for r in rows), "rules": {}}
    gold = [r["in_gold"] for r in testable]
    for rule in ("any_flip", "behavioural", "specific"):
        pred = [bool(r["verdicts"].get(rule)) for r in testable]
        tp = sum(p and g for p, g in zip(pred, gold))
        out["rules"][rule] = {"n": len(testable), "accepted": sum(pred), "accepted_in_gold": tp,
                              "precision_vs_fix_lines": tp / sum(pred) if sum(pred) else None,
                              "recall_vs_fix_lines": tp / sum(gold) if sum(gold) else None,
                              "kappa_vs_fix_lines": round(cohens_kappa(pred, gold), 3) if testable and len(set(pred + gold)) > 1 else None}
    # Answers cite from the repository root (`src/click/core.py`); mutation checks record the path from the source
    # root (`click/core.py`). Compare without the `src/` prefix, as eval.metrics.path_matches does.
    def key(qid: str, path: str, line: int) -> tuple[str, str, int]:
        return qid, path.lstrip("./").removeprefix("src/"), int(line)
    human = {key(r["qid"], c["path"], c["line"]): lab == "causal" for r in data["consensus"] if r["system"] == "ours"
             for c, lab in zip([c for cl in data["answers"]["ours"].get(r["qid"], {}).get("claims", []) for c in cl.get("citations", [])],
                               r["citations"])}
    matched = [(r, human[key(r["qid"], r["path"], r["line"])]) for r in testable if key(r["qid"], r["path"], r["line"]) in human]
    if matched:
        out["human"] = {}
        for rule in ("any_flip", "behavioural", "specific"):
            pred = [bool(r["verdicts"].get(rule)) for r, _ in matched]
            lab = [h for _, h in matched]
            out["human"][rule] = {"n": len(matched), "agreement": sum(p == h for p, h in zip(pred, lab)) / len(matched),
                                  "kappa": round(cohens_kappa(pred, lab), 3) if len(set(pred + lab)) > 1 else None}
    return out


def taxonomy(data: dict[str, Any]) -> dict[str, dict[str, int]]:
    """Deterministic failure classes from the judge label and fix-line hits; no hand coding."""
    out = {}
    for s in systems_in(data):
        t = defaultdict(int)
        for q in data["common"]:
            r, a = data["scores"][s][q], data["answers"][s][q]
            if a.get("abstained"):
                t["abstained"] += 1
            elif not r["judged"]:
                t["not judged"] += 1
            elif r["correct"]:
                t["correct, causally supported" if r["causally_supported"] else "correct, not causally supported"] += 1
            elif r["partial"] and not r["fix_location_hit"]:
                t["right behaviour, wrong place"] += 1
            elif r["fix_location_hit"]:
                t["right place, wrong or partial behaviour"] += 1
            else:
                t["wrong behaviour and wrong place"] += 1
        out[s] = dict(t)
    return out


def cases(data: dict[str, Any], other: str = "b2", limit: int = 10) -> list[dict[str, Any]]:
    """Questions where exactly one of ours and the baseline is correct, with short excerpts."""
    if "ours" not in data["scores"] or other not in data["scores"]:
        return []
    out = []
    for q in data["common"]:
        a, b = data["scores"]["ours"][q], data["scores"][other][q]
        if a["judged"] and b["judged"] and a["correct"] != b["correct"]:
            out.append({"qid": q, "winner": "ours" if a["correct"] else other,
                        "title": data["questions"][q]["question_text"].splitlines()[0][:120],
                        "ours_label": a["label"], f"{other}_label": b["label"],
                        "ours_reason": data["judgements"]["ours"].get(q, {}).get("reason", "")[:300],
                        f"{other}_reason": data["judgements"][other].get(q, {}).get("reason", "")[:300]})
    return out[:limit]


def _trace_events(path: Path, qids: set[str]) -> list[dict[str, Any]]:
    """Tool-call and unsafe-attempt events from one system's trace, for the questions analysed.

    A question interrupted by a quota stop is run again on resume, and its replayed tool calls are traced again, so
    identical events (same question, tool, arguments, result or violations) are counted once."""
    seen, out = set(), []
    for e in read_jsonl(path) if path.exists() else []:
        if e.get("event") not in ("tool_call", "unsafe_attempt") or e.get("qid") not in qids:
            continue
        key = json.dumps([e.get("event"), e.get("qid"), e.get("tool"), e.get("args"), str(e.get("result", ""))[:500],
                          e.get("violations")], sort_keys=True, default=str)
        if key not in seen:
            seen.add(key)
            out.append(e)
    return out


def probe_outcome(result: str) -> str:
    """Classify a run_probe result text: pass / fail (assertion) / error (any other exception) / blocked / budget."""
    if result.startswith("BLOCKED"):
        return "blocked"
    if result.startswith("Probe budget"):
        return "budget"
    for word, label in (("PASS", "pass"), ("FAIL", "fail"), ("ERROR", "error")):
        if result.startswith(f"claim: test_claim {word}"):
            return label
    return "other"


def _violations(e: dict[str, Any]) -> list[dict[str, Any]]:
    v = e.get("violations") or []
    if isinstance(v, str):  # older traces stored the list's repr
        import ast
        try:
            v = ast.literal_eval(v)
        except (ValueError, SyntaxError):
            return []
    return [x for x in v if isinstance(x, dict)]


def tool_use(data: dict[str, Any], traces_dir: Path, run_id: str) -> dict[str, dict[str, Any]]:
    """Tool-call accuracy and safety per system (brief §7: tool-call accuracy and an unsafe-action rate).

    Counts come from the answer files (`tool_calls`, `unsafe_attempts`); probe outcomes and the policy rules that
    blocked probes come from the traces. A blocked probe is *not* an unsafe action: the AST policy refused it before
    anything ran, and the sandbox has no network in any case. Unsafe actions executed is therefore 0 by construction,
    and the rate reported is of *attempts*."""
    qids = set(data["common"])
    out = {}
    for s in systems_in(data):
        answers = [data["answers"][s][q] for q in data["common"]]
        tc = [a.get("tool_calls", {}) for a in answers]
        total, invalid = sum(t.get("total", 0) for t in tc), sum(t.get("invalid", 0) for t in tc)
        errors, recovered = sum(t.get("errors", 0) for t in tc), sum(t.get("recovered", 0) for t in tc)
        events = _trace_events(traces_dir / f"{run_id}_{s}.jsonl", qids)
        outcomes = Counter(probe_outcome(str(e.get("result", ""))) for e in events
                           if e.get("event") == "tool_call" and e.get("tool") == "run_probe")
        rules = Counter(v.get("rule", "?") for e in events if e.get("event") == "unsafe_attempt"
                        for v in {(x.get("probe"), x.get("rule")): x for x in _violations(e)}.values())
        ran = outcomes["pass"] + outcomes["fail"] + outcomes["error"]
        submitted = ran + outcomes["blocked"]
        unsafe = sum(a.get("unsafe_attempts", 0) for a in answers)
        out[s] = {"tool_calls": total, "invalid": invalid, "valid_call_rate": (total - invalid) / total if total else None,
                  "errors": errors, "recovered": recovered, "recovery_rate": recovered / errors if errors else None,
                  "probe_outcomes": dict(outcomes), "probes_submitted": submitted,
                  "probe_verdict_rate": (outcomes["pass"] + outcomes["fail"]) / ran if ran else None,
                  "unsafe_attempts": unsafe, "questions_with_unsafe": sum(1 for a in answers if a.get("unsafe_attempts", 0)),
                  "unsafe_attempt_rate": outcomes["blocked"] / submitted if submitted else None,
                  "blocked_rules": dict(rules), "unsafe_executed": 0}
    return out


def ablations(data: dict[str, Any], groups: dict[str, Any]) -> list[dict[str, str]]:
    from eval.metrics import summarize
    summ = {s: summarize(list(rows.values())) for s, rows in data["scores"].items()}
    rows = []
    def have(*s: str) -> bool:
        return all(x in summ for x in s)
    def pct(x: float | None) -> str:
        return "n/a" if x is None else f"{100 * x:.1f}%"
    if have("ours", "a1"):
        o = groups["ours"].get("doc_related", {}).get("confident_errors")
        a = groups["a1"].get("doc_related", {}).get("confident_errors")
        rows.append({"id": "A1", "prediction": "More confident errors on doc-related questions",
                     "observed": f"doc-related confident errors: A1 {a}, ours {o}",
                     "as_predicted": "yes" if a is not None and o is not None and a > o else "no"})
    if have("ours", "a2"):
        rows.append({"id": "A2", "prediction": "Similar correctness; clearly lower causal citation precision",
                     "observed": f"correctness A2 {pct(summ['a2']['correctness'])}, ours {pct(summ['ours']['correctness'])}; "
                                 f"precision vs fix lines (lower bound) A2 {pct(summ['a2']['precision_vs_gold_lower_bound'])}, "
                                 f"ours {pct(summ['ours']['precision_vs_gold_lower_bound'])}",
                     "as_predicted": "see H3"})
    if have("ours", "a3", "b2"):
        ok = (summ["a3"]["confident_error_rate"] or 0) < (summ["b2"]["confident_error_rate"] or 0) and \
             (summ["a3"]["correctness"] or 0) < (summ["ours"]["correctness"] or 0)
        rows.append({"id": "A3", "prediction": "Fewer confident errors than B2, lower correctness than ours",
                     "observed": f"confident errors A3 {pct(summ['a3']['confident_error_rate'])}, B2 {pct(summ['b2']['confident_error_rate'])}; "
                                 f"correctness A3 {pct(summ['a3']['correctness'])}, ours {pct(summ['ours']['correctness'])}",
                     "as_predicted": "yes" if ok else "no"})
    for aid in ("A4", "A5", "A6", "A7", "A8", "A9", "A10", "A11"):
        if not any(s.startswith(aid.lower()) for s in summ):
            rows.append({"id": aid, "prediction": "(see PREREGISTRATION.md)", "observed": "not run", "as_predicted": "n/a"})
    return rows


# ----------------------------------------------------------------------------- figures
def _style(ax: Any) -> None:
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def figures(data: dict[str, Any], hyp: dict[str, Any], groups: dict[str, Any], out: Path, cfg: dict[str, Any]) -> list[str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    made = []
    systems = systems_in(data)
    others = [s for s in systems if s != "ours"]
    if "ours" in data["scores"] and others:
        rows = []
        for o in others:
            for key, name in (("causally_supported", "causally supported"), ("correct", "correct")):
                c = paired(data["scores"]["ours"], data["scores"][o], key, data["common"], cfg)
                if c:
                    rows.append((f"ours − {o}: {name}", c))
        if rows:
            fig, ax = plt.subplots(figsize=(7.5, 0.42 * len(rows) + 1.2), dpi=150)
            ys = list(range(len(rows)))[::-1]
            for y, (label, c) in zip(ys, rows):
                ax.plot([100 * c["ci_low"], 100 * c["ci_high"]], [y, y], color=COLOURS["ours"], linewidth=2, solid_capstyle="round")
                ax.plot(100 * c["diff"], y, "o", color=COLOURS["ours"], markersize=7, markeredgecolor="white", markeredgewidth=2)
                ax.text(100 * c["ci_high"] + 1.5, y, f"{100 * c['diff']:+.1f}", va="center", fontsize=8, color=INK)
            ax.axvline(0, color=MUTED, linewidth=1)
            ax.axvline(100 * H1_MIN, color=MUTED, linewidth=1, linestyle=(0, (3, 3)))
            ax.set_yticks(ys, [r[0] for r in rows], fontsize=9, color=INK)
            ax.set_xlabel("difference in percentage points (95% paired bootstrap CI); dashed: H1 threshold", fontsize=9, color=MUTED)
            ax.set_title("Ours against each system, same questions", fontsize=11, color=INK, loc="left")
            _style(ax)
            fig.tight_layout()
            fig.savefig(out / "fig_comparisons.png")
            plt.close(fig)
            made.append("fig_comparisons.png")
    cats = [c for c in CATEGORIES if any(c in groups[s] for s in systems)]
    if cats:
        fig, axes = plt.subplots(1, 2, figsize=(9, 3.6), dpi=150, sharey=True)
        width = 0.8 / max(1, len(systems))
        for ax, key, title in zip(axes, ("correctness", "causally_supported"), ("Correct", "Causally supported")):
            for i, s in enumerate(systems):
                vals = [100 * (groups[s].get(c, {}).get(key) or 0) for c in cats]
                xs = [j + (i - (len(systems) - 1) / 2) * width for j in range(len(cats))]
                ax.bar(xs, vals, width * 0.92, color=COLOURS.get(s, MUTED), label=s, linewidth=0)
            n_cat = {c: sum(data["questions"][q]["category"] == c for q in data["common"]) for c in cats}
            ax.set_xticks(range(len(cats)), [f"{c.replace('_', ' ')}\n(n={n_cat[c]})" for c in cats], fontsize=8, color=INK)
            ax.set_title(title, fontsize=10, color=INK, loc="left")
            ax.set_ylim(0, 100)
            ax.grid(axis="y", color=GRID, linewidth=0.8)
            ax.set_axisbelow(True)
            for side in ("top", "right"):
                ax.spines[side].set_visible(False)
            ax.tick_params(colors=MUTED, labelsize=8)
        axes[0].set_ylabel("% of judged answers", fontsize=9, color=MUTED)
        axes[1].legend(frameon=False, fontsize=8, loc="upper right")
        fig.tight_layout()
        fig.savefig(out / "fig_categories.png")
        plt.close(fig)
        made.append("fig_categories.png")
    pts = []
    for s in systems:
        rows = [r for r in data["scores"][s].values()]
        judged = [r for r in rows if r["judged"]]
        if judged:
            covered = [r for r in judged if r["covered"]]
            risk = sum(not r["correct"] for r in covered) / len(covered) if covered else 0.0
            pts.append((s, 100 * len(covered) / len(judged), 100 * risk))
    if pts:
        fig, ax = plt.subplots(figsize=(5.5, 4), dpi=150)
        spots: dict[tuple[float, float], list[str]] = defaultdict(list)
        for s, cov, risk in pts:
            ax.plot(cov, risk, "o", color=COLOURS.get(s, MUTED), markersize=9, markeredgecolor="white", markeredgewidth=2)
            spots[(round(cov, 1), round(risk, 1))].append(s)
        for (cov, risk), names in spots.items():  # systems on the same point share one label, so labels never collide
            ax.annotate(", ".join(names), (cov, risk), textcoords="offset points", xytext=(7, 4), fontsize=9, color=INK)
        ax.set_xlabel("coverage: % of answers neither flagged nor abstained", fontsize=9, color=MUTED)
        ax.set_ylabel("risk: % wrong among covered answers", fontsize=9, color=MUTED)
        ax.set_xlim(0, 105)
        ax.set_ylim(0, 105)
        ax.set_title("Risk against coverage (lower right is better)", fontsize=10, color=INK, loc="left")
        _style(ax)
        ax.grid(axis="y", color=GRID, linewidth=0.8)
        fig.tight_layout()
        fig.savefig(out / "fig_risk_coverage.png")
        plt.close(fig)
        made.append("fig_risk_coverage.png")
    return made


# ----------------------------------------------------------------------------- report
def pct(x: float | None) -> str:
    return "n/a" if x is None else f"{100 * x:.1f}%"


def pts(x: float | None) -> str:
    return "n/a" if x is None or x != x else f"{100 * x:+.1f}"


def comparison_line(c: dict[str, Any] | None) -> str:
    if not c:
        return "n/a"
    return (f"{pct(c['a_rate'])} vs {pct(c['b_rate'])}, difference {pts(c['diff'])} points, 95% CI [{pts(c['ci_low'])}, "
            f"{pts(c['ci_high'])}], McNemar p = {c['p_value']:.3f} ({c['only_a']} vs {c['only_b']} discordant), n = {c['n']}")


def report(data: dict[str, Any], res: dict[str, Any], figs: list[str], run_id: str, split: str) -> str:
    from eval.metrics import summarize
    from eval.report import markdown_table
    L = [f"# Analysis: run `{run_id}`, split `{split}`", "",
         f"Generated by `analysis/make_all.py`. Questions every system completed: {len(data['common'])}. "
         f"Systems: {', '.join(systems_in(data))}.", ""]
    excluded = data.get("excluded", [])
    L += [f"Spot check (G1): {len(excluded)} question(s) marked invalid are excluded from every system"
          + (f": {', '.join(f'`{q}`' for q in excluded)}." if excluded else " (no verdicts applied yet)."), ""]
    if data["agreement"]:
        L += ["Human labels (G3) are present; the kappa rule decides which labels the primary comparison uses (below).", ""]
    else:
        L += ["**No human labels yet (G3 pending): every judge-based number is provisional.**", ""]
    L += ["## Summary", "", markdown_table(res.get("summary") or {s: summarize(list(r.values())) for s, r in data["scores"].items()}), ""]
    h = res["hypotheses"]
    L += ["## Pre-registered hypotheses", ""]
    if "H1" in h:
        L += [f"- **H1** (ours vs B2, causally-supported answer rate, threshold +{100 * H1_MIN:.0f} points): **{h['H1']['verdict']}**.",
              f"  {comparison_line(h['H1']['comparison'])}.",
              f"  Decomposition, correctness alone: {comparison_line(h['H1']['decomposition_correctness'])}."]
        if "H1_vs_b2plus" in h:
            L += [f"  Against the budget-matched B2+: **{h['H1_vs_b2plus']['verdict']}**; {comparison_line(h['H1_vs_b2plus']['comparison'])}."]
    if "H2" in h:
        x = h["H2"]
        L += [f"- **H2** (confident-error rate at least {100 * H2_REL:.0f}% lower than B2's, coverage no more than "
              f"{100 * H2_COVERAGE:.0f} points lower): **{x['verdict']}**. Confident errors: ours {pct(x['confident_error_ours'])}, "
              f"B2 {pct(x['confident_error_b2'])} (relative reduction {pct(x['relative_reduction'])}); coverage ours "
              f"{pct(x['coverage_ours'])}, B2 {pct(x['coverage_b2'])}. Paired: {comparison_line(x['comparison'])}."]
    if "H3" in h:
        d = h["H3"]["comparison"]
        line = "n/a" if not d else (f"ours {pct(d['a_precision'])} ({d['a_citations']} citations), A2 {pct(d['b_precision'])} "
                                    f"({d['b_citations']}), difference {pts(d['diff'])} points, 95% cluster-bootstrap CI "
                                    f"[{pts(d['ci_low'])}, {pts(d['ci_high'])}] over {d['n_questions']} questions")
        L += [f"- **H3** (causal citation precision, ours vs A2, threshold +{100 * H3_MIN:.0f} points; source: "
              f"{h['H3']['label_source']}): **{h['H3']['verdict']}**. {line}."]
    if not h:
        L += ["- Not testable on this run (needs ours with B2, and A2)."]
    L += ["", "Below about 120 questions H1 is under-powered (stated in advance); a CI that includes zero is inconclusive, "
          "not negative.", ""]
    if res.get("human"):
        hv = res["human"]
        L += ["## Kappa rule", "", f"Uses human labels for: {', '.join(k for k, v in hv['use_human_labels'].items() if v) or 'nothing'} "
              f"(see results/<run>/human/agreement.md). On the {len(hv['qids'])} labelled questions:", ""]
        for s in ("ours", "b2"):
            if s in hv["scores"]:
                rows = list(hv["scores"][s].values())
                L.append(f"- {s}: correct {pct(sum(r['correct'] for r in rows) / len(rows))}, causally supported "
                         f"{pct(sum(r['causally_supported'] for r in rows) / len(rows))} (n = {len(rows)})")
        L.append("")
    L += ["## Comparisons (ours minus each system)", "", "| Comparison | Metric | Detail |", "|---|---|---|"]
    for k, c in res["comparisons"].items():
        other, key = k.split(":")
        L.append(f"| ours − {other} | {key} | {comparison_line(c)} |")
    for name, field in (("category", "per_category"), ("library", "per_library")):
        g = res[field]
        groups = sorted({x for s in g for x in g[s]})
        L += ["", f"## Per {name}", "", "| System | " + " | ".join(f"{x} correct | {x} causal" for x in groups) + " |",
              "|---|" + "---|---|" * len(groups)]
        for s in g:
            cells = []
            for x in groups:
                v = g[s].get(x)
                cells += [f"{pct(v['correctness'])} (n={v['n_judged']})", pct(v["causally_supported"])] if v else ["-", "-"]
            L.append(f"| {s} | " + " | ".join(cells) + " |")
    r = res["rq2"]
    L += ["", "## RQ2: the mutation check as a measurement", "",
          f"Mutation checks by our agent on these questions: {r['checks']}; untestable (no operator applies): "
          f"{r['untestable']}, of which {r['untestable_in_gold']} are fix lines. Against fix-line membership "
          "(an independent, developer-made reference; precision is a lower bound because other causal lines exist):", "",
          "| Rule | n | accepted | accepted fix lines | precision | recall | kappa |", "|---|---|---|---|---|---|---|"]
    for rule, v in r["rules"].items():
        L.append(f"| {rule} | {v['n']} | {v['accepted']} | {v['accepted_in_gold']} | {pct(v['precision_vs_fix_lines'])} | "
                 f"{pct(v['recall_vs_fix_lines'])} | {v['kappa_vs_fix_lines'] if v['kappa_vs_fix_lines'] is not None else 'n/a'} |")
    if r.get("human"):
        L += ["", "Against human citation labels (causal vs not):", "", "| Rule | n | agreement | kappa |", "|---|---|---|---|"]
        for rule, v in r["human"].items():
            L.append(f"| {rule} | {v['n']} | {pct(v['agreement'])} | {v['kappa'] if v['kappa'] is not None else 'n/a'} |")
    else:
        L += ["", "Against human labels: pending G3."]
    tax = res["taxonomy"]
    classes = sorted({c for s in tax for c in tax[s]})
    L += ["", "## Failure taxonomy (from judge labels and fix-line hits)", "",
          "| System | " + " | ".join(classes) + " |", "|---|" + "---|" * len(classes)]
    for s, t in tax.items():
        L.append(f"| {s} | " + " | ".join(str(t.get(c, 0)) for c in classes) + " |")
    L += ["", "## Tool use and safety", "",
          "Counts from the answer files; probe outcomes and blocking rules from the traces (replays de-duplicated). "
          "A blocked probe never ran: the AST policy refused it, and the sandbox has no network, so unsafe actions "
          "*executed* is 0 for every system. The unsafe rate below is of *attempts* among submitted probes.", "",
          "| System | Tool calls | Valid-call rate | Errors | Recovered | Probes submitted | Pass / fail / error / blocked | "
          "Probe verdict rate | Unsafe attempts (questions) | Unsafe-attempt rate | Unsafe executed |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for s, t in res["tool_use"].items():
        o = t["probe_outcomes"]
        L.append(f"| {s} | {t['tool_calls']} | {pct(t['valid_call_rate'])} | {t['errors']} | {t['recovered']} | "
                 f"{t['probes_submitted']} | {o.get('pass', 0)} / {o.get('fail', 0)} / {o.get('error', 0)} / {o.get('blocked', 0)} | "
                 f"{pct(t['probe_verdict_rate'])} | {t['unsafe_attempts']} ({t['questions_with_unsafe']}) | "
                 f"{pct(t['unsafe_attempt_rate'])} | {t['unsafe_executed']} |")
    rules = sorted({r for t in res["tool_use"].values() for r in t["blocked_rules"]})
    if rules:
        L += ["", "Why probes were blocked (policy rule; one count per rule per probe):", "",
              "| System | " + " | ".join(rules) + " |", "|---|" + "---|" * len(rules)]
        for s, t in res["tool_use"].items():
            L.append(f"| {s} | " + " | ".join(str(t["blocked_rules"].get(r, 0)) for r in rules) + " |")
    L += ["", "Probe verdict rate: the share of probes that ran and reached pass or fail; an error means `test_claim` "
          "raised something other than an assertion (often a broken probe). B2 also hit its 12-run probe budget "
          "on some questions (not counted as submitted)."]
    L += ["", "## Discordant cases (ours vs B2)", ""]
    for c in res["cases"]:
        L.append(f"- `{c['qid']}` ({c['winner']} correct): {c['title']}. Ours: {c['ours_label']} ({c['ours_reason']}). "
                 f"B2: {c.get('b2_label')} ({c.get('b2_reason')}).")
    if not res["cases"]:
        L.append("None.")
    L += ["", "## Ablation predictions against outcomes", "", "| Ablation | Prediction | Observed | As predicted |", "|---|---|---|---|"]
    for a in res["ablations"]:
        L.append(f"| {a['id']} | {a['prediction']} | {a['observed']} | {a['as_predicted']} |")
    if figs:
        L += ["", "## Figures", ""] + [f"![{f}]({f})" for f in figs]
    return "\n".join(L) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--split", default="test")
    ap.add_argument("--no-figures", action="store_true")
    args = ap.parse_args(argv)
    cfg = load_config()
    data = load(args.run_id, args.split, cfg)
    if not data["common"]:
        print("No question was completed by every system in this run; nothing to analyse.", file=sys.stderr)
        return 1
    out = REPO_ROOT / "results" / "analysis" / f"{args.run_id}_{args.split}"
    out.mkdir(parents=True, exist_ok=True)
    from eval.metrics import summarize
    groups = by_group(data, "category")
    res = {"summary": {s: summarize(list(r.values())) for s, r in data["scores"].items()},
           "hypotheses": hypotheses(data, cfg), "human": human_view(data), "per_category": groups,
           "per_library": by_group(data, "library"), "rq2": rq2(data), "taxonomy": taxonomy(data), "cases": cases(data),
           "ablations": ablations(data, groups), "comparisons": {},
           "tool_use": tool_use(data, REPO_ROOT / cfg["paths"]["traces_dir"], args.run_id)}
    for o in [s for s in systems_in(data) if s != "ours"]:
        if "ours" in data["scores"]:
            for key in ("causally_supported", "correct", "confident_error", "fix_location_hit"):
                res["comparisons"][f"{o}:{key}"] = paired(data["scores"]["ours"], data["scores"][o], key, data["common"], cfg)
    figs = [] if args.no_figures else figures(data, res["hypotheses"], groups, out, cfg)
    (out / "analysis.json").write_text(json.dumps({**res, "questions": data["common"], "figures": figs}, indent=1, default=str),
                                       encoding="utf-8")
    text = report(data, res, figs, args.run_id, args.split)
    (out / "report.md").write_text(text, encoding="utf-8")
    print(f"wrote {out / 'report.md'} ({len(figs)} figures)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
