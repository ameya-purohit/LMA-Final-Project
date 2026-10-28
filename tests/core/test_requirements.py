"""requirements.txt and pyproject.toml must list the same dependencies,
so replicating from either gives the same environment."""

from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    tomllib = None

ROOT = Path(__file__).resolve().parents[2]


def _requirements() -> set[str]:
    lines = (ROOT / "requirements.txt").read_text().splitlines()
    return {ln.strip() for ln in lines if ln.strip() and not ln.lstrip().startswith("#")}


def _pyproject() -> set[str]:
    text = (ROOT / "pyproject.toml").read_text()
    if tomllib is not None:
        return set(tomllib.loads(text)["project"]["dependencies"])
    block = text.split("dependencies = [", 1)[1].split("]", 1)[0]
    return {ln.strip().strip(",").strip('"') for ln in block.splitlines() if ln.strip()}


def test_requirements_match_pyproject():
    assert _requirements() == _pyproject()
