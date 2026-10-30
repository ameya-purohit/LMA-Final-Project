"""The runner via the local backend, on a hand-written trusted library (no Docker)."""

import pytest

from sandbox.session import LocalBackend, detect_source_root, detect_version
from tools.probe import render, run_probe


@pytest.fixture
def local(fakelib_tree):
    s = LocalBackend(fakelib_tree, "fakelib", trusted=True, config={"sandbox": {"probe_timeout_s": 2}})
    yield s
    s.cleanup()


def test_local_backend_refuses_without_trusted(fakelib_tree):
    with pytest.raises(PermissionError):
        LocalBackend(fakelib_tree, "fakelib")


def test_layout_detection(fakelib_tree):
    assert detect_source_root(fakelib_tree, "fakelib") == "src"
    assert detect_version(fakelib_tree, "fakelib", "src") == "1.2.3"


def test_pass_fail_raise_outcomes(local, probes):
    r = run_probe(local, probes.passing, [probes.failing, probes.raising])
    claim, failing, raising = r.results
    assert claim.status == "pass" and claim.outcome == {"kind": "return", "repr": "8"}
    assert failing.status == "fail" and "expected 9" in failing.message
    assert raising.status == "error" and raising.outcome["kind"] == "raise"
    assert raising.outcome["type"] == "ValueError" and raising.outcome["msg"] == "negative input"
    assert raising.outcome["innermost_frame"] == "fakelib/__init__.py:10"  # inside the library, not the probe
    assert "test_claim PASS" in render(r)


def test_timeout_enforced(local, probes):
    r = run_probe(local, probes.slow)
    assert r.claim.outcome["type"] == "ProbeTimeout"


def test_metadata_shim(local, probes):
    assert run_probe(local, probes.metadata).claim.status == "pass"


def test_syntax_error_in_probe_is_reported(local):
    r = run_probe(local, "def observe(:\n    pass\n")
    assert r.claim.status == "error" and r.claim.outcome["type"] == "SyntaxError"
    assert not r.executable


def test_overlay_shadows_library(local, probes):
    """A mutant copy of the package placed in an overlay dir wins over the original."""
    overlay = local.scratch / "mutant1"
    (overlay / "fakelib").mkdir(parents=True)
    (overlay / "fakelib" / "__init__.py").write_text("def double(x):\n    return 3 * x\n")
    r = run_probe(local, probes.passing, overlay=str(overlay))
    assert r.claim.outcome == {"kind": "return", "repr": "12"} and r.claim.status == "fail"


def test_line_tracing(local, probes):
    r = run_probe(local, probes.raising, trace_lines_for=["fakelib/__init__.py"])
    assert 9 in r.claim.executed_lines["fakelib/__init__.py"]  # the `if x < 0` line


def test_memory_addresses_normalized(local):
    code = "def observe():\n    return object()\n\ndef test_claim():\n    pass\n"
    assert "0x?" in run_probe(local, code).claim.outcome["repr"]


def test_pytest_job(local):
    out = local.run_pytest(["tests/test_double.py"])
    assert out["tests"]["tests/test_double.py::test_ok"]["status"] == "passed"
    bad = out["tests"]["tests/test_double.py::test_bad"]
    assert bad["status"] == "failed" and "assert 4 == 5" in bad["message"]
