"""experiments.selection: information gain and Bayes updates, by hand."""

import pytest

from experiments.selection import HIT, MISS, OTHER, Belief, entropy, pick_next, should_stop


def blames(h, loc):
    return {"H1": {("a.py", 1)}, "H2": {("a.py", 2)}}.get(h, set()).__contains__(loc)


def test_entropy():
    assert entropy(0.5) == 1.0 and entropy(0) == 0 and entropy(1) == 0


def test_start_weights_and_gain_prefers_a_line_that_splits_the_hypotheses():
    b = Belief.start(["H1", "H2"], blames)
    assert b.weights == pytest.approx({"H1": 0.4, "H2": 0.4, OTHER: 0.2})
    assert b.gain(("a.py", 1)) > b.gain(("a.py", 9)) > 0
    loc, _ = pick_next(b, [("a.py", 9), ("a.py", 1)], set())
    assert loc == ("a.py", 1)


def test_update_by_hand():
    b = Belief.start(["H1", "H2"], blames)
    b.update(("a.py", 1), "accepted")
    raw = {"H1": 0.4 * HIT, "H2": 0.4 * MISS, OTHER: 0.2 * 0.2}
    total = sum(raw.values())
    assert b.weights == pytest.approx({k: v / total for k, v in raw.items()})
    before = dict(b.weights)
    b.update(("a.py", 2), "inconclusive")
    assert b.weights == before


def test_stop_rules():
    b = Belief.start(["H1"], blames)
    b.weights = {"H1": 0.85, OTHER: 0.15}
    assert should_stop(b, True, 0.5) and should_stop(b, False, 0.5) is None
    assert "informative" in should_stop(b, False, 0.0)
