from pathlib import Path

import pytest

from core import config as C


def test_deep_merge_nested_and_lists_replaced():
    base = {"a": {"b": 1, "c": [1, 2]}, "d": 3}
    out = C.deep_merge(base, {"a": {"c": [9]}, "e": 5})
    assert out == {"a": {"b": 1, "c": [9]}, "d": 3, "e": 5}
    assert base == {"a": {"b": 1, "c": [1, 2]}, "d": 3}, "base must not be mutated"


def test_load_default_has_one_section_per_area():
    cfg = C.load_config()
    for section in ("paths", "llm", "sandbox", "mutation", "data", "retrieval", "tools", "agent", "baselines", "eval"):
        assert section in cfg
    assert cfg["llm"]["temperature"] == 0.0


def test_model_ids_only_in_config():
    cfg = C.load_config()
    assert cfg["llm"]["main"]["model"] == "gemini-3.1-flash-lite"
    assert cfg["llm"]["judge"]["provider"] == "groq"
    assert cfg["llm"]["judge"]["model"] == "openai/gpt-oss-20b"


def test_overrides_from_dict_and_file(tmp_path: Path):
    f = tmp_path / "o.yaml"
    f.write_text("agent:\n  ablation:\n    no_mutation: true\n")
    cfg = C.load_config([{"agent": {"max_probe_runs": 4}}, f])
    assert cfg["agent"]["max_probe_runs"] == 4
    assert cfg["agent"]["ablation"]["no_mutation"] is True
    assert cfg["agent"]["ablation"]["no_execution"] is False


def test_bad_top_level(tmp_path: Path):
    f = tmp_path / "bad.yaml"
    f.write_text("- 1\n- 2\n")
    with pytest.raises(ValueError):
        C.load_config([f])


def test_get_hash_and_diff():
    a = C.load_config()
    b = C.load_config([{"agent": {"ablation": {"flag_only": True}}}])
    assert C.get(a, "llm.main.model") == "gemini-3.1-flash-lite"
    assert C.get(a, "no.such.key", 7) == 7
    assert C.config_hash(a) == C.config_hash(C.load_config())
    assert C.config_hash(a) != C.config_hash(b)
    assert C.diff(a, b) == {"agent.ablation.flag_only": (False, True)}
