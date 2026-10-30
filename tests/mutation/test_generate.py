"""Mutant generation: operators, AST-equal skipping, byte-identity outside the mutated line."""

import re

from tools.mutate import enclosing_function_lines, generate_mutants

from pathlib import Path

CORE = Path(__file__).resolve().parents[1] / "fixtures" / "toylib" / "src" / "toylib" / "core.py"
SRC = CORE.read_text()


def line_of(name):
    return next(i for i, l in enumerate(SRC.splitlines(), 1) if re.search(rf"# MARK: {name}\b", l))


def descs(line, **kw):
    return [(m.operator, m.description) for m in generate_mutants(SRC, line, "toylib/core.py", **kw)]


def test_planted_line_numbers():
    assert line_of("strict_default") == 12
    assert line_of("decider") == 88


def test_decider_operators():
    d = descs(88)
    ops = [o for o, _ in d]
    assert ("constant", "0 -> -1") in d and ("constant", "0 -> 1") in d and ("constant", "0 -> None") in d
    assert any(o == "constant" and "negative" in x for o, x in d)  # string -> ""
    assert ("negate_condition", "negate if condition") in d
    assert ("swap_comparison", "< -> <=") in d
    assert any(o == "delete_statement" and "raise" in x for o, x in d)
    assert ops == sorted(ops, key=["constant", "negate_condition", "swap_comparison",
                                   "delete_statement", "return_none"].index)


def test_strict_default_and_return_and_min():
    assert descs(12) == [("constant", "True -> False"), ("delete_statement", "delete `STRICT_DEFAULT = True`")]
    ret = descs(line_of("return_result"))
    assert ("return_none", "return <expr> -> return None") in ret
    assert any(o == "delete_statement" and "min(" in x for o, x in descs(line_of("min_result")))


def test_constants_only_and_no_const_line():
    assert all(o == "constant" for o, _ in descs(88, operators=["constant"]))
    assert descs(line_of("compare_no_const"), operators=["constant"]) == []
    assert ("swap_comparison", ">= -> >") in descs(line_of("compare_no_const"))


def test_every_mutant_changes_only_its_line():
    """Byte-identical outside the mutated span, for every mutant of every planted line."""
    original = SRC.splitlines(keepends=True)
    marks = [i for i, l in enumerate(original, 1) if "# MARK:" in l]
    total = 0
    for line in marks:
        for m in generate_mutants(SRC, line, "toylib/core.py"):
            new = m.code.splitlines(keepends=True)
            assert len(new) == len(original)
            for i, (a, b) in enumerate(zip(original, new), 1):
                if i != line:
                    assert a == b, f"mutant {m.description} of line {line} changed line {i}"
            comment = original[line - 1][original[line - 1].index("#"):]
            assert new[line - 1].endswith(comment), "the trailing comment must survive"
            assert new[line - 1] != original[line - 1]
            total += 1
    assert total > 20


def test_ast_equal_mutants_skipped():
    src = "x = 1\ny = (x)\n"
    # the only node on line 2 that an operator applies to is the assignment (delete); no no-op mutants
    assert [m.operator for m in generate_mutants(src, 2)] == ["delete_statement"]


def test_blank_and_comment_lines_have_no_mutants():
    assert generate_mutants(SRC, 2) == []
    assert generate_mutants(SRC, 10) == []  # comment line


def test_enclosing_function_lines():
    name, lines = enclosing_function_lines(SRC, 88)
    assert name == "clamp" and lines == [87, 88, 89, 90, 91]
    assert enclosing_function_lines(SRC, 12) is None
