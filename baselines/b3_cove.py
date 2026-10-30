"""B3, ReAct then Chain-of-Verification (Dhuliawala et al.): verification by reading.

B2's answer; then write verification questions; answer each independently with
read-only tools, without seeing the draft; then revise. This tests verifying by
reading against verifying by execution. B2's part is identical to B2, so with the
cache it costs no extra quota when B2 has already run.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from agent.toolloop import StepBudget
from baselines.b2_react import react
from baselines.common import FINAL, finish, load_prompt, make_parts, system_message
from llm.types import Message
from tools.registry import ToolRegistry

MAX_QUESTIONS = 3
STEPS_PER_QUESTION = 2


class VerificationQuestions(BaseModel):
    questions: list[str] = Field(description="Short questions that check the draft's facts")


class VerificationAnswer(BaseModel):
    answer: str
    path: str = ""
    line: int = 0


def run(question: str, workspace: Any, client: Any, config: dict[str, Any], tracer: Any = None) -> dict[str, Any]:
    llm, registry, loop = make_parts(workspace, client, config, tracer)
    out, steps = react(question, workspace, llm, registry, loop, config)
    draft = out.parsed.answer_text if out.parsed else ""
    if not draft or llm.remaining <= 2:
        return finish(out, llm, registry, steps, workspace)
    history = [system_message(), Message(role="user", content=load_prompt("cove_questions").format(
        question=question, answer=draft, n=MAX_QUESTIONS))]
    q_out = loop.run(history, (), {"write_verification_questions": ("Plan the verification.", VerificationQuestions)},
                     StepBudget(0), reserve=1)
    answers = []
    for q in (q_out.parsed.questions if q_out.parsed else [])[:MAX_QUESTIONS]:
        if llm.remaining <= 1:
            break
        hist = [system_message(), Message(role="user", content=load_prompt("cove_answer").format(
            question=q, steps=STEPS_PER_QUESTION))]
        a = loop.run(hist, ToolRegistry.READ_ONLY, {"answer_verification": ("Answer the verification question.", VerificationAnswer)},
                     StepBudget(STEPS_PER_QUESTION), reserve=1)
        if a.parsed is not None:
            answers.append(f"Q: {q}\nA: {a.parsed.answer} (at {a.parsed.path}:{a.parsed.line})")
    revise = [system_message(), Message(role="user", content=load_prompt("cove_revise").format(
        question=question, answer=draft, verification="\n\n".join(answers) or "(no verification completed)"))]
    final = loop.run(revise, (), FINAL, StepBudget(0), reserve=0)
    return finish(final if final.parsed else out, llm, registry, steps, workspace, extra={"verification": answers})
