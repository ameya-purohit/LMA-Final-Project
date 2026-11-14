"""eval.localization: a hand-computed mini example."""

from eval.localization import ranked_locations, score_locations, verification_counts
from eval.localization import tested_lines as lines_tested

GOLD = [{"path": "src/p/a.py", "line_start": 10, "line_end": 12}, {"path": "src/p/b.py", "line_start": 5, "line_end": 5}]


def fn(path, line):
    return {"a": "a.f", "b": "b.g"}[path.split("/")[-1][0]] if line > 1 else None


def test_ranked_locations_from_citations_and_from_ranking():
    ans = {"claims": [{"citations": [{"path": "p/a.py", "line": 3}, {"path": "p/a.py", "line": 11}]},
                      {"citations": [{"path": "p/a.py", "line": 3}]}]}
    assert ranked_locations(ans) == [("p/a.py", 3), ("p/a.py", 11)]
    assert ranked_locations({"ranking": [{"path": "x.py", "line": 1}], "claims": ans["claims"]}) == [("x.py", 1)]


def test_scores_by_hand():
    s = score_locations([("p/a.py", 3), ("src/p/a.py", 11), ("p/b.py", 5), ("p/b.py", 9)], GOLD, fn)
    assert s["line_top1"] == 0 and s["line_top3"] == 1 and s["line_mrr"] == 0.5
    assert s["line_precision"] == 0.5 and s["line_recall"] == 1.0 and abs(s["line_f1"] - 2 / 3) < 1e-9
    assert s["fn_top1"] == 1 and s["fn_precision"] == 1.0 and s["fn_recall"] == 1.0
    assert s["multi"] and s["multi_found"]


def test_no_prediction():
    s = score_locations([], GOLD)
    assert s["line_top3"] == 0 and s["line_mrr"] == 0 and s["line_f1"] == 0


def test_verification_counts_for_both_kinds_of_answer():
    multi = {"architecture": "multiagent", "experiments": {"experiments": [
        {"kind": "single", "locs": ["src/p/a.py:11"], "verdict": "accepted"},
        {"kind": "single", "locs": ["src/p/a.py:30"], "verdict": "accepted"},
        {"kind": "single", "locs": ["src/p/a.py:31"], "verdict": "inconclusive"},
        {"kind": "pair", "locs": ["src/p/a.py:11", "src/p/a.py:30"], "verdict": "accepted"}]}}
    c = verification_counts(multi, GOLD)
    assert c == {"tested": 3, "tested_gold": 1, "accepted_gold": 1, "tested_other": 2, "accepted_other": 1, "inconclusive": 1}
    e0 = {"decisions": [{"decision": "mutation_check", "loc": "p/b.py:5", "causal": False},
                        {"decision": "mutation_check", "loc": "p/b.py:5", "causal": True},
                        {"decision": "proposed_citation", "loc": "p/a.py:2", "causal": None}]}
    assert lines_tested(e0) == [(("p/b.py", 5), "rejected"), (("p/a.py", 2), "inconclusive")]
