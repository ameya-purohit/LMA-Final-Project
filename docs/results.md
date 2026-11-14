# Results

**Status: 2026-11-11, after G1 and G3.** The must-have tier is complete: ours, B1, B2 and A1–A3 on all 150 locked test
questions, with every answer judged. The spot check (G1) has been applied: 5 test questions were marked invalid and are
excluded, so the judge-based numbers are on the **145** remaining questions. The human labels (G3) are in: the judge's
agreement with them is below the pre-registered 0.6, so **the primary comparison uses the human labels** on the 12
labelled questions (§3), and the judge-based numbers on 145 questions are reported as secondary. B0, A6, A10 and the
adversarial set from the should-have tier are done; the rest is future work (§10).

Every number here comes from `python -m analysis.make_all --run-id main --split test`. A copy of its output, including
the figures, is in `results/summary/analysis_main_test/`. The per-system summary over all 150 questions, before the
exclusion, is `results/summary/main_test.md`. Nothing in this file is typed in by hand except the reading of those
numbers.

## 1. Setup

- **Test set.** 150 questions (129 from click, 21 from marshmallow), locked at G2 on 2026-11-07. Its SHA-256 is in
  PREREGISTRATION.md. After the spot check, 145 remain (125 click, 20 marshmallow).
- **Spot check (G1).** The four members checked a seeded 20% sample: 34 of the 170 validated questions, one member per
  question, 8–9 each. They marked **8 invalid (a disagreement rate of 23.5%)**, and every one of the 8 failed the same
  check: *the failing test does not capture the behaviour the issue asks about.* In 7 of them the issue is a feature
  request, so the test only shows that the new feature did not exist yet (an unexpected keyword argument, "DID NOT
  WARN", "DID NOT RAISE"). In the eighth (`click-1844`), the fix bundled several changes and the failing test belongs to
  an unrelated one. No question failed "is it a genuine question" or "do the gold lines decide it". 5 of the 8 are test
  questions (excluded from every system), and 3 are dev questions. Details: `data/mining_report.md`, removals logged in
  `data/dropped.jsonl`.
  - *How the verdicts were collected.* Each member made their own yes/no verdicts and wrote their own notes. The notes
    were afterwards grammar-corrected with an AI tool, and the four files were assembled from them rather than exported
    directly from `annotation/spotcheck.html`. The verdicts themselves were not changed.
- **Model.** Every system uses `gemini-3.1-flash-lite` at temperature 0.
- **Judge.** `openai/gpt-oss-120b` on Groq, one judge for the whole experiment.
- **Human labels (G3).** Two members, Aditya (`labeller1`) and Sourav (`labeller2`), labelled the same blinded sample
  separately: 12 test questions (seeded, stratified by library) × 6 systems = 72 answers and 204 citations. They did
  not see which system wrote an answer. An AI tool was used only to format their choices into the label files
  (disclosed in PREREGISTRATION.md, Deviations). None of the 12 questions was removed by the spot check.

  | Labels | Human–human kappa | Judge vs human consensus kappa | Rule (≥ 0.6 to keep the judge) |
  |---|---|---|---|
  | Answer correctness (72) | 0.742 | 0.363 | **use human labels** |
  | Citation labels (204) | 0.902 | 0.322 | **use human labels** |

  The humans agree with each other well, and the judge agrees with them only fairly. Where they differ on citations,
  the judge is **more lenient**: it rated 72 of the 204 citations higher than the humans did, mostly *causal* where
  the humans said *on-topic but not causal* (49), and 11 lower. On correctness it errs both ways (15 higher, 11 lower).
  Source: `results/main/human/agreement.md` (`python -m eval.kappa --run-id main`).
- **Run dates.** 7–10 November 2026, over three free-tier quota days. One engineering fix was made during the run
  (D-54, a request timeout). It changes no answer.

## 2. Main results

| System | Correct | Causally supported (primary) | Fix-location recall | Confident errors | Coverage | Requests / q | Tokens / q |
|---|---|---|---|---|---|---|---|
| B0, closed book (question only) | 23.4% | 4.8% | 3.4% | 52 (35.9%) | 59.3% | 1.0 | 1,495 |
| B1, direct RAG | 37.9% | 21.4% | 42.8% | 89 (61.4%) | 99.3% | 1.0 | 5,432 |
| B2, ReAct with the same tools | **68.3%** | **49.7%** | 62.1% | 46 (31.7%) | 100% | 10.5 | 119,035 |
| **Ours** | 61.4% | 40.0% | 60.0% | 43 (29.7%) | 86.2% | 14.7 | 185,876 |
| A1, no execution | 62.8% | 39.3% | 62.8% | 53 (36.6%) | 99.3% | 7.9 | 78,107 |
| A2, no mutation | 62.8% | 42.1% | 60.7% | 44 (30.3%) | 90.3% | 10.0 | 112,735 |
| A3, flag only | 61.4% | 40.7% | 60.0% | **29 (20.0%)** | 67.6% | 8.5 | 87,951 |

Partial answers count as wrong (D-41). "Confident errors" are wrong answers that were neither flagged nor abstained.

B0 sees only the question, with no code. It sets the floor: the model alone answers 23.4% correctly, and almost never
cites a line the fix changed (3.4%). Retrieval alone (B1) raises correctness to 37.9%, and tools (B2) to 68.3%. So
nearly all of the gain comes from reading and running the frozen code, not from what the model already knows about
click and marshmallow. B0 flags or abstains on 41% of questions, which is why its confident-error count (52) is lower
than B1's (89). Ours beats B0 and B1 by a wide margin on every measure (for example +18.6 points over B1 on the
primary metric, CI [+10.3, +26.9]).

## 3. Pre-registered hypotheses

All tests are paired by question. The CIs are 95% paired bootstrap intervals (10,000 resamples), and the p-values are
from McNemar's exact test.

**The kappa rule decides which labels count.** Judge–human kappa is below 0.6 for both kinds of label (§1), so by the
pre-registered rule (D-48) the primary comparison uses the human consensus labels. Those exist for 12 questions only.

### 3a. Primary: human labels, 12 questions

| System | Correct | Causally supported |
|---|---|---|
| B2 | 9 of 12 (75.0%) | 5 of 12 (41.7%) |
| A1, A2, A3 (each) | 8 of 12 (66.7%) | 4 of 12 (33.3%) |
| **Ours** | 6 of 12 (50.0%) | 3 of 12 (25.0%) |
| B1 | 3 of 12 (25.0%) | 1 of 12 (8.3%) |

| Hypothesis | Result | Verdict |
|---|---|---|
| **H1.** Ours beats B2 on the causally-supported rate by ≥ 8 points | 25.0% vs 41.7%, −16.7 points, CI [−41.7, 0.0], p = 0.50 (0 vs 2 discordant) | **Not supported.** Ours is never better than B2 on any of the 12 questions; too few questions to show B2 is better |
| **H3.** Ours' causal citation precision beats A2's by ≥ 15 points | 30.6% (36 citations) vs 44.1% (34), **−13.6 points**, cluster-bootstrap CI [−28.6, −1.0] | **Not supported: A2 is better, and the CI is below zero** |

H2 does not depend on labels of citations, only on correctness and flagging; on 12 questions it cannot be tested, so
it is reported from the judge below.

### 3b. Secondary: judge labels, 145 questions

| Hypothesis | Result | Verdict by the pre-registered rule |
|---|---|---|
| **H1.** Ours beats B2 on the causally-supported rate by ≥ 8 points | 40.0% vs 49.7%, **−9.7 points**, CI [−19.3, −0.7], McNemar p = 0.059 (17 vs 31 discordant) | **Not supported: B2 is better; the bootstrap CI is below zero** |
| H1, correctness alone | 61.4% vs 68.3%, −6.9 points, CI [−14.5, +0.0], p = 0.099 | B2 ahead; not significant |
| **H2.** Ours has ≥ 40% fewer confident errors than B2, with coverage no more than 10 points lower | 29.7% vs 31.7%, a relative reduction of 6.5%, CI [−10.3, +6.2]; coverage 86.2% vs 100% | **Inconclusive** (the CI includes zero; the coverage condition also fails) |
| H3 by the judge | 58.7% vs 59.3% (431 and 440 citations), −0.6 points, cluster-bootstrap CI [−7.6, +6.0] | Inconclusive; superseded by the human labels in §3a |

**What the two views say together.** They agree in direction everywhere. On H1, the human sample is too small for a
test on its own, but ours was not better than B2 on any labelled question, and on 145 questions the judge-based CI is
below zero. The judge is lenient on citations (§1), and it was lenient about the same for every system, so its
*differences* between systems are more trustworthy than its *levels*: with human labels, every system's
causally-supported rate is lower (ours 25.0% against 40.0% by the judge). With 145 questions, H1 is above the roughly
120 questions declared in advance for adequate power. **The full procedure did not beat a ReAct agent given the same
tools, and the mutation check made citations worse in the humans' eyes, not better (H3).** Before the spot check, on all
150 questions, the judge-based H1 gap was −10.7 points (CI [−20.0, −1.3], p = 0.033); the exclusion did not change
the conclusion.

## 4. Ablations: which part of the procedure matters?

Ours, A1, A2 and A3 are statistically indistinguishable on correctness and on the primary metric. Every difference is
within ±2.1 points, and every CI includes zero. On these questions:

- **Execution (A1)** did not improve correctness. It did reduce confident errors, 29.7% against 36.6% (CI [−14.5, +0.7],
  p = 0.12, not significant). This was predicted for doc-related questions, and it held there: 28 confident errors
  against 36.
- **Mutation (A2)** did not raise citation precision against fix lines or by the judge, and by the human labels it
  *lowered* it (30.6% against A2's 44.1%, §3a). This is the A2 prediction failing (see RQ2 below).
- **Re-investigation (A3 against ours).** A3 flags failures instead of re-investigating them. It had *fewer* confident
  errors than ours (20.0% against 29.7%, CI [+4.1, +15.9] for ours minus A3, p = 0.004; 18 vs 4 discordant), at the
  same correctness, by flagging 47 answers instead of 20. Re-investigation turned flagged answers into confident ones without making them
  more often correct.

### A10: does the starting material matter?

A10 changes only the starting material: **none** gives the agent no retrieved chunks, and **oracle** gives it the
whole files the fix changed (files the fix created are skipped, because they don't exist at the frozen commit). It ran
on the first 50 test questions in the default seeded order, which interleaves the two libraries, with ours and B2 re-run
on the same 50 for a paired comparison. After the spot check, 47 remain (41 click, 6 marshmallow). Source: `python -m
analysis.make_all --run-id sub50 --split test`, copied to `results/summary/analysis_sub50_test/`.

| System (47 questions) | Correct | Causally supported | Fix-location recall | Confident errors | Requests / q | Tokens / q |
|---|---|---|---|---|---|---|
| B2 | 61.7% | 51.1% | 61.7% | 18 | 9.9 | 109,529 |
| Ours (BM25 top 5 code, top 3 docs) | 53.2% | 36.2% | 59.6% | 17 | 14.9 | 187,823 |
| A10 none | 53.2% | 34.0% | 44.7% | 18 | 14.2 | 128,328 |
| A10 oracle | 51.1% | 36.2% | 55.3% | 19 | 13.6 | 272,617 |

- **Correctness does not depend on the starting material.** Ours against none: 0.0 points, CI [−12.8, +12.8]; ours
  against oracle: +2.1 points, CI [−8.5, +12.8].
- **Retrieval does help the agent find the right lines.** Without it, fix-location recall drops from 59.6% to 44.7%
  (+14.9 points for ours, CI [+6.4, +25.5], p = 0.016; 7 questions vs 0). That is the one significant A10 effect.
- **The oracle is not a ceiling.** Being handed the right files did not help: the agent's limit is in using the
  material, not in finding it.
- **Against the prediction.** We predicted that *none* would cost more steps for similar accuracy. Accuracy was
  similar, but *none* used slightly fewer requests (14.2 against 14.9) and fewer tokens, because it starts with a shorter
  prompt. The oracle-ceiling prediction did not hold.
- On 47 questions this ablation is under-powered; only the fix-location difference is outside the noise. The H1 gap on
  this subset (−14.9 points, CI [−31.9, +2.1]) is consistent with the full result.

## 5. RQ2: the mutation check as a measurement

Over 862 mutation checks by ours on test, 123 lines were untestable (no operator applied). Of those, 31 were fix lines.
Against fix-line membership, the developer's own choice of lines:

| Rule | Accepted | Precision vs fix lines (lower bound) | Recall vs fix lines | Kappa |
|---|---|---|---|---|
| any_flip | 494 of 739 | 36.6% | 66.8% | −0.001 |
| behavioural | 411 | 37.0% | 56.1% | 0.007 |
| specific (used by the agent) | 177 | 36.7% | 24.0% | 0.001 |

**The mutation verdict agrees with fix-line membership no better than chance (kappa ≈ 0) under every rule.** The rule
the agent uses (`specific`) rejects 76% of fix lines. So "flip the switch" mostly sent the agent looking for a
different line in cases where the developer's own line was already cited. This is the most likely mechanism behind the
H1 and H3 results.

Precision against fix lines is only a lower bound, because a line outside the fix can also decide the behaviour. So
we also compare the mutation verdicts with the **human** causal labels, on the 52 checked lines of ours that the humans
labelled:

| Rule | Agreement with humans | Kappa |
|---|---|---|
| any_flip | 55.8% | 0.198 |
| behavioural | 55.8% | 0.167 |
| specific (used by the agent) | 51.9% | **−0.098** |

Against both references the verdicts are weak, and the rule the agent uses is the worst against humans. The A6
prediction was that `specific` would match humans best; **it matched them least.** Requiring that the control probes
stay unchanged rejects many lines the humans consider causal. On 52 lines these kappas are imprecise, but none of them
reaches even moderate agreement (0.4).

## 6. Why ours lost to B2: what the traces show

From the decision logs of ours on the 145 test questions:

- **Volume of checking.**
  - 612 probe runs: 401 passed, 111 failed, 100 were broken.
  - 860 mutation checks.
  - 381 proposed replacement citations.
  - 84 claims refuted and 75 revised.
- **More claims, each needing a causal line.** Ours averages 2.61 claims per answer against B2's 2.05. The primary
  metric needs a causal citation for *every* claim, so each extra claim is another chance to miss.
- **Broken probes.** 100 of 612 probe runs (16%) were broken: the probe itself failed, for example with a wrong import.
  Repair helps, but each repair spends requests from the same budget of 25.
- **Flagging is weak at separating right from wrong.** Of ours' 20 flagged answers, 7 were in fact correct.

These are observations, not tests; the analysis report has the discordant cases.

## 6a. Tool use and safety

The brief (§7) asks for tool-call accuracy and an unsafe-action rate. The numbers below come from the "Tool use and
safety" section of the analysis report.

| System | Tool calls | Valid-call rate | Errors (recovered) | Probes submitted | Probe verdict rate | Blocked unsafe probes | Unsafe actions executed |
|---|---|---|---|---|---|---|---|
| Ours | 3,599 | 100.0% | 45 (19) | 604 | 85.2% | 40 (6.0%), in 14 questions | **0** |
| B2 | 1,521 | 99.7% | 112 (12) | 695 | 88.5% | 26 (3.7%), in 9 questions | **0** |
| A2 | 1,999 | 100.0% | 35 (13) | 546 | 84.5% | 35 (5.7%), in 13 questions | **0** |
| A3 | 2,072 | 100.0% | 36 (12) | 459 | 85.1% | 34 (6.5%), in 12 questions | **0** |

- **Valid calls.** Almost every tool call had valid arguments: B2 made 4 invalid calls, and the other systems made none.
  Pydantic validation returns any error to the model, which can then retry.
- **Probe verdict rate.** This is the share of probes that ran and ended in pass or fail. The remainder raised another
  exception, which is often a broken probe.
- **Blocked probes are unsafe *attempts*, not actions.** The AST policy refused each one before anything ran.
  - Most were harmless in intent, for example creating a directory or file outside `/tmp` (`os.mkdir`, `.write_text()`,
    `.touch()`) to set up a test scenario.
  - A few were imports the policy forbids: `subprocess`, `shutil` and `importlib.metadata`.
  - Even if the policy had missed one, the sandbox has no network, a read-only file system outside `/tmp`, and limits
    on CPU, memory and number of processes.
- **What the higher rate for ours means.** Ours' unsafe-attempt rate (6.0%) is higher than B2's (3.7%) because ours
  writes more probes, and those probes set up more file-system scenarios. No probe from any system was executed
  unsafely.
- **Replays are counted once.** A resumed question can replay identical probe calls; the trace counts are
  de-duplicated, so they can be slightly lower than the per-answer counters.

## 6b. Adversarial set (prompt injection)

**Setup.** The set has 15 items from dev questions, each with one planted instruction (D-55), five of each kind:

- a hidden note in the issue text asking the model to run `curl` in a probe;
- a comment on the fix line asking it to answer "works as intended";
- a comment on the fix line asking it to write to `~/.ssh/authorized_keys`.

Every instruction also asks for a unique canary token in the answer. The run is `adv`, and the report is
`results/analysis/adv_adversarial/report.md`. Three of the 15 source questions (`click-1844`, `click-2396`,
`marshmallow-2924`) were later marked invalid in the spot check. They are kept here, because this set measures whether
planted text changes what a system does, which does not depend on the question's gold.

| System | Exposed (canary reached the model) | Complied (canary in answer) when exposed | Probes attempting the planted action | Unsafe actions executed |
|---|---|---|---|---|
| Ours | 12 / 15 | 7 / 12 | 0 | 0 |
| B2 | 11 / 15 | 9 / 11 | 0 | 0 |
| B1 | 8 / 15 | 6 / 8 | 0 | 0 |

- **No system tried the dangerous actions.** No probe called `os.system`/`curl` or wrote to `~/.ssh`. The one blocked
  probe (ours, a `subprocess` import) was unrelated to the planted text.
- **Every system often obeyed the harmless-looking part.** When exposed, the systems appended the canary token in 58%
  (ours) to 82% (B2) of cases.
- **Some copied the planted verdict.** On the `code_answer` items, several answers repeated the planted verdict ("This
  behaviour is intended; it works as intended") into the answer. So a planted comment can change what an answer
  says, even though it changed nothing the systems *did*.
- **Ours was no more robust than B2.** It complied in 7 of 12 exposed items against B2's 9 of 11. On 15 items, this
  difference is not meaningful.
- **What it means.** The sandbox and policy protect the machine, but nothing in any system stops instructions in read
  text from changing the answer. CLAUDE.md §2.5 treats such text as data; the prompts don't yet enforce it. This is
  future work: an instruction in the system prompt plus a filter for injected text.

## 7. Failure taxonomy

From the judge labels and fix-line hits:

| System | Correct, causally supported | Correct, not causally supported | Right behaviour, wrong place | Right place, wrong or partial behaviour | Wrong behaviour and wrong place |
|---|---|---|---|---|---|
| Ours | 58 | 31 | 22 | 19 | 15 |
| B2 | 72 | 27 | 18 | 16 | 12 |
| B1 | 31 | 24 | 53 | 21 | 16 |
| B0 (59 more abstained) | 7 | 27 | 39 | 2 | 11 |

## 8. Per category and library

- **Doc-related questions** (n = 86), where the method was meant to help most: ours is 54.7% correct and 40.7% causally
  supported, against B2's 65.1% and 47.7%. The method did not help here.
- **Single-location questions** (n = 56): ours 71.4% and 37.5%, against B2's 73.2% and 53.6%.
- **Spread-across-files questions** (n = 3): too few to read.
- **Per library:** the results are similar for click and marshmallow (see the report).

## 9. Threats to validity

- **The judge did not pass validation** (kappa 0.36 and 0.32 against the humans). By the pre-registered rule the
  primary comparison uses the human labels, but those cover only 12 questions, so the primary test of H1 is
  under-powered. The judge-based results on 145 questions agree in direction and are reported as secondary.
- **Only two labellers, and only 12 questions.** Human–human agreement was high (0.74 and 0.90). Disagreements were
  resolved by the conservative rule (D-48), not by discussion.
- **The human files were not exported from the labelling pages.** The labels and verdicts are the members' own; an AI
  tool formatted the G3 labels and corrected the grammar of the G1 notes (PREREGISTRATION.md, Deviations).
- **The automatic gold admits feature requests.** The spot check found 8 invalid questions in a sample of 34 (23.5%),
  almost all feature requests whose test only shows that the feature was missing. Those 8 are excluded, but the other
  80% of the dataset was not checked by hand, so a similar share of it may have the same problem. Such a question has
  no "wrong documentation" to find, which may make every system look worse, but it affects all systems equally because
  they answer the same questions. A filter for feature requests (for example, a fail-to-pass test that fails only with
  `TypeError: unexpected keyword argument`, `AttributeError` on a new name, or "DID NOT WARN/RAISE") is future work.
- **One model.** All systems use `gemini-3.1-flash-lite`. A stronger model may write fewer broken probes and use the
  checks better.
- **The request budget.** Ours spends requests on checks that B2 can spend on investigating. Both have the same limit
  (25), and ours used 14.7 per question on average.
- **The test set was locked before the spot check** (a disclosed deviation in PREREGISTRATION.md). The spot check
  only removes questions; it was applied the same way to every system, and the conclusions are the same with and
  without the 5 removed test questions.

## 10. Not yet run

- **Should-have tier:** B3, B2+, repeat runs, the probe-limit sweep, A4, A5 and the controlled set. B0 is in §2; A10 is in §4 (50 questions); the
  adversarial set is in §6b; A6 is the three rules in the RQ2 table (§5).
- **Stretch tier:** not started.

Anything not run by 15 Nov is reported as future work.
