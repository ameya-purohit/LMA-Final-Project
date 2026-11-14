"""demo/data.py: the presentation demo shows the same numbers as the report, and its live toylib demo is right."""

import py_compile
from types import SimpleNamespace

import pytest

from core.config import REPO_ROOT
from demo import data as D


def test_app_compiles_without_streamlit_installed():
    py_compile.compile(str(REPO_ROOT / "demo" / "app.py"), doraise=True)


def test_summary_rows_follow_the_report_order_and_values():
    m = lambda c, cs: {"n": 10, "correctness": c, "causally_supported": cs, "fix_location_recall": 0.5,  # noqa: E731
                       "n_confident_errors": 3, "coverage": 0.9, "requests_mean": 4.0, "tokens_mean": 100.0}
    rows = D.summary_rows({"summary": {"ours": m(0.6, 0.4), "b2": m(0.7, 0.5), "zz": m(0, 0)}})
    assert [r["system"] for r in rows] == ["b2", "ours"]
    assert rows[1]["correct"] == 0.6 and rows[1]["causally_supported"] == 0.4 and rows[1]["label"].startswith("Ours")


def test_committed_results_match_the_report():
    res = D.analysis("main_test")
    if res is None or "summary" not in res:
        pytest.skip("committed analysis not present")
    rows = {r["system"]: r for r in D.summary_rows(res)}
    assert rows["ours"]["n"] == 145 and rows["ours"]["causally_supported"] == pytest.approx(0.40)
    assert rows["b2"]["causally_supported"] == pytest.approx(72 / 145)
    human = {r["system"]: r for r in D.human_rows(res)}
    assert human["ours"]["causally_supported"] == pytest.approx(3 / 12) and human["b2"]["causally_supported"] == pytest.approx(5 / 12)


def test_human_rows_count_rates():
    res = {"human": {"scores": {"ours": {"q1": {"correct": True, "causally_supported": False},
                                         "q2": {"correct": False, "causally_supported": False}}}}}
    assert D.human_rows(res) == [{"system": "ours", "label": D.SYSTEM_NAMES["ours"], "n": 2, "correct": 0.5,
                                  "causally_supported": 0.0}]


def test_timeline_reads_the_decision_log():
    steps = D.timeline({"decisions": [
        {"decision": "draft", "n_claims": 2},
        {"decision": "probe_result", "claim": 1, "verdict": "fail", "repairs": 0},
        {"decision": "refuted", "claim": 1, "observed": "raised ValueError"},
        {"decision": "mutation_check", "claim": 1, "loc": "src/p/a.py:5", "causal": False},
        {"decision": "something_new", "x": 1},
    ]})
    assert [s["icon"] for s in steps] == ["📝", "❌", "🔁", "🚫", "•"]
    assert "not causal" in steps[3]["title"] and "raised ValueError" in steps[2]["detail"]


def test_explain_verdict_names_the_reason():
    def rep(*flags, untestable=False, error=None):
        return SimpleNamespace(untestable=untestable, error=error,
                               mutants=[SimpleNamespace(flags=f, claim={"kind": "raise", "type": "NameError"}) for f in flags])
    f = lambda c, b, s, br=False: {"claim_changed": c, "behavioural": b, "specific": s, "breakage": br}  # noqa: E731
    assert D.explain_verdict(rep(f(True, True, True))).startswith("Accepted")
    assert "not specific" in D.explain_verdict(rep(f(True, True, False)))
    assert "break the program (NameError)" in D.explain_verdict(rep(f(True, False, False, True)))
    assert "no mutant" in D.explain_verdict(rep(f(False, False, False)))
    assert "untestable" in D.explain_verdict(rep(untestable=True))


def test_frozen_snippet_stays_inside_the_tree(tmp_path, monkeypatch):
    monkeypatch.setattr(D, "REPO_ROOT", tmp_path)
    tree = tmp_path / ".cache" / "trees" / "click" / "abc"
    (tree / "src").mkdir(parents=True)
    (tree / "src" / "m.py").write_text("a = 1\nb = 2\nc = 3\n")
    q = {"library": "click", "frozen_commit": "abc"}
    assert "> " + "    2  b = 2" in D.frozen_snippet(q, "src/m.py", 2, context=1)
    assert D.frozen_snippet(q, "../../../../etc/passwd", 1) is None and D.frozen_snippet(q, "nope.py", 1) is None


def test_toylib_claims_point_at_the_planted_lines():
    claims = D.toylib_claims()
    decider = next(p for c in claims for p in c["planted"] if p["mark"] == "decider")
    assert decider == {"mark": "decider", "line": 88, "causal": True}
    assert D.toylib_source()[11].startswith("STRICT_DEFAULT")


def test_live_demo_flips_the_switch_on_toylib():
    """The page's two buttons, without Streamlit: the decider line is accepted, line 12 is rejected."""
    from analysis.toylib_ablations import REL
    from tools.mutate import mutate_and_run
    c1 = D.toylib_claims()[0]
    session = D.toylib_session(use_docker=False)
    try:
        probe = session.run_probes([("claim", c1["claim"]), ("control", c1["control"])])["results"]
        assert [r["status"] for r in probe] == ["pass", "pass"]
        assert D.describe_outcome(probe[0]["outcome"]) == "raises ValueError('negative')"
        assert mutate_and_run(session, REL, 88, c1["claim"], [c1["control"]]).causal
        assert not mutate_and_run(session, REL, 12, c1["claim"], [c1["control"]]).causal
    finally:
        session.cleanup()


def test_extension_rows_match_the_report():
    ext = D.extension()
    if ext is None:
        pytest.skip("results/summary/extension.json not built")
    rows = {r["system"]: r for r in D.ext_rows(ext)}
    assert list(rows) == D.EXT_ORDER
    assert round(rows["E2"]["line_top3"], 3) == 0.553 and round(rows["E3"]["line_top3"], 3) == 0.362   # report §8.3
    assert round(rows["E1"]["requests"], 1) == 7.6 and round(rows["E0"]["requests"], 1) == 14.9      # report §8.4


def test_loc_in_gold_reads_extension_locations():
    gold = [{"path": "src/click/core.py", "line_start": 1632, "line_end": 1633, "kind": "changed"}]
    assert D.loc_in_gold("src/click/core.py:1633", gold) and D.loc_in_gold("click/core.py:1632", gold)
    assert not D.loc_in_gold("src/click/core.py:1634", gold) and not D.loc_in_gold("no-line", gold)
