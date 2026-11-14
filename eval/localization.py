"""Localization and causal-verification metrics for the exploratory extension. Pure functions, no LLM.

Every system is scored on a ranked list of (path, line) locations:
- E1-E6: their deterministic `ranking` (accepted lines first, see multiagent/orchestrator.py);
- every other system (E0 = ours, B2, ...): its citations in the order the answer gives them, without repeats.

A location is a **line-level hit** if it falls inside a `gold_evidence` range (a line the developer's fix changed),
and a **function-level hit** if it sits in the same function as a gold line. Top-k: a hit among the first k.
MRR: 1 / rank of the first hit among the first 10 (0 if none). Precision: share of predicted locations that hit.
Recall: share of gold ranges (line level) or gold functions (function level) hit by some prediction. F1: their
harmonic mean. All of them are lower bounds on real quality, because a truly causal line outside the fix counts as
a miss (the same caveat as the main study's precision).
"""

from __future__ import annotations

from typing import Any, Callable

Loc = tuple[str, int]
FunctionOf = Callable[[str, int], Any]   # (path, line) -> a hashable function id, or None at module level


def ranked_locations(answer: dict[str, Any], limit: int = 10) -> list[Loc]:
    if answer.get("ranking") is not None:
        locs = [(r["path"], int(r["line"])) for r in answer["ranking"]]
    else:
        locs = [(c["path"], int(c["line"])) for cl in answer.get("claims", []) for c in cl.get("citations", [])]
    out: list[Loc] = []
    for loc in locs:
        if loc not in out:
            out.append(loc)
    return out[:limit]


def _norm(p: str) -> str:
    return p.lstrip("./").removeprefix("src/")


def range_index(path: str, line: int, gold: list[dict[str, Any]]) -> int | None:
    """Index of the gold range containing the line, or None."""
    for i, g in enumerate(gold):
        if _norm(path) == _norm(g["path"]) and g["line_start"] <= line <= g["line_end"]:
            return i
    return None


def gold_functions(gold: list[dict[str, Any]], function_of: FunctionOf) -> set[Any]:
    out = set()
    for g in gold:
        for ln in range(g["line_start"], g["line_end"] + 1):
            f = function_of(g["path"], ln)
            if f is not None:
                out.add(f)
    return out


def score_locations(locs: list[Loc], gold: list[dict[str, Any]], function_of: FunctionOf | None = None) -> dict[str, Any]:
    """Every per-question localization measure for one ranked list."""
    line_hits = [range_index(p, ln, gold) is not None for p, ln in locs]
    ranges_hit = {i for i in (range_index(p, ln, gold) for p, ln in locs) if i is not None}
    out: dict[str, Any] = {"n_predicted": len(locs), "n_gold_ranges": len(gold), "multi": len(gold) >= 2}
    out.update(_ranked("line", line_hits, len(ranges_hit), len(gold)))
    top5_ranges = {i for i in (range_index(p, ln, gold) for p, ln in locs[:5]) if i is not None}
    out["multi_found"] = len(top5_ranges) >= 2
    if function_of is not None:
        gf = gold_functions(gold, function_of)
        fns = [function_of(p, ln) for p, ln in locs]
        fn_hits = [h or (f is not None and f in gf) for h, f in zip(line_hits, fns)]
        found = {f for f in fns if f is not None and f in gf}
        out.update(_ranked("fn", fn_hits, len(found), len(gf) or len(gold)))
    return out


def _ranked(prefix: str, hits: list[bool], n_found: int, n_gold: int) -> dict[str, float]:
    first = next((i + 1 for i, h in enumerate(hits) if h), None)
    precision = sum(hits) / len(hits) if hits else 0.0
    recall = min(1.0, n_found / n_gold) if n_gold else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {f"{prefix}_top1": float(bool(hits[:1] and hits[0])), f"{prefix}_top3": float(any(hits[:3])),
            f"{prefix}_mrr": 1.0 / first if first and first <= 10 else 0.0,
            f"{prefix}_precision": precision, f"{prefix}_recall": recall, f"{prefix}_f1": f1}


def tested_lines(answer: dict[str, Any]) -> list[tuple[Loc, str]]:
    """(line, verdict) for every line the system mutation-checked, verdict in accepted / rejected / inconclusive.

    E1-E6 record three-way verdicts. The locked agent (E0) records causal True / False / None (untestable); its False
    also covers non-specific flips, which E1-E6 call inconclusive, so its rejection rate is not directly comparable.
    Baselines only record a verdict for the lines they cited and checked."""
    out: list[tuple[Loc, str]] = []
    if answer.get("architecture") == "multiagent":
        for e in (answer.get("experiments") or {}).get("experiments", []):
            if e["kind"] == "single":
                p, ln = e["locs"][0].rsplit(":", 1)
                out.append(((p, int(ln)), e["verdict"]))
        return out
    seen = set()
    for d in answer.get("decisions", []):
        if d.get("decision") in ("mutation_check", "proposed_citation") and d.get("loc"):
            p, ln = d["loc"].rsplit(":", 1)
            loc = (p, int(ln))
            if loc in seen:
                continue
            seen.add(loc)
            c = d.get("causal")
            out.append((loc, "accepted" if c is True else "rejected" if c is False else "inconclusive"))
    if not answer.get("decisions"):
        for cl in answer.get("claims", []):
            for c in cl.get("citations", []):
                if c.get("causal") is not None or c.get("untestable"):
                    v = "accepted" if c.get("causal") else "inconclusive" if c.get("untestable") else "rejected"
                    out.append(((c["path"], int(c["line"])), v))
    return out


def verification_counts(answer: dict[str, Any], gold: list[dict[str, Any]]) -> dict[str, int]:
    c = {"tested": 0, "tested_gold": 0, "accepted_gold": 0, "tested_other": 0, "accepted_other": 0, "inconclusive": 0}
    for (p, ln), v in tested_lines(answer):
        c["tested"] += 1
        c["inconclusive"] += v == "inconclusive"
        if range_index(p, ln, gold) is not None:
            c["tested_gold"] += 1
            c["accepted_gold"] += v == "accepted"
        else:
            c["tested_other"] += 1
            c["accepted_other"] += v == "accepted"
    return c
