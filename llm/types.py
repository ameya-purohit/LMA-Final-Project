"""Provider-neutral message, tool and reply types.

Why neutral types: ours and every baseline must share one LLM client
(CLAUDE.md §2.3). Agents build histories of `Message`s; each provider module
translates them to its own SDK format. The optional `raw` field carries
provider-native content that must be replayed unchanged (Gemini thought
signatures, D-03), tagged with the provider that produced it so a different
provider never receives it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Role = Literal["system", "user", "assistant", "tool"]


@dataclass
class ToolCall:
    """One function call requested by the model."""
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class Message:
    """One turn in a neutral history.

    - `system`/`user`: `content` is the text.
    - `assistant`: `content` is any text, `tool_calls` the calls made;
      `raw` is the provider-native content (see module docstring).
    - `tool`: the result of one call; `tool_call_id` and `name` link it to the call.
    """
    role: Role
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None
    name: str | None = None
    raw: dict[str, Any] | None = None
    raw_provider: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Message":
        d = dict(d)
        d["tool_calls"] = [ToolCall(**tc) for tc in d.get("tool_calls") or []]
        return cls(**d)


@dataclass
class ToolSpec:
    """A function the model may call, described by a JSON schema."""
    name: str
    description: str
    parameters: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Usage:
    """Token counts for one call. Tokens are a reported research metric."""
    input: int = 0
    output: int = 0
    cached: int = 0
    thinking: int = 0
    total: int = 0

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(*(a + b for a, b in zip(self.as_tuple(), other.as_tuple())))

    def as_tuple(self) -> tuple[int, int, int, int, int]:
        return (self.input, self.output, self.cached, self.thinking, self.total)


@dataclass
class Reply:
    """What `LLMClient.complete` returns.

    `from_cache` is True when the reply came from the SQLite cache (no request
    was sent, no quota used). `raw` is provider-native content to store in the
    history for replay.
    """
    text: str
    tool_calls: list[ToolCall]
    usage: Usage
    raw: dict[str, Any] | None = None
    provider: str = ""
    model: str = ""
    from_cache: bool = False
    finish_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Reply":
        d = dict(d)
        d["tool_calls"] = [ToolCall(**tc) for tc in d.get("tool_calls") or []]
        d["usage"] = Usage(**d.get("usage") or {})
        return cls(**d)

    def as_message(self) -> Message:
        """The assistant turn to append to a history, raw content included."""
        return Message(role="assistant", content=self.text, tool_calls=list(self.tool_calls),
                       raw=self.raw, raw_provider=self.provider or None)


class LLMError(Exception):
    """Any non-retryable failure from a provider."""


class RateLimited(LLMError):
    """A 429. `per_day` means a daily quota (do not retry today).

    `retry_after` is the server-suggested delay in seconds, if any;
    `quota_id`/`quota_value` are parsed from the error details when given.
    """

    def __init__(self, message: str, *, retry_after: float | None = None, per_day: bool = False,
                 quota_id: str | None = None, quota_value: str | None = None):
        super().__init__(message)
        self.retry_after = retry_after
        self.per_day = per_day
        self.quota_id = quota_id
        self.quota_value = quota_value


class TransientError(LLMError):
    """A 5xx or connection error: retry with backoff."""


class QuotaExhausted(LLMError):
    """A daily limit was hit. Batch runs stop cleanly and resume after the reset."""
