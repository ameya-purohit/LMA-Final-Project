"""LLMClient with fake providers: cache, retries, quota stop, token logging."""

import datetime as dt

import pytest

from core.config import load_config
from llm.cache import ReplyCache
from llm.client import LLMClient, QuotaLog
from llm.trace import Tracer
from llm.types import (LLMError, Message, QuotaExhausted, RateLimited, Reply, ToolCall, ToolSpec,
                       TransientError, Usage)


class FakeProvider:
    """Returns (or raises) the scripted items in order and records every call."""
    name = "gemini"

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def call(self, model, messages, tools, params):
        self.calls.append((model, messages, tools, params))
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeClock:
    def __init__(self):
        self.t = 1000.0
        self.sleeps = []

    def clock(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s


def reply(text="ok", calls=(), usage=Usage(10, 5, 2, 3, 20)):
    return Reply(text=text, tool_calls=list(calls), usage=usage, raw={"role": "model"}, provider="gemini",
                 model="gemini-3.1-flash-lite")


def make(tmp_path, script, cfg_override=None, day=dt.datetime(2026, 10, 28, 12, 0)):
    cfg = load_config([cfg_override or {}])
    fake = FakeProvider(script)
    clock = FakeClock()
    tracer = Tracer(None)
    client = LLMClient(cfg, providers={"gemini": fake, "groq": fake}, cache=ReplyCache(tmp_path / "c.sqlite"),
                       tracer=tracer, quota_log=QuotaLog(tmp_path / "quota.md"), clock=clock.clock,
                       sleep=clock.sleep, now=lambda: day)
    return client, fake, clock, tracer


MSGS = [Message(role="system", content="be brief"), Message(role="user", content="hi")]


def test_cache_hit_makes_zero_calls(tmp_path):
    client, fake, _, tracer = make(tmp_path, [reply("first")])
    r1 = client.complete(MSGS)
    r2 = client.complete(MSGS)
    assert len(fake.calls) == 1
    assert r1.text == r2.text == "first"
    assert not r1.from_cache and r2.from_cache
    assert client.stats["main"]["api_requests"] == 1 and client.stats["main"]["cache_hits"] == 1
    assert [rec["from_cache"] for rec in tracer.records if rec["event"] == "llm_call"] == [False, True]


def test_cache_survives_restart(tmp_path):
    client, fake, _, _ = make(tmp_path, [reply("x")])
    client.complete(MSGS)
    client2, fake2, _, _ = make(tmp_path, [])
    assert client2.complete(MSGS).text == "x" and fake2.calls == []


def test_cache_key_covers_tools_and_params(tmp_path):
    tool = ToolSpec("f", "d", {"type": "object", "properties": {}})
    client, fake, _, _ = make(tmp_path, [reply("a"), reply("b"), reply("c")])
    client.complete(MSGS)
    client.complete(MSGS, [tool])
    client.complete(MSGS, [tool], force_tool=True)
    assert len(fake.calls) == 3


def test_429_retry_honours_server_delay(tmp_path):
    err = RateLimited("slow down", retry_after=7.0, quota_id="GenerateRequestsPerMinutePerProjectPerModel-FreeTier",
                      quota_value="15")
    client, fake, clock, tracer = make(tmp_path, [err, TransientError("503"), reply("done")])
    assert client.complete(MSGS).text == "done"
    assert len(fake.calls) == 3
    assert any(7.0 <= s < 8.0 for s in clock.sleeps), clock.sleeps  # server delay + <1s jitter
    assert client.stats["main"]["retries"] == 2
    assert [r["kind"] for r in tracer.records if r["event"] == "llm_error"] == ["rate_limited", "transient"]
    assert "PerMinute" in (tmp_path / "quota.md").read_text()


def test_gives_up_after_max_attempts(tmp_path):
    client, fake, _, _ = make(tmp_path, [TransientError("503")] * 3, {"llm": {"retry": {"max_attempts": 3}}})
    with pytest.raises(LLMError, match="gave up after 3"):
        client.complete(MSGS)
    assert len(fake.calls) == 3


def test_fatal_error_not_retried(tmp_path):
    client, fake, _, _ = make(tmp_path, [LLMError("400 bad request")])
    with pytest.raises(LLMError, match="400"):
        client.complete(MSGS)
    assert len(fake.calls) == 1


def test_per_day_429_raises_quota_exhausted_and_logs_limit(tmp_path):
    err = RateLimited("quota", per_day=True, quota_id="GenerateRequestsPerDayPerProjectPerModel-FreeTier",
                      quota_value="500")
    client, fake, _, _ = make(tmp_path, [err, reply()])
    with pytest.raises(QuotaExhausted, match="500"):
        client.complete(MSGS)
    assert len(fake.calls) == 1, "a daily limit must not be retried"
    text = (tmp_path / "quota.md").read_text()
    assert "PerDay" in text and "| 500 |" in text and "| yes |" in text


def test_configured_daily_limit_stops_before_calling(tmp_path):
    client, fake, _, _ = make(tmp_path, [reply("a"), reply("b")], {"llm": {"main": {"rpd": 2}}})
    client.complete([Message(role="user", content="1")])
    client.complete([Message(role="user", content="2")])
    with pytest.raises(QuotaExhausted, match="daily limit 2"):
        client.complete([Message(role="user", content="3")])
    assert len(fake.calls) == 2
    # cached requests still work after the limit: resumed runs replay for free
    assert client.complete([Message(role="user", content="1")]).from_cache


def test_new_pacific_day_resets_count(tmp_path):
    client, _, _, _ = make(tmp_path, [reply("a")], {"llm": {"main": {"rpd": 1}}}, day=dt.datetime(2026, 10, 28))
    client.complete([Message(role="user", content="1")])
    tomorrow, fake, _, _ = make(tmp_path, [reply("b")], {"llm": {"main": {"rpd": 1}}}, day=dt.datetime(2026, 10, 29))
    assert tomorrow.complete([Message(role="user", content="2")]).text == "b"


def test_rpm_throttle_spaces_requests(tmp_path):
    client, _, clock, _ = make(tmp_path, [reply("a"), reply("b")], {"llm": {"main": {"rpm": 15}}})
    client.complete([Message(role="user", content="1")])
    client.complete([Message(role="user", content="2")])
    assert clock.sleeps == [pytest.approx(4.0)]  # 60 / 15


def test_tokens_logged_and_summed(tmp_path):
    client, _, _, tracer = make(tmp_path, [reply(usage=Usage(10, 5, 2, 3, 20)), reply("b", usage=Usage(1, 1, 0, 0, 2))])
    client.complete([Message(role="user", content="1")])
    client.complete([Message(role="user", content="2")])
    calls = [r for r in tracer.records if r["event"] == "llm_call"]
    assert calls[0]["usage"] == {"input": 10, "output": 5, "cached": 2, "thinking": 3, "total": 20}
    assert client.stats["main"]["usage"] == Usage(11, 6, 2, 3, 22)


def test_trace_has_context_and_no_raw(tmp_path):
    client, _, _, tracer = make(tmp_path, [reply(calls=[ToolCall("c1", "f", {"x": 1})])])
    with tracer.context(qid="click-1", system="ours"):
        r = client.complete(MSGS)
    rec = [x for x in tracer.records if x["event"] == "llm_call"][0]
    assert rec["qid"] == "click-1" and rec["system"] == "ours"
    assert rec["output"]["tool_calls"] == [{"id": "c1", "name": "f", "arguments": {"x": 1}}]
    assert "raw" not in rec["input"][0]
    assert r.as_message().raw == {"role": "model"} and r.as_message().raw_provider == "gemini"


def test_params_from_config_and_role_routing(tmp_path):
    client, fake, _, _ = make(tmp_path, [reply(), reply()], {"llm": {"main": {"thinking_level": "low"}}})
    client.complete(MSGS)
    client.complete(MSGS, role="judge")
    (m1, _, _, p1), (m2, _, _, p2) = fake.calls
    assert m1 == "gemini-3.1-flash-lite" and p1["temperature"] == 0.0 and p1["thinking_level"] == "low"
    assert m2 == "openai/gpt-oss-20b" and "thinking_level" not in p2
    with pytest.raises(ValueError):
        client.complete(MSGS, role="other")


def test_accepts_dict_messages(tmp_path):
    client, fake, _, _ = make(tmp_path, [reply()])
    client.complete([{"role": "user", "content": "hi"}])
    assert fake.calls[0][1][0].content == "hi"


def test_environment_lists_models_and_sdks(tmp_path):
    client, _, _, _ = make(tmp_path, [])
    env = client.environment()
    assert env["models"]["main"]["model"] == "gemini-3.1-flash-lite"
    assert set(env["sdk"]) == {"google-genai", "openai", "mistralai"}
