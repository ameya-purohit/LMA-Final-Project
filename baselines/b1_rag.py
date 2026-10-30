"""B1, direct RAG: one call with the same starting material every system gets.
Isolates the value of any investigation at all."""

from __future__ import annotations

from typing import Any

from agent.output import starting_material
from baselines.common import load_prompt, one_shot


def run(question: str, workspace: Any, client: Any, config: dict[str, Any], tracer: Any = None) -> dict[str, Any]:
    material = starting_material(workspace, question, config)
    return one_shot(load_prompt("rag").format(question=question, material=material), workspace, client, config, tracer)
