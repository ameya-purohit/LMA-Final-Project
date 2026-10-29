"""Groq provider: the `openai` SDK pointed at Groq's OpenAI-compatible API.

Used for the judge (decision D-02). Groq reports daily limits in the 429
message text, e.g. "... on requests per day (RPD): Limit 14400, Used ...",
which we parse into a quota id and value.
"""

from __future__ import annotations

import re
from typing import Any

from llm.providers import openai_format as fmt
from llm.types import LLMError, Message, RateLimited, Reply, ToolSpec, TransientError

NAME = "groq"
BASE_URL = "https://api.groq.com/openai/v1"

_LIMIT = re.compile(r"on (?P<what>[\w ]+?) \((?P<id>[A-Z]{3})\): Limit (?P<value>\d+)")
_TRY_AGAIN = re.compile(r"try again in (?:(?P<m>\d+)m)?(?P<s>[\d.]+)s", re.I)


def classify_error(exc: Exception) -> Exception:
    status = getattr(exc, "status_code", None)
    text = str(exc)
    if status == 429:
        m = _LIMIT.search(text)
        quota_id = m.group("id") if m else None
        per_day = bool(quota_id and quota_id.endswith("D")) or bool(re.search(r"per day", text, re.I))
        retry_after = None
        headers = getattr(getattr(exc, "response", None), "headers", None) or {}
        if headers.get("retry-after"):
            try:
                retry_after = float(headers["retry-after"])
            except ValueError:
                pass
        if retry_after is None:
            t = _TRY_AGAIN.search(text)
            if t:
                retry_after = float(t.group("s")) + 60 * float(t.group("m") or 0)
        return RateLimited(text[:500], retry_after=retry_after, per_day=per_day,
                           quota_id=quota_id, quota_value=m.group("value") if m else None)
    if isinstance(status, int) and status >= 500:
        return TransientError(text[:500])
    if status is None and exc.__class__.__name__ in ("APIConnectionError", "APITimeoutError"):
        return TransientError(f"{exc.__class__.__name__}: {text}"[:500])
    return LLMError(f"{exc.__class__.__name__}: {text}"[:500])


class GroqProvider:
    name = NAME

    def __init__(self, api_key: str):
        from openai import OpenAI
        # max_retries=0: retries and pacing are done by our client, uniformly for all providers.
        self._client = OpenAI(api_key=api_key, base_url=BASE_URL, max_retries=0, timeout=120)

    def call(self, model: str, messages: list[Message], tools: list[ToolSpec] | None,
             params: dict[str, Any]) -> Reply:
        kwargs: dict[str, Any] = {"model": model, "messages": fmt.to_messages(messages),
                                  "temperature": params.get("temperature", 0.0)}
        if params.get("max_output_tokens"):
            kwargs["max_tokens"] = params["max_output_tokens"]
        if tools:
            kwargs["tools"] = fmt.to_tools(tools)
            if params.get("force_tool"):
                kwargs["tool_choice"] = "required"
        if params.get("json_mode"):
            kwargs["response_format"] = {"type": "json_object"}
        try:
            r = self._client.chat.completions.create(**kwargs)
        except Exception as exc:
            raise classify_error(exc) from exc
        choice = r.choices[0]
        return Reply(text=choice.message.content or "", tool_calls=fmt.parse_tool_calls(choice.message.tool_calls),
                     usage=fmt.parse_usage(r.usage), raw=None, provider=NAME, model=model,
                     finish_reason=choice.finish_reason)
