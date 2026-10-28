import subprocess
import zipfile
from pathlib import Path

import pytest
import yaml

from scripts import make_bundles as mb

ROOT = Path(__file__).resolve().parents[2]


def own():
    return mb.load_ownership(ROOT / "bundles" / "ownership.yaml")


@pytest.mark.parametrize("path,owner", [
    ("tools/probe.py", "aditya"),
    ("tools/mutate.py", "sourav"),
    ("tools/registry.py", "sunil"),
    ("llm/providers/gemini.py", "ameya"),
    ("data/questions_all.jsonl", "ameya"),
    ("docs/explainers/agent.md", "ameya"),
    ("docs/explainers/retrieval.md", "sunil"),
    ("docs/proposal_v2.md", "sunil"),
    ("tests/fixtures/toylib/src/toylib/core.py", "sourav"),
    ("tests/llm/test_cache.py", "ameya"),
    ("scripts/smoke_llm.py", "ameya"),
    ("scripts/make_bundles.py", "sunil"),
    ("results/summary/table.csv", "sourav"),
    ("CLAUDE.md", "sunil"),
    ("requirements.txt", "sunil"),
])
def test_owner_rules(path, owner):
    assert mb.owner_of(path, own()) == owner


def test_unowned_detected():
    assert mb.check_all_owned(["weird/file.txt", "core/config.py"], own()) == ["weird/file.txt"]


def test_push_order_and_members():
    o = own()
    assert o["push_order"] == ["sunil", "ameya", "aditya", "sourav"]
    assert {m["github"] for m in o["members"].values()} == {
        "ameya-purohit", "Suniljadaun", "adityaND19", "Sourav-Nath-01"}


def test_push_md_has_no_ai_attribution_and_right_steps():
    text = mb.push_md("ameya", "ameya_mid", ["llm/client.py", "tests/llm/test_x.py"], [], own())
    assert "Co-Authored-By" not in text and "Claude" not in text
    assert "git checkout -b ameya-llm-data-agent" in text
    assert "tests/llm" in text
    assert "Sunil Kumar" in text  # must wait for earlier bundles
    assert "invitations" in text and "-x PUSH.md" in text
    assert "pip install -r requirements.txt" in text


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def test_build_in_temp_repo(tmp_path):
    """End to end on a throwaway repo: ignored files never ship; --since works."""
    out = tmp_path / "out"
    tmp_path = tmp_path / "repo"
    tmp_path.mkdir()
    (tmp_path / "bundles").mkdir()
    (tmp_path / "bundles" / "ownership.yaml").write_text(yaml.safe_dump(own()))
    (tmp_path / "core").mkdir()
    (tmp_path / "core" / "a.py").write_text("x = 1\n")
    (tmp_path / "llm").mkdir()
    (tmp_path / "llm" / "b.py").write_text("y = 2\n")
    (tmp_path / ".gitignore").write_text(".env\n")
    (tmp_path / ".env").write_text("GEMINI_API_KEY=secret\n")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")

    z = mb.build("sunil", "sunil_scaffold", out_dir=out, root=tmp_path)
    names = zipfile.ZipFile(z).namelist()
    assert "core/a.py" in names and "PUSH.md" in names and "bundles/ownership.yaml" in names
    assert ".env" not in names and "llm/b.py" not in names

    rev = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True).stdout.strip()
    (tmp_path / "llm" / "b.py").write_text("y = 3\n")
    z2 = mb.build("ameya", "ameya_update_1", since=rev, out_dir=out, root=tmp_path)
    assert sorted(zipfile.ZipFile(z2).namelist()) == ["PUSH.md", "llm/b.py"]
    with pytest.raises(SystemExit):
        mb.build("sourav", "sourav_update_1", since=rev, out_dir=out, root=tmp_path)


def test_real_repo_fully_owned():
    files = mb.repo_files(ROOT)
    assert mb.check_all_owned(files, own()) == []
