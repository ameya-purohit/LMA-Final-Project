"""Gold is built by code alone: the validation rule, evidence ranges, category and templates."""

from data.build_gold import category, clean_question, docstrings, evidence_from_hunks, gold_answer
from data.patch import Hunk
from data.validate_pairs import changed_test_names, decide, node_name, select_changed, find_test_ranges


TEST_FILE = """import pytest

def helper():
    return 1

@pytest.mark.parametrize("x", [1, 2])
def test_one(x):
    assert x

class TestThing:
    def test_two(self):
        assert True
"""


def test_ranges_include_decorators_and_classes():
    assert find_test_ranges(TEST_FILE) == [("test_one", 6, 8), ("TestThing::test_two", 11, 12)]


def _diff(start, count):
    return f"@@ -1 +{start},{count} @@\n+x\n"


def test_changed_test_names():
    assert changed_test_names(_diff(6, 1), TEST_FILE) == {"test_one"}, "a change to the decorator counts"
    assert changed_test_names(_diff(12, 1), TEST_FILE) == {"TestThing::test_two"}
    assert changed_test_names(_diff(3, 2), TEST_FILE) is None, "a helper change means every test in the file"


def test_node_name():
    assert node_name("tests/t.py::TestThing::test_two[a-b]") == ("tests/t.py", "TestThing::test_two")


def test_select_changed():
    tests = {"t.py::a": {}, "t.py::b[1]": {}, "u.py::c": {}, "v.py::d": {}}
    assert set(select_changed(tests, {"t.py": {"b"}, "u.py": None})) == {"t.py::b[1]", "u.py::c"}


def st(status, message=""):
    return {"status": status, "message": message}


CHANGED = {"t.py": {"a", "b"}}


def test_decide_valid():
    v = decide({"t.py::a": st("failed", "boom"), "t.py::b": st("passed"), "t.py::other": st("failed", "unrelated")},
               {"t.py::a": st("passed"), "t.py::b": st("passed"), "t.py::other": st("failed")}, CHANGED)
    assert v["valid"] and v["fail_to_pass"] == ["t.py::a"]
    assert v["observed_before"] == [{"test": "t.py::a", "status": "failed", "message": "boom"}]
    assert v["observed_after"] == [{"test": "t.py::a", "status": "passed"}]


def test_decide_new_test_missing_before_import_error():
    """The new test imports a name the frozen code lacks: the file fails to collect before the fix."""
    v = decide({"t.py": st("error", "ImportError: cannot import X")}, {"t.py::a": st("passed"), "t.py::z": st("passed")}, CHANGED)
    assert v["valid"] and v["fail_to_pass"] == ["t.py::a"] and "ImportError" in v["observed_before"][0]["message"]


def test_decide_invalid_cases():
    assert decide({"t.py::a": st("passed")}, {"t.py::a": st("passed")}, CHANGED)["reason"] == "no_test_fails_before_fix"
    assert decide({"t.py::a": st("failed")}, {"t.py::a": st("failed")}, CHANGED)["reason"] == "fail_to_pass_test_not_passing_after_fix"
    assert decide({"t.py": st("error")}, {"t.py": st("error", "missing dep")}, CHANGED)["reason"] == "test_error_with_fix_applied"
    assert decide({}, {}, CHANGED)["reason"] == "no_changed_tests_collected"


def h(old_start, old, new, new_start=1):
    return Hunk(old_start, len(old), new_start, len(new), old, new)


def test_evidence_changed_deleted_anchor_and_merging():
    ev = evidence_from_hunks("a.py", [h(10, ["a = 1", "b = 2"], ["a = 3"]), h(20, ["c = 1"], []), h(30, [], ["new = 1"])])
    assert ev == [{"path": "a.py", "line_start": 10, "line_end": 11, "kind": "changed"},
                  {"path": "a.py", "line_start": 20, "line_end": 20, "kind": "deleted"},
                  {"path": "a.py", "line_start": 30, "line_end": 30, "kind": "anchor_for_insert"}]


def test_evidence_ignores_whitespace_and_comments():
    assert evidence_from_hunks("a.py", [h(1, ["a = 1"], ["  a = 1"]), h(5, ["# old"], ["# new"]), h(9, ["", "# x"], [""])]) == []
    ev = evidence_from_hunks("a.py", [h(5, ["# old", "code = 1"], ["code = 2"])])
    assert ev == [{"path": "a.py", "line_start": 6, "line_end": 6, "kind": "changed"}], "only the code line is evidence"
    assert evidence_from_hunks("a.py", [h(0, [], ["x = 1"])])[0]["line_start"] == 1, "an insert at the top anchors on line 1"
    assert evidence_from_hunks("a.py", [h(5, ["# c"], ["x = 1"])])[0]["kind"] == "anchor_for_insert"


def test_category():
    assert category("the docs say", [], False, 1) == "doc_related"
    assert category("Documentation is wrong", [], False, 1) == "doc_related"
    assert category("a bug", ["docs/x.rst"], False, 1) == "doc_related"
    assert category("a bug", [], True, 1) == "doc_related"
    assert category("a bug", [], False, 2) == "spread_across_files"
    assert category("a bug", [], False, 1) == "single_location"
    assert category("the doctor is in", [], False, 1) == "single_location"


def test_docstrings_detects_changes():
    assert docstrings('def f():\n    """a"""\n') != docstrings('def f():\n    """b"""\n')
    assert docstrings("def f(:") == []


def test_clean_question():
    q = clean_question(" T ", "<!-- template -->\nHello @octocat, see user@example.com\n")
    assert q == "T\n\nHello @user, see user@example.com"
    assert clean_question("T", None) == "T"
    assert clean_question("T", "x" * 7000).endswith("[truncated]")


def test_gold_answer_is_a_template():
    text = gold_answer({"test": "t.py::a", "message": "assert\n  1 == 2"},
                       [{"path": "a.py", "line_start": 3, "line_end": 4, "kind": "changed"}], 77)
    assert text == "On the frozen version, `t.py::a` fails: assert 1 == 2. The behaviour is decided in `a.py` lines 3-4, which the merged fix (PR #77) changed."
