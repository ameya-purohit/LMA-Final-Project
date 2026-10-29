"""Mistral provider (`mistralai` SDK). Used only if Mistral is chosen as the
final judge at P8 (decision D-02); not needed before then."""

from __future__ import annotations

from typing import Any

from llm.providers import openai_format as fmt
from llm.types import LLMError, Message, RateLimited, Reply, ToolSpec, TransientError

NAME = "mistral"


def classify_error(exc: Exception) -> Exception:
    status = getattr(exc, "status_code", None)
    text = str(exc)
    if status == 429:
        per_day = "day" in text.lower() or "month" in text.lower()
        return RateLimited(text[:500], retry_after=None, per_day=per_day)
    if isinstance(status, int) and status >= 500:
        return TransientError(text[:500])
    return LLMError(f"{exc.__class__.__name__}: {text}"[:500])


class MistralProvider:
    name = NAME

    def __init__(self, api_key: str):
        from mistralai import Mistral
        self._client = Mistral(api_key=api_key)

    def call(self, model: str, messages: list[Message], tools: list[ToolSpec] | None,
             params: dict[str, Any]) -> Reply:
        kwargs: dict[str, Any] = {"model": model, "messages": fmt.to_messages(messages),
                                  "temperature": params.get("temperature", 0.0)}
        if params.get("max_output_tokens"):
            kwargs["max_tokens"] = params["max_output_tokens"]
        if tools:
            kwargs["tools"] = fmt.to_tools(tools)
            if params.get("force_tool"):
                kwargs["tool_choice"] = "any"
        if params.get("json_mode"):
            kwargs["response_format"] = {"type": "json_object"}
        try:
            r = self._client.chat.complete(**kwargs)
        except Exception as exc:
            raise classify_error(exc) from exc
        choice = r.choices[0]
        content = choice.message.content
        if isinstance(content, list):  # Mistral may return content chunks
            content = "".join(getattr(c, "text", "") or "" for c in content)
        return Reply(text=content or "", tool_calls=fmt.parse_tool_calls(choice.message.tool_calls),
                     usage=fmt.parse_usage(r.usage), raw=None, provider=NAME, model=model,
                     finish_reason=str(choice.finish_reason) if choice.finish_reason else None)
