"""The one LLM client used by our agent, every baseline and the judge.

`complete(messages, tools, role=...)` does, in order:
1. Look the request up in the SQLite cache; a hit costs no request and no quota.
2. Refuse (raise `QuotaExhausted`) if today's request count for this model has
   reached the configured daily limit, so batch runs stop cleanly and resume.
3. Wait so requests per minute stay under the configured limit.
4. Call the provider; retry 429s and 5xx errors with exponential backoff and
   jitter, honouring any delay the server suggests. A per-day 429 raises
   `QuotaExhausted` at once. Every quota the server reports is logged to
   `docs/quota.md`, because Google no longer publishes free-tier limits.
5. Store the reply in the cache and write a trace record with token counts.

Why one client: fairness (CLAUDE.md §2.3). Every system gets identical
caching, pacing, retries and logging, so none is advantaged by plumbing.
"""

from __future__ import annotations

import datetime as dt
import platform
import random
import time
from importlib import metadata
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from core.config import REPO_ROOT
from llm.cache import ReplyCache, cache_key
from llm.trace import Tracer
from llm.types import LLMError, Message, QuotaExhausted, RateLimited, Reply, ToolSpec, TransientError, Usage

# Gemini's free-tier daily quota resets at midnight Pacific time; we count days the same way.
QUOTA_TZ = ZoneInfo("America/Los_Angeles")


def make_provider(name: str) -> Any:
    """Build a real provider. Imported lazily so tests never need SDKs or keys."""
    from core.env import require_key
    if name == "gemini":
        from llm.providers.gemini import GeminiProvider
        return GeminiProvider(require_key("GEMINI_API_KEY"))
    if name == "groq":
        from llm.providers.groq import GroqProvider
        return GroqProvider(require_key("GROQ_API_KEY"))
    if name == "mistral":
        from llm.providers.mistral import MistralProvider
        return MistralProvider(require_key("MISTRAL_API_KEY"))
    raise ValueError(f"unknown provider {name!r}")


class QuotaLog:
    """Appends each distinct quota the server reports to a Markdown table."""

    HEADER = ("# Measured API quotas\n\nWritten automatically by `llm/client.py` whenever a provider "
              "returns a 429 that names its quota. Throttle settings in `config/default.yaml` follow these.\n\n"
              "| first seen (UTC) | provider | model | quota id | limit | per day |\n|---|---|---|---|---|---|\n")

    def __init__(self, path: str | Path | None):
        self.path = Path(path) if path else None
        self._seen: set[tuple] = set()

    def record(self, provider: str, model: str, err: RateLimited) -> None:
        key = (provider, model, err.quota_id, err.quota_value)
        if self.path is None or not err.quota_id or key in self._seen:
            return
        self._seen.add(key)
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(self.HEADER, encoding="utf-8")
        existing = self.path.read_text(encoding="utf-8")
        row_key = f"| {provider} | {model} | {err.quota_id} | {err.quota_value} |"
        if row_key in existing:
            return
        now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M")
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(f"| {now} {row_key} {'yes' if err.per_day else 'no'} |\n")


class LLMClient:
    """See the module docstring. Every collaborator can be injected for tests."""

    def __init__(self, config: dict[str, Any], *, providers: dict[str, Any] | None = None,
                 cache: ReplyCache | None = None, tracer: Tracer | None = None,
                 quota_log: QuotaLog | None = None, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep, now: Callable[[], dt.datetime] | None = None,
                 seed: int = 0):
        self.config = config
        llm_cfg = config["llm"]
        self._providers = dict(providers or {})
        self.cache = cache if cache is not None else ReplyCache(REPO_ROOT / config["paths"]["llm_cache"])
        self.tracer = tracer if tracer is not None else Tracer(None)
        self.quota_log = quota_log if quota_log is not None else QuotaLog(REPO_ROOT / llm_cfg["quota_log"])
        self._clock, self._sleep = clock, sleep
        self._now = now or (lambda: dt.datetime.now(QUOTA_TZ))
        self._rng = random.Random(seed)
        self._last_call: dict[str, float] = {}
        self.stats: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------ helpers
    def role_config(self, role: str) -> dict[str, Any]:
        if role not in ("main", "judge"):
            raise ValueError(f"role must be 'main' or 'judge', not {role!r}")
        return self.config["llm"][role]

    def _provider(self, name: str) -> Any:
        if name not in self._providers:
            self._providers[name] = make_provider(name)
        return self._providers[name]

    def _stats(self, role: str) -> dict[str, Any]:
        return self.stats.setdefault(role, {"calls": 0, "api_requests": 0, "cache_hits": 0,
                                            "retries": 0, "usage": Usage()})

    def _params(self, role_cfg: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
        llm_cfg = self.config["llm"]
        params = {"temperature": llm_cfg["temperature"], "max_output_tokens": llm_cfg["max_output_tokens"]}
        if role_cfg.get("thinking_level"):
            params["thinking_level"] = role_cfg["thinking_level"]
        params.update({k: v for k, v in extra.items() if v is not None})
        return params

    def _throttle(self, role: str, rpm: float) -> None:
        """Space requests at least 60/rpm seconds apart (simple and easy to reason about)."""
        interval = 60.0 / rpm if rpm else 0.0
        last = self._last_call.get(role)
        if last is not None:
            wait = interval - (self._clock() - last)
            if wait > 0:
                self._sleep(wait)
        self._last_call[role] = self._clock()

    def _backoff(self, attempt: int, retry_after: float | None) -> float:
        retry = self.config["llm"]["retry"]
        if retry_after is not None:
            return retry_after + self._rng.uniform(0, 1.0)
        base = min(retry["max_delay_s"], retry["base_delay_s"] * (2 ** attempt))
        return base * (0.5 + self._rng.random())  # jitter in [0.5, 1.5) x base

    # --------------------------------------------------------------------- main
    def complete(self, messages: list[Message | dict[str, Any]], tools: list[ToolSpec] | None = None, *,
                 role: str = "main", **params: Any) -> Reply:
        """Send one request (or answer it from the cache). Extra `params` such as
        `force_tool=True` or `json_mode=True` are passed to the provider and are
        part of the cache key."""
        role_cfg = self.role_config(role)
        provider_name, model = role_cfg["provider"], role_cfg["model"]
        msgs = [m if isinstance(m, Message) else Message.from_dict(m) for m in messages]
        call_params = self._params(role_cfg, params)
        key = cache_key(provider_name, model, [m.to_dict() for m in msgs],
                        [t.to_dict() for t in tools] if tools else None, call_params)
        st = self._stats(role)
        st["calls"] += 1

        cached = self.cache.get(key)
        if cached is not None:
            st["cache_hits"] += 1
            self._trace(role, provider_name, model, key, msgs, cached, attempts=0, latency=0.0)
            return cached

        day = self._now().date().isoformat()
        rpd = role_cfg.get("rpd")
        if rpd and self.cache.requests_on(day, provider_name, model) >= rpd:
            raise QuotaExhausted(f"{provider_name}/{model}: configured daily limit {rpd} reached for {day} "
                                 f"(Pacific). Resume after midnight Pacific time.")

        provider = self._provider(provider_name)
        max_attempts = self.config["llm"]["retry"]["max_attempts"]
        last_error: Exception | None = None
        for attempt in range(max_attempts):
            self._throttle(role, role_cfg.get("rpm") or 0)
            self.cache.count_request(day, provider_name, model)
            st["api_requests"] += 1
            started = self._clock()
            try:
                reply = provider.call(model, msgs, tools, call_params)
            except RateLimited as err:
                self.quota_log.record(provider_name, model, err)
                self.tracer.write("llm_error", role=role, provider=provider_name, model=model,
                                  kind="rate_limited", per_day=err.per_day, quota_id=err.quota_id,
                                  quota_value=err.quota_value, attempt=attempt + 1, message=str(err)[:300])
                if err.per_day:
                    raise QuotaExhausted(f"{provider_name}/{model}: daily quota hit "
                                         f"({err.quota_id or 'per-day'} = {err.quota_value}). {err}") from err
                last_error = err
                delay = self._backoff(attempt, err.retry_after)
            except TransientError as err:
                self.tracer.write("llm_error", role=role, provider=provider_name, model=model,
                                  kind="transient", attempt=attempt + 1, message=str(err)[:300])
                last_error = err
                delay = self._backoff(attempt, None)
            except LLMError as err:
                self.tracer.write("llm_error", role=role, provider=provider_name, model=model,
                                  kind="fatal", attempt=attempt + 1, message=str(err)[:300])
                raise
            else:
                reply.from_cache = False
                self.cache.put(key, reply)
                st["usage"] = st["usage"] + reply.usage
                self._trace(role, provider_name, model, key, msgs, reply, attempts=attempt + 1,
                            latency=self._clock() - started)
                return reply
            if attempt + 1 < max_attempts:
                st["retries"] += 1
                self._sleep(delay)
        raise LLMError(f"{provider_name}/{model}: gave up after {max_attempts} attempts: {last_error}")

    def _trace(self, role: str, provider: str, model: str, key: str, msgs: list[Message], reply: Reply,
               *, attempts: int, latency: float) -> None:
        # Raw provider content is left out of the trace to keep it readable; it is in the cache under `key`.
        self.tracer.write(
            "llm_call", role=role, provider=provider, model=model, cache_key=key,
            from_cache=reply.from_cache, attempts=attempts, latency_s=round(latency, 3),
            input=[{k: v for k, v in m.to_dict().items() if k not in ("raw", "raw_provider")} for m in msgs],
            output={"text": reply.text, "tool_calls": [tc.__dict__ for tc in reply.tool_calls],
                    "finish_reason": reply.finish_reason},
            usage=reply.usage.__dict__,
        )

    def environment(self) -> dict[str, Any]:
        """Exact model IDs and SDK versions, logged with every run (CLAUDE.md §2.4)."""
        def version(pkg: str) -> str | None:
            try:
                return metadata.version(pkg)
            except metadata.PackageNotFoundError:
                return None
        return {
            "python": platform.python_version(),
            "models": {role: {"provider": self.config["llm"][role]["provider"],
                              "model": self.config["llm"][role]["model"]} for role in ("main", "judge")},
            "temperature": self.config["llm"]["temperature"],
            "sdk": {p: version(p) for p in ("google-genai", "openai", "mistralai")},
        }
