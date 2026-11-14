"""eval.run: resumability, the quota exit code, the test-set lock, and config diffs show only control logic."""

import json

import pytest

from core.config import diff, load_config
from eval import run as R
from llm.types import QuotaExhausted


def test_test_set_is_locked():
    assert R.main(["--system", "b1", "--split", "test"]) == R.EXIT_REFUSED == 2


def test_test_set_needs_the_preregistration_lock(tmp_path):
    draft, locked = tmp_path / "draft.md", tmp_path / "locked.md"
    draft.write_text("**Status: DRAFT.** ...")
    locked.write_text("**Status: LOCKED (2026-11-07, gate G2).** ...")
    assert not R.test_set_locked(draft) and R.test_set_locked(locked) and not R.test_set_locked(tmp_path / "none.md")


def test_run_all_stops_on_a_refusal(monkeypatch):
    import scripts.run_all as RA
    from eval import judge
    calls = []
    monkeypatch.setattr(R, "main", lambda argv: calls.append(argv) or R.EXIT_REFUSED)
    monkeypatch.setattr(judge, "main", lambda argv: pytest.fail("must not judge after a refusal"))
    assert RA.main(["--split", "test", "--systems", "ours", "b2", "--by-question", "--limit", "3"]) == 2
    assert len(calls) == 1 and "--allow-test" not in calls[0]


def test_ablations_differ_only_in_control_logic():
    base = load_config()
    for system, override in R.SYSTEM_OVERRIDES.items():
        changed = diff(base, load_config([override]))
        for key in changed:
            # The extension's E1-E6 switch components on through multiagent.flags only (PREREGISTRATION.md).
            assert key.startswith(("agent.ablation.", "baselines.", "multiagent.flags.")), \
                f"{system} changes {key}, which is not control logic"


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
    assert R.main(["--system", "b1", "--run-id", "t", "--qid-order"]) == R.EXIT_QUOTA
    out = small_repo / "results" / "t" / "b1"
    assert (out / "q1.json").exists() and not (out / "q2.json").exists()
    assert R.main(["--system", "b1", "--run-id", "t", "--qid-order"]) == 0
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


def _qs(n_click, n_marsh):
    return [{"qid": f"click-{i}", "library": "click"} for i in range(n_click)] + \
           [{"qid": f"marshmallow-{i}", "library": "marshmallow"} for i in range(n_marsh)]


def test_run_order_interleaves_libraries_in_every_prefix():
    qs = _qs(129, 21)
    order = R.run_order(qs, 82)
    assert sorted(q["qid"] for q in order) == sorted(q["qid"] for q in qs), "a permutation: nothing lost or repeated"
    for n in (10, 20, 50, 100, 150):
        marsh = sum(q["library"] == "marshmallow" for q in order[:n])
        assert abs(marsh - 21 * n / 150) <= 1, (n, marsh)


def test_run_order_is_seeded_and_ignores_input_order():
    qs = _qs(30, 10)
    ids = [q["qid"] for q in R.run_order(qs, 82)]
    assert ids == [q["qid"] for q in R.run_order(list(reversed(qs)), 82)]
    assert ids != [q["qid"] for q in R.run_order(qs, 83)]
    assert R.run_order([], 82) == []


def test_oracle_material_skips_files_the_fix_created(tmp_path):
    """click-1484's fix added shell_completion.py, which does not exist at the frozen commit."""
    from tools.workspace import Workspace
    pkg = tmp_path / "src" / "p"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "core.py").write_text("X = 1\n")
    ws = Workspace("p", "p", tmp_path)
    text = R.oracle_material({"fix_source_files": ["src/p/core.py", "src/p/new_module.py"]}, ws)
    assert "[code] src/p/core.py" in text and "    1  X = 1" in text and "new_module" not in text
