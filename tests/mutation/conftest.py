"""toylib fixture helpers for the mutation tests."""

import re
import textwrap
from pathlib import Path
from types import SimpleNamespace

import pytest

TOYLIB = Path(__file__).resolve().parents[1] / "fixtures" / "toylib"
CORE = TOYLIB / "src" / "toylib" / "core.py"
REL = "toylib/core.py"


def mark_line(name: str) -> int:
    """Line number of the line tagged `# MARK: <name>` in toylib/core.py."""
    for i, line in enumerate(CORE.read_text().splitlines(), start=1):
        if re.search(rf"# MARK: {re.escape(name)}\b", line):
            return i
    raise KeyError(name)


def probe(expr: str, claim: str) -> str:
    """A probe whose observe() returns `expr` and whose test_claim() runs `claim`."""
    return textwrap.dedent(f"""
        import pytest
        from toylib import at_least, clamp, safe_div

        def observe():
            return {expr}

        def test_claim():
            {claim}
    """)


PROBES = SimpleNamespace(
    c1_claim=probe("clamp(-1, strict=False)", "with pytest.raises(ValueError):\n                clamp(-1, strict=False)"),
    c1_control=probe("clamp(5, strict=False)", "assert clamp(5, strict=False) == 5"),
    c2_claim=probe("clamp(500, strict=False)", "assert clamp(500, strict=False) == 100"),
    c2_control=probe("clamp(5, strict=False)", "assert clamp(5, strict=False) == 5"),
    div_claim=probe("safe_div(1, 0)", "with pytest.raises(ValueError):\n                safe_div(1, 0)"),
    div_control=probe("safe_div(6, 3)", "assert safe_div(6, 3) == 2.0"),
    ge_claim=probe("at_least(18, 18)", "assert at_least(18, 18) is True"),
    ge_control=probe("at_least(30, 18)", "assert at_least(30, 18) is True"),
    vacuous=probe("callable(clamp)", "assert callable(clamp)"),
    unsafe="import os\n\ndef observe():\n    return os.system('id')\n\ndef test_claim():\n    pass\n",
)


@pytest.fixture
def toy_probes():
    return PROBES


@pytest.fixture
def marks():
    return mark_line


@pytest.fixture(params=["local", pytest.param("docker", marks=pytest.mark.docker)])
def toy_session(request):
    """The same assertions run on the trusted local backend and in the Docker sandbox."""
    from core.config import load_config
    cfg = load_config()
    if request.param == "local":
        from sandbox.session import LocalBackend
        s = LocalBackend(TOYLIB, "toylib", trusted=True, config=cfg)
        yield s
        s.cleanup()
    else:
        import shutil
        import subprocess
        from sandbox.session import SandboxSession
        if shutil.which("docker") is None or subprocess.run(
                ["docker", "image", "inspect", cfg["sandbox"]["image"]], capture_output=True).returncode != 0:
            pytest.skip("Docker or sandbox image not available")
        s = SandboxSession(TOYLIB, "toylib", config=cfg)
        s.start()
        yield s
        s.cleanup()
