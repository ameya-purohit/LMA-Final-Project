"""Paired statistics: McNemar's exact test and a paired bootstrap (proposal §3).

All systems answer the same questions, so comparisons are paired. McNemar's exact
test looks only at discordant pairs (one system right, the other wrong). The
bootstrap resamples questions, keeping each question's two outcomes together.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np
from scipy.stats import binomtest


def mcnemar_exact(a: Sequence[bool], b: Sequence[bool]) -> dict[str, float | int]:
    """Exact two-sided McNemar test: a binomial test on the discordant pairs with p = 0.5."""
    if len(a) != len(b):
        raise ValueError("paired samples must have the same length")
    only_a = sum(bool(x) and not bool(y) for x, y in zip(a, b))
    only_b = sum(bool(y) and not bool(x) for x, y in zip(a, b))
    n = only_a + only_b
    p = 1.0 if n == 0 else float(binomtest(only_a, n, 0.5, alternative="two-sided").pvalue)
    return {"only_a": only_a, "only_b": only_b, "discordant": n, "p_value": p}


def paired_bootstrap(a: Sequence[bool], b: Sequence[bool], *, resamples: int = 10000, seed: int = 82,
                     ci: float = 0.95) -> dict[str, float | int]:
    """Bootstrap CI of the difference in rates (a - b). Percentile method, with a fixed seed."""
    if len(a) != len(b):
        raise ValueError("paired samples must have the same length")
    x = np.asarray(a, dtype=float) - np.asarray(b, dtype=float)
    if x.size == 0:
        return {"n": 0, "diff": float("nan"), "ci_low": float("nan"), "ci_high": float("nan")}
    rng = np.random.default_rng(seed)
    means = x[rng.integers(0, x.size, size=(resamples, x.size))].mean(axis=1)
    tail = (1 - ci) / 2 * 100
    return {"n": int(x.size), "diff": float(x.mean()), "ci_low": float(np.percentile(means, tail)),
            "ci_high": float(np.percentile(means, 100 - tail))}
