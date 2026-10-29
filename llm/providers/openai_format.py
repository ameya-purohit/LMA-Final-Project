"""Conversion between neutral messages and the OpenAI chat format.

Groq (through the `openai` SDK) and Mistral (through `mistralai`) both take
this format, so the conversion lives here once.
"""

from __future__ import annotations

import json
from typing import Any

from llm.types import Message, ToolCall, ToolSpec, Usage


def to_messages(messages: list[Message]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in messages:
        if m.role in ("system", "user"):
            out.append({"role": m.role, "content": m.content})
        elif m.role == "assistant":
            d: dict[str, Any] = {"role": "assistant", "content": m.content or ""}
            if m.tool_calls:
                d["tool_calls"] = [{"id": tc.id, "type": "function",
                                    "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)}}
                                   for tc in m.tool_calls]
            out.append(d)
        elif m.role == "tool":
            out.append({"role": "tool", "tool_call_id": m.tool_call_id or "", "name": m.name or "",
                        "content": m.content})
    return out


def to_tools(tools: list[ToolSpec] | None) -> list[dict[str, Any]] | None:
    if not tools:
        return None
    return [{"type": "function", "function": {"name": t.name, "description": t.description,
                                              "parameters": t.parameters}} for t in tools]


def parse_tool_calls(raw_calls: Any) -> list[ToolCall]:
    """Parse tool calls; arguments that are not valid JSON become `{"_raw": text}`
    so the caller can report an invalid call to the model instead of crashing."""
    calls = []
    for tc in raw_calls or []:
        fn = tc.function
        args_text = fn.arguments if isinstance(fn.arguments, str) else json.dumps(fn.arguments or {})
        try:
            args = json.loads(args_text or "{}")
            if not isinstance(args, dict):
                args = {"_raw": args_text}
        except json.JSONDecodeError:
            args = {"_raw": args_text}
        calls.append(ToolCall(id=tc.id or "", name=fn.name, arguments=args))
    return calls


def parse_usage(usage: Any) -> Usage:
    if usage is None:
        return Usage()
    cached = 0
    details = getattr(usage, "prompt_tokens_details", None)
    if details is not None:
        cached = int(getattr(details, "cached_tokens", 0) or 0)
    thinking = 0
    cdetails = getattr(usage, "completion_tokens_details", None)
    if cdetails is not None:
        thinking = int(getattr(cdetails, "reasoning_tokens", 0) or 0)
    return Usage(input=int(usage.prompt_tokens or 0), output=int(usage.completion_tokens or 0),
                 cached=cached, thinking=thinking, total=int(usage.total_tokens or 0))
