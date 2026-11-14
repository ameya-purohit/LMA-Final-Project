"""Choosing the next experiment by information gain (exploratory extension, E5). Pure functions, no I/O.

The agents give competing hypotheses, each naming the places it blames. A mutation check of line l has two
informative outcomes: the line is accepted as causal, or it is rejected. A hypothesis that blames l (l sits in a
function it names, or within two lines of a line it names) predicts "accepted" with probability HIT; any other
hypothesis predicts it with probability MISS, because the check is imperfect. A catch-all "none of these" hypothesis
keeps some weight, so the agents' list never has to be complete.

Expected information gain of checking l, with weights w over hypotheses and p_h = P(accepted | h, l):
    EIG(l) = H(sum_h w_h p_h) - sum_h w_h H(p_h)            (H = binary entropy, in bits)
After a result, Bayes' rule updates the weights; an inconclusive result changes nothing. We stop when one named
hypothesis holds most of the weight and some line was accepted, when no check would tell us much, or when the budget
is spent. The numbers below are fixed in advance and logged with every run; they were not tuned on test questions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import log2
from typing import Callable

HIT = 0.8           # P(accepted | the hypothesis blames this line)
MISS = 0.1          # P(accepted | it does not)
OTHER = "other"     # the catch-all hypothesis
OTHER_PRIOR = 0.2
OTHER_P = 0.2       # P(accepted | none of the named hypotheses is right)
STOP_WEIGHT = 0.8
MIN_GAIN = 0.01

Loc = tuple[str, int]


def entropy(p: float) -> float:
    if p <= 0.0 or p >= 1.0:
        return 0.0
    return -(p * log2(p) + (1 - p) * log2(1 - p))


@dataclass
class Belief:
    """Weights over hypotheses, and which lines each one blames."""
    weights: dict[str, float]
    blames: Callable[[str, Loc], bool]
    history: list[dict] = field(default_factory=list)

    @classmethod
    def start(cls, hypothesis_ids: list[str], blames: Callable[[str, Loc], bool]) -> "Belief":
        named = [h for h in hypothesis_ids if h != OTHER]
        w = {h: (1 - OTHER_PRIOR) / len(named) for h in named} if named else {}
        w[OTHER] = OTHER_PRIOR if named else 1.0
        return cls(w, blames)

    def p_accept(self, h: str, loc: Loc) -> float:
        if h == OTHER:
            return OTHER_P
        return HIT if self.blames(h, loc) else MISS

    def gain(self, loc: Loc) -> float:
        p = sum(w * self.p_accept(h, loc) for h, w in self.weights.items())
        return entropy(p) - sum(w * entropy(self.p_accept(h, loc)) for h, w in self.weights.items())

    def update(self, loc: Loc, verdict: str) -> None:
        """Bayes' rule on an accepted or rejected line; an inconclusive result carries no information."""
        if verdict not in ("accepted", "rejected"):
            self.history.append({"loc": loc, "verdict": verdict, "updated": False})
            return
        new = {h: w * (self.p_accept(h, loc) if verdict == "accepted" else 1 - self.p_accept(h, loc))
               for h, w in self.weights.items()}
        total = sum(new.values()) or 1.0
        self.weights = {h: w / total for h, w in new.items()}
        self.history.append({"loc": loc, "verdict": verdict, "weights": dict(self.weights)})

    def leader(self) -> tuple[str, float]:
        h = max(self.weights, key=lambda k: (self.weights[k], k != OTHER))
        return h, self.weights[h]


def pick_next(belief: Belief, candidates: list[Loc], done: set[Loc]) -> tuple[Loc | None, float]:
    """The untested candidate with the highest expected information gain; ties go to the better-ranked line."""
    best, best_gain = None, -1.0
    for rank, loc in enumerate(candidates):
        if loc in done:
            continue
        g = belief.gain(loc) - 1e-6 * rank
        if g > best_gain:
            best, best_gain = loc, g
    return best, best_gain


def should_stop(belief: Belief, any_accepted: bool, best_gain: float) -> str | None:
    """Why to stop now, or None to go on."""
    h, w = belief.leader()
    if any_accepted and h != OTHER and w >= STOP_WEIGHT:
        return f"hypothesis {h} holds {w:.2f} of the weight"
    if best_gain < MIN_GAIN:
        return f"no remaining check is informative (best gain {best_gain:.3f} bits)"
    return None
