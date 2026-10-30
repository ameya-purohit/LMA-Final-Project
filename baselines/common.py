"""What the baselines share: the `final_answer` tool and turning its arguments into the output schema.

Every baseline ends with `final_answer` and may flag or abstain, like our agent.
Grades are ours alone, so baselines report no grade. A baseline's citation is
marked causal only if it actually ran `mutate_and_run` on that line (B2 may).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from agent.claim_table import ClaimIn
from agent.output import assemble
from agent.toolloop import LoopResult, MeteredClient, StepBudget, ToolLoop
from llm.types import Message
from tools.registry import Budget, ToolRegistry

PROMPTS = Path(__file__).resolve().parent / "prompts"


def load_prompt(name: str) -> str:
    return (PROMPTS / f"{name}.txt").read_text(encoding="utf-8")


class ConflictIn(BaseModel):
    doc_says: str = ""
    execution_shows: str = ""
    decided_at: str = ""


class BaselineClaim(ClaimIn):
    observed_output: str = Field(default="", description="What running the code showed, if it was run")


class BaselineFinal(BaseModel):
    answer_text: str = Field(description="The final answer to the question")
    claims: list[BaselineClaim] = Field(default_factory=list, description="The answer's atomic claims (at most 5)")
    conflicts: list[ConflictIn] = Field(default_factory=list, description="Places where docs and behaviour disagree")
    flagged_uncertain: bool = Field(default=False, description="True if you are not confident in the answer")
    abstained: bool = Field(default=False, description="True if you cannot answer")


FINAL = {"final_answer": ("Give the final answer and its atomic claims.", BaselineFinal)}


def make_parts(workspace: Any, client: Any, config: dict[str, Any], tracer: Any = None) -> tuple[MeteredClient, ToolRegistry, ToolLoop]:
    ag = config["agent"]
    llm = MeteredClient(client, ag["max_requests_per_question"])
    registry = ToolRegistry(workspace, budget=Budget(ag["max_probe_runs"], ag["max_mutation_checks"]), tracer=tracer)
    return llm, registry, ToolLoop(llm, registry, max_tools_per_turn=ag["max_tools_per_turn"], tracer=tracer)


def system_message() -> Message:
    from agent.output import load_prompt as agent_prompt
    return Message(role="system", content=agent_prompt("system"))


def finish(out: LoopResult, llm: MeteredClient, registry: ToolRegistry, steps: StepBudget, workspace: Any,
           extra: dict[str, Any] | None = None) -> dict[str, Any]:
    final: BaselineFinal | None = out.parsed
    log = registry.mutation_log
    claims = []
    for c in (final.claims if final else [])[:5]:
        claims.append({"text": c.text, "grade": None, "scope": c.scope, "source_kind": c.source_kind, "status": "unchecked",
                       "citations": [{"path": x.path, "line": x.line, "causal": log.get((x.path, x.line))} for x in c.citations],
                       "observed_output": c.observed_output})
    return assemble(
        answer_text=final.answer_text if final else "",
        claims=claims, conflicts=[c.model_dump() for c in final.conflicts] if final else [],
        flagged_uncertain=bool(final.flagged_uncertain) if final else True,
        abstained=bool(final.abstained) if final else True,
        llm=llm, registry=registry, steps=steps.used, workspace=workspace, extra=extra)


def one_shot(prompt: str, workspace: Any, client: Any, config: dict[str, Any], tracer: Any = None) -> dict[str, Any]:
    """B0 and B1: exactly one request, forced to end with final_answer."""
    llm, registry, loop = make_parts(workspace, client, config, tracer)
    steps = StepBudget(0)
    out = loop.run([system_message(), Message(role="user", content=prompt)], (), FINAL, steps)
    return finish(out, llm, registry, steps, workspace)
