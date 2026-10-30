"""The hand-written tool-calling loop shared by our agent and the baselines.

One turn: send the history and the allowed tools, append the model's reply, run
each tool it called, and append the results. The loop ends when the model calls a
*terminal* tool (a structured output such as `submit_draft` or `final_answer`)
with valid arguments, or when the question's limits are reached.

Limits live here so every system obeys the same ones: at most 8 investigation
steps (model turns that use a read-only tool) and a cap on requests per question.
Execution tools have their own budgets in the registry, so a turn that only runs
a probe costs no investigation step, for ours and for B2 alike.
No framework: this file is the whole agent loop, on purpose (CLAUDE.md §2.1).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError

from llm.types import Message, Reply, Usage
from tools.registry import ToolRegistry, tool_spec


class OutOfRequests(Exception):
    """The per-question request limit is reached."""


class MeteredClient:
    """Wraps the LLM client for one question: counts requests and tokens, enforces the cap.

    `requests` counts every logical call (what a run from an empty cache would
    cost); `api_requests` counts those that really reached the API. Both are reported.
    """

    def __init__(self, client: Any, max_requests: int):
        self.client = client
        self.max_requests = max_requests
        self.requests = 0
        self.api_requests = 0
        self.usage = Usage()

    @property
    def remaining(self) -> int:
        return self.max_requests - self.requests

    def complete(self, messages: list[Message], tools: list[Any] | None = None, **params: Any) -> Reply:
        if self.remaining <= 0:
            raise OutOfRequests(f"request limit {self.max_requests} reached")
        reply = self.client.complete(messages, tools, **params)
        self.requests += 1
        self.api_requests += 0 if reply.from_cache else 1
        self.usage = self.usage + reply.usage
        return reply


@dataclass
class StepBudget:
    """Investigation steps, shared across the whole question."""
    total: int
    used: int = 0

    @property
    def left(self) -> int:
        return self.total - self.used


@dataclass
class LoopResult:
    name: str | None = None           # the terminal tool that ended the loop, or None
    args: dict[str, Any] = field(default_factory=dict)
    parsed: Any = None                # the validated pydantic object
    turns: int = 0
    stopped_by: str = "terminal"      # terminal | requests | no_call


class ToolLoop:
    def __init__(self, llm: MeteredClient, registry: ToolRegistry, *, max_tools_per_turn: int = 3, tracer: Any = None):
        self.llm = llm
        self.registry = registry
        self.max_tools_per_turn = max_tools_per_turn
        self.tracer = tracer

    def run(self, history: list[Message], tools: tuple[str, ...], terminals: dict[str, tuple[str, type[BaseModel]]],
            steps: StepBudget, *, reserve: int = 0) -> LoopResult:
        """Run turns until a terminal tool is called. `history` is extended in place.

        When the steps run out, the read-only tools disappear, so the model must
        conclude. `reserve` keeps that many requests back for later stages.
        """
        result = LoopResult()
        nudges = 0
        while True:
            if self.llm.remaining <= reserve:
                result.stopped_by = "requests"
                return result
            allowed = [t for t in tools if steps.left > 0 or t not in ToolRegistry.READ_ONLY]
            specs = self.registry.specs(allowed) + [tool_spec(n, d, m) for n, (d, m) in terminals.items()]
            names = allowed + list(terminals)
            reply = self.llm.complete(history, specs, force_tool=True, allowed_tools=names)
            result.turns += 1
            history.append(reply.as_message())
            if not reply.tool_calls:
                nudges += 1
                self.registry.counts["invalid"] += 1
                if nudges > 2:
                    result.stopped_by = "no_call"
                    return result
                history.append(Message(role="user", content=f"You must call one of these tools: {', '.join(names)}."))
                continue
            used_step = False
            done = False
            for i, call in enumerate(reply.tool_calls):
                if call.name in terminals and not done:
                    _, model = terminals[call.name]
                    self.registry.counts["total"] += 1
                    try:
                        parsed = model.model_validate(call.arguments)
                    except ValidationError as exc:
                        self.registry.counts["invalid"] += 1
                        problems = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
                        history.append(self._tool_msg(call, f"Invalid arguments: {problems}. Call {call.name} again."))
                        continue
                    result.name, result.args, result.parsed = call.name, call.arguments, parsed
                    done = True
                    history.append(self._tool_msg(call, "Received."))
                elif call.name in terminals or i >= self.max_tools_per_turn:
                    history.append(self._tool_msg(call, "Skipped: too many tool calls in one turn."))
                else:
                    out = self.registry.call(call.name, call.arguments)
                    used_step = used_step or call.name in ToolRegistry.READ_ONLY
                    history.append(self._tool_msg(call, out.text))
            if used_step:
                steps.used += 1
            if done:
                return result

    @staticmethod
    def _tool_msg(call: Any, text: str) -> Message:
        return Message(role="tool", name=call.name, tool_call_id=call.id, content=text)
