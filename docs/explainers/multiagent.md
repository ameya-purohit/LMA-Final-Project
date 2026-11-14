# Explainer: the multi-agent orchestrator (E1-E6)  · owner: Ameya

## Problem
The locked agent does everything in one conversation: it investigates, writes probes, checks citations and answers.
The main study found it no better than ReAct (B2), and its mutation check rejected real fix lines. The extension asks:
does splitting the work into specialised roles, with better retrieval, a code graph and smarter experiments, localize
the cause of a reported behaviour better, and at what cost?

## How it works (plain words)
`multiagent/orchestrator.py` runs five roles in a fixed order. Three are LLM agents (same Gemini model as everything
else), each with its own conversation and one job; two are plain code.
1. **Bug Investigator** (LLM, may read code for up to 3 steps): writes down what was expected, what actually happens,
   a scenario that triggers it, and 2-4 *competing* hypotheses, each blaming different lines or functions.
2. **Probe Engineer** (LLM): writes a *reproduce* probe (runs the scenario and asserts the reported behaviour), 1-2
   *controls* (ordinary nearby behaviour), and optional boundary and hypothesis-distinguishing probes. They run in the
   Docker sandbox; a probe that cannot run is sent back for repair, at most twice.
3. **Code Analyst** (LLM, may read code for up to 2 steps): ranks the lines most likely to decide the behaviour. From
   E3 it also sees a deterministic list from the code graph: lines in the backward slices of the suspects that the
   reproduce probe executed and the controls did not.
4. **Experiment Engineer** (code, `experiments/engine.py`): mutation checks on the fused candidate list (RRF of the
   analyst's list, the hypotheses' lines and, from E3, the graph list). E4 adds pairs, E5 information-gain order.
5. **Causal Verifier** (LLM): sees the hypotheses, every probe result and every experiment, and marks each hypothesis
   accepted / rejected / inconclusive, writes the answer with citations, and may propose a one-line patch. Code then
   validates the patch by re-running the reproduce probe and controls on a patched copy.

Agents never talk to each other in free text: each produces one pydantic object (`multiagent/schemas.py`) through a
function tool, and the orchestrator passes it on. The final ranking used for scoring is computed in code: accepted
lines, then lines of an accepted pair, lines the verifier cited, inconclusive, untested, rejected.
Budget per question: 12 LLM requests (each role keeps requests in reserve for the roles after it), 12 probe runs,
8 single-line checks, 3 pair checks. The flags in `config.multiagent.flags` switch E2-E6 on one at a time.

## Worked example (toylib, from `tests/multiagent/test_orchestrator_toylib.py`)
Question: why does `clamp(-1)` raise? The investigator proposes H1 "the module default on line 12 decides it" and
H2 "the guard on line 88 raises for negatives". The probe engineer writes `clamp(-1, strict=False)` (reproduce) and
`clamp(5, strict=False) == 5` (control); both run. The analyst ranks lines 12 and 88. The experiment engineer finds
line 88 *accepted* (changing `x < 0` to `x < -1` stops the raise and leaves `clamp(5)` alone) and line 12 *rejected*.
The verifier accepts H2, cites line 88 and proposes `if strict: raise ValueError("negative")`, which code validates.
Final ranking: line 88 first. Four LLM requests in total.

## Weaknesses
- Every role depends on the one before: a wrong scenario from the investigator gives a probe that tests the wrong
  thing, and then every experiment is about the wrong behaviour.
- The hand-offs are lossy on purpose (only the typed fields pass), so a useful remark in one agent's reasoning is lost.
- It was designed after the main results were known: exploratory, not a confirmatory test.
- The fused ranking weights its sources equally (RRF); nothing was tuned, which is honest but not optimal.

## Viva Q&A
1. **Why is this "multi-agent" and not one agent with more prompts?** Each LLM role has its own conversation, its own
   instructions and one output schema, and never sees the others' reasoning, only their typed results. That is the
   usual meaning of specialised agents; the orchestrator decides the order, not the agents.
2. **Why not let the agents decide what to do next, as in AutoGen?** Free-form agent chat costs many requests, is
   non-deterministic and hard to test. Our quota is 500 requests a day per key, so control flow is code.
3. **Why are the Experiment Engineer and the ranking not LLMs?** Choosing the next mutation and ranking by verdict are
   rules we can state and test; an LLM adds cost and variance there without adding information.
4. **How is it fair to E0 and B2?** Same model, temperature, cache, sandbox, mutation code, question text and output
   schema; E0/B2 answers on the same 47 questions are reused unchanged. The budget is lower (12 vs 25 requests).
5. **What would make you trust a result from it?** A paired comparison whose 95% CI excludes zero on the same questions,
   and a gain that shows up at function level too, not only on one metric.
