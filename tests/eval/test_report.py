"""eval.report: loads stored answers and judgements, keeps unjudged answers as pending."""

import json

from eval.report import common_questions, load_scores, markdown_table, paired_comparison, pct, restrict
from eval.metrics import summarize
from core.config import load_config

Q = {"q1": {"qid": "q1", "gold_evidence": [{"path": "a.py", "line_start": 1, "line_end": 2, "kind": "changed"}]},
     "q2": {"qid": "q2", "gold_evidence": []}}


def write(root, system, qid, judgement=None, requests=2):
    (root / system).mkdir(exist_ok=True, parents=True)
    answer = {"qid": qid, "system": system, "requests": requests, "claims": [{"text": "t", "citations": [{"path": "a.py", "line": 1}]}]}
    (root / system / f"{qid}.json").write_text(json.dumps(answer))
    if judgement:
        (root / "judgements" / system).mkdir(parents=True, exist_ok=True)
        (root / "judgements" / system / f"{qid}.json").write_text(json.dumps(judgement))


def test_scores_table_and_pending(tmp_path):
    write(tmp_path, "ours", "q1", {"correctness": "correct", "citations": ["causal"]})
    write(tmp_path, "ours", "q2")
    write(tmp_path, "b2", "q1", {"correctness": "incorrect", "citations": ["irrelevant"]})
    scores = load_scores(tmp_path, Q)
    assert set(scores) == {"ours", "b2"}, "the judgements folder is not a system"
    table = markdown_table({s: summarize(r) for s, r in scores.items()})
    assert "| ours | 2 | 1 | 1 | 0 | 100.0% |" in table and "| b2 | 1 | 1 | 0 | 0 | 0.0% |" in table
    cmp = paired_comparison(scores["ours"], scores["b2"], "correct", load_config())
    assert cmp["n"] == 1 and cmp["only_a"] == 1 and cmp["diff"] == 1
    assert paired_comparison(scores["ours"], [], "correct", load_config()) is None


def test_nothing_judged_is_pending_not_zero():
    assert pct(None) == "pending"


def test_comparison_uses_only_questions_every_system_completed(tmp_path):
    """Quota stopped b2 early: ours's extra question must not enter any comparison."""
    good = {"correctness": "correct", "citations": ["causal"]}
    write(tmp_path, "ours", "q1", good)
    write(tmp_path, "ours", "q2", good)
    write(tmp_path, "b2", "q1", {"correctness": "incorrect", "citations": ["irrelevant"]})
    scores = load_scores(tmp_path, Q)
    common, judged = common_questions(scores)
    assert common == ["q1"] and judged == ["q1"]
    rows = restrict(scores["ours"], common, judged)
    assert [r["qid"] for r in rows] == ["q1"] and summarize(rows)["n"] == 1


def test_judgement_missing_for_one_system_removes_the_question_from_judged_metrics(tmp_path):
    good = {"correctness": "correct", "citations": ["causal"]}
    for q in ("q1", "q2"):
        write(tmp_path, "ours", q, good)
    write(tmp_path, "b2", "q1", good)
    write(tmp_path, "b2", "q2")
    scores = load_scores(tmp_path, Q)
    common, judged = common_questions(scores)
    assert common == ["q1", "q2"] and judged == ["q1"]
    s = summarize(restrict(scores["ours"], common, judged))
    assert s["n"] == 2 and s["n_judged"] == 1 and s["correctness"] == 1.0
