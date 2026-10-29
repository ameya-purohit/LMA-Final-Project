# Explainer: the LLM client

Owner: Ameya Purohit. Files: `llm/types.py`, `llm/cache.py`, `llm/trace.py`, `llm/client.py`,
`llm/providers/{gemini,groq,mistral,openai_format}.py`, `scripts/smoke_llm.py`, tests in `tests/llm/`.

## Problem

Our agent, four baselines, the ablations and the judge all talk to language models.
For the comparison to be fair, they must do it the *same* way: same model, same
temperature, same retries, same caching. We also live on free API tiers, where the
binding limit is **requests per day** (about 500 for Gemini flash-lite), so no request
may be wasted, and a long batch run must stop cleanly when the day's quota runs out
and pick up again tomorrow. Finally, tokens and requests are research metrics, so every
call has to be logged.

## How it works (plain words)

Every system calls one function:

```python
reply = client.complete(messages, tools, role="main")   # or role="judge"
```

- **Neutral messages** (`llm/types.py`). A history is a list of `Message`s with a role
  (system, user, assistant, tool). Each provider module translates this list into its
  own SDK's format, so no system depends on a particular SDK.
- **Thought signatures.** Gemini 3 attaches an opaque *thought signature* to each
  function call, and it must be sent back unchanged on the next turn or multi-turn tool
  use breaks. So an assistant `Message` keeps the model's native content in `raw`
  (tagged `raw_provider="gemini"`), and the Gemini module replays it exactly. Any other
  provider ignores it.
- **Cache** (`llm/cache.py`). Before calling the API, the client hashes (provider,
  model, messages, tools, settings) with SHA-256 and looks the hash up in SQLite. At
  temperature 0 an identical request deserves an identical answer, so a hit is returned
  at once: **zero requests, zero quota**. Re-running or resuming a batch is free.
- **Daily limit.** The same SQLite file counts real requests per model per day (Pacific
  time, when Gemini's quota resets). At the configured `rpd`, the client raises
  `QuotaExhausted` *before* calling. Batch runs catch it, save state and exit.
- **Pacing.** Requests are spaced at least 60/rpm seconds apart (4 s at 15 per minute).
- **Retries.** A 429 (rate limit) or a 5xx (server overloaded) is retried with growing
  waits (2 s, 4 s, 8 s ... capped at 90 s, with random jitter), or after the delay the
  server asks for. But a 429 that says the **per-day** quota is used up is never retried:
  it becomes `QuotaExhausted`. Any 400-type error is a real bug and is raised at once.
- **Learning the limits.** Google no longer publishes free-tier limits, so whenever a
  429 names its quota (for example `GenerateRequestsPerDayPerProjectPerModel-FreeTier = 500`),
  the client appends it to `docs/quota.md`.
- **Trace** (`llm/trace.py`). Every call writes one JSONL record: the input messages,
  the output text and tool calls, token counts (input, output, cached, thinking),
  attempts, latency, cache hit or not. A `context(qid=..., system=...)` block tags all
  records for one question.

## Worked example

The smoke test (`scripts/smoke_llm.py`) gives Gemini a dummy tool, `get_temperature(city)`:

1. Turn 1: the user asks for Pune's temperature. Gemini replies with a function call
   `get_temperature({"city": "Pune"})`, and its raw content carries a thought signature.
2. We append `reply.as_message()` (raw included) and a tool message with the result
   `{"celsius": 37}`.
3. Turn 2: Gemini answers "The current temperature in Pune is 37 degrees Celsius."
   It could only know 37 from our tool result, so the round trip worked, signature and all.

Run on 2026-10-28: 3 Gemini requests (217 input, 29 output tokens) and 1 Groq request.

## Weaknesses

- **Temperature 0 is not perfectly deterministic** for API models. The cache hides
  this: a cached answer is replayed even if a fresh call might differ. Repeat runs
  (should-have tier) therefore need their own cache.
- **The daily counter only knows our own requests.** Requests made from another machine
  with the same key are invisible to it; the server's per-day 429 is the backstop.
- **Fixed-interval pacing** is slower than a sliding window when requests are bursty.
- **Groq and Mistral limits are parsed from error text**, which those providers could
  change without notice.
- Tool-call ids: Gemini may not return ids, so we generate them. They only link a tool
  result to its call inside our own history.

## Viva Q&A

1. **Why not use LangChain or the OpenAI-compatible Gemini endpoint for everything?**
   The course rules forbid agent frameworks, and we have to explain every line. The
   compatible endpoint does not clearly document how it handles Gemini 3 thought
   signatures, which multi-turn tool calling depends on. The native SDK keeps them,
   and our smoke test proves it end to end.
2. **How can a cache be fair to all systems? Doesn't it give someone an advantage?**
   The cache only returns an answer for a byte-identical request (same model, history,
   tools, settings). It changes cost, never content: every system would have received
   the same answer at temperature 0. It also lets ablations A2/A3 reuse the full
   agent's identical first steps without spending quota.
3. **What happens when the daily quota runs out in the middle of the test set?**
   The client raises `QuotaExhausted`. The evaluation runner catches it, keeps every
   finished answer (they are already written and cached), and exits with code 3. The
   next day, re-running replays the finished part from the cache at no cost and continues.
4. **Why are tokens and requests logged at all?**
   They are reported research metrics (cost per question for every system), and
   requests per question decide how many test questions we can afford before the deadline.
5. **How do you know a key never ends up in a log?**
   Keys are read in one place (`core/env.py`) and handed straight to the SDK clients.
   Traces record messages and replies only, and error messages are truncated text from
   the provider, which never echoes the key. We also scanned the smoke-test trace for
   the key values: none found.
