"""When to stop, and whether the answer must be flagged. Pure rules, no LLM."""

from __future__ import annotations

from agent.claim_table import ClaimTable

# Requests kept back for the final answer, so a run that uses its budget still answers.
FINAL_RESERVE = 1


def all_settled(table: ClaimTable) -> bool:
    """Every behavioural claim is executed and every citation of a confirmed claim is causal."""
    if table.with_status("unverified"):
        return False
    for c in table.with_status("confirmed"):
        if not any(x.causal for x in c.citations):
            return False
    return True


def flagged_uncertain(table: ClaimTable) -> bool:
    """Flag the answer if any claim is unverified or refuted, or nothing at all was verified.

    A claim with no causal citation is reported through its grade, not by
    flagging: it was still executed, so it is not an uncertain statement.
    """
    if not table.claims:
        return True
    if table.with_status("unverified", "refuted"):
        return True
    return not table.with_status("confirmed", "read_supported", "skipped")
