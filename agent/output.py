"""Things every system shares at its edges: starting material and the output schema (CLAUDE.md §6.8)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"


def load_prompt(name: str) -> str:
    return (PROMPT_DIR / f"{name}.txt").read_text(encoding="utf-8")


def prompt_hashes() -> dict[str, str]:
    """Hash of every prompt file; gate G2 records these in PREREGISTRATION.md."""
    return {p.stem: hashlib.sha256(p.read_bytes()).hexdigest()[:16] for p in sorted(PROMPT_DIR.glob("*.txt"))}


def starting_material(workspace: Any, question_text: str, config: dict[str, Any], *, override: str | None = None) -> str:
    """The same top-5 code and top-3 doc chunks for every system (A10 changes it through config)."""
    from retrieval.index import format_starting_material
    if override is not None:
        return override
    mode = config.get("agent", {}).get("ablation", {}).get("retrieval", "standard")
    if mode == "none":
        return "(no starting material; use the search tools)"
    r = config.get("retrieval", {})
    code, docs = workspace.index.starting_material(question_text, r.get("code_top_k", 5), r.get("doc_top_k", 3))
    return format_starting_material(code, docs)


def assemble(*, answer_text: str, claims: list[dict[str, Any]], conflicts: list[dict[str, Any]], flagged_uncertain: bool,
             abstained: bool, llm: Any, registry: Any, steps: int, workspace: Any = None, extra: dict[str, Any] | None = None
             ) -> dict[str, Any]:
    """The shared output schema, built in code rather than by the model."""
    counts = registry.counts
    session = getattr(workspace, "_session", None) if workspace is not None else None
    result = {
        "answer_text": answer_text, "claims": claims, "conflicts": conflicts,
        "flagged_uncertain": flagged_uncertain, "abstained": abstained,
        "tokens": {"input": llm.usage.input, "output": llm.usage.output, "cached": llm.usage.cached,
                   "thinking": llm.usage.thinking, "total": llm.usage.total},
        "requests": llm.requests, "api_requests": llm.api_requests,
        "steps": steps, "probe_runs": counts["probe_runs"], "mutant_runs": counts["mutant_runs"],
        "cpu_seconds": round(float(getattr(session, "cpu_seconds", 0.0)), 3),
        "tool_calls": {k: counts[k] for k in ("total", "invalid", "errors", "recovered")},
        "unsafe_attempts": counts["unsafe_attempts"],
    }
    result.update(extra or {})
    return result
