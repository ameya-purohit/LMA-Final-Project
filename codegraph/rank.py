"""Rank suspicious lines from the code graph and from what the probes executed (exploratory extension, E3+).

Two signals, both deterministic:
- **Static slice**: lines that can affect a seed line (a line an agent suspects, or the line where the library raised).
- **Executed-line spectrum**: the sandbox records which library lines each probe ran. A line run by the claim probe
  (which shows the behaviour asked about) but by no control probe (which shows ordinary behaviour) is the most
  suspicious; a line every probe runs is less so. This is spectrum-based fault localization with one "failing" run;
  the score is the Ochiai formula 1/sqrt(1 + c), where c is how many control probes also ran the line.

The slice keeps the search small; the spectrum orders it. Lines the claim probe never ran are dropped when a trace
exists, which is what makes the slice "dynamic": static slice intersected with executed lines.

`rrf` (reciprocal rank fusion) merges rankings from different sources without having to calibrate their scores.
"""

from __future__ import annotations

from math import sqrt
from typing import Hashable, Iterable, Sequence, TypeVar

T = TypeVar("T", bound=Hashable)
Loc = tuple[str, int]


def rrf(rankings: Sequence[Sequence[T]], k: int = 60, weights: Sequence[float] | None = None) -> list[T]:
    """Reciprocal rank fusion: score(x) = sum over rankings of w / (k + rank). Ties keep first-seen order.

    k = 60 is the value from Cormack et al. (2009), used unchanged so it is not a tuned knob."""
    weights = weights or [1.0] * len(rankings)
    score: dict[T, float] = {}
    order: dict[T, int] = {}
    for w, ranking in zip(weights, rankings):
        for r, item in enumerate(ranking, 1):
            score[item] = score.get(item, 0.0) + w / (k + r)
            order.setdefault(item, len(order))
    return sorted(score, key=lambda x: (-score[x], order[x]))


def spectrum(claim_lines: dict[str, Iterable[int]], control_lines: list[dict[str, Iterable[int]]],
             to_repo: callable = lambda p: p) -> dict[Loc, float]:
    """Ochiai suspiciousness of every line the claim probe executed: 1 / sqrt(1 + controls that also ran it)."""
    controls = [{(to_repo(p), ln) for p, lines in c.items() for ln in lines} for c in control_lines]
    out: dict[Loc, float] = {}
    for p, lines in claim_lines.items():
        for ln in lines:
            loc = (to_repo(p), ln)
            c = sum(loc in s for s in controls)
            out[loc] = 1.0 / sqrt(1 + c)
    return out


def graph_candidates(graph, seeds: list[Loc], *, spectrum_scores: dict[Loc, float] | None = None,
                     raise_site: Loc | None = None, limit: int = 15) -> list[Loc]:
    """Candidate lines from the slices of the seeds, ordered by spectrum, then by slice distance.

    Seeds are the agents' top suspects (at most 3) and the raise site, if the claim probe raised inside the library.
    Without a trace (`spectrum_scores` None) every slice line is kept, ordered by distance."""
    pool: dict[Loc, int] = {}
    for seed in ([raise_site] if raise_site else []) + seeds[:3]:
        for dist, loc in enumerate(graph.static_slice(*seed)):
            pool[loc] = min(pool.get(loc, dist), dist)
    if spectrum_scores:
        # The executed functions around the seeds: lines the claim ran but no control did are strong evidence even
        # outside the slice (a callee that returns the wrong value, for example).
        for seed in ([raise_site] if raise_site else []) + seeds[:3]:
            f = graph.function_at(*seed)
            if f is None:
                continue
            _, callees = graph.neighbours(f.qualname)
            for q in [f.qualname] + callees:
                g = graph.functions.get(q)
                for (p, ln), s in spectrum_scores.items():
                    if g and s >= 1.0 and graph.normalize(p) == g.path and g.start <= ln <= g.end:
                        pool.setdefault((g.path, ln), 1000 + ln - g.start)
        executed = {(graph.normalize(p) or p, ln): s for (p, ln), s in spectrum_scores.items()}
        pool = {loc: d for loc, d in pool.items() if loc in executed}
        ranked = sorted(pool, key=lambda loc: (-executed[loc], pool[loc], loc))
    else:
        ranked = sorted(pool, key=lambda loc: (pool[loc], loc))
    return ranked[:limit]
