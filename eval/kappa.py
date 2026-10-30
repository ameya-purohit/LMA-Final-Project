"""Cohen's kappa: agreement between two raters beyond chance.

If human-judge kappa is below 0.6, the primary comparison uses human labels (§6.11).
"""

from __future__ import annotations

from collections import Counter
from typing import Hashable, Sequence


def cohens_kappa(a: Sequence[Hashable], b: Sequence[Hashable]) -> float:
    if len(a) != len(b) or not a:
        raise ValueError("kappa needs two non-empty label lists of the same length")
    n = len(a)
    observed = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    expected = sum(ca[k] * cb.get(k, 0) for k in ca) / (n * n)
    if expected == 1.0:
        return 1.0 if observed == 1.0 else 0.0
    return (observed - expected) / (1 - expected)
