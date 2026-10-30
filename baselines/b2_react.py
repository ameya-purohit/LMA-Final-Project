"""B2, ReAct with all the same tools, including `run_probe` and `mutate_and_run`.

The key baseline: with identical tools and limits, any difference from our agent
comes from how the tools are used, which is what RQ1 asks. B2+ is this file with
`baselines.b2_extra_steps` set in config, not new code.
"""

from __future__ import annotations

from typing import Any

from agent.output import starting_material
from agent.toolloop import StepBudget
from baselines.common import FINAL, finish, load_prompt, make_parts, system_message
from llm.types import Message
from tools.registry import ToolRegistry

ALL_TOOLS = ToolRegistry.READ_ONLY + ToolRegistry.EXECUTION


def react(question: str, workspace: Any, llm: Any, registry: Any, loop: Any, config: dict[str, Any]) -> tuple[Any, StepBudget]:
    ag = config["agent"]
    steps = StepBudget(ag["max_investigation_steps"] + config.get("baselines", {}).get("b2_extra_steps", 0))
    prompt = load_prompt("react").format(question=question, material=starting_material(workspace, question, config),
                                         steps=steps.total, probe_runs=ag["max_probe_runs"], package=workspace.package)
    history = [system_message(), Message(role="user", content=prompt)]
    out = loop.run(history, ALL_TOOLS, FINAL, steps, reserve=1)
    if out.parsed is None:
        # The request limit is near: the last request must be the answer, as for our agent.
        history.append(Message(role="user", content="The budget is used up. Call final_answer now."))
        out = loop.run(history, (), FINAL, steps, reserve=0)
    return out, steps


def run(question: str, workspace: Any, client: Any, config: dict[str, Any], tracer: Any = None) -> dict[str, Any]:
    llm, registry, loop = make_parts(workspace, client, config, tracer)
    out, steps = react(question, workspace, llm, registry, loop, config)
    return finish(out, llm, registry, steps, workspace)
