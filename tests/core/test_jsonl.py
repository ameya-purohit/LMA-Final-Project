import pytest

from core.jsonl import append_jsonl, dumps, read_jsonl, write_jsonl


def test_roundtrip_and_append(tmp_path):
    p = tmp_path / "sub" / "x.jsonl"
    assert write_jsonl(p, [{"b": 1, "a": "é"}, {"c": [1, 2]}]) == 2
    append_jsonl(p, {"d": None})
    assert read_jsonl(p) == [{"a": "é", "b": 1}, {"c": [1, 2]}, {"d": None}]
    assert not p.with_suffix(".jsonl.tmp").exists()


def test_blank_lines_skipped_and_bad_line_reported(tmp_path):
    p = tmp_path / "x.jsonl"
    p.write_text('{"a": 1}\n\n{oops\n')
    with pytest.raises(ValueError, match=":3:"):
        read_jsonl(p)


def test_dumps_is_stable():
    assert dumps({"b": 1, "a": 2}) == '{"a":2,"b":1}'


def test_lone_surrogates_do_not_crash_writes(tmp_path):
    """Real test output can hold undecodable bytes (seen while validating a click pair)."""
    p = tmp_path / "x.jsonl"
    write_jsonl(p, [{"m": "bad \udcff byte"}])
    append_jsonl(p, {"m": "bad \udcff byte"})
    assert len(read_jsonl(p)) == 2
