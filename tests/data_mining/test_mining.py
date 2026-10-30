"""The miner against a fake GitHub, plus patch splitting, the split and the schema check."""

import json
import subprocess

import pytest

from data import freeze
from data.mining.fix_pairs import GitHub, classify_files, is_bot, linked_issue_numbers, mine_library
from data.patch import apply_patch, parse_hunks, split_files, split_patch
from data.split import stratified_split
from data.validate_questions import check_questions

SPEC = {"owner": "o", "repo": "r", "package": "pkg", "tests_dir": "tests"}


@pytest.mark.parametrize("text,expected", [
    ("Fixes #12", [12]), ("closes #3 and resolves #4", [3, 4]), ("fix: #7", [7]),
    ("Resolved https://github.com/o/r/issues/9", [9]), ("see #5 for context", []), ("prefix #5", []),
])
def test_link_regex(text, expected):
    assert linked_issue_numbers({"title": "", "body": text}) == expected


def test_is_bot():
    assert is_bot({"type": "Bot", "login": "x"}) and is_bot({"login": "renovate[bot]"}) and not is_bot({"type": "User", "login": "a"})


def test_classify_files():
    files = [{"filename": f} for f in ("src/pkg/a.py", "pkg/b.py", "tests/test_a.py", "docs/x.rst", "CHANGES.rst", "setup.py")]
    g = classify_files(files, "pkg", "tests")
    assert g["source"] == ["src/pkg/a.py", "pkg/b.py"] and g["test"] == ["tests/test_a.py"]
    assert g["docs"] == ["docs/x.rst", "CHANGES.rst"] and g["other"] == ["setup.py"]


class FakeResponse:
    def __init__(self, data, status=200, headers=None):
        self.data, self.status_code, self.headers = data, status, headers or {}

    def json(self):
        return self.data

    def raise_for_status(self):
        pass


class FakeSession:
    def __init__(self, routes):
        self.routes = routes
        self.calls = 0

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls += 1
        path = url.replace("https://api.github.com", "")
        data = self.routes.get(path)
        if data is None:
            return FakeResponse(None, 404)
        if params and params.get("page", 1) > 1:
            return FakeResponse([])
        return FakeResponse(data)


def pr(n, merged="2021-01-01T00:00:00Z", title="", body=""):
    return {"number": n, "merged_at": merged, "title": title, "body": body, "html_url": f"u/{n}", "merge_commit_sha": f"m{n}",
            "base": {"ref": "main", "sha": f"b{n}"}}


ISSUE = {"number": 50, "html_url": "i/50", "created_at": "2020-06-01", "title": "T", "body": "B", "user": {"login": "a", "type": "User"}}
SRC_AND_TEST = [{"filename": "src/pkg/a.py"}, {"filename": "tests/test_a.py"}]
ROUTES = {
    "/repos/o/r/pulls": [pr(1, title="Fixes #50"), pr(2, merged=None), pr(3, merged="2019-01-01T00:00:00Z"),
                         pr(4, title="no link"), pr(5, title="fix #51"), pr(6, title="fix #50"), pr(7, title="fix #50"),
                         pr(8, title="fix #52"), pr(9, title="fix #50")],
    "/repos/o/r/issues/50": ISSUE,
    "/repos/o/r/issues/51": {**ISSUE, "number": 51, "pull_request": {}},
    "/repos/o/r/issues/52": {**ISSUE, "number": 52, "user": {"login": "x[bot]", "type": "Bot"}},
    "/repos/o/r/issues/4/timeline": [], "/repos/o/r/issues/5/timeline": [],
    "/repos/o/r/pulls/1/files": SRC_AND_TEST,
    "/repos/o/r/pulls/6/files": [{"filename": "docs/a.rst"}, {"filename": "tests/t.py"}],
    "/repos/o/r/pulls/7/files": [{"filename": "src/pkg/a.py"}],
    "/repos/o/r/pulls/9/files": [{"filename": f"src/pkg/f{i}.py"} for i in range(11)] + [{"filename": "tests/t.py"}],
    "/repos/o/r/pulls/1": {"commits": 2},
}


def run_miner(tmp_path):
    session = FakeSession(ROUTES)
    gh = GitHub(tmp_path / "gh", token="t", session=session, sleep=lambda s: None)
    dropped, counts = [], {}
    pairs = mine_library(gh, "lib", SPEC, merged_since="2020-01-01", max_source_files=10, drop=dropped.append, counts=counts)
    return pairs, dropped, counts, session


def test_funnel_counts_and_reasons(tmp_path):
    pairs, dropped, counts, _ = run_miner(tmp_path)
    assert [p["pr_number"] for p in pairs] == [1] and pairs[0]["pr_commits"] == 2
    assert counts["closed_prs"] == 9 and counts["merged_prs_all_time"] == 8 and counts["merged_prs"] == 7
    assert counts["linked_issue"] == 5 and counts["issue_not_bot"] == 4 and counts["source_and_test"] == 2 and counts["candidates"] == 1
    assert sorted(d["reason"] for d in dropped) == sorted(["no_linked_issue", "no_linked_issue", "no_source_change", "no_test_change",
                                                           "issue_by_bot", "too_many_source_files"])


def test_cache_makes_rerun_free(tmp_path):
    _, _, _, first = run_miner(tmp_path)
    assert first.calls > 0
    _, _, _, second = run_miner(tmp_path)
    assert second.calls == 0


DIFF = """diff --git a/src/pkg/a.py b/src/pkg/a.py
--- a/src/pkg/a.py
+++ b/src/pkg/a.py
@@ -1,2 +1,2 @@
-x = 1
+x = 2
 y = 2
diff --git a/tests/test_a.py b/tests/test_a.py
--- a/tests/test_a.py
+++ b/tests/test_a.py
@@ -1 +1,2 @@
 import pkg
+# new
diff --git a/docs/a.rst b/docs/a.rst
--- a/docs/a.rst
+++ b/docs/a.rst
@@ -1 +1 @@
-old
+new
diff --git a/CHANGES.rst b/CHANGES.rst
--- a/CHANGES.rst
+++ b/CHANGES.rst
@@ -1 +1 @@
-old
+new
"""


def test_split_patch():
    parts = split_patch(DIFF, "pkg", "tests")
    assert parts.source_paths == ["src/pkg/a.py"] and parts.test_paths == ["tests/test_a.py"]
    assert parts.docs_paths == ["docs/a.rst"] and parts.other_paths == ["CHANGES.rst"]
    assert "x = 2" in parts.source and "x = 2" not in parts.test and "# new" in parts.test
    assert [p for p, _ in split_files(DIFF)] == ["src/pkg/a.py", "tests/test_a.py", "docs/a.rst", "CHANGES.rst"]


def test_parse_hunks():
    h = parse_hunks(split_files(DIFF)[0][1])[0]
    assert (h.old_start, h.old_count, h.new_start, h.new_count) == (1, 2, 1, 2)
    assert h.old_lines == ["x = 1"] and h.new_lines == ["x = 2"]


def _repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    def g(*a):
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *a], check=True, capture_output=True)
    g("init", "-q")
    (repo / "a.py").write_text("x = 1\ny = 2\n")
    g("add", "-A"); g("commit", "-qm", "one")
    base = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    (repo / "a.py").write_text("x = 3\ny = 2\n")
    g("add", "-A"); g("commit", "-qm", "two")
    (repo / "b.py").write_text("z = 1\n")
    g("add", "-A"); g("commit", "-qm", "three")
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    return repo, base, head


def test_apply_patch_inside_an_enclosing_repo(tmp_path):
    """`git apply` would silently do nothing here if it discovered the enclosing repository."""
    repo, base, head = _repo(tmp_path)
    tree = repo / "tree"
    tree.mkdir()
    (tree / "a.py").write_text("x = 1\ny = 2\n")
    diff = freeze.git(repo, "diff", base, head)
    apply_patch(tree, diff)
    assert (tree / "a.py").read_text() == "x = 3\ny = 2\n" and (tree / "b.py").exists()
    with pytest.raises(RuntimeError):
        apply_patch(tree, diff)


def test_freeze_squash_and_rebase_and_export(tmp_path):
    repo, base, head = _repo(tmp_path)
    assert freeze.commit_exists(repo, head) and not freeze.commit_exists(repo, "0" * 40)
    assert freeze.is_ancestor(repo, base, head) and not freeze.is_ancestor(repo, head, base)
    # squash: the last commit alone holds the PR's files
    parent = freeze.parents(repo, head)[0]
    assert freeze.frozen_commit(repo, head, {"b.py"}, 1) == parent
    # rebase: two PR commits, whose files span both
    assert freeze.frozen_commit(repo, head, {"a.py", "b.py"}, 2) == base
    tree = freeze.export_tree(repo, base, tmp_path / "t")
    assert (tree / "a.py").read_text() == "x = 1\ny = 2\n" and not (tree / "b.py").exists()
    assert freeze.export_tree(repo, base, tmp_path / "t") == tree


def _q(qid, lib="click", cat="single_location"):
    return {"qid": qid, "library": lib, "category": cat}


def test_split_is_stratified_exact_and_seeded():
    qs = [_q(f"a{i}") for i in range(60)] + [_q(f"b{i}", "marshmallow", "doc_related") for i in range(40)]
    dev, test = stratified_split(qs, 20, 82)
    assert len(dev) == 20 and len(test) == 80 and not {q["qid"] for q in dev} & {q["qid"] for q in test}
    assert sum(q["library"] == "click" for q in dev) == 12
    again, _ = stratified_split(list(reversed(qs)), 20, 82)
    assert [q["qid"] for q in dev] == [q["qid"] for q in again], "must not depend on input order"
    other, _ = stratified_split(qs, 20, 83)
    assert [q["qid"] for q in dev] != [q["qid"] for q in other]


VALID = {"qid": "click-1", "library": "click", "issue_url": "u", "issue_number": 1, "created_at": "2021", "question_text": "why?",
         "fix_pr_url": "p", "fix_pr_number": 2, "fix_merge_commit": "m", "frozen_commit": "f", "fail_to_pass": ["t"],
         "observed_before": [{"test": "t", "status": "failed", "message": "x"}], "observed_after": [{"test": "t", "status": "passed"}],
         "gold_evidence": [{"path": "a.py", "line_start": 1, "line_end": 2, "kind": "changed"}], "fix_source_files": ["a.py"],
         "fix_diff_stats": {"files": 1, "lines_added": 1, "lines_removed": 1}, "gold_answer": "g", "category": "single_location"}


def test_check_questions():
    assert check_questions([VALID]) == []
    assert any("duplicate" in p for p in check_questions([VALID, VALID]))
    assert any("schema" in p for p in check_questions([{**VALID, "category": "bad"}]))
    assert any("names the fix" in p for p in check_questions([{**VALID, "question_text": "see pull/2"}]))
    assert any("empty" in p for p in check_questions([{**VALID, "fail_to_pass": []}]))
    assert any("equals" in p for p in check_questions([{**VALID, "frozen_commit": "m"}]))
