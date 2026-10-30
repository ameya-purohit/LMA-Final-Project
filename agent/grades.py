"""Deterministic evidence grades (proposal §6.5). No LLM decides a grade.

[E+C] confirmed by a probe, and every citation is causal
[E]   confirmed by a probe
[T]   a cited repository test was run in the sandbox and passed
[R]   read in code only
[D]   stated only in documentation

[E] and [T] rank equally; if they disagree, that is a conflict to investigate.
A refuted or still-unverified claim gets its reading grade at most, and the code
assembling the answer flags it, so it is never stated as fact.
"""

from __future__ import annotations

from agent.claim_table import Claim

RANK = {"E+C": 1, "E": 2, "T": 2, "R": 3, "D": 4}


def grade(claim: Claim, *, no_execution: bool = False) -> str | None:
    if claim.status == "refuted":
        return None
    if no_execution:
        return "D" if claim.source_kind == "doc" else "R"
    if claim.status == "confirmed":
        cited = [c for c in claim.citations if c.causal is not None]
        if claim.citations and cited and len(cited) == len(claim.citations) and all(c.causal for c in cited):
            return "E+C"
        return "E"
    if claim.test_passed:
        return "T"
    return "D" if claim.source_kind == "doc" else "R"


def apply_grades(claims: list[Claim], *, no_execution: bool = False) -> None:
    for c in claims:
        c.grade = grade(c, no_execution=no_execution)
