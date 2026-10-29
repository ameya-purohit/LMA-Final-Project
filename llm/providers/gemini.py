"""Gemini provider on the native `google-genai` SDK (decision D-03).

Translates neutral `Message`s to `types.Content`, calls `generate_content`
with automatic function calling disabled (our loops run tools themselves),
and translates the reply back. The model's `Content` is stored in `raw` via
`model_dump(mode="json", exclude_none=True)` and replayed with
`Content.model_validate`, which keeps thought signatures byte-exact.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from llm.types import LLMError, Message, RateLimited, Reply, ToolCall, ToolSpec, TransientError, Usage

NAME = "gemini"


def _types():
    # Imported lazily so the rest of the LLM layer (and its tests) work without the SDK.
    from google.genai import types
    return types


def to_contents(messages: list[Message]) -> tuple[str | None, list[Any]]:
    """Return (system_instruction, contents).

    Consecutive tool results are grouped into one user turn, because Gemini
    expects the responses to all calls of a model turn together.
    """
    types = _types()
    system_parts = [m.content for m in messages if m.role == "system"]
    contents: list[Any] = []
    pending_tool_parts: list[Any] = []

    def flush_tools() -> None:
        if pending_tool_parts:
            contents.append(types.Content(role="user", parts=list(pending_tool_parts)))
            pending_tool_parts.clear()

    for m in messages:
        if m.role == "system":
            continue
        if m.role == "tool":
            pending_tool_parts.append(types.Part.from_function_response(
                name=m.name or "tool", response={"result": m.content}))
            continue
        flush_tools()
        if m.role == "user":
            contents.append(types.Content(role="user", parts=[types.Part.from_text(text=m.content)]))
        elif m.role == "assistant":
            if m.raw is not None and m.raw_provider == NAME:
                contents.append(types.Content.model_validate(m.raw))
            else:
                parts = []
                if m.content:
                    parts.append(types.Part.from_text(text=m.content))
                for tc in m.tool_calls:
                    parts.append(types.Part.from_function_call(name=tc.name, args=tc.arguments))
                contents.append(types.Content(role="model", parts=parts or [types.Part.from_text(text="")]))
    flush_tools()
    system = "\n\n".join(system_parts) if system_parts else None
    return system, contents


def to_tools(tools: list[ToolSpec] | None) -> list[Any] | None:
    if not tools:
        return None
    types = _types()
    decls = [types.FunctionDeclaration(name=t.name, description=t.description,
                                       parameters_json_schema=t.parameters) for t in tools]
    return [types.Tool(function_declarations=decls)]


def build_config(system: str | None, tools: list[ToolSpec] | None, params: dict[str, Any]) -> Any:
    types = _types()
    kwargs: dict[str, Any] = {
        "temperature": params.get("temperature", 0.0),
        "max_output_tokens": params.get("max_output_tokens"),
        "system_instruction": system,
        "tools": to_tools(tools),
        "automatic_function_calling": types.AutomaticFunctionCallingConfig(disable=True),
    }
    if params.get("thinking_level"):
        kwargs["thinking_config"] = types.ThinkingConfig(thinking_level=params["thinking_level"])
    if tools and params.get("force_tool"):
        kwargs["tool_config"] = types.ToolConfig(function_calling_config=types.FunctionCallingConfig(
            mode="ANY", allowed_function_names=params.get("allowed_tools")))
    return types.GenerateContentConfig(**{k: v for k, v in kwargs.items() if v is not None})


def parse_response(response: Any, model: str) -> Reply:
    """Turn a `GenerateContentResponse` into a neutral `Reply`."""
    candidates = response.candidates or []
    if not candidates or candidates[0].content is None:
        reason = getattr(candidates[0], "finish_reason", None) if candidates else None
        feedback = getattr(response, "prompt_feedback", None)
        return Reply(text="", tool_calls=[], usage=parse_usage(response.usage_metadata), raw=None,
                     provider=NAME, model=model, finish_reason=str(reason or feedback or "EMPTY"))
    content = candidates[0].content
    texts, calls = [], []
    for part in content.parts or []:
        if getattr(part, "function_call", None):
            fc = part.function_call
            calls.append(ToolCall(id=fc.id or f"call_{uuid.uuid4().hex[:8]}", name=fc.name,
                                  arguments=dict(fc.args or {})))
        elif getattr(part, "text", None) and not getattr(part, "thought", False):
            texts.append(part.text)
    reason = candidates[0].finish_reason
    return Reply(text="".join(texts), tool_calls=calls, usage=parse_usage(response.usage_metadata),
                 raw=content.model_dump(mode="json", exclude_none=True), provider=NAME, model=model,
                 finish_reason=getattr(reason, "name", None) or (str(reason) if reason else None))


def parse_usage(meta: Any) -> Usage:
    if meta is None:
        return Usage()
    g = lambda name: int(getattr(meta, name, 0) or 0)  # noqa: E731
    return Usage(input=g("prompt_token_count"), output=g("candidates_token_count"),
                 cached=g("cached_content_token_count"), thinking=g("thoughts_token_count"),
                 total=g("total_token_count"))


_DELAY = re.compile(r"^([\d.]+)s$")


def classify_error(exc: Exception) -> Exception:
    """Map an SDK exception to RateLimited / TransientError / LLMError.

    For a 429 we read the quota violation (quotaId, quotaValue) and the
    RetryInfo delay from the error details. A quota id containing "PerDay"
    marks a daily limit (CLAUDE.md §2.4).
    """
    code = getattr(exc, "code", None)
    if code == 429:
        quota_id = quota_value = None
        retry_after = None
        per_day = False
        details = getattr(exc, "details", None) or {}
        # `details` is the response JSON, normally {"error": {..., "details": [...]}}.
        inner = details.get("error", details) if isinstance(details, dict) else {}
        items = inner.get("details", []) if isinstance(inner, dict) else []
        for item in items:
            kind = item.get("@type", "")
            if kind.endswith("QuotaFailure"):
                for v in item.get("violations", []):
                    quota_id = v.get("quotaId") or quota_id
                    quota_value = v.get("quotaValue") or quota_value
                    if "PerDay" in (v.get("quotaId") or ""):
                        per_day = True
            elif kind.endswith("RetryInfo"):
                m = _DELAY.match(str(item.get("retryDelay", "")))
                if m:
                    retry_after = float(m.group(1))
        text = str(exc)
        if not quota_id and re.search(r"per ?day", text, re.I):
            per_day = True
        return RateLimited(text[:500], retry_after=retry_after, per_day=per_day,
                           quota_id=quota_id, quota_value=quota_value)
    if isinstance(code, int) and code >= 500:
        return TransientError(str(exc)[:500])
    if code is None and exc.__class__.__name__ in ("ConnectError", "ReadTimeout", "ConnectTimeout",
                                                   "RemoteProtocolError", "TimeoutException"):
        return TransientError(f"{exc.__class__.__name__}: {exc}"[:500])
    return LLMError(f"{exc.__class__.__name__}: {exc}"[:500])


class GeminiProvider:
    name = NAME

    def __init__(self, api_key: str):
        from google import genai
        self._client = genai.Client(api_key=api_key)

    def call(self, model: str, messages: list[Message], tools: list[ToolSpec] | None,
             params: dict[str, Any]) -> Reply:
        system, contents = to_contents(messages)
        config = build_config(system, tools, params)
        try:
            response = self._client.models.generate_content(model=model, contents=contents, config=config)
        except Exception as exc:  # translated below; the client decides about retries
            raise classify_error(exc) from exc
        return parse_response(response, model)
