"""toylib.core: a tiny library with planted ground truth (the live viva demo).

The documentation claims: "strict is on by default, so negatives raise".
That is wrong on purpose: `_OVERRIDES` below switches strict off, so the real
default is non-strict. Tests in tests/mutation/ check that the mutation check
accepts the line that really decides each behaviour and rejects lines that
only look related. Every planted line carries a `# MARK: <name>` comment.
"""

# The documented default. It looks like it decides strictness, but it is
# overridden by _OVERRIDES, so no mutation of this line changes behaviour.
STRICT_DEFAULT = True  # MARK: strict_default

# Overrides applied at import time (imagine they were read from a config
# file). This is what really switches strict mode off.
_OVERRIDES = {"strict": False}  # MARK: overrides

# Upper bound used by clamp(). Changing 100 -> 101 changes clamp(500) but
# not clamp(5), so this line is causal AND specific for "clamp(500) == 100".
LIMIT = 100  # MARK: limit

# Message shared by both zero-division guards in safe_div(), so that neither
# guard line holds a string constant of its own (otherwise the "string -> ''"
# operator would change the message and make one guard look causal alone).
ZERO_MSG = "zero"  # MARK: zero_msg


def _effective_strict(strict):
    """Resolve strict=None to the configured default (the override wins)."""
    if strict is None:  # MARK: strict_none
        return _OVERRIDES.get("strict", STRICT_DEFAULT)  # MARK: override_lookup
    return strict


def _check_nonzero(b):
    """The second, redundant guard used by safe_div()."""
    if b == 0:  # MARK: helper_guard
        raise ValueError(ZERO_MSG)


def safe_div(a, b):
    """Divide a by b; raise ValueError("zero") when b is 0.

    The check is made twice, inline and in a helper. Each guard alone is
    redundant: mutating either line alone changes nothing, and only mutating
    both together does. This documents a known limitation of single-line
    mutation (redundant lines) and why group mutation exists.
    """
    if b == 0: raise ValueError(ZERO_MSG)  # MARK: guard_inline  # noqa: E701
    _check_nonzero(b)  # MARK: guard_helper
    return a / b


def at_least(value, threshold):
    """Return True if value >= threshold.

    The deciding line has no constants, so only the negation and swap
    operators can flip it. With constant operators only (ablation A11) this
    causal line is falsely rejected.
    """
    if value >= threshold:  # MARK: compare_no_const
        return True
    return False


# ---------------------------------------------------------------------------
# clamp() is the example from the proposal's figure. Its line numbers are
# fixed on purpose: STRICT_DEFAULT is on line 12 and the deciding line is
# line 88, and a test checks both. The claim "clamp(-1, strict=False) raises
# ValueError" is decided by line 88:
#   - mutant `x < 0` -> `x < -1`: clamp(-1) no longer raises, while the
#     control clamp(5) still returns 5, so line 88 is causal and specific;
#   - every mutant of line 12 leaves the outcome unchanged, so line 12 is
#     rejected even though the docs point to it.
# For "clamp(500, strict=False) == 100":
#   - `return result` -> `return None` changes the claim AND the control,
#     so it is rejected by the specificity rule;
#   - deleting `result = min(...)` raises UnboundLocalError: breakage.
# ---------------------------------------------------------------------------


def clamp(x, strict=None):
    """Clamp x into [0, LIMIT].

    Documentation (out of date): strict is on by default, so negatives raise.
    """
    strict = _effective_strict(strict)  # MARK: resolve_strict
    if strict or x < 0: raise ValueError("negative")  # MARK: decider  # noqa: E701
    result: int  # makes `result` local, so deleting the next line gives UnboundLocalError
    result = min(x, LIMIT)  # MARK: min_result
    return result  # MARK: return_result
