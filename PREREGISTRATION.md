# Pre-registration

**Status: DRAFT.** This file becomes LOCKED at gate G2, before any test-set
run. After that, H1-H3, thresholds, metrics and ablation predictions are never
edited; any change goes in "Deviations" below, dated, with a reason.

Source: `docs/proposal_v2.md` §3 (research questions and hypotheses), §10
(metrics) and §11 (ablation predictions), adapted to the build specification
in `CLAUDE.md` where noted under Deviations.

## Research questions

**RQ1 (the procedure).** Does verifying each behavioural claim by execution and
each citation by mutation, with failures fed back into the investigation, give
more correct, causally cited answers and fewer confident errors than (a) a
ReAct agent with the same tools, including execution and mutation, under a
matched budget, and (b) self-verification by reading (Chain-of-Verification)?

**RQ2 (the mutation check as a measurement).** How well does the mutation check
agree with human judgements of whether a citation causally decides the
behaviour, compared with an LLM judge? Which acceptance rule agrees best: any
outcome change, behavioural changes only, or behavioural changes plus a
specificity control?

## Hypotheses

- **H1.** On real questions whose behaviour is executable, our agent beats B2
  (ReAct with all the same tools) on the **causally-supported answer rate** by
  at least **8 percentage points**. The paired 95% bootstrap CI must exclude
  zero. We also report the comparison against the budget-matched B2+.
- **H2.** Our agent's **confident-error rate** (wrong answers neither flagged
  as uncertain nor abstained) is at least **40% lower (relative)** than B2's,
  **while its coverage (share of answers not flagged) is no more than 10
  points below B2's**.
- **H3.** Human-judged **causal citation precision** is at least **15 points
  higher** with the mutation check than without it (ablation A2, same agent
  otherwise).

Each hypothesis is falsified if its threshold is not met or its CI includes
zero. Tests are paired: McNemar's exact test on discordant pairs, and a paired
bootstrap with 10,000 resamples (95% CI).

**Decomposition of H1.** We report correctness and citation support
separately. If the H1 gain comes only from the citation part, with no change in
correctness, we report it as a citation result, not a correctness result.

**Power.** With n = 120 and discordance 0.20, SE of the paired difference is
about 4.0 points, so an 8-point effect has roughly 50% power. If H1's CI
includes zero, the result is reported as **inconclusive, not negative**, with
the CI. With fewer than about 120 test questions H1 is under-powered; this is
stated in advance.

## Metrics

**Primary: causally-supported answer rate.** The answer is correct, and every
key claim has at least one citation that counts as causal.
- *Correct*: matches `observed_before` and `gold_answer`, as judged by the
  validated judge; human labels take precedence where they exist.
- *Causal citation*: falls inside a `gold_evidence` range (a line changed by the
  developer's merged fix), or is labelled *causal* by a human or the validated
  judge.

**Secondary.**
- Correctness alone.
- Confident-error rate and coverage, with a risk-coverage curve.
- Fix-location recall (share of questions with at least one citation inside a
  `gold_evidence` range); precision against gold ranges, reported as a
  *lower bound*.
- RQ2 agreement: each mutation acceptance rule (`any_flip`, `behavioural`,
  `specific`) and the LLM judge against human citation labels, and against
  fix-line membership.
- Tool use from traces: probe executable rate, valid-call rate, recovery after
  errors, unsafe attempts, tokens, requests, probe runs, mutant runs, CPU
  seconds per question.

**Judge validation.** Two members label a blinded sample of 40-80 answers and
every citation from ours and A2. Cohen's kappa is reported for human-human and
human-judge. **If human-judge kappa is below 0.6, the primary comparison uses
human labels.**

## Systems

B0 closed book · B1 direct RAG · B2 ReAct with every tool ours has (including
`run_probe` and `mutate_and_run`), 8 investigation steps and 12 probe runs ·
B2+ B2 with extra steps up to our median tokens per question in the pilot ·
B3 B2 followed by Chain-of-Verification by reading · Ours.

## Ablation predictions (written before any run)

| ID | Variant | Prediction |
|---|---|---|
| A1 | No execution: claims checked by reading only | More confident errors on doc-related questions, because reading tends to trust the docs and misread overrides |
| A2 | Execution, no mutation check | Similar correctness; clearly lower causal citation precision |
| A3 | Failures only flag claims, no re-investigation | Fewer confident errors than B2 (claims get flagged) but lower correctness than the full agent |
| A4 | One probe for the whole answer | More vacuous or partial probes; lower probe validity |
| A5 | Verify only doc-only or conflicting claims | Most of the gain at about half the probe cost |
| A6 | Acceptance rule: any flip / behavioural / specific | "Any flip" accepts many non-causal lines; `specific` matches humans best. Computed from the same mutation runs |
| A10 | Retrieval: none, and oracle | None costs more steps for similar accuracy; oracle shows the ceiling |
| A7 | LLM resolves conflicts instead of grade order | More answers that follow the docs when the docs are wrong |
| A8 | No probe repair | Lower executable rate, so lower coverage |
| A9 | Same pipeline on a small open model | Open question; either result is informative |
| A11 | Constant operators only | More false rejections from equivalent mutants |

## Locked values (filled at G2)

- Test-set file: `data/questions_test.jsonl`
- Test-set size: TODO(fixed at G2)
- Test-set SHA-256: TODO(fixed at G2)
- Final prompt hashes: TODO(fixed at G2)
- Final judge: TODO(chosen at P8)

## Deviations

Planned deviations from `docs/proposal_v2.md`, known before any run:

- **2026-10-27. Gold comes from merged fixes, not hand annotation.** Every
  question is a GitHub issue fixed by a merged PR (SWE-bench recipe). Gold
  evidence is the source lines the fix changed; gold behaviour is what the PR's
  own test observes on the frozen (pre-fix) code. Humans spot-check a random
  20% instead of a second annotator re-annotating 40%. Reason: objective,
  scalable gold chosen by the developers, independent of our tool. Stack
  Overflow questions are not used.
- **2026-10-27. No unanswerable questions.** Every question has a fix, so the
  "not answerable" category is empty. Abstention is still measured through
  flagged-uncertain answers and the controlled set's control questions.
- **2026-10-27. Retrieval is BM25 only** in the must-have tier (no code
  embeddings).
- **2026-10-27. Smaller controlled set** (about 15 conflict + 15 control
  questions instead of 30 + 30) and repeat runs on 30 questions instead of 60,
  with the probe-limit sweep on 30 questions, because of free-tier request
  limits.
- **2026-10-27. Probes call `observe()` and `test_claim()` directly** instead of
  running under pytest, and the leniency study traces lines with
  `sys.settrace` instead of coverage.py.
- **2026-10-27. Free-tier model** (`gemini-3.1-flash-lite`) instead of a paid
  model; cost is reported in requests and tokens.
