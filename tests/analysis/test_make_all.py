"""analysis/make_all.py: pre-registered verdict rules, precision CI, taxonomy, RQ2 and the human-label view."""

import pytest

from analysis import make_all as M
from core.config import load_config

CFG = load_config([{"eval": {"bootstrap_resamples": 2000}}])


def test_h1_verdicts_follow_the_preregistered_rules():
    assert M.verdict_h1(None).startswith("not tested")
    assert M.verdict_h1({"diff": 0.05, "ci_low": -0.02, "ci_high": 0.12}).startswith("inconclusive")
    assert M.verdict_h1({"diff": -0.2, "ci_low": -0.3, "ci_high": -0.05}).startswith("not supported (the baseline is better")
    assert M.verdict_h1({"diff": 0.05, "ci_low": 0.01, "ci_high": 0.09}).startswith("not supported (gain 5.0 points")
    assert M.verdict_h1({"diff": 0.12, "ci_low": 0.02, "ci_high": 0.2}) == "supported"


def _row(correct, causal=False, partial=False, fix=False, covered=True):
    return {"judged": True, "correct": correct, "partial": partial, "causally_supported": causal, "fix_location_hit": fix,
            "confident_error": (not correct) and covered, "covered": covered, "label": "correct" if correct else "partial" if partial else "incorrect"}


def _data(ours, b2):
    qids = [f"q{i}" for i in range(len(ours))]
    return {"common": qids, "scores": {"ours": dict(zip(qids, ours)), "b2": dict(zip(qids, b2))},
            "answers": {s: {q: {} for q in qids} for s in ("ours", "b2")},
            "judgements": {"ours": {}, "b2": {}}, "consensus": [], "agreement": None, "mutation_checks": [],
            "questions": {q: {"category": "single_location", "library": "click", "gold_evidence": []} for q in qids}}


def test_h1_and_h2_on_a_clear_win():
    ours = [_row(True, True) for _ in range(30)]
    b2 = [_row(False) for _ in range(30)]
    h = M.hypotheses(_data(ours, b2), CFG)
    assert h["H1"]["verdict"] == "supported" and h["H1"]["comparison"]["diff"] == pytest.approx(1.0)
    assert h["H2"]["verdict"] == "supported" and h["H2"]["relative_reduction"] == pytest.approx(1.0)


def test_h2_fails_when_coverage_drops_too_far():
    ours = [_row(True, True) for _ in range(20)] + [_row(False, covered=False) for _ in range(10)]
    b2 = [_row(False) for _ in range(30)]
    h = M.hypotheses(_data(ours, b2), CFG)
    assert h["H2"]["coverage_ours"] == pytest.approx(20 / 30) and h["H2"]["verdict"] == "not supported"


def test_precision_difference_is_pooled_and_paired_by_question():
    a = {"q1": [True, True], "q2": [True, False], "q3": [True]}
    b = {"q1": [False, False], "q2": [True, False], "q3": [False]}
    d = M.precision_diff(a, b, ["q1", "q2", "q3"], CFG)
    assert d["a_precision"] == pytest.approx(4 / 5) and d["b_precision"] == pytest.approx(1 / 5)
    assert d["diff"] == pytest.approx(0.6) and d["ci_low"] <= d["diff"] <= d["ci_high"]
    assert M.precision_diff({}, {}, ["q1"], CFG) is None


def test_taxonomy_classes_are_deterministic():
    rows = [_row(True, True), _row(True, False), _row(False, partial=True), _row(False, partial=True, fix=True), _row(False)]
    data = _data(rows, rows)
    data["answers"]["ours"]["q4"] = {"abstained": True}
    t = M.taxonomy(data)["ours"]
    assert t == {"correct, causally supported": 1, "correct, not causally supported": 1, "right behaviour, wrong place": 1,
                 "right place, wrong or partial behaviour": 1, "abstained": 1}


def test_human_view_keeps_labels_aligned_with_citations():
    """Regression: a fix-line citation must still consume its human label, or later labels shift."""
    data = _data([_row(True)], [_row(True)])
    data["questions"]["q0"]["gold_evidence"] = [{"path": "src/p/a.py", "line_start": 5, "line_end": 5, "kind": "changed"}]
    data["answers"]["ours"]["q0"] = {"claims": [{"citations": [{"path": "src/p/a.py", "line": 5}]},
                                                {"citations": [{"path": "src/p/b.py", "line": 9}]}]}
    data["consensus"] = [{"qid": "q0", "system": "ours", "correctness": "correct", "citations": ["irrelevant", "on_topic"]}]
    data["agreement"] = {"kappa": {"answer": {"use_human_labels": True}, "citation": {"use_human_labels": False}}}
    hv = M.human_view(data)
    # claim 1 is causal by fix line; claim 2's label is on_topic (not irrelevant, which belonged to claim 1)
    assert hv["scores"]["ours"]["q0"]["causally_supported"] is False
    data["consensus"][0]["citations"] = ["irrelevant", "causal"]
    assert M.human_view(data)["scores"]["ours"]["q0"]["causally_supported"] is True


def test_rq2_rules_against_fix_lines_and_untestable_count():
    data = _data([_row(True)], [_row(True)])
    data["questions"]["q0"]["gold_evidence"] = [{"path": "src/p/a.py", "line_start": 5, "line_end": 6, "kind": "changed"}]
    v = lambda a, b, s: {"any_flip": a, "behavioural": b, "specific": s}  # noqa: E731
    data["mutation_checks"] = [
        {"qid": "q0", "locs": ["src/p/a.py:5"], "verdicts": v(True, True, True)},
        {"qid": "q0", "locs": ["src/p/a.py:9"], "verdicts": v(True, True, False)},
        {"qid": "q0", "locs": ["src/p/a.py:6"], "untestable": True},
        {"qid": "other", "locs": ["src/p/a.py:5"], "verdicts": v(True, True, True)},
    ]
    r = M.rq2(data)
    assert r["checks"] == 3 and r["untestable"] == 1 and r["untestable_in_gold"] == 1
    assert r["rules"]["any_flip"]["precision_vs_fix_lines"] == pytest.approx(0.5)
    assert r["rules"]["specific"]["precision_vs_fix_lines"] == pytest.approx(1.0) and r["rules"]["specific"]["recall_vs_fix_lines"] == 1.0


def test_rq2_matches_human_labels_across_the_src_prefix():
    """Answers cite `src/p/a.py`; mutation checks record `p/a.py` (from the source root). Both must match."""
    data = _data([_row(True)], [_row(True)])
    data["answers"]["ours"]["q0"] = {"claims": [{"citations": [{"path": "src/p/a.py", "line": 5},
                                                               {"path": "src/p/a.py", "line": 9}]}]}
    data["consensus"] = [{"qid": "q0", "system": "ours", "citations": ["causal", "irrelevant"]}]
    v = lambda a, b, s: {"any_flip": a, "behavioural": b, "specific": s}  # noqa: E731
    data["mutation_checks"] = [{"qid": "q0", "locs": ["p/a.py:5"], "verdicts": v(True, True, True)},
                               {"qid": "q0", "locs": ["p/a.py:9"], "verdicts": v(True, False, False)}]
    h = M.rq2(data)["human"]
    assert h["specific"]["n"] == 2 and h["specific"]["agreement"] == 1.0
    assert h["any_flip"]["agreement"] == 0.5


def test_probe_outcomes_are_classified_from_result_text():
    assert M.probe_outcome('claim: test_claim PASS; observe() returned "1"') == "pass"
    assert M.probe_outcome("claim: test_claim FAIL; ...") == "fail"
    assert M.probe_outcome("claim: test_claim ERROR; ...") == "error"
    assert M.probe_outcome("BLOCKED by the sandbox policy; nothing was run.") == "blocked"
    assert M.probe_outcome("Probe budget used up (12 runs).") == "budget"


def test_tool_use_counts_and_deduplicates_replayed_events(tmp_path):
    import json
    data = _data([_row(True)], [_row(True)])
    data["answers"]["ours"]["q0"] = {"tool_calls": {"total": 10, "invalid": 1, "errors": 2, "recovered": 1}, "unsafe_attempts": 1}
    data["answers"]["b2"]["q0"] = {"tool_calls": {"total": 4, "invalid": 0, "errors": 0, "recovered": 0}, "unsafe_attempts": 0}
    ev = [{"event": "tool_call", "qid": "q0", "tool": "run_probe", "args": {"c": 1}, "result": "claim: test_claim PASS"},
          {"event": "tool_call", "qid": "q0", "tool": "run_probe", "args": {"c": 2}, "result": "claim: test_claim ERROR"},
          {"event": "unsafe_attempt", "qid": "q0", "tool": "run_probe",
           "violations": "[{'rule': 'blocked_import', 'probe': 'claim'}, {'rule': 'blocked_import', 'probe': 'control_1'}]"},
          {"event": "tool_call", "qid": "q0", "tool": "run_probe", "args": {"c": 3}, "result": "BLOCKED by the sandbox policy"},
          {"event": "tool_call", "qid": "other", "tool": "run_probe", "args": {}, "result": "claim: test_claim PASS"}]
    lines = [json.dumps(e) for e in ev]
    (tmp_path / "r_ours.jsonl").write_text("\n".join(lines + lines[:1]) + "\n")  # first event replayed once
    t = M.tool_use(data, tmp_path, "r")
    o = t["ours"]
    assert o["probe_outcomes"] == {"pass": 1, "error": 1, "blocked": 1} and o["probes_submitted"] == 3
    assert o["valid_call_rate"] == pytest.approx(0.9) and o["recovery_rate"] == pytest.approx(0.5)
    assert o["probe_verdict_rate"] == pytest.approx(0.5) and o["unsafe_attempt_rate"] == pytest.approx(1 / 3)
    assert o["blocked_rules"] == {"blocked_import": 2} and o["unsafe_executed"] == 0
    assert t["b2"]["probes_submitted"] == 0 and t["b2"]["unsafe_attempt_rate"] is None


def test_spot_check_removals_are_read_from_the_drop_log(tmp_path):
    import json
    log = tmp_path / "dropped.jsonl"
    log.write_text("\n".join(json.dumps(d) for d in [
        {"qid": "click-1", "stage": "spot_check", "reason": "spot_check_invalid"},
        {"qid": "click-2", "stage": "validate", "reason": "no_fail_to_pass"},
        {"stage": "spot_check"}]) + "\n")
    assert M.spot_check_exclusions(log) == {"click-1"}
    assert M.spot_check_exclusions(tmp_path / "missing.jsonl") == set()
