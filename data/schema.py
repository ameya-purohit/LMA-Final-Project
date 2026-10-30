"""The question record: one JSONL line per question (CLAUDE.md §6.1).

`question_text` and the frozen tree are all a system ever sees. Every other
field is the answer key and stays on the evaluation side (see
`tools/workspace.py`, which has no access to these fields).
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel


class ObservedBefore(BaseModel):
    test: str
    status: str
    message: str


class ObservedAfter(BaseModel):
    test: str
    status: str


class GoldEvidence(BaseModel):
    path: str
    line_start: int
    line_end: int
    kind: Literal["changed", "deleted", "anchor_for_insert"]


class DiffStats(BaseModel):
    files: int
    lines_added: int
    lines_removed: int


class SpotCheck(BaseModel):
    checked_by: Optional[str] = None
    valid: Optional[bool] = None
    reason: Optional[str] = None


class Question(BaseModel):
    qid: str
    library: str
    issue_url: str
    issue_number: int
    created_at: str
    question_text: str
    fix_pr_url: str
    fix_pr_number: int
    fix_merge_commit: str
    frozen_commit: str
    fail_to_pass: list[str]
    observed_before: list[ObservedBefore]
    observed_after: list[ObservedAfter]
    gold_evidence: list[GoldEvidence]
    fix_source_files: list[str]
    fix_diff_stats: DiffStats
    gold_answer: str
    category: Literal["doc_related", "spread_across_files", "single_location"]
    executable: bool = True
    post_cutoff: bool = False
    gold_source: str = "auto_fix"
    spot_check: SpotCheck = SpotCheck()
