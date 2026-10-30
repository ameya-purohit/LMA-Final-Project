# Explainer: baselines

Owner: Aditya Narayan Dwivedi. Files: `baselines/common.py`, `baselines/b0_closed.py`, `baselines/b1_rag.py`,
`baselines/b2_react.py`, `baselines/b3_cove.py`, `baselines/prompts/`, tests in `tests/baselines/`.

## Problem

A result only means something against a comparison. We must separate three explanations of any gain: having tools at
all, spending more, and the procedure itself. So each baseline isolates one of them, and all share the same model,
client, tools, sandbox and output schema.

## How it works (plain words)

| ID | System | What it isolates |
|---|---|---|
| B0 | Closed book: one call, question only | What the model already remembers |
| B1 | Direct RAG: one call with the starting material | The value of any investigation |
| B2 | ReAct: all tools, including `run_probe` and `mutate_and_run`, same limits | **Key baseline.** Is the gain from the tools, or from our procedure? |
| B2+ | B2 with extra steps; a config value, not new code | Is the gain just more compute? |
| B3 | B2's answer, then Chain-of-Verification by reading | Verifying by reading against verifying by execution |

B0 and B1 are one request forced to end in `final_answer`. B2 uses the same `agent/toolloop.py` as our agent, and is free
to call any tool in any order. B3 writes verification questions, answers each independently with read-only tools without
seeing the draft, and then revises. Every baseline can flag uncertainty or abstain. A citation is marked causal only if
B2 actually ran `mutate_and_run` on that line.

## Worked example

Live on the toylib question: B0 (1 request) says it has no repository access. B1 (1 request) reads the override and cites
line 88. B2 (9 requests) ran 5 probes and also cited line 88, but ran no mutants. B3 (19 logical requests, 10 real because
B2's part came from the cache) reached a similar answer by reading. So on this easy case B2 chose not to use the
mutation tool at all, which is the behaviour the comparison is meant to measure.

## Weaknesses

- **Equal prompt effort is hard to prove.** Prompt iterations are logged, and are made on dev only.
- **B2's flag is its own judgement,** while ours follows a rule. Coverage compares a model's confidence with a procedure's.
- **B3 costs many requests,** so it is in the should-have tier and may run on fewer questions.
- **B0's citations are from memory** and can point at files that do not exist. They are graded as they are.

## Viva Q&A

1. **Why give B2 the mutation tool?**
   Otherwise a gain in citation quality could simply come from having a tool B2 lacked. With identical tools, any
   difference comes from how they are used, which is exactly what RQ1 asks.
2. **What if B2 ties with ours?**
   That is a valid result: it would mean having the tools matters more than the procedure. We would report that, and the
   ablations would show which parts still help.
3. **How do you show the systems differ only in control logic?**
   `core.config.diff` between any two systems lists only `agent.ablation.*` and `baselines.*` keys, and a test asserts it.
   They share one client, one registry, one sandbox.
4. **Why does a probe-only turn not use a step?**
   So that both systems have the same budget. Ours has 8 investigation steps plus its checks, and if every B2 turn counted
   as a step, B2 would be limited to 8 turns in all and the comparison would be unfair.
5. **Why is B3 not the main baseline?**
   It checks by reading only. It answers a narrower question (reading against running), while B2 tests the procedure with
   identical abilities.
