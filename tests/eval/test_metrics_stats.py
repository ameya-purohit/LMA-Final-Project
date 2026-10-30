"""Metrics reproduce a hand-computed mini example; statistics match known values."""

import pytest

from eval import judge as J
from eval.kappa import cohens_kappa
from eval.metrics import citation_flags, in_gold, path_matches, score_question, summarize
from eval.stats import mcnemar_exact, paired_bootstrap
from scripts.quota_plan import plan

GOLD = [{"path": "src/click/core.py", "line_start": 10, "line_end": 12, "kind": "changed"}]
Q = {"qid": "q1", "gold_evidence": GOLD}


def answer(citations, flagged=False, abstained=False, requests=4):
    return {"qid": "q1", "system": "s", "flagged_uncertain": flagged, "abstained": abstained, "requests": requests,
            "api_requests": requests, "tokens": {"total": 100, "input": 80, "output": 20},
            "tool_calls": {"total": 10, "invalid": 1}, "claims": [{"text": "c", "citations": citations}]}


def test_path_matching():
    assert path_matches("src/click/core.py", "src/click/core.py")
    assert path_matches("click/core.py", "src/click/core.py")
    assert not path_matches("src/click/parser.py", "src/click/core.py")
    assert in_gold("click/core.py", 11, GOLD) and not in_gold("click/core.py", 13, GOLD)


def test_citation_counts_as_causal_by_gold_or_judge():
    a = answer([{"path": "src/click/core.py", "line": 10}, {"path": "src/click/x.py", "line": 1}, {"path": "src/click/y.py", "line": 1}])
    flags = citation_flags(a, GOLD, ["irrelevant", "causal", "on_topic"])[0]
    assert [f["causal"] for f in flags] == [True, True, False] and [f["in_gold"] for f in flags] == [True, False, False]


def test_mini_example_by_hand():
    """Five answers, computed by hand:
    q1 correct, cites gold, covered             -> correct, causally supported, fix-location hit
    q2 correct, cites no gold, judge says on_topic -> correct only
    q3 partial, covered                          -> wrong, confident error
    q4 incorrect, flagged                        -> wrong, not a confident error, not covered
    q5 incorrect, covered, abstained=False, cites gold -> wrong, confident error, fix-location hit
    correctness 2/5, causally supported 1/5, confident errors 2/5, coverage 4/5, recall 2/5, requests mean (2+4+6+8+10)/5 = 6
    """
    gold_cite = {"path": "src/click/core.py", "line": 11}
    off_cite = {"path": "src/click/other.py", "line": 1}
    cases = [("correct", [gold_cite], False, ["causal"]), ("correct", [off_cite], False, ["on_topic"]),
             ("partial", [off_cite], False, ["irrelevant"]), ("incorrect", [off_cite], True, ["irrelevant"]),
             ("incorrect", [gold_cite], False, ["on_topic"])]
    scores = []
    for i, (label, cites, flagged, cite_labels) in enumerate(cases):
        a = answer(cites, flagged=flagged, requests=2 * (i + 1))
        a["qid"] = f"q{i + 1}"
        scores.append(score_question(a, Q, {"correctness": label, "citations": cite_labels}))
    s = summarize(scores)
    assert s["correctness"] == pytest.approx(2 / 5)
    assert s["causally_supported"] == pytest.approx(1 / 5)
    assert s["confident_error_rate"] == pytest.approx(2 / 5) and s["n_confident_errors"] == 2
    assert s["coverage"] == pytest.approx(4 / 5)
    assert s["fix_location_recall"] == pytest.approx(2 / 5)
    assert s["requests_mean"] == pytest.approx(6) and s["requests_max"] == 10 and s["n_partial"] == 1
    assert s["precision_vs_gold_lower_bound"] == pytest.approx(2 / 5)
    assert s["valid_call_rate"] == pytest.approx(0.9)


def test_unjudged_answer_is_not_counted_as_wrong():
    s = score_question(answer([]), Q, None)
    assert not s["judged"] and not s["wrong"] and not s["confident_error"] and s["covered"]
    assert summarize([s])["correctness"] is None and summarize([s])["coverage"] == 1.0


def test_abstained_is_not_covered():
    assert not score_question(answer([], abstained=True), Q, {"correctness": "incorrect", "citations": []})["confident_error"]


def test_mcnemar_known_values():
    # 10 discordant pairs split 9/1: two-sided exact p = 2 * (C(10,9)+C(10,10)) / 2^10 = 22/1024
    a = [True] * 9 + [False] * 1 + [True] * 5
    b = [False] * 9 + [True] * 1 + [True] * 5
    out = mcnemar_exact(a, b)
    assert out["only_a"] == 9 and out["only_b"] == 1 and out["p_value"] == pytest.approx(22 / 1024)
    assert mcnemar_exact([True, False], [True, False])["p_value"] == 1.0


def test_bootstrap_known_values():
    same = paired_bootstrap([True, False, True], [True, False, True])
    assert same["diff"] == 0 and same["ci_low"] == 0 and same["ci_high"] == 0
    all_better = paired_bootstrap([True] * 20, [False] * 20)
    assert all_better["diff"] == 1 and all_better["ci_low"] == 1 and all_better["ci_high"] == 1
    # 12 of 20 pairs +1, rest 0: mean 0.6, SE sqrt(.6*.4/20) = 0.1095, so the 95% CI is about 0.6 +/- 0.21
    mixed = paired_bootstrap([True] * 12 + [False] * 8, [False] * 20, resamples=10000)
    assert mixed["diff"] == pytest.approx(0.6) and mixed["ci_low"] == pytest.approx(0.4, abs=0.05) and mixed["ci_high"] == pytest.approx(0.8, abs=0.05)
    assert paired_bootstrap([True, False], [False, True], seed=1) == paired_bootstrap([True, False], [False, True], seed=1)


def test_kappa_known_values():
    assert cohens_kappa(["a", "b"], ["a", "b"]) == 1.0
    # classic example: po = 0.7, pe = 0.5, kappa = 0.4
    a = ["y"] * 25 + ["y"] * 25 + ["n"] * 25 + ["n"] * 25
    b = ["y"] * 25 + ["n"] * 25 + ["y"] * 5 + ["n"] * 45
    assert cohens_kappa(a, b) == pytest.approx((0.7 - 0.5) / 0.5)
    with pytest.raises(ValueError):
        cohens_kappa([], [])


def test_judge_parsing_and_prompt(tmp_path):
    j = J.parse_judgement('```json\n{"correctness":"partial","reason":"r","citations":["causal"]}\n```', 3)
    assert j.correctness == "partial" and j.citations == ["causal", "irrelevant", "irrelevant"]
    assert J.parse_judgement('{"correctness":"correct","citations":["causal","on_topic"]}', 1).citations == ["causal"]
    (tmp_path / "a.py").write_text("one\ntwo\nthree\n")
    assert ">>" in J.snippet(tmp_path, "a.py", 2) and "does not exist" in J.snippet(tmp_path, "a.py", 9)
    assert "does not exist" in J.snippet(tmp_path, "../../etc/passwd", 1) and "does not exist" in J.snippet(tmp_path, "b.py", 1)
    question = {"qid": "q", "question_text": "Q?", "gold_answer": "G", "observed_before": [{"test": "t", "status": "failed", "message": "m"}]}
    msgs = J.build_messages(question, {"answer_text": "A", "system": "ours", "claims": [{"text": "c", "citations": [{"path": "a.py", "line": 1}]}]}, tmp_path, "DIFF")
    user = msgs[1].content
    assert "G" in user and "DIFF" in user and "Citation 1: a.py:1" in user and "ours" not in user, "the judge must not see the system name"


def test_judge_prompt_survives_undecodable_test_output(tmp_path):
    """Seen on click-1844: the recorded failure message held a lone surrogate."""
    q = {"qid": "q", "question_text": "Q", "gold_answer": "G", "observed_before": [{"test": "t", "status": "failed", "message": "bad \udcff"}]}
    msgs = J.build_messages(q, {"answer_text": "A", "claims": []}, tmp_path, "")
    msgs[1].content.encode("utf-8")


def test_judge_unparseable_is_recorded_not_invented(tmp_path):
    class Client:
        def complete(self, *a, **k):
            from llm.types import Reply, Usage
            return Reply("not json", [], Usage(), model="m")
    q = {"qid": "q", "question_text": "Q", "gold_answer": "G", "observed_before": []}
    out = J.judge_answer(Client(), q, {"system": "s", "claims": []}, tmp_path, "")
    assert out["correctness"] is None and "unparseable" in out["error"]


def test_quota_plan():
    p = plan({"ours": 10, "b1": 1, "b2": 9}, daily=500, days=2)
    assert p["budget"] == 1000 and p["must_have_questions_affordable"] == 50
    assert [r["questions"] for r in p["rows"]] == [50, 50, 50] and p["left"] == 0
    tight = plan({"ours": 10, "b2": 10}, daily=100, days=1, questions=8)
    assert [r["questions"] for r in tight["rows"]] == [8, 2]
