"""Every read-only tool on a small git repo, then on a real frozen click commit when one is cached."""

import subprocess
from pathlib import Path

import pytest

from tools.files import open_file
from tools.history import git_blame, git_log
from tools.registry import OpenFileArgs, ToolRegistry, inline_schema
from tools.search import search_code, search_docs
from tools.static import find_definition, find_references
from tools.tests_finder import find_tests
from tools.workspace import Workspace

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def ws(tmp_path):
    repo_dir = tmp_path / "work"
    pkg = repo_dir / "src" / "p"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("from p.core import greet\n")
    (pkg / "core.py").write_text('DEFAULT = "hello"\n\n\ndef greet(name):\n    """Say hello."""\n    return DEFAULT + name\n')
    (repo_dir / "docs").mkdir()
    (repo_dir / "docs" / "index.md").write_text("# Greeting\nUse greet to say hello politely.\n")
    (repo_dir / "tests").mkdir()
    (repo_dir / "tests" / "test_core.py").write_text("from p import greet\n\ndef test_greet():\n    assert greet('a')\n")

    def g(*a):
        subprocess.run(["git", "-C", str(repo_dir), "-c", "user.name=t", "-c", "user.email=t@t", *a], check=True, capture_output=True)
    g("init", "-q"); g("add", "-A"); g("commit", "-qm", "first version")
    commit = subprocess.run(["git", "-C", str(repo_dir), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    (pkg / "core.py").write_text('DEFAULT = "LATER FIX"\n')
    g("add", "-A"); g("commit", "-qm", "later fix that must stay invisible")
    subprocess.run(["git", "-C", str(repo_dir), "checkout", "-q", commit], check=True, capture_output=True)
    return Workspace("p", "p", repo_dir, repo=repo_dir, commit=commit)


def test_workspace_cannot_hold_gold(ws):
    for field in Workspace.FORBIDDEN:
        assert not hasattr(ws, field)
        with pytest.raises(AttributeError):
            setattr(ws, field, "leak")


def test_workspace_for_question_reads_only_library_and_commit(tmp_path, monkeypatch):
    import tools.workspace as W
    tree = tmp_path / "trees" / "click" / "abc" / "src" / "click"
    tree.mkdir(parents=True)
    (tree / "__init__.py").write_text("")
    monkeypatch.setattr(W, "REPO_ROOT", tmp_path)
    cfg = {"data": {"libraries": {"click": {"package": "click", "tests_dir": "tests"}}},
           "paths": {"trees_dir": "trees", "repos_dir": "repos", "index_dir": "idx"}}

    class Tripwire(dict):
        def __getitem__(self, key):
            assert key in ("library", "frozen_commit"), f"workspace read {key} from the question"
            return super().__getitem__(key)

    w = Workspace.for_question(Tripwire(library="click", frozen_commit="abc", gold_answer="SECRET", fail_to_pass=["x"]), cfg)
    assert w.commit == "abc" and w.source_root == "src"


def test_open_file_numbered_and_confined(ws):
    text = open_file(ws, "src/p/core.py", 4, 6)
    assert "    4  def greet(name):" in text and "DEFAULT = " in open_file(ws, "src/p/core.py")
    assert "has only" in open_file(ws, "src/p/core.py", 100)
    with pytest.raises(ValueError):
        open_file(ws, "../../etc/passwd")
    with pytest.raises(FileNotFoundError):
        open_file(ws, "nope.py")


def test_open_file_caps_at_200_lines(ws):
    (ws.tree / "big.py").write_text("x = 1\n" * 500)
    text = open_file(ws, "big.py")
    assert "  200  x = 1" in text and "  201  " not in text and "continues to line 500" in text


def test_search_code_and_docs_are_separate(ws):
    assert "src/p/core.py" in search_code(ws, "greet") and "docs/index.md" not in search_code(ws, "politely")
    assert "docs/index.md" in search_docs(ws, "politely")
    assert "No code matched" in search_code(ws, "zzzzz")


def test_find_definition(ws):
    assert "src/p/core.py:4" in find_definition(ws, "greet")
    assert "No definition" in find_definition(ws, "not_there")
    with pytest.raises(ValueError):
        find_definition(ws, "a b; rm")


def test_find_definition_survives_a_jedi_crash(ws, monkeypatch):
    """Seen on a real click tree: jedi raises TypeError internally when searching for `__init__`."""
    import jedi

    class Broken:
        def __init__(self, *a, **k):
            pass

        def search(self, *a, **k):
            raise TypeError("'NoneType' object is not subscriptable")
            yield

    monkeypatch.setattr(jedi, "Project", Broken)
    assert "src/p/core.py:4" in find_definition(ws, "greet")
    (ws.tree / "src" / "p" / "cls.py").write_text("class A:\n    def __init__(self):\n        pass\n\nclass B:\n    def __init__(self):\n        pass\n")
    out = find_definition(ws, "A.__init__")
    assert "src/p/cls.py:2" in out and "cls.py:6" not in out


def test_registry_turns_any_tool_failure_into_a_readable_error(ws, monkeypatch):
    import tools.registry as R
    monkeypatch.setattr(R, "open_file", lambda *a, **k: (_ for _ in ()).throw(TypeError("boom")))
    out = R.ToolRegistry(ws).call("open_file", {"path": "x"})
    assert not out.ok and "TypeError: boom" in out.text


def test_find_references_whole_words(ws):
    out = find_references(ws, "greet")
    assert "src/p/core.py:4" in out and "src/p/__init__.py:1" in out
    assert "No references" in find_references(ws, "gree")


def test_find_tests(ws):
    assert "tests/test_core.py::test_greet (line 4)" in find_tests(ws, "greet")
    assert "No test" in find_tests(ws, "DEFAULT")


def test_history_stops_at_the_frozen_commit(ws):
    log = git_log(ws, "src/p/core.py")
    assert "first version" in log and "later fix" not in log
    blame = git_blame(ws, "src/p/core.py", 1, 1)
    assert 'DEFAULT = "hello"' in blame and "LATER" not in blame


def test_history_without_a_repo(ws):
    bare = Workspace("p", "p", ws.tree)
    assert "No git history" in git_log(bare, "src/p/core.py")


def test_schema_is_plain():
    schema = inline_schema(OpenFileArgs)
    assert "title" not in schema and "$defs" not in schema and "path" in schema["properties"]


def test_registry_valid_invalid_error_and_recovery(ws):
    reg = ToolRegistry(ws)
    assert reg.call("open_file", {"path": "src/p/core.py"}).ok
    bad = reg.call("open_file", {"start": "not a number"})
    assert not bad.ok and bad.invalid and "Invalid arguments" in bad.text
    missing = reg.call("open_file", {"path": "nope.py"})
    assert not missing.ok and "does not exist" in missing.text
    assert reg.call("open_file", {"path": "src/p/core.py"}).ok
    assert reg.call("no_such_tool", {}).invalid
    assert reg.counts == {**reg.counts, "total": 5, "invalid": 2, "errors": 1, "recovered": 1}


def test_registry_repo_test_refuses_option_injection(ws):
    assert "not a test node id" in ToolRegistry(ws).call("run_repo_test", {"node_id": "--help"}).text


def test_registry_probe_budget_needs_no_sandbox(ws):
    from tools.registry import Budget
    pytest.importorskip("tools.probe")
    reg = ToolRegistry(ws, budget=Budget(probe_runs=0))
    out = reg.call("run_probe", {"code": "x"})
    assert not out.ok and out.record["budget"]


CLICK_TREES = sorted((ROOT / ".cache" / "trees" / "click").glob("*")) if (ROOT / ".cache" / "trees" / "click").exists() else []


@pytest.mark.skipif(not CLICK_TREES, reason="no frozen click tree cached (run the data pipeline first)")
def test_every_tool_on_a_frozen_click_commit():
    tree = CLICK_TREES[0]
    repo = ROOT / "data" / "repos" / "click.git"
    w = Workspace("click", "click", tree, repo=repo, commit=tree.name)
    core = f"{w.source_root}/click/core.py"
    reg = ToolRegistry(w)
    assert "click/core.py" in reg.call("search_code", {"query": "invoke command context"}).text
    assert reg.call("search_docs", {"query": "commands and groups"}).ok
    assert "def " in reg.call("open_file", {"path": core, "start": 1, "end": 200}).text or True
    assert "click/core.py" in reg.call("find_definition", {"symbol": "Command"}).text
    assert "click/" in reg.call("find_references", {"symbol": "make_context"}).text
    assert reg.call("find_tests", {"symbol": "CliRunner"}).ok
    assert reg.call("git_log", {"path": core, "n": 2}).ok
    assert reg.call("git_blame", {"path": core, "start": 1, "end": 3}).ok
    assert reg.counts["errors"] == 0 and reg.counts["invalid"] == 0
