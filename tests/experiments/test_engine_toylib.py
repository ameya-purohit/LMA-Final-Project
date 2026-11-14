"""The Experiment Engineer on toylib's planted lines (trusted, hand-written probes; local backend)."""

import textwrap

import pytest

pytest.importorskip("tools.mutate")
pytest.importorskip("networkx")
from analysis.toylib_ablations import CLAIMS, TOYLIB, mark_line  # noqa: E402
from codegraph.graph import CodeGraph  # noqa: E402
from experiments.engine import ExperimentEngine  # noqa: E402

CORE = "src/toylib/core.py"
SAFE_CLAIM = textwrap.dedent("""
    import pytest
    from toylib import safe_div
    def observe():
        return safe_div(1, 0)
    def test_claim():
        with pytest.raises(ValueError):
            safe_div(1, 0)
""")
SAFE_CONTROL = textwrap.dedent("""
    from toylib import safe_div
    def observe():
        return safe_div(6, 3)
    def test_claim():
        assert safe_div(6, 3) == 2.0
""")


@pytest.fixture
def session():
    from core.config import load_config
    from sandbox.session import LocalBackend
    s = LocalBackend(TOYLIB, "toylib", trusted=True, config=load_config())
    s.start()
    yield s
    s.cleanup()


def c1():
    return CLAIMS[0]["claim"], [CLAIMS[0]["control"]]


def test_three_way_verdicts_on_the_planted_lines(session):
    claim, controls = c1()
    eng = ExperimentEngine(session, claim, controls)
    eng.run_ranked([(CORE, mark_line("strict_default")), ("toylib/core.py", mark_line("decider")), (CORE, 1)])
    v = {e.locs[0]: e.verdict for e in eng.experiments}
    assert v[f"{CORE}:88"] == "accepted"
    assert v[f"{CORE}:12"] == "rejected", "True -> False changes nothing; deleting the line only breaks the program"
    assert eng.counts["single_checks"] == 2 and eng.counts["skipped_untestable"] == 1


def test_same_line_in_two_spellings_is_checked_once(session):
    claim, controls = c1()
    eng = ExperimentEngine(session, claim, controls)
    eng.single((CORE, 88))
    eng.single(("toylib/core.py", 88))
    assert eng.counts["single_checks"] == 1 and eng.counts["cache_hits"] == 1


def test_return_line_is_not_specific(session):
    claim, controls = CLAIMS[1]["claim"], [CLAIMS[1]["control"]]
    exp = ExperimentEngine(session, claim, controls).single((CORE, mark_line("return_result")))
    assert exp.verdict == "inconclusive" and "control" in exp.reason


def test_pairwise_mutation_finds_redundant_guards(session):
    eng = ExperimentEngine(session, SAFE_CLAIM, [SAFE_CONTROL], graph=CodeGraph(TOYLIB, "toylib", "src"))
    a, b = (CORE, mark_line("guard_inline")), (CORE, mark_line("guard_helper"))
    eng.run_ranked([a, b])
    assert all(e.verdict != "accepted" for e in eng.experiments), "each guard alone is masked by the other"
    eng.run_pairs([a, b])
    pair = [e for e in eng.experiments if e.kind == "pair"]
    assert pair and pair[0].verdict == "accepted"


def test_active_selection_stops_early(session):
    claim, controls = c1()
    eng = ExperimentEngine(session, claim, controls, graph=CodeGraph(TOYLIB, "toylib", "src"))
    hyps = [{"id": "H1", "locations": [(CORE, 12)], "symbols": []},
            {"id": "H2", "locations": [(CORE, 88)], "symbols": ["clamp"]}]
    stop = eng.run_active([(CORE, 12), (CORE, 88), (CORE, 90), (CORE, 91)], hyps)
    assert any(e.verdict == "accepted" for e in eng.experiments)
    assert eng.counts["single_checks"] < 4 and stop


def test_patch_validation(session):
    claim, controls = c1()
    eng = ExperimentEngine(session, claim, controls)
    ok = eng.validate_patch(CORE, 88, 'if strict: raise ValueError("negative")')
    assert ok["validated"], ok
    bad = eng.validate_patch(CORE, 88, 'if True: raise ValueError("negative")')
    assert not bad["validated"] and bad["reason"] == "claim unchanged"
    assert not eng.validate_patch(CORE, 88, "a\nb")["validated"]
