"""Metrics over stored answers and judgements. Pure functions, so a mini example can
be computed by hand and compared exactly.

Definitions (CLAUDE.md §6.11, PREREGISTRATION.md):
- correct: the judge (or a human, who takes precedence) labels the answer "correct".
- wrong: labelled "incorrect" or "partial" (D-41). An answer that is only partly right
  is not safe to act on, so a confident partial answer counts as a confident error.
- covered: neither flagged uncertain nor abstained.
- confident error: wrong and covered.
- a citation counts as causal if it falls inside a `gold_evidence` range, or is
  labelled causal by a human or the validated judge.
- causally supported: correct, and every claim has at least one causal citation.
"""

from __future__ import annotations

from statistics import mean, median
from typing import Any


def path_matches(cited: str, gold: str) -> bool:
    """Repository-relative paths; a citation may leave out the `src/` prefix."""
    a, b = cited.lstrip("./"), gold.lstrip("./")
    return a == b or a == b.removeprefix("src/") or a.removeprefix("src/") == b


def in_gold(path: str, line: int, gold_evidence: list[dict[str, Any]]) -> bool:
    return any(path_matches(path, e["path"]) and e["line_start"] <= line <= e["line_end"] for e in gold_evidence)


def citation_flags(answer: dict[str, Any], gold_evidence: list[dict[str, Any]], labels: list[str] | None) -> list[list[dict[str, bool]]]:
    """Per claim, per citation: {in_gold, causal}. `labels` are the judge's, in citation order."""
    out = []
    i = 0
    for claim in answer.get("claims", []):
        row = []
        for c in claim.get("citations", []):
            gold = in_gold(c["path"], c["line"], gold_evidence)
            label = labels[i] if labels and i < len(labels) else None
            row.append({"in_gold": gold, "causal": gold or label == "causal"})
            i += 1
        out.append(row)
    return out


def score_question(answer: dict[str, Any], question: dict[str, Any], judgement: dict[str, Any] | None) -> dict[str, Any]:
    """Every per-question measure for one answer."""
    label = judgement.get("correctness") if judgement else None
    flags = citation_flags(answer, question["gold_evidence"], judgement.get("citations") if judgement else None)
    all_cites = [c for row in flags for c in row]
    covered = not answer.get("flagged_uncertain") and not answer.get("abstained")
    correct = label == "correct"
    judged = label is not None
    every_claim_causal = bool(flags) and all(any(c["causal"] for c in row) for row in flags)
    return {
        "qid": answer["qid"], "system": answer.get("system"), "judged": judged, "label": label,
        "correct": correct, "partial": label == "partial", "wrong": judged and not correct, "covered": covered,
        "confident_error": judged and not correct and covered,
        "causally_supported": correct and every_claim_causal,
        "fix_location_hit": any(c["in_gold"] for c in all_cites),
        "n_citations": len(all_cites), "n_in_gold": sum(c["in_gold"] for c in all_cites),
        "requests": answer.get("requests", 0), "api_requests": answer.get("api_requests", 0),
        "tokens": answer.get("tokens", {}).get("total", 0), "input_tokens": answer.get("tokens", {}).get("input", 0),
        "output_tokens": answer.get("tokens", {}).get("output", 0), "steps": answer.get("steps", 0),
        "probe_runs": answer.get("probe_runs", 0), "mutant_runs": answer.get("mutant_runs", 0),
        "cpu_seconds": answer.get("cpu_seconds", 0.0), "invalid_calls": answer.get("tool_calls", {}).get("invalid", 0),
        "total_calls": answer.get("tool_calls", {}).get("total", 0), "errors": answer.get("tool_calls", {}).get("errors", 0),
        "unsafe_attempts": answer.get("unsafe_attempts", 0),
    }


def summarize(scores: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate for one system. Judge-based rates are over judged answers only."""
    n = len(scores)
    judged = [s for s in scores if s["judged"]]
    nj = len(judged)
    rate = lambda key, rows: (sum(bool(s[key]) for s in rows) / len(rows)) if rows else None  # noqa: E731
    avg = lambda key: mean(s[key] for s in scores) if scores else None  # noqa: E731
    cites = sum(s["n_citations"] for s in scores)
    return {
        "n": n, "n_judged": nj, "n_correct": sum(s["correct"] for s in judged), "n_partial": sum(s["partial"] for s in judged),
        "correctness": rate("correct", judged), "causally_supported": rate("causally_supported", judged),
        "confident_error_rate": rate("confident_error", judged), "n_confident_errors": sum(s["confident_error"] for s in judged),
        "coverage": rate("covered", scores), "fix_location_recall": rate("fix_location_hit", scores),
        "precision_vs_gold_lower_bound": (sum(s["n_in_gold"] for s in scores) / cites) if cites else None,
        "requests_mean": avg("requests"), "requests_median": median(s["requests"] for s in scores) if scores else None,
        "requests_max": max((s["requests"] for s in scores), default=None), "api_requests_total": sum(s["api_requests"] for s in scores),
        "tokens_mean": avg("tokens"), "input_tokens_mean": avg("input_tokens"), "output_tokens_mean": avg("output_tokens"),
        "steps_mean": avg("steps"), "probe_runs_mean": avg("probe_runs"), "mutant_runs_mean": avg("mutant_runs"),
        "cpu_seconds_mean": avg("cpu_seconds"),
        "valid_call_rate": (1 - sum(s["invalid_calls"] for s in scores) / max(1, sum(s["total_calls"] for s in scores))) if scores else None,
        "unsafe_attempts": sum(s["unsafe_attempts"] for s in scores),
    }
