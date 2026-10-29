from llm.cache import ReplyCache, cache_key
from llm.types import Message, Reply, ToolCall, Usage


def test_key_is_stable_and_sensitive():
    m = [{"role": "user", "content": "hi"}]
    k = cache_key("gemini", "m", m, None, {"temperature": 0})
    assert k == cache_key("gemini", "m", m, [], {"temperature": 0})
    assert k != cache_key("gemini", "m2", m, None, {"temperature": 0})
    assert k != cache_key("gemini", "m", [{"role": "user", "content": "hi!"}], None, {"temperature": 0})
    assert k != cache_key("groq", "m", m, None, {"temperature": 0})


def test_put_get_roundtrip(tmp_path):
    c = ReplyCache(tmp_path / "x.sqlite")
    r = Reply("t", [ToolCall("1", "f", {"a": [1]})], Usage(1, 2, 3, 4, 10), raw={"parts": [{"thought_signature": "AP9z"}]},
              provider="gemini", model="m")
    c.put("k", r)
    got = c.get("k")
    assert got.from_cache and got.tool_calls[0].arguments == {"a": [1]} and got.usage.total == 10
    assert got.raw == r.raw
    assert c.get("missing") is None and len(c) == 1


def test_daily_counter(tmp_path):
    c = ReplyCache(tmp_path / "x.sqlite")
    assert c.count_request("2026-10-28", "gemini", "m") == 1
    assert c.count_request("2026-10-28", "gemini", "m") == 2
    assert c.requests_on("2026-10-29", "gemini", "m") == 0


def test_message_dict_roundtrip():
    m = Message(role="assistant", content="x", tool_calls=[ToolCall("1", "f", {})], raw={"a": 1}, raw_provider="gemini")
    assert Message.from_dict(m.to_dict()) == m


def test_usage_add():
    assert Usage(1, 2, 3, 4, 5) + Usage(1, 1, 1, 1, 1) == Usage(2, 3, 4, 5, 6)
