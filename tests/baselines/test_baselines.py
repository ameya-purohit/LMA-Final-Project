"""Baselines with a scripted LLM: shared schema, limits, and only control logic differing."""

from types import SimpleNamespace

import pytest

from baselines import b0_closed, b1_rag, b2_react, b3_cove
from core.config import diff, load_config
from llm.types import Reply, ToolCall, Usage

SCHEMA_KEYS = {"answer_text", "claims", "conflicts", "flagged_uncertain", "abstained", "tokens", "requests", "api_requests",
               "steps", "probe_runs", "mutant_runs", "cpu_seconds", "tool_calls", "unsafe_attempts"}


def call(name, **args):
    return Reply("", [ToolCall(name, name, args)], Usage(10, 5, 0, 0, 15), provider="gemini", model="fake")


FINAL = call("final_answer", answer_text="the answer", flagged_uncertain=True,
             claims=[{"text": "c", "citations": [{"path": "src/p/a.py", "line": 3}], "observed_output": "5"}])


class Scripted:
    def __init__(self, replies):
        self.replies = list(replies)
        self.seen = []

    def complete(self, messages, tools, **params):
        self.seen.append({"messages": list(messages), "tools": [t.name for t in tools or []]})
        return self.replies.pop(0)


class FakeIndex:
    def starting_material(self, q, a, b):
        return [], []


@pytest.fixture
def ws(tmp_path):
    return SimpleNamespace(package="p", index=FakeIndex(), tree=tmp_path, resolve=lambda p: tmp_path / p)


def test_b0_one_call_no_repository(ws):
    client = Scripted([FINAL])
    out = b0_closed.run("what?", ws, client, load_config())
    assert out["requests"] == 1 and client.seen[0]["tools"] == ["final_answer"]
    assert SCHEMA_KEYS <= set(out) and out["answer_text"] == "the answer" and out["flagged_uncertain"]
    assert out["claims"][0]["grade"] is None and out["claims"][0]["citations"][0]["causal"] is None
    assert "Material retrieved" not in client.seen[0]["messages"][1].content


def test_b1_one_call_with_starting_material(ws):
    client = Scripted([FINAL])
    out = b1_rag.run("what?", ws, client, load_config())
    assert out["requests"] == 1 and "Material retrieved" in client.seen[0]["messages"][1].content


def test_b2_has_every_tool_and_ends_with_final(ws):
    client = Scripted([call("open_file", path="missing.py"), FINAL])
    out = b2_react.run("what?", ws, client, load_config())
    tools = client.seen[0]["tools"]
    assert {"run_probe", "mutate_and_run", "run_repo_test", "search_code", "final_answer"} <= set(tools)
    assert out["steps"] == 1 and out["requests"] == 2 and SCHEMA_KEYS <= set(out)


def test_b2_is_forced_to_answer_when_requests_run_out(ws):
    cfg = load_config([{"agent": {"max_requests_per_question": 3}}])
    client = Scripted([call("open_file", path="x"), call("open_file", path="x"), FINAL])
    out = b2_react.run("what?", ws, client, cfg)
    assert out["requests"] == 3 and out["answer_text"] == "the answer" and client.seen[-1]["tools"] == ["final_answer"]


def test_b2_plus_is_config_only(ws):
    base = load_config()
    plus = load_config([{"baselines": {"b2_extra_steps": 2}}])
    assert diff(base, plus) == {"baselines.b2_extra_steps": (0, 2)}
    replies = [call("open_file", path="x")] * 10 + [FINAL]
    client = Scripted(replies)
    out = b2_react.run("what?", ws, client, plus)
    assert out["steps"] == 10 and client.seen[-1]["tools"].count("open_file") == 0


def test_b3_verifies_by_reading_then_revises(ws):
    client = Scripted([FINAL,
                       call("write_verification_questions", questions=["q1", "q2"]),
                       call("answer_verification", answer="a1", path="a.py", line=1),
                       call("answer_verification", answer="a2"),
                       call("final_answer", answer_text="revised")])
    out = b3_cove.run("what?", ws, client, load_config())
    assert out["answer_text"] == "revised" and len(out["verification"]) == 2 and out["requests"] == 5
    assert "run_probe" not in client.seen[2]["tools"], "CoVe verifies by reading only"
    assert "the answer" not in client.seen[2]["messages"][1].content, "verification must not see the draft"


def test_mutation_verdict_flows_to_citation(ws):
    client = Scripted([FINAL])
    from baselines.common import make_parts, one_shot
    out = one_shot("q", ws, client, load_config())
    assert out["claims"][0]["citations"][0]["causal"] is None
    _, reg, _ = make_parts(ws, Scripted([]), load_config())
    reg.mutation_log[("src/p/a.py", 3)] = True
    assert reg.mutation_log[("src/p/a.py", 3)]


def test_empty_final_abstains(ws):
    nothing = Reply("", [], Usage())
    client = Scripted([nothing, nothing, nothing])
    out = b0_closed.run("q", ws, client, load_config())
    assert out["abstained"] and out["flagged_uncertain"] and out["answer_text"] == ""
