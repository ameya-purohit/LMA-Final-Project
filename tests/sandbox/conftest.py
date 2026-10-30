"""A tiny hand-written library and probes shared by the sandbox tests."""

import textwrap
from types import SimpleNamespace

import pytest

FAKELIB_INIT = textwrap.dedent('''
    """A tiny library used only by the sandbox tests (hand-written, trusted)."""
    import importlib.metadata

    __version__ = "1.2.3"


    def double(x):
        if x < 0:
            raise ValueError("negative input")
        return 2 * x


    def own_version():
        # Reads the installed version the way many real libraries do; needs the metadata shim.
        return importlib.metadata.version("fakelib")
''')

PASSING = textwrap.dedent('''
    import fakelib

    def observe():
        return fakelib.double(4)

    def test_claim():
        assert fakelib.double(4) == 8
''')

FAILING = textwrap.dedent('''
    import fakelib

    def observe():
        return fakelib.double(4)

    def test_claim():
        assert fakelib.double(4) == 9, "expected 9"
''')

RAISING = textwrap.dedent('''
    import fakelib

    def observe():
        return fakelib.double(-1)

    def test_claim():
        fakelib.double(-1)
''')

SLOW = textwrap.dedent('''
    def observe():
        while True:
            pass

    def test_claim():
        pass
''')

METADATA = textwrap.dedent('''
    import fakelib

    def observe():
        return fakelib.own_version()

    def test_claim():
        assert fakelib.own_version() == "1.2.3"
''')


@pytest.fixture
def fakelib_tree(tmp_path):
    root = tmp_path / "fakelib-tree"
    pkg = root / "src" / "fakelib"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(FAKELIB_INIT)
    tests = root / "tests"
    tests.mkdir()
    (tests / "test_double.py").write_text(
        "import fakelib\n\ndef test_ok():\n    assert fakelib.double(2) == 4\n\n"
        "def test_bad():\n    assert fakelib.double(2) == 5\n")
    root.chmod(0o755)
    return root


@pytest.fixture
def probes():
    """The probe sources above, as a fixture (helper modules are not importable in importlib mode)."""
    return SimpleNamespace(passing=PASSING, failing=FAILING, raising=RAISING, slow=SLOW, metadata=METADATA)
