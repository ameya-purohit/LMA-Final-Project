"""codegraph: call graph, dependences and slices on toylib, whose planted lines we know."""

from pathlib import Path

import pytest

pytest.importorskip("networkx")
from codegraph.graph import CodeGraph, function_dependences  # noqa: E402
from codegraph.rank import graph_candidates, rrf, spectrum  # noqa: E402

TOYLIB = Path(__file__).resolve().parents[1] / "fixtures" / "toylib"
CORE = "src/toylib/core.py"
if not TOYLIB.exists():
    pytest.skip("toylib is in a later bundle", allow_module_level=True)


@pytest.fixture(scope="module")
def g():
    return CodeGraph(TOYLIB, "toylib", "src")


def test_functions_and_calls(g):
    clamp = g.function_at(CORE, 88)
    assert clamp is not None and clamp.name == "clamp"
    callers, callees = g.neighbours(clamp.qualname)
    assert any(c.endswith("_effective_strict") for c in callees)
    assert g.find("safe_div") and g.find("core.safe_div")[0].path == CORE


def test_slice_of_the_decider_reaches_the_strict_resolution_and_parameters(g):
    sl = g.static_slice(CORE, 88)
    assert sl[0] == (CORE, 88)
    assert (CORE, 87) in sl, "strict is assigned on line 87 and read on line 88"
    assert (CORE, 12) not in sl, "the module default is only read inside _effective_strict, not in clamp"


def test_slice_of_return_includes_the_constant_it_reads(g):
    sl = g.static_slice(CORE, 91)
    assert (CORE, 90) in sl and (CORE, 20) in sl, "result = min(x, LIMIT) and LIMIT = 100"


def test_paths_are_accepted_in_both_spellings(g):
    assert g.normalize("toylib/core.py") == CORE == g.normalize("./src/toylib/core.py")
    assert g.package_files()[0].startswith("toylib/") and g.to_repo_path("toylib/core.py") == CORE


def test_redundant_guards_are_connected(g):
    assert g.connected((CORE, 49), (CORE, 50))


def test_control_and_data_edges():
    import ast
    fn = ast.parse("def f(a):\n    x = a\n    if x:\n        y = 1\n    return y\n").body[0]
    d = function_dependences(fn)
    assert d.edges[2, 3]["kind"] == "data" and d.edges[3, 4]["kind"] == "control" and d.has_edge(4, 5)


def test_rrf_prefers_items_ranked_high_in_several_lists():
    assert rrf([["a", "b", "c"], ["b", "a"], ["b"]])[0] == "b"
    assert rrf([["x"], []]) == ["x"]


def test_spectrum_and_candidates(g):
    claim = {"toylib/core.py": [87, 88, 90]}
    control = [{"toylib/core.py": [87, 90]}]
    s = spectrum(claim, control, g.to_repo_path)
    assert s[(CORE, 88)] == 1.0 and s[(CORE, 87)] < 1.0
    ranked = graph_candidates(g, [(CORE, 88)], spectrum_scores=s)
    assert ranked[0] == (CORE, 88) and (CORE, 12) not in ranked


def test_slice_from_a_decorator_line_starts_at_the_def(tmp_path):
    """Regression: a cited decorator line sits above the `def`, so it has no node in the dependence graph
    (click-3700 and click-1739 crashed with NodeNotFound before the fix)."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "m.py").write_text("import functools\n\n\n@functools.lru_cache()\ndef f(x):\n    y = x + 1\n    return y\n")
    cg = CodeGraph(tmp_path, "pkg", ".")
    sl = cg.static_slice("pkg/m.py", 4)
    assert sl and sl[0] == ("pkg/m.py", 5)
    assert cg.connected(("pkg/m.py", 4), ("pkg/m.py", 7)) in (True, False)
