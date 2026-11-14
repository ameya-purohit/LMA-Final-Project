"""annotation/apply_spotcheck.py: remove invalid questions, log them, report disagreement; idempotent."""

import json

import pytest
from pydantic import ValidationError

from annotation import apply_spotcheck as A
from core.jsonl import read_jsonl, write_jsonl


def _v(qid, member, *answers, note=""):
    g, t, d = answers
    return {"qid": qid, "member": member, "genuine_question": g, "test_captures_behaviour": t, "gold_lines_decide": d,
            "genuine_question_note": note if not g else "", "test_captures_behaviour_note": "",
            "gold_lines_decide_note": note if not d else "", "valid": g and t and d, "checked_at": "2026-11-07T10:00:00Z"}


def _q(qid):
    return {"qid": qid, "library": "click", "fix_pr_number": 10, "issue_number": 5,
            "spot_check": {"checked_by": None, "valid": None, "reason": None}}


@pytest.fixture
def repo(tmp_path):
    ann, data = tmp_path / "annotation", tmp_path / "data"
    ann.mkdir(), data.mkdir()
    (ann / "sample_manifest.json").write_text(json.dumps({"assignment": {"sunil": ["q1", "q2"], "sourav": ["q3"]}}))
    write_jsonl(data / "questions_all.jsonl", [_q("q1"), _q("q2"), _q("q3"), _q("q4")])
    write_jsonl(data / "dropped.jsonl", [{"library": "click", "pr": 1, "stage": "mining", "reason": "no_linked_issue"}])
    (data / "mining_report.md").write_text("# Mining report\n\n## Funnel\n\nrows\n")
    write_jsonl(ann / "spotcheck_sunil_done.jsonl",
                [_v("q1", "sunil", True, True, True), _v("q2", "sunil", False, True, False, note="feature request")])
    write_jsonl(ann / "spotcheck_sourav_done.jsonl", [_v("q3", "sourav", True, True, True)])
    return ann, data


def _run(ann, data, *extra):
    return A.main(["--annotation-dir", str(ann), "--data-dir", str(data), *extra])


def test_invalid_questions_are_removed_logged_and_reported(repo):
    ann, data = repo
    assert _run(ann, data) == 0
    qs = {q["qid"]: q for q in read_jsonl(data / "questions_all.jsonl")}
    assert sorted(qs) == ["q1", "q3", "q4"], "q2 was marked invalid; q4 was not sampled and stays"
    assert qs["q1"]["spot_check"] == {"checked_by": "sunil", "valid": True, "reason": None}
    assert qs["q4"]["spot_check"]["checked_by"] is None
    drops = [d for d in read_jsonl(data / "dropped.jsonl") if d["stage"] == "spot_check"]
    assert len(drops) == 1 and drops[0]["qid"] == "q2" and drops[0]["checked_by"] == "sunil"
    assert "genuine_question: no (feature request)" in drops[0]["detail"] and "gold_lines_decide: no" in drops[0]["detail"]
    report = (data / "mining_report.md").read_text()
    assert "## Funnel" in report and "## Spot check (gate G1)" in report and "33.3%" in report and "| q2 | sunil | 67% |" in report


def test_running_twice_changes_nothing(repo):
    ann, data = repo
    _run(ann, data)
    files = {p.name: p.read_text() for p in data.iterdir()}
    _run(ann, data)
    assert {p.name: p.read_text() for p in data.iterdir()} == files


def test_missing_verdicts_block_unless_allowed(repo, capsys):
    ann, data = repo
    (ann / "spotcheck_sourav_done.jsonl").unlink()
    assert _run(ann, data) == 1 and "q3" in capsys.readouterr().err
    assert len(read_jsonl(data / "questions_all.jsonl")) == 4, "nothing applied"
    assert _run(ann, data, "--allow-missing") == 0


def test_wrong_member_and_unsampled_questions_are_problems(repo, capsys):
    ann, data = repo
    write_jsonl(ann / "spotcheck_ameya_done.jsonl", [_v("q3", "ameya", True, True, True), _v("q9", "ameya", True, True, True)])
    assert _run(ann, data) == 1
    err = capsys.readouterr().err
    assert "q3 was assigned to sourav" in err and "q9 is not in the sample" in err


def test_valid_must_match_the_answers():
    bad = _v("q1", "sunil", True, False, True)
    bad["valid"] = True
    with pytest.raises(ValidationError):
        A.Verdict.model_validate(bad)


def test_disagreement_rates():
    vs = [A.Verdict.model_validate(_v("a", "m", True, True, True)), A.Verdict.model_validate(_v("b", "m", True, False, True)),
          A.Verdict.model_validate(_v("c", "m", False, False, False)), A.Verdict.model_validate(_v("d", "m", True, True, True))]
    s = A.disagreement(vs)
    assert s["checked"] == 4 and s["invalid"] == 2 and s["overall_rate"] == 0.5
    assert s["per_criterion"] == {"genuine_question": 0.25, "test_captures_behaviour": 0.5, "gold_lines_decide": 0.25}
    assert s["per_question"] == {"a": 0.0, "b": 0.333, "c": 1.0, "d": 0.0}
