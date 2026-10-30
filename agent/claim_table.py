"""The claim table: the agent's explicit working state.

Each claim records what is claimed, what it cites, how it was checked, and with
what result. Making this state explicit is what lets us measure every component,
ablate it, and read a trace afterwards (proposal §6.4). The structured tool
arguments the model must produce are pydantic models here too.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field

Status = Literal["unverified", "confirmed", "refuted", "non_behavioural", "skipped", "read_supported"]


# ---------------------------------------------------- what the model must call
class CitationIn(BaseModel):
    path: str = Field(description="File path relative to the repository root")
    line: int = Field(ge=1, description="The single line that decides the claim")


class ClaimIn(BaseModel):
    text: str = Field(description="One atomic, checkable statement about what the frozen code does")
    scope: Literal["instance", "general"] = Field(default="instance", description="One case, or a general rule")
    behavioural: bool = Field(default=True, description="False only if it cannot be executed (e.g. design rationale)")
    source_kind: Literal["code", "doc", "test"] = Field(default="code", description="What supports the claim so far")
    citations: list[CitationIn] = Field(default_factory=list)
    test_node: str = Field(default="", description="Optional: a repository test (pytest node id) that asserts this")


class SubmitDraft(BaseModel):
    answer: str = Field(description="Draft answer to the question")
    claims: list[ClaimIn] = Field(description="The draft split into atomic claims (at most 5)")


class ProbeIn(BaseModel):
    claim_id: int
    code: str = Field(description="Python file defining observe() and test_claim()")
    controls: list[str] = Field(default_factory=list, description="1-2 control probes: same entry point, unrelated inputs")


class WriteProbe(BaseModel):
    probes: list[ProbeIn]


class AssessmentIn(BaseModel):
    claim_id: int
    setup_matches_question: bool = Field(description="Does the probe's setup match the scenario in the question?")
    reason: str = ""


class AssessRefutation(BaseModel):
    assessments: list[AssessmentIn]


class ReviseClaim(BaseModel):
    claim_id: int
    text: str = Field(description="The corrected claim, consistent with the observed output")
    behavioural: bool = True
    source_kind: Literal["code", "doc", "test"] = "code"
    citations: list[CitationIn] = Field(default_factory=list)


class ProposeCitation(BaseModel):
    claim_id: int
    path: str
    line: int = Field(ge=1)
    reason: str = ""


class ReadingVerdict(BaseModel):
    claim_id: int
    supported: bool = Field(description="Does the code you read support this claim?")
    evidence: str = ""


class VerifyByReading(BaseModel):
    verdicts: list[ReadingVerdict]


class ResolveConflict(BaseModel):
    claim_id: int
    follow: Literal["docs", "execution"] = Field(description="Which source the answer should follow")
    reason: str = ""


class FinalAnswer(BaseModel):
    answer_text: str = Field(description="The final answer, written from the claim table")
    abstained: bool = Field(default=False, description="True if the evidence does not allow an answer")


# ---------------------------------------------------------------- the table
@dataclass
class Citation:
    path: str
    line: int
    causal: bool | None = None       # None: not checked


@dataclass
class Claim:
    id: int
    text: str
    scope: str = "instance"
    behavioural: bool = True
    source_kind: str = "code"
    citations: list[Citation] = field(default_factory=list)
    test_node: str = ""
    status: str = "unverified"
    probe: str = ""
    controls: list[str] = field(default_factory=list)
    observed_output: str = ""
    repairs: int = 0
    rewrites: int = 0
    revisions: int = 0
    proposals: int = 0
    vacuity_checked: bool = False
    vacuous: bool = False
    test_passed: bool | None = None
    grade: str | None = None
    note: str = ""


@dataclass
class Conflict:
    doc_says: str
    execution_shows: str
    decided_at: str = ""


class ClaimTable:
    def __init__(self) -> None:
        self.claims: list[Claim] = []
        self.conflicts: list[Conflict] = []
        self.decisions: list[dict[str, Any]] = []

    def add_draft(self, claims: list[ClaimIn]) -> None:
        for c in claims:
            self.claims.append(Claim(
                id=len(self.claims) + 1, text=c.text, scope=c.scope, behavioural=c.behavioural,
                source_kind=c.source_kind, citations=[Citation(x.path, x.line) for x in c.citations],
                test_node=c.test_node, status="unverified" if c.behavioural else "non_behavioural"))

    def get(self, claim_id: int) -> Claim | None:
        return next((c for c in self.claims if c.id == claim_id), None)

    def with_status(self, *statuses: str) -> list[Claim]:
        return [c for c in self.claims if c.status in statuses]

    def prioritised(self) -> list[Claim]:
        """Which unverified claim first: those supported only by docs, then the rest (proposal §6.4)."""
        pending = self.with_status("unverified")
        return sorted(pending, key=lambda c: (c.source_kind != "doc", c.id))

    def log(self, decision: str, **inputs: Any) -> None:
        """Every agent decision is recorded with its inputs, for the trace and the viva."""
        self.decisions.append({"decision": decision, **inputs})

    def render(self) -> str:
        """The table as text for the model."""
        if not self.claims:
            return "(no claims)"
        rows = []
        for c in self.claims:
            cites = ", ".join(f"{x.path}:{x.line}" + ("" if x.causal is None else (" CAUSAL" if x.causal else " not causal"))
                              for x in c.citations) or "none"
            obs = f" | observed: {c.observed_output[:300]}" if c.observed_output else ""
            rows.append(f"[{c.id}] ({c.status}{', ' + c.grade if c.grade else ''}) {c.text} | cites: {cites}{obs}")
        return "\n".join(rows)

    def to_dict(self) -> dict[str, Any]:
        return {"claims": [asdict(c) for c in self.claims], "conflicts": [asdict(c) for c in self.conflicts],
                "decisions": self.decisions}
