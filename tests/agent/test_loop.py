"""The agent with a scripted fake LLM and fake tools: every decision point, no sandbox and no quota."""

from types import SimpleNamespace

import pytest

from agent.grades import grade
from agent.loop import OurAgent, classify_probe
from agent.claim_table import Citation, Claim, ClaimTable
from agent.stop import all_settled, flagged_uncertain
from core.config import load_config
from llm.types import Reply, ToolCall, Usage
from tools.registry import ToolRegistry, ToolResult


def call(name, **args):
    return Reply(text="", tool_calls=[ToolCall(id=f"c-{name}", name=name, arguments=args)],
                 usage=Usage(10, 5, 0, 0, 15), provider="gemini", model="fake")


class Scripted:
    """Returns scripted replies in order; fails loudly if the agent asks for more."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def complete(self, messages, tools, **params):
        self.calls.append({"tools": [t.name for t in tools or []], "params": params, "n_messages": len(messages)})
        assert self.replies, f"agent asked for an unscripted request; tools={self.calls[-1]['tools']}"
        return self.replies.pop(0)


def report(status="pass", outcome=None, message="", blocked=False, error=None, executable=True):
    claim = SimpleNamespace(status=status, outcome=outcome or {"kind": "return", "repr": "1"}, message=message)
    return SimpleNamespace(blocked=blocked, error=error, claim=claim, controls=[], executable=executable, causal=False)


class FakeRegistry(ToolRegistry):
    """Real validation and counting; run_probe and mutate_and_run are replaced by scripts."""

    def __init__(self, probes=(), mutations=None):
        super().__init__(SimpleNamespace(package="toylib"))
        self.probe_script = list(probes)
        self.mutations = dict(mutations or {})
        self.mutated = []
        desc, model, _ = self._tools["run_probe"]
        self._tools["run_probe"] = (desc, model, self._fake_probe)
        desc, model, _ = self._tools["mutate_and_run"]
        self._tools["mutate_and_run"] = (desc, model, self._fake_mutate)
        desc, model, _ = self._tools["open_file"]
        self._tools["open_file"] = (desc, model, lambda a: ToolResult("open_file", "file text"))

    def _fake_probe(self, a):
        self.counts["probe_runs"] += 1
        r = self.probe_script.pop(0)
        return ToolResult("run_probe", "probe output", record={"report": r})

    def _fake_mutate(self, a):
        self.counts["mutation_checks"] += 1
        self.mutated.append((a.path, a.line))
        return ToolResult("mutate_and_run", "mutation output",
                          record={"report": SimpleNamespace(causal=self.mutations.get((a.path, a.line), False))})


CLAIM = {"text": "clamp(-1) raises", "citations": [{"path": "src/toylib/core.py", "line": 88}]}
DRAFT = call("submit_draft", answer="draft", claims=[CLAIM])
PROBE = call("write_probe", probes=[{"claim_id": 1, "code": "probe", "controls": ["control"]}])
FINAL = call("final_answer", answer_text="final text")
CAUSAL = {("src/toylib/core.py", 88): True}
FAIL = dict(status="fail", outcome={"kind": "return", "repr": "-1"}, message="assert failed")


def make(script, probes=(), mutations=None, ablation=None, **kw):
    cfg = load_config([{"agent": {"ablation": ablation or {}, **kw}}])
    client = Scripted(script)
    reg = FakeRegistry(probes, mutations)
    ws = SimpleNamespace(package="toylib", session=object())
    agent = OurAgent(ws, client, cfg, registry=reg, material_override="MATERIAL",
                     vacuity_check=kw.pop("vacuity", None))
    return agent, client, reg


def test_happy_path_gives_e_plus_c():
    agent, client, reg = make([DRAFT, PROBE, FINAL], [report()], CAUSAL)
    out = agent.answer("q?")
    assert out["answer_text"] == "final text" and not out["flagged_uncertain"] and not client.replies
    c = out["claims"][0]
    assert c["status"] == "confirmed" and c["grade"] == "E+C" and c["citations"][0]["causal"] is True
    assert out["requests"] == 3 and out["probe_runs"] == 1
    assert reg.mutated == [("src/toylib/core.py", 88)]
    assert client.calls[0]["params"]["force_tool"] is True


def test_investigation_then_draft_counts_steps():
    open_call = call("open_file", path="src/toylib/core.py")
    agent, client, _ = make([open_call, open_call, DRAFT, PROBE, FINAL], [report()], CAUSAL)
    out = agent.answer("q?")
    assert out["steps"] == 2 and out["requests"] == 5


def test_steps_run_out_only_terminal_left():
    open_call = call("open_file", path="x")
    agent, client, _ = make([open_call, DRAFT, PROBE, FINAL], [report()], CAUSAL, max_investigation_steps=1)
    agent.answer("q?")
    assert "open_file" in client.calls[0]["tools"] and client.calls[1]["tools"] == ["submit_draft"]


def test_broken_probe_repaired():
    agent, client, _ = make([DRAFT, PROBE, PROBE, FINAL],
                            [report(status="error", outcome={"kind": "raise", "type": "NameError", "innermost_frame": "claim.py:3"}),
                             report()], CAUSAL)
    out = agent.answer("q?")
    assert out["claims"][0]["status"] == "confirmed" and out["probe_runs"] == 2


def test_broken_probe_abandoned_after_two_repairs_is_flagged():
    broken = dict(status="error", outcome={"kind": "raise", "type": "NameError", "innermost_frame": "claim.py:3"})
    agent, client, _ = make([DRAFT, PROBE, PROBE, PROBE, FINAL], [report(**broken) for _ in range(3)])
    out = agent.answer("q?")
    assert out["flagged_uncertain"] and out["claims"][0]["status"] == "unverified"
    assert out["claims"][0]["grade"] == "R"


def test_library_exception_counts_as_refutation_not_a_broken_probe():
    raising = report(status="error", outcome={"kind": "raise", "type": "ValueError", "msg": "x", "innermost_frame": "toylib/core.py:88"})
    assert classify_probe(raising, "toylib") == "fail"
    probe_bug = report(status="error", outcome={"kind": "raise", "type": "TypeError", "innermost_frame": "claim.py:2"})
    assert classify_probe(probe_bug, "toylib") == "broken"
    assert classify_probe(report(blocked=True), "toylib") == "broken"
    assert classify_probe(report(error="sandbox died"), "toylib") == "broken"
    assert classify_probe(report(executable=False), "toylib") == "broken"


def test_refuted_setup_differs_rewrites_probe():
    assess = call("assess_refutation", assessments=[{"claim_id": 1, "setup_matches_question": False, "reason": "wrong args"}])
    agent, client, _ = make([DRAFT, PROBE, assess, PROBE, FINAL], [report(**FAIL), report()], CAUSAL)
    out = agent.answer("q?")
    assert out["claims"][0]["status"] == "confirmed"


def test_refuted_setup_matches_reinvestigates_and_revises():
    assess = call("assess_refutation", assessments=[{"claim_id": 1, "setup_matches_question": True}])
    revise = call("revise_claim", claim_id=1, text="clamp(-1) returns -1", citations=[{"path": "src/toylib/core.py", "line": 88}])
    agent, client, _ = make([DRAFT, PROBE, assess, revise, PROBE, FINAL], [report(**FAIL), report()], CAUSAL)
    out = agent.answer("q?")
    assert out["claims"][0]["text"] == "clamp(-1) returns -1" and out["claims"][0]["status"] == "confirmed"
    assert any(d["decision"] == "revised" for d in out["decisions"])


def test_doc_claim_refuted_records_conflict():
    doc_claim = dict(CLAIM, source_kind="doc", text="the docs say strict is on")
    draft = call("submit_draft", answer="d", claims=[doc_claim])
    assess = call("assess_refutation", assessments=[{"claim_id": 1, "setup_matches_question": True}])
    revise = call("revise_claim", claim_id=1, text="strict is off", citations=[{"path": "src/toylib/core.py", "line": 88}])
    agent, client, _ = make([draft, PROBE, assess, revise, PROBE, FINAL], [report(**FAIL), report()], CAUSAL)
    out = agent.answer("q?")
    assert out["conflicts"][0]["doc_says"] == "the docs say strict is on"
    assert out["conflicts"][0]["decided_at"] == "src/toylib/core.py:88"


def test_doc_claims_verified_first():
    table = ClaimTable()
    from agent.claim_table import ClaimIn
    table.add_draft([ClaimIn(text="code claim"), ClaimIn(text="doc claim", source_kind="doc"),
                     ClaimIn(text="why", behavioural=False)])
    assert [c.text for c in table.prioritised()] == ["doc claim", "code claim"]
    assert table.claims[2].status == "non_behavioural"


def test_non_causal_citation_reinvestigated_and_replaced():
    propose = call("propose_citation", claim_id=1, path="src/toylib/core.py", line=16)
    agent, client, reg = make([DRAFT, PROBE, propose, FINAL], [report()], {("src/toylib/core.py", 16): True})
    out = agent.answer("q?")
    c = out["claims"][0]
    assert c["citations"] == [{"path": "src/toylib/core.py", "line": 16, "causal": True}] and c["grade"] == "E+C"


def test_some_causal_citations_drop_the_rest():
    claim = dict(CLAIM, citations=[{"path": "a.py", "line": 1}, {"path": "src/toylib/core.py", "line": 88}])
    agent, _, _ = make([call("submit_draft", answer="d", claims=[claim]), PROBE, FINAL], [report()], CAUSAL)
    out = agent.answer("q?")
    assert [x["line"] for x in out["claims"][0]["citations"]] == [88] and out["claims"][0]["grade"] == "E+C"


def test_no_causal_line_found_keeps_grade_e():
    propose = call("propose_citation", claim_id=1, path="src/toylib/core.py", line=16)
    agent, client, _ = make([DRAFT, PROBE, propose, propose, FINAL], [report()], {})
    agent._vacuity = lambda *a: SimpleNamespace(vacuous=False)
    out = agent.answer("q?")
    assert out["claims"][0]["grade"] == "E" and not out["flagged_uncertain"]


def test_vacuous_probe_regenerated_once():
    propose = call("propose_citation", claim_id=1, path="src/toylib/core.py", line=88)
    agent, client, reg = make([DRAFT, PROBE, propose, propose, PROBE, FINAL], [report(), report()], {})
    calls = []
    agent._vacuity = lambda *a: (calls.append(a), SimpleNamespace(vacuous=True))[1]
    out = agent.answer("q?")
    assert len(calls) == 1 and out["probe_runs"] == 2 and out["claims"][0]["status"] == "confirmed"


def test_a1_no_execution_verifies_by_reading():
    verify = call("verify_by_reading", verdicts=[{"claim_id": 1, "supported": True}])
    agent, client, reg = make([DRAFT, verify, FINAL], ablation={"no_execution": True})
    out = agent.answer("q?")
    assert out["probe_runs"] == 0 and reg.mutated == []
    assert out["claims"][0]["status"] == "read_supported" and out["claims"][0]["grade"] == "R"
    assert not out["flagged_uncertain"]


def test_a2_no_mutation_grades_e():
    agent, client, reg = make([DRAFT, PROBE, FINAL], [report()], CAUSAL, ablation={"no_mutation": True})
    out = agent.answer("q?")
    assert reg.mutated == [] and out["claims"][0]["grade"] == "E" and out["claims"][0]["citations"][0]["causal"] is None


def test_a3_flag_only_never_reinvestigates():
    assess = call("assess_refutation", assessments=[{"claim_id": 1, "setup_matches_question": True}])
    agent, client, _ = make([DRAFT, PROBE, assess, FINAL], [report(**FAIL)], ablation={"flag_only": True})
    out = agent.answer("q?")
    assert out["claims"][0]["status"] == "refuted" and out["flagged_uncertain"] and out["claims"][0]["grade"] is None


def test_a3_non_causal_is_not_reinvestigated():
    agent, client, _ = make([DRAFT, PROBE, FINAL], [report()], {}, ablation={"flag_only": True})
    out = agent.answer("q?")
    assert out["claims"][0]["grade"] == "E" and out["claims"][0]["citations"][0]["causal"] is False


def test_a2_a3_share_full_agent_prefix():
    """Identical requests up to the point of divergence are what make them free through the cache."""
    runs = []
    for ab in ({}, {"no_mutation": True}, {"flag_only": True}):
        agent, client, _ = make([DRAFT, PROBE, FINAL], [report()], CAUSAL, ablation=ab)
        agent.answer("q?")
        runs.append(client.calls[:2])
    assert runs[0] == runs[1] == runs[2]


def test_a4_whole_answer_probe_merges_claims():
    draft = call("submit_draft", answer="whole", claims=[CLAIM, dict(CLAIM, text="second")])
    agent, _, _ = make([draft, PROBE, FINAL], [report()], CAUSAL, ablation={"whole_answer_probe": True})
    out = agent.answer("q?")
    assert len(out["claims"]) == 1 and out["claims"][0]["text"] == "whole"


def test_a5_selective_probes_doc_claims_only():
    draft = call("submit_draft", answer="d", claims=[CLAIM, dict(CLAIM, text="doc", source_kind="doc")])
    probe = call("write_probe", probes=[{"claim_id": 2, "code": "p"}])
    agent, _, _ = make([draft, probe, FINAL], [report()], CAUSAL, ablation={"selective": True})
    out = agent.answer("q?")
    assert [c["status"] for c in out["claims"]] == ["skipped", "confirmed"] and not out["flagged_uncertain"]


def test_a7_llm_conflict_can_follow_docs():
    draft = call("submit_draft", answer="d", claims=[dict(CLAIM, source_kind="doc")])
    assess = call("assess_refutation", assessments=[{"claim_id": 1, "setup_matches_question": True}])
    resolve = call("resolve_conflict", claim_id=1, follow="docs")
    agent, _, _ = make([draft, PROBE, assess, resolve, FINAL], [report(**FAIL)], ablation={"llm_conflicts": True})
    out = agent.answer("q?")
    assert out["claims"][0]["status"] == "read_supported" and out["claims"][0]["grade"] == "D"


def test_a8_no_repair():
    broken = dict(status="error", outcome={"kind": "raise", "type": "NameError", "innermost_frame": "claim.py:3"})
    agent, _, _ = make([DRAFT, PROBE, FINAL], [report(**broken)], ablation={"no_repair": True})
    assert agent.answer("q?")["claims"][0]["status"] == "unverified"


def test_request_cap_keeps_one_for_the_final_answer():
    open_call = call("open_file", path="x")
    agent, client, _ = make([open_call] * 3 + [FINAL], max_requests_per_question=4)
    out = agent.answer("q?")
    assert out["requests"] == 4 and out["answer_text"] == "final text" and out["flagged_uncertain"]


def test_invalid_terminal_arguments_are_reported_and_counted():
    bad = call("submit_draft", answer="no claims field")
    agent, client, reg = make([bad, DRAFT, PROBE, FINAL], [report()], CAUSAL)
    out = agent.answer("q?")
    assert out["tool_calls"]["invalid"] == 1 and out["claims"][0]["status"] == "confirmed"


def test_model_with_no_tool_call_is_nudged():
    nothing = Reply(text="hmm", tool_calls=[], usage=Usage(), provider="gemini", model="fake")
    agent, client, _ = make([nothing, DRAFT, PROBE, FINAL], [report()], CAUSAL)
    assert agent.answer("q?")["tool_calls"]["invalid"] == 1


@pytest.mark.parametrize("status,citations,expected", [
    ("confirmed", [Citation("a", 1, True)], "E+C"),
    ("confirmed", [Citation("a", 1, True), Citation("a", 2, False)], "E"),
    ("confirmed", [], "E"),
    ("confirmed", [Citation("a", 1, None)], "E"),
    ("refuted", [], None),
    ("unverified", [], "R"),
])
def test_grades(status, citations, expected):
    assert grade(Claim(1, "t", status=status, citations=citations)) == expected


def test_grades_other_kinds():
    assert grade(Claim(1, "t", status="unverified", source_kind="doc")) == "D"
    assert grade(Claim(1, "t", status="unverified", test_passed=True)) == "T"
    assert grade(Claim(1, "t", status="confirmed"), no_execution=True) == "R"


def test_stop_rules():
    table = ClaimTable()
    assert flagged_uncertain(table)
    table.claims.append(Claim(1, "t", status="confirmed", citations=[Citation("a", 1, True)]))
    assert all_settled(table) and not flagged_uncertain(table)
    table.claims.append(Claim(2, "t", status="unverified"))
    assert not all_settled(table) and flagged_uncertain(table)
