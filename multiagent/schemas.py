"""Typed messages between the agents (exploratory extension). Each is the argument schema of a function tool the
model must call, validated with pydantic; an invalid call is returned to the model and counted, as in the locked
agent. Agents never talk to each other in free text: the orchestrator passes these objects along."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Location(BaseModel):
    path: str = Field(description="Repository-relative path, e.g. src/click/core.py")
    line: int = Field(ge=1, description="Line number in the frozen code")


class Hypothesis(BaseModel):
    id: str = Field(description="H1, H2, ...")
    statement: str = Field(description="What in the code causes the reported behaviour, if this hypothesis is right")
    locations: list[Location] = Field(default_factory=list, description="Lines this hypothesis blames (at most 3)")
    symbols: list[str] = Field(default_factory=list, description="Functions or methods it blames, e.g. Option.get_default")
    predicts: str = Field(default="", description="An observable consequence that would distinguish it from the others")


class Investigation(BaseModel):
    """Bug Investigator -> everyone."""
    expected_behaviour: str = Field(description="What the reporter expected")
    actual_behaviour: str = Field(description="What the reporter says happens instead")
    scenario: str = Field(description="A minimal way to trigger it with the library's public API")
    hypotheses: list[Hypothesis] = Field(min_length=1, max_length=4, description="2-4 competing causal hypotheses")


class DistinguishingProbe(BaseModel):
    hypothesis_id: str
    code: str = Field(description="A probe (observe() and test_claim()) whose outcome differs if this hypothesis is right")


class Probes(BaseModel):
    """Probe Engineer -> Experiment Engineer."""
    reproduce: str = Field(description="Probe whose observe() runs the reported scenario and whose test_claim() "
                                       "asserts the behaviour the issue reports")
    controls: list[str] = Field(min_length=1, max_length=2, description="1-2 probes of nearby ordinary behaviour "
                                                                        "that should not change if the cause is fixed")
    boundary: str = Field(default="", description="Optional probe at the edge of the scenario (empty if none)")
    distinguishing: list[DistinguishingProbe] = Field(default_factory=list, max_length=2)


class Candidate(BaseModel):
    path: str
    line: int = Field(ge=1)
    why: str = Field(default="", description="One short reason")


class Ranking(BaseModel):
    """Code Analyst -> Experiment Engineer: suspicious lines, most suspicious first."""
    candidates: list[Candidate] = Field(min_length=1, max_length=8)


class HypothesisVerdict(BaseModel):
    id: str
    verdict: Literal["accepted", "rejected", "inconclusive"]
    reason: str = ""


class VerifiedClaim(BaseModel):
    text: str
    citations: list[Location] = Field(default_factory=list, max_length=3)


class Patch(BaseModel):
    path: str = ""
    line: int = 0
    new_text: str = Field(default="", description="The replacement for that one line (empty for no patch)")


class Verdict(BaseModel):
    """Causal Verifier -> final answer."""
    hypotheses: list[HypothesisVerdict] = Field(default_factory=list)
    answer_text: str = Field(description="The answer to the developer's question, from the evidence")
    claims: list[VerifiedClaim] = Field(default_factory=list, max_length=5)
    patch: Patch = Field(default_factory=Patch)
    flagged_uncertain: bool = False
    abstained: bool = False
