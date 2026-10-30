"""eval.run: resumability, the quota exit code, the test-set lock, and config diffs show only control logic."""

import json

import pytest

from core.config import diff, load_config
from eval import run as R
from llm.types import QuotaExhausted


def test_test_set_is_locked():
    assert R.main(["--system", "b1", "--split", "test"]) == 2


def test_ablations_differ_only_in_control_logic():
    base = load_config()
    for system, override in R.SYSTEM_OVERRIDES.items():
        changed = diff(base, load_config([override]))
        for key in changed:
            assert key.startswith(("agent.ablation.", "baselines.")), f"{system} changes {key}, which is not control logic"


@pytest.fixture
def small_repo(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    q = {"qid": "q1", "library": "click", "frozen_commit": "abc", "question_text": "why?"}
    q2 = {**q, "qid": "q2"}
    (tmp_path / "data" / "questions_dev.jsonl").write_text(json.dumps(q) + "\n" + json.dumps(q2) + "\n")
    monkeypatch.setattr(R, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(R, "LLMClient", lambda *a, **k: type("C", (), {"tracer": k["tracer"], "environment": lambda s: {}})())
    monkeypatch.setattr(R, "ReplyCache", lambda *a, **k: None)
    return tmp_path


def test_resumes_and_stops_cleanly_on_quota(small_repo, monkeypatch):
    seen = []

    def fake(system, q, config, client, tracer):
        seen.append(q["qid"])
        if q["qid"] == "q2" and len(seen) == 2:
            raise QuotaExhausted("per day")
        return {"qid": q["qid"], "requests": 1, "api_requests": 1, "flagged_uncertain": False, "claims": []}

    monkeypatch.setattr(R, "run_question", fake)
    assert R.main(["--system", "b1", "--run-id", "t"]) == R.EXIT_QUOTA
    out = small_repo / "results" / "t" / "b1"
    assert (out / "q1.json").exists() and not (out / "q2.json").exists()
    assert R.main(["--system", "b1", "--run-id", "t"]) == 0
    assert (out / "q2.json").exists() and seen == ["q1", "q2", "q2"], "q1 must not run again"


def test_one_crash_does_not_stop_the_batch(small_repo, monkeypatch):
    def fake(system, q, config, client, tracer):
        if q["qid"] == "q1":
            raise RuntimeError("boom")
        return {"qid": q["qid"], "requests": 1, "api_requests": 1, "flagged_uncertain": False, "claims": []}

    monkeypatch.setattr(R, "run_question", fake)
    assert R.main(["--system", "b1", "--run-id", "t2"]) == 0
    out = small_repo / "results" / "t2" / "b1"
    assert not (out / "q1.json").exists() and (out / "q2.json").exists()
