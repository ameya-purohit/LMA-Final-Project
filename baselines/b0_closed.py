"""B0, closed book: one call, question only. Measures what the model already remembers."""

from __future__ import annotations

from typing import Any

from baselines.common import load_prompt, one_shot


def run(question: str, workspace: Any, client: Any, config: dict[str, Any], tracer: Any = None) -> dict[str, Any]:
    return one_shot(load_prompt("closed").format(question=question), workspace, client, config, tracer)
