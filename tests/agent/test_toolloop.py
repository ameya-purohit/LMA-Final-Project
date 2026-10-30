from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from agent.toolloop import MeteredClient, OutOfRequests, StepBudget, ToolLoop
from llm.types import Message, Reply, ToolCall, Usage
from tools.registry import ToolRegistry, ToolResult


class Done(BaseModel):
    text: str


TERMINAL = {"done": ("finish", Done)}


def reply(*calls, cached=False):
    return Reply("", [ToolCall(f"{i}", n, a) for i, (n, a) in enumerate(calls)], Usage(3, 2, 0, 0, 5), from_cache=cached)


class Client:
    def __init__(self, replies):
        self.replies = list(replies)
        self.tools = []

    def complete(self, messages, tools, **params):
        self.tools.append(params["allowed_tools"])
        return self.replies.pop(0)


def registry():
    reg = ToolRegistry(SimpleNamespace(package="p"))
    for name in ("open_file", "run_probe"):
        desc, model, _ = reg._tools[name]
        reg._tools[name] = (desc, model, lambda a, n=name: ToolResult(n, f"{n} ran"))
    return reg


def loop(replies, max_requests=25, **kw):
    client = Client(replies)
    llm = MeteredClient(client, max_requests)
    return ToolLoop(llm, registry(), **kw), llm, client


def test_metered_client_counts_cached_separately_and_enforces_cap():
    llm = MeteredClient(Client([reply(), reply(cached=True)]), 2)
    llm.complete([], None, allowed_tools=[])
    llm.complete([], None, allowed_tools=[])
    assert llm.requests == 2 and llm.api_requests == 1 and llm.usage.total == 10
    with pytest.raises(OutOfRequests):
        llm.complete([], None, allowed_tools=[])


def test_read_tool_uses_step_execution_tool_does_not():
    tl, llm, client = loop([reply(("open_file", {"path": "x"})), reply(("run_probe", {"code": "c"})), reply(("done", {"text": "t"}))])
    steps = StepBudget(8)
    history = [Message(role="user", content="q")]
    out = tl.run(history, ("open_file", "run_probe"), TERMINAL, steps)
    assert out.name == "done" and out.parsed.text == "t"
    assert steps.used == 1, "a turn that only runs a probe must not use an investigation step"
    assert [m.role for m in history].count("tool") == 3


def test_read_tools_removed_when_steps_run_out_execution_stays():
    tl, _, client = loop([reply(("open_file", {"path": "x"})), reply(("done", {"text": "t"}))])
    tl.run([], ("open_file", "run_probe"), TERMINAL, StepBudget(1))
    assert "open_file" in client.tools[0] and client.tools[1] == ["run_probe", "done"]


def test_too_many_calls_in_a_turn_are_skipped():
    calls = [("open_file", {"path": str(i)}) for i in range(5)]
    tl, _, _ = loop([reply(*calls), reply(("done", {"text": "t"}))], max_tools_per_turn=3)
    history = []
    tl.run(history, ("open_file",), TERMINAL, StepBudget(8))
    results = [m.content for m in history if m.role == "tool"]
    assert sum("Skipped" in r for r in results) == 2 and sum("ran" in r for r in results) == 3


def test_every_call_in_a_turn_gets_a_response_when_terminal_is_mixed_in():
    """Gemini requires a response for every function call of a turn."""
    tl, _, _ = loop([reply(("done", {"text": "t"}), ("open_file", {"path": "x"}))])
    history = []
    tl.run(history, ("open_file",), TERMINAL, StepBudget(8))
    assert len([m for m in history if m.role == "tool"]) == 2


def test_reserve_stops_before_the_last_request():
    tl, llm, _ = loop([reply(("open_file", {"path": "x"}))], max_requests=2)
    out = tl.run([], ("open_file",), TERMINAL, StepBudget(8), reserve=1)
    assert out.parsed is None and out.stopped_by == "requests" and llm.requests == 1


def test_gives_up_after_repeated_no_call():
    tl, _, _ = loop([reply(), reply(), reply()])
    out = tl.run([], ("open_file",), TERMINAL, StepBudget(8))
    assert out.stopped_by == "no_call" and out.parsed is None
