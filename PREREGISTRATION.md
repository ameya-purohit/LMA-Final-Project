# Pre-registration

**Status: LOCKED (2026-11-07, gate G2).** H1-H3, thresholds, metrics and ablation
predictions below are no longer edited; any change goes in "Deviations", dated,
with a reason. No test question was run before this lock.

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

## Locked values (filled at G2, 2026-11-07)

- Test-set file: `data/questions_test.jsonl`, **150 questions** (129 click, 21 marshmallow)
- Test-set SHA-256: `8a9c8139b3d210daf35c2428b249cde01836d1ff91f23b131333bd1bee8a1eae`
- Dev-set SHA-256 (for reference; dev is not part of any hypothesis test): `dd597157c5158321fbf3060e5315b6c11b93af1f30741aa806085d625040eb2a`
- Code at lock: commit `7d389669e216a7583677ef30b9b810a6613cc7f5` (local history), with the locking commit on top.
- Main model: Gemini `gemini-3.1-flash-lite`, temperature 0, thinking level unset, for every system.
- Final judge: Groq `openai/gpt-oss-120b`, temperature 0, the checklist prompt in `eval/judge.py` (D-37, D-42); one judge
  for the whole experiment, on up to four members' keys (D-53).
- Correctness: a partial answer counts as wrong (D-41).
- Kappa rule (D-48): applied separately to answer correctness and to citation labels; for each kind whose
  consensus-judge kappa is below 0.6, the primary comparison uses the human labels for that kind.
- Spot check (G1) after the lock: questions the team marks invalid are excluded from every system's results; the split
  is not rebuilt; checkers see no system answers for their questions before submitting (see Deviations).
- Final prompt hashes (SHA-256):
  - `agent/prompts/assess_refutation.txt` `8cd5e8bff94b9c92a1e04e2beeae9eba6e497fd4bbe660334fe4d54a33ec0fdd`
  - `agent/prompts/final_answer.txt` `7c0f0ae25d30634a4d3675a410ed3934d450fb1c34e3f7559ce3c5852b5bf94d`
  - `agent/prompts/investigate.txt` `ff854e64958dfedbeb0ec06d9130e6b2947d646f4171f71f2d3c292651a79067`
  - `agent/prompts/regenerate_vacuous.txt` `903f5127fbb54e7048fba259d3331068e1a1dcf77adec5e55e5e1e51834e9c46`
  - `agent/prompts/reinvestigate_citation.txt` `9983186881558fd7b41ad850ebc355038564ff389ee29a705747fed5ce90b461`
  - `agent/prompts/reinvestigate_refuted.txt` `ca752a0f30dc2a081a69ae33edf4c29c022773aa321d2bff26ff50156d8b9e25`
  - `agent/prompts/repair_probe.txt` `906f192b3fcd8941ac915fb7e18e1aac90b54d2227252af84bbf1c2f12c859a6`
  - `agent/prompts/resolve_conflict.txt` `4916c65586429bc72f130b6ad64be6a1aa2cc06853ab051ceda218ff05aa97fd`
  - `agent/prompts/rewrite_probe.txt` `9b585948011b52eb7f7a2d58151cca0c41a1dcbc07405c3ef65649a114afefd8`
  - `agent/prompts/system.txt` `afed327d8befae086a780effc7ac3e6eff9a8826c3a8289530c711bd27023055`
  - `agent/prompts/verify_by_reading.txt` `6754f2c3e9cdfd910b3a53684c4c8fbb0879487840380729d160235f45cf6d87`
  - `agent/prompts/write_probe.txt` `e77b4ae72549accd5185e310998febc0d3db195d2cd2d2b0b37cbc272ddddb9c`
  - `baselines/prompts/closed.txt` `5f200dc353672231778323455359d87f37901317dc9a6e6bec1d12830c09b589`
  - `baselines/prompts/cove_answer.txt` `e033372207b68a3b16af55a8c5a20aa6a9440f4979563ee5d3d4d3c5c2630de5`
  - `baselines/prompts/cove_questions.txt` `4da9d5dd1658a1e3f8fa30d784864969fae7346be1f4e6238abb9d8680d626ff`
  - `baselines/prompts/cove_revise.txt` `cc3debac7bf4670182673417beb52d499c0f7a780608a2d4d2b9ce4ad81b0bfb`
  - `baselines/prompts/rag.txt` `953335cf441388d900b8322c611d34cfb546fac6f74e95f5b4f685612d86d64f`
  - `baselines/prompts/react.txt` `cb7db5f3c59097c9a7f55ff761aeb47c4a4fd6063053e50dde17466c9f11dcaa`
- Other files whose text the models see (tool and schema descriptions, judge prompt, limits):
  - `agent/claim_table.py` `0b06f8dc94e2117fefd1900041c8f08d93c603952386f89f53a5e08f91926ce2`
  - `agent/loop.py` `ff43204b9327875453b528f329465ccce2f4961961c2cf00dd66c3b9007c27b2`
  - `tools/registry.py` `eb938b038c4a2448977ad258f99cf31d6ba61a6d9df139651bcd9b0dfe9b55a3`
  - `eval/judge.py` `90ca30563a06b1de77fbe9ffd4887d923877041652f27710fd26df22aa105cbc`
  - `config/default.yaml` `16f86661527d52d5b96467d6accbf0ecd2b03f889b371730fcaa2ec0650e2dcd`

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
- **2026-10-30. Pre-2020 issues are kept when the fix merged in 2020 or later.** The proposal says questions
  from 2020 onwards; CLAUDE.md §6.9 applies the cutoff to the merge date, because the frozen commit is the fix's
  base commit. Of 176 questions, 43 were opened before 2020. Results can be split on this.
- **2026-10-30. Partial answers count as wrong** (D-41), fixed before any metric was computed.
- **2026-10-30. Final judge is Groq `openai/gpt-oss-120b`** (D-37, D-42). Ameya decided not to add a Mistral key, so
  there is no re-judging with Mistral. The test-set size is chosen at G2 to fit the judge's daily token limit too.
- **2026-10-30. Feature-request filter planned** (D-43), to apply when the split is rebuilt at G1, before the test set
  is locked: issues with a feature or enhancement label, or GitHub issue type Feature, are dropped, with each removal logged.
- **2026-10-30. Preliminary dev runs happened before gate G1**, for the mid submission. The split will be rebuilt
  after the spot check, and dev questions may then change. No test question has been run. Prompts were not
  iterated between these runs.
- **2026-11-07. Feature-request filter applied** (D-43): 176 → 170 questions, before G1 and before any test run.
- **2026-11-07. Questions once in dev stay in dev** (D-44), so questions inspected during development never enter
  the test set. Dev is the old 19 (`click-3059` was a feature request) plus `click-1821`.
- **2026-11-07. Issue-timeline link fallback not extended** (decision H3). The fallback in the mining code found 0
  links; extending it would add pairs that need days of sandbox validation, too late before 15 Nov. All 367 links
  come from closing keywords. Future work.
- **2026-11-07. Lines with nothing to mutate are "untestable"** (D-47), a third outcome of the citation check,
  fixed before the pilot and before any test run; reported separately in the RQ2 table.
- **2026-11-07. Pilot runs before G1 completes**, to use the free quota while the team spot-checks. Six dev
  questions are in the spot-check sample; if any is removed, its pilot results are dropped from the pilot report.
  The decision to run the pilot early does not change any system, prompt or metric.
- **2026-11-07. Quota from several keys; paid judge plan** (D-50). From this date the main model runs on up to four
  team members' own Gemini free-tier keys (each member agreed), rotating to the next key when one key's daily quota is
  used up, and the judge runs on Groq's paid Developer plan. The models (`gemini-3.1-flash-lite`, `openai/gpt-oss-120b`),
  prompts, temperature and cache are unchanged; only the number of requests per day changes. Disclosed because Google's
  limits are per project.
- **2026-11-07. Prompt iteration 1, then one change to ours only** (D-51). After the single planned prompt round
  (equal for all systems, `docs/prompt_log.md`), two changes were made to our agent alone, on dev, before the lock:
  the claim-revision schema gets the "cite at least one line" rule that iteration 1 gave the shared schema, and a claim
  left with no citation keeps its last proposed line, marked not causal. Disclosed because it is extra development
  effort on ours after seeing dev results; B2 is unchanged (no revision step), and its dev answers replay from the cache.
- **2026-11-07. Judge on several free Groq keys** (D-53). The paid Groq plan named in D-50 was not in effect: the key
  stopped at the free tier's 200,000 tokens a day. The judge may rotate over up to four members' Groq keys. Same model
  (`openai/gpt-oss-120b`) and prompt for every judgement; one judge for the whole experiment.
- **2026-11-07. Test set locked before the spot check (G1) was applied.** The four members' spot-check files had
  not arrived at the lock. Since a spot-check verdict depends only on the issue, the fix and its test, never on a
  system's answer, the questions marked invalid will be excluded from every system's results after the runs, each
  removal logged in `data/dropped.jsonl`. The test file and its SHA-256 stay as locked, and the split is not rebuilt.
  Checkers are not shown system answers for their questions before they submit.
- **2026-11-11. How the human verdicts and labels were recorded.** The spot-check verdicts (G1) and the G3 labels
  were made by team members, but the files were not exported directly from `annotation/spotcheck.html` and
  `eval/label.html`. For G1, each member chose their own verdicts and wrote their own notes; the notes were then
  grammar-corrected with an AI tool and the files assembled from them. For G3, the two labellers (Aditya Narayan
  Dwivedi as `labeller1`, Sourav Nath as `labeller2`) labelled separately, and an AI tool was used only to format their
  choices into the label files. No label or verdict was chosen or changed by an AI tool. The file format, the sample
  and every analysis step are as planned. Disclosed because the planned route (the pages' own export) was not followed.

## Exploratory extension (added 2026-11-12, after the main results; NOT part of the locked study)

Written before any extension run on test questions. Everything above stays the study's primary, locked result. This
section adds a multi-agent extension that was designed **after** the main results were seen, so every number it
produces is exploratory and is reported in its own section, never mixed into H1-H3.

**Question set.** The 47 test questions of the `sub50` run (the A10 subset, after G1). E0 (= `ours`) and B2 already have
answers on exactly these questions, so they are reused unchanged. Prompts of the new agents are developed on dev only.
The retrieval study (R1-R5) uses no LLM, so it runs on all 145 test questions.

**Configurations.**

| ID | What it is |
|---|---|
| E0 | `ours`, the locked single agent (reused results) |
| E1 | Multi-agent: Bug Investigator, Code Analyst, Probe Engineer (LLM); Experiment Engineer (code); Causal Verifier (LLM). BM25 retrieval, single-line mutation of candidates in rank order |
| E2 | E1 + hybrid retrieval (BM25 + dense, RRF, cross-encoder rerank) for starting material and search |
| E3 | E2 + code graph (call graph, def-use and control dependences) and slicing (static slice, executed-line spectrum of claim vs control probes) fused into the candidate ranking |
| E4 | E3 + dependency-guided pairwise mutation of candidate pairs that single mutations did not settle |
| E5 | E4 + information-gain experiment selection with early stopping and de-duplication of equivalent mutants |
| E6 | E5 with its analysis and execution tools (code graph, slicing, probes, mutation, patch validation, experiment results) called through a local MCP server instead of in-process; the agents' read-only search tools stay in-process |

Same model (`gemini-3.1-flash-lite`), temperature, sandbox, judge and question text for all. Budget per question for
E1-E6: at most 12 LLM requests, 8 single-line mutation checks, 3 pair checks, 12 probe runs.

**Metrics** (computed in code from the developer's fix lines, no LLM):
- Localization over each system's ranked locations (E0/B2: their citations in order): Top-1, Top-3, MRR (first 10),
  precision, recall (share of gold ranges hit) and F1, at line level (inside a `gold_evidence` range) and function level
  (same enclosing function as a gold line).
- Causal verification over mutation-tested lines: acceptance rate on gold lines, acceptance rate on non-gold lines
  (an upper bound on false acceptance, since some non-gold lines are truly causal), inconclusive rate.
- Efficiency: requests, tokens, mutant runs, probe runs, wall time per question.
- Retrieval (R1 BM25, R2 dense, R3 BM25+dense RRF, R4 R3+rerank, R5 R4+call-graph expansion): Recall@K, Precision@K,
  MRR@K for K = 1, 5, 10, where a code chunk is relevant if it overlaps a gold range.
- Single-location vs multi-location faults (gold has one range vs two or more) reported separately; for the latter,
  the share of questions where at least two distinct gold ranges are among the top 5 locations.
- Correctness by the same judge, if its quota allows, on the same 47 questions.

**Predictions (written before any run).**
1. R4 beats R1 on Recall@5 (paired, McNemar). R2 alone does not beat R1 (a small general text model on code).
2. E1 is not worse than E0 on line-level Top-3 and uses fewer requests per question.
3. E3 beats E2 on line-level Top-3, because executed-line spectra point at code the probe really runs.
4. E4 finds two or more gold ranges on more multi-location questions than E3.
5. E5 needs fewer mutant runs than E4 for a Top-3 within 5 points of E4.
6. E6 gives the same answers as E5 (same cache, same tool outputs) at a small wall-time cost.

With 47 questions, a difference smaller than about 15 points cannot be told apart from noise; any CI that contains zero
is reported as inconclusive, and no claim of improvement is made without one that does not.
