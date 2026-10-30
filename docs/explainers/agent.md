# Explainer: the agent

Owner: Ameya Purohit. Files: `agent/toolloop.py`, `agent/claim_table.py`, `agent/loop.py`, `agent/grades.py`,
`agent/stop.py`, `agent/output.py`, `agent/prompts/`, tests in `tests/agent/`.

## Problem

An LLM can read code and still get behaviour wrong: it trusts the docs and misreads overrides. It can also cite a line
that looks related but decides nothing. A standard agent may have the tools to check itself and simply not use them.
Our agent makes checking part of its control flow, and turns each failed check into its next goal.

## How it works (plain words)

`agent/toolloop.py` is the hand-written loop: send the history and allowed tools, append the reply, run each tool, append
the results, and stop when the model calls a *terminal* tool, a structured output like `submit_draft`. `agent/loop.py`
drives these stages:

1. **Investigate.** Read-only tools, at most 8 steps shared across the question. Ends with `submit_draft`: an answer
   plus atomic claims, each with its citations.
2. **Prioritise.** Claims supported only by docs are checked first.
3. **Run it.** `write_probe` gives a probe and controls for all claims in one call, to save requests. Each is run in the
   sandbox. A probe that fails for its own reasons (a wrong import) is repaired, at most twice.
4. **Handle refutations.** `assess_refutation` compares the probe's setup with the question. Different setup: rewrite
   the probe. Same setup: the claim is refuted, and the observed output becomes the goal for `revise_claim`.
5. **Flip the switch.** Each citation of a confirmed claim goes through `mutate_and_run`. If one is causal, the others are
   dropped. If none is, the goal becomes "find the line that decides this", through `propose_citation`.
6. **Vacuity.** A confirmed claim with no causal citation has its probe checked. If no mutation can change the probe's
   outcome, the probe tests nothing, so it is regenerated once.
7. **Grade** by rule: [E+C], [E], [T], [R], [D]. No LLM decides a grade.
8. **Final answer.** `final_answer` writes the text from the claim table. The output schema is assembled in code.

The **claim table** is the agent's explicit state: each claim, its citations, status, probe, and observed output. Ablation
flags in the config switch parts off: A1 reads instead of runs, A2 skips mutation, A3 only flags failures, and so on.

## Worked example

Live run on toylib ("the docs say strict is on by default, so why does `clamp(5)` not raise?"), 11 requests:
the agent investigated in 7 steps, ran 3 probes and 14 mutants, and answered that the documentation is wrong, citing
`_OVERRIDES` on line 16 and the decider on line 88. All three claims reached [E+C]. In a scripted test, a draft that
cites line 12 has that citation rejected and the agent proposes line 88, which passes.

## Weaknesses

- **Probes are written by an LLM** and can be wrong. Repair, the refutation check and the vacuity check reduce this
  but cannot remove it. A human audit of probes is planned.
- **Tokens.** One running history makes later requests large (about 150,000 tokens on the first dev question). We accept
  this because requests are scarcer than tokens on the free tier.
- **Citation of a whole-file claim.** Claims like "this function is used" can pass the mutation check while saying little.
- **Requests.** Non-causal citations can use several extra turns; the 25-request cap can end the checks early, and any
  unverified claim is then flagged.

## Viva Q&A

1. **Why write the loop by hand rather than use LangChain?**
   The course asks us to explain every line, and the control flow is the research. The whole loop is one short file, `agent/toolloop.py`.
2. **What is the difference from B2, which has the same tools?**
   B2 chooses freely whether to check anything. Ours always splits the answer into claims, always runs them, always
   tests citations, and feeds failures back. RQ1 asks whether that structure helps.
3. **How do you tell a bad probe from a real refutation?**
   By where the error happened. An exception inside the library is an observation about the library. An error anywhere
   else, such as a NameError in the probe, is a bug in the probe, which is repaired rather than believed.
4. **How can ablations be cheap?**
   A2 and A3 are identical to the full agent up to the point where they diverge. At temperature 0 with identical
   prompts, that shared prefix comes from the cache and uses no quota. A test checks the requests really are identical.
5. **When does it flag an answer?**
   By rule: if any claim is unverified or refuted, or nothing was verified. A claim that was executed but has no causal
   citation keeps grade [E] and is not flagged, because the behaviour itself was observed.
