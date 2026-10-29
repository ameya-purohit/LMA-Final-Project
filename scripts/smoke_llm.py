"""Live smoke test of the LLM layer (uses a few requests of free quota).

1. A plain call to the main model (Gemini) and to the judge (Groq), and to
   Mistral if its key is present.
2. A Gemini function-calling round trip over 2 turns with a dummy tool. Turn 1
   must call the tool; we replay the model's raw content (with its thought
   signature) plus the tool result, and turn 2 must answer using the result.
   This proves thought signatures survive our neutral history (decision D-03).

By default a fresh temporary cache is used, so every call really goes to the
API. Usage: python scripts/smoke_llm.py [--use-cache]
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import REPO_ROOT, load_config  # noqa: E402
from core.env import key_present  # noqa: E402
from llm.cache import ReplyCache  # noqa: E402
from llm.client import LLMClient  # noqa: E402
from llm.trace import Tracer  # noqa: E402
from llm.types import Message, ToolSpec  # noqa: E402

WEATHER_TOOL = ToolSpec(
    name="get_temperature",
    description="Return the current temperature in degrees Celsius for a city.",
    parameters={"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
)
SECRET_TEMPERATURE = "37"  # an unusual value the model can only know from the tool result


def make_client(overrides: list[dict] | None = None, use_cache: bool = False) -> tuple[LLMClient, Path]:
    cfg = load_config(overrides or [])
    trace_path = REPO_ROOT / cfg["paths"]["traces_dir"] / f"smoke_{time.strftime('%Y%m%d_%H%M%S')}.jsonl"
    cache_path = REPO_ROOT / cfg["paths"]["llm_cache"] if use_cache else Path(tempfile.mkdtemp()) / "smoke.sqlite"
    return LLMClient(cfg, cache=ReplyCache(cache_path), tracer=Tracer(trace_path)), trace_path


def plain_call(client: LLMClient, role: str) -> str:
    r = client.complete([Message(role="user", content="Reply with exactly one word: pong")], role=role)
    if not r.text.strip():
        raise AssertionError(f"{role}: empty reply (finish_reason={r.finish_reason})")
    return f"{r.provider}/{r.model} replied {r.text.strip()[:30]!r}; tokens in={r.usage.input} out={r.usage.output} " \
           f"thinking={r.usage.thinking}"


def function_round_trip(client: LLMClient) -> str:
    history = [
        Message(role="system", content="Use the provided tool to look up facts. Never guess a temperature."),
        Message(role="user", content="What is the temperature in Pune right now? Use the tool, then answer in one sentence."),
    ]
    first = client.complete(history, [WEATHER_TOOL], role="main")
    if not first.tool_calls:
        raise AssertionError(f"turn 1: expected a tool call, got text {first.text[:100]!r}")
    call = first.tool_calls[0]
    parts = (first.raw or {}).get("parts", [])
    has_signature = any("thought_signature" in p for p in parts)
    history.append(first.as_message())
    history.append(Message(role="tool", name=call.name, tool_call_id=call.id,
                           content=f'{{"city": "{call.arguments.get("city", "")}", "celsius": {SECRET_TEMPERATURE}}}'))
    second = client.complete(history, [WEATHER_TOOL], role="main")
    if SECRET_TEMPERATURE not in second.text:
        raise AssertionError(f"turn 2: answer does not use the tool result: {second.text[:200]!r}")
    return (f"turn 1 called {call.name}({call.arguments}); thought signature present: {has_signature}; "
            f"turn 2 answered {second.text.strip()[:80]!r}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--use-cache", action="store_true", help="use the shared cache instead of a fresh one")
    args = ap.parse_args(argv)
    client, trace_path = make_client(use_cache=args.use_cache)
    checks = [("gemini plain call", lambda: plain_call(client, "main")),
              ("groq judge plain call", lambda: plain_call(client, "judge")),
              ("gemini 2-turn function calling", lambda: function_round_trip(client))]
    if key_present("MISTRAL_API_KEY"):
        mclient, _ = make_client([{"llm": {"judge": {"provider": "mistral", "model": "mistral-large-latest"}}}],
                                 args.use_cache)
        checks.append(("mistral plain call", lambda: plain_call(mclient, "judge")))
    failed = 0
    for label, fn in checks:
        try:
            print(f"[OK ] {label}: {fn()}")
        except Exception as exc:  # report every check, then fail overall
            failed += 1
            print(f"[FAIL] {label}: {type(exc).__name__}: {str(exc)[:300]}")
    for role, st in client.stats.items():
        print(f"stats {role}: api_requests={st['api_requests']} cache_hits={st['cache_hits']} "
              f"retries={st['retries']} tokens={st['usage'].__dict__}")
    print(f"trace: {trace_path.relative_to(REPO_ROOT)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
