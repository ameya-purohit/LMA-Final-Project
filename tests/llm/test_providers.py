"""Provider translation and error classification, offline (no network)."""

from types import SimpleNamespace

from llm.providers import gemini, groq, openai_format
from llm.types import LLMError, Message, RateLimited, ToolCall, ToolSpec, TransientError

TOOL = ToolSpec("get_weather", "Weather for a city", {"type": "object", "properties": {"city": {"type": "string"}},
                                                       "required": ["city"]})


def test_gemini_contents_group_tool_results_and_replay_raw():
    from google.genai import types
    raw_model = types.Content(role="model", parts=[
        types.Part(function_call=types.FunctionCall(name="get_weather", args={"city": "Pune"}), thought_signature=b"\x01sig"),
        types.Part(function_call=types.FunctionCall(name="get_weather", args={"city": "Delhi"})),
    ]).model_dump(mode="json", exclude_none=True)
    msgs = [
        Message(role="system", content="sys"),
        Message(role="user", content="weather?"),
        Message(role="assistant", tool_calls=[ToolCall("a", "get_weather", {"city": "Pune"})], raw=raw_model,
                raw_provider="gemini"),
        Message(role="tool", name="get_weather", tool_call_id="a", content="sunny"),
        Message(role="tool", name="get_weather", tool_call_id="b", content="rain"),
    ]
    system, contents = gemini.to_contents(msgs)
    assert system == "sys"
    assert [c.role for c in contents] == ["user", "model", "user"]
    assert contents[1].parts[0].thought_signature == b"\x01sig", "thought signature must survive replay"
    assert len(contents[2].parts) == 2 and contents[2].parts[1].function_response.response == {"result": "rain"}


def test_gemini_ignores_raw_from_other_provider():
    msgs = [Message(role="assistant", content="hi", raw={"bogus": 1}, raw_provider="groq")]
    _, contents = gemini.to_contents(msgs)
    assert contents[0].role == "model" and contents[0].parts[0].text == "hi"


def test_gemini_config_disables_afc_and_sets_tools():
    cfg = gemini.build_config("sys", [TOOL], {"temperature": 0.0, "max_output_tokens": 100, "thinking_level": "low"})
    assert cfg.automatic_function_calling.disable is True
    assert cfg.tools[0].function_declarations[0].parameters_json_schema["required"] == ["city"]
    assert cfg.thinking_config.thinking_level.value.lower() == "low"
    assert gemini.build_config(None, None, {}).thinking_config is None


def test_gemini_parse_response_skips_thoughts():
    from google.genai import types
    resp = types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=[
            types.Part(text="thinking...", thought=True), types.Part(text="Answer"),
            types.Part(function_call=types.FunctionCall(name="f", args={"x": 1}), thought_signature=b"s")]),
            finish_reason="STOP")],
        usage_metadata=types.GenerateContentResponseUsageMetadata(prompt_token_count=10, candidates_token_count=4,
                                                                 thoughts_token_count=3, total_token_count=17))
    r = gemini.parse_response(resp, "m")
    assert r.text == "Answer" and r.tool_calls[0].name == "f" and r.tool_calls[0].arguments == {"x": 1}
    assert r.usage.input == 10 and r.usage.thinking == 3 and r.usage.total == 17
    assert types.Content.model_validate(r.raw).parts[2].thought_signature == b"s"


def _api_error(code, body):
    from google.genai import errors
    return errors.APIError(code, body)


def test_gemini_429_per_day_parsed():
    body = {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "message": "quota", "details": [
        {"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": [
            {"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier", "quotaValue": "500"}]},
        {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "41s"}]}}
    e = gemini.classify_error(_api_error(429, body))
    assert isinstance(e, RateLimited) and e.per_day and e.quota_value == "500" and e.retry_after == 41.0


def test_gemini_429_per_minute_and_5xx_and_400():
    body = {"error": {"code": 429, "details": [{"@type": "x.QuotaFailure", "violations": [
        {"quotaId": "GenerateRequestsPerMinutePerProjectPerModel-FreeTier", "quotaValue": "15"}]}]}}
    e = gemini.classify_error(_api_error(429, body))
    assert isinstance(e, RateLimited) and not e.per_day and e.quota_value == "15"
    assert isinstance(gemini.classify_error(_api_error(503, {"error": {"code": 503}})), TransientError)
    bad = gemini.classify_error(_api_error(400, {"error": {"code": 400, "message": "bad"}}))
    assert isinstance(bad, LLMError) and not isinstance(bad, (RateLimited, TransientError))


def test_openai_format_roundtrip_and_bad_json_args():
    msgs = openai_format.to_messages([
        Message(role="user", content="q"),
        Message(role="assistant", tool_calls=[ToolCall("c1", "f", {"a": 1})]),
        Message(role="tool", tool_call_id="c1", name="f", content="r"),
    ])
    assert msgs[1]["tool_calls"][0]["function"]["arguments"] == '{"a": 1}'
    assert msgs[2] == {"role": "tool", "tool_call_id": "c1", "name": "f", "content": "r"}
    raw = [SimpleNamespace(id="x", function=SimpleNamespace(name="f", arguments="{not json"))]
    assert openai_format.parse_tool_calls(raw)[0].arguments == {"_raw": "{not json"}


class _StatusError(Exception):
    def __init__(self, status, text, headers=None):
        super().__init__(text)
        self.status_code = status
        self.response = SimpleNamespace(headers=headers or {})


def test_groq_errors():
    e = groq.classify_error(_StatusError(429, "Rate limit reached for model `m` on requests per day (RPD): "
                                              "Limit 1000, Used 1000, Requested 1. Please try again in 1m30.5s."))
    assert isinstance(e, RateLimited) and e.per_day and e.quota_id == "RPD" and e.quota_value == "1000"
    assert e.retry_after == 90.5
    e = groq.classify_error(_StatusError(429, "on tokens per minute (TPM): Limit 8000, Used 7000", {"retry-after": "3"}))
    assert not e.per_day and e.quota_id == "TPM" and e.retry_after == 3.0
    assert isinstance(groq.classify_error(_StatusError(502, "bad gateway")), TransientError)
