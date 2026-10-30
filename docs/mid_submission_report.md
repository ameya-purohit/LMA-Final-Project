# Run It, Then Cite It: mid-submission report

LMA Group Project, CL3.410, Monsoon 2026 · Team Disco 82 · Ameya Purohit, Aditya Narayan Dwivedi, Sourav Nath, Sunil Kumar

**The project in one paragraph.** Developers ask how a library behaves when its documentation may be wrong. The agent under study, called the *full agent* below (system id `ours` in the code), answers, then checks itself twice: it tests each claim by running a small generated program (a *probe*) against the library frozen just before the fix, and it accepts a cited line only if changing that line in a throw-away copy changes the claim's outcome and leaves unrelated behaviour alone. Failed checks become its next investigation goal. It is compared with a ReAct agent that has the same tools and limits, and with verification by reading.

**The headline, stated plainly.** The pipeline works end to end and the dataset is built. On the 14 dev questions completed by all seven systems, the full agent got 7 answers correct and the ReAct baseline (B2) got 10. The difference is not statistically significant (p = 0.25, 95% CI −42.9 to 0.0 points) and rests on an unvalidated judge, but it does not favour the full agent, and it is reported as it stands.

All experimental results are **preliminary**: dev set only, automatic judge (Groq `openai/gpt-oss-120b`, the same for every system) not yet validated against human labels, gold not yet spot-checked by humans. The test set has not been run. H1, H2 and H3 have not been tested.

---

## 1. Progress

| Phase | Status | Evidence |
|---|---|---|
| P0 Foundation | Done | Config, CI, bundles |
| P1 LLM layer | Done | Cache, retries, quota stop, tracing; live two-turn tool call keeps Gemini's thought signatures |
| P2 Sandbox | Done | No network, read-only, non-root, policy check; 9 Docker tests |
| P3 Mutation and toylib | Done | Every planted case passes locally and in Docker |
| P4 Data pipeline | Done | 176 validated questions (section 2) |
| P5 Retrieval and tools | Done | BM25, 11 tools, tool errors are recoverable and counted |
| P6 Agent | Done | Every decision point tested with a scripted LLM; live toylib run |
| P7 Baselines | Done | B0, B1, B2, B2+, B3; one live toylib run for B0-B3 |
| P8 Evaluation | Done | Judge, metrics, McNemar, bootstrap, kappa, resumable runner |
| P9 Spot-check kit, G1 | Pending | |
| P10 Pilot and prompt iteration | Pending | The runs below used first-draft prompts; no iteration yet |
| G2 lock, P11 test runs, G3 labels, P12 analysis | Pending | |

**Tests.** 249 unit tests and 17 Docker tests pass. `scripts/check_bundle_order.py` checks that each prefix of the push order (Sunil, then Ameya, Aditya, Sourav) passes its own tests. **Why it matters:** every member's merge leaves `main` working.

**Code.** All code reaches GitHub through four member bundles, each pushed from that member's own account. Decisions are logged in `DECISIONS.md` (D-01 to D-43), and each component has an explainer in `docs/explainers/`.

---

## 2. Dataset

**Method.** Following SWE-bench: an issue is the question, and the merged fix and its test are the answer key. A question is kept only if the PR's own test **fails on the frozen code and passes with the fix**, both run in the sandbox. Gold is computed by code from git diffs and test output. No LLM writes or filters any gold field.

### Funnel (real counts)

| Step | click | marshmallow | total | Why the count drops here |
|---|---|---|---|---|
| Closed PRs listed | 1898 | 1405 | 3303 | Everything GitHub returned |
| Merged, any date | 1086 | 1099 | 2185 | The rest were closed without merging |
| Merged since 2020-01-01 | 801 | 605 | 1406 | Older versions may need older interpreters than the Python 3.10 sandbox |
| Linked to an issue | 286 | 81 | 367 | Most PRs carry no closing keyword such as "fixes #12" |
| Issue not by a bot | 286 | 81 | 367 | No linked issue was written by a bot |
| Changes source AND tests | 180 | 39 | 219 | 83 had no test change and 65 no source change, so they cannot be validated by running |
| At most 10 source files | 180 | 39 | 219 | No linked PR was a large refactor |
| **Validated: fails before, passes after** | 153 | 29 | **182** | 37 did not pass the test-running rule (reasons below) |
| **Gold built, unique issue** | 147 | 29 | **176** | 3 repeated an issue already answered; 3 named their fix in the issue text |

### Drop reasons

| Stage | Reason | Count | Why it happens |
|---|---|---|---|
| Mining | No linked issue | 1039 | No closing keyword. The fallback through the PR's timeline found none (section 6) |
| Mining | No test change | 83 | The fix came without a test, so there is nothing to run |
| Mining | No source change | 65 | The PR touched docs or tests only |
| Validation | No test fails before the fix | 23 | The changed tests already pass on the frozen code, so they do not detect the fix |
| Validation | A failing test still fails after the fix | 7 | Strict rule: every failing test must pass with the fix |
| Validation | Timeout | 4 | A test run went past 120 s |
| Validation | Test error even with the fix | 2 | Both marshmallow; the test module fails at import even with the fix applied |
| Validation | Sandbox failure | 1 | The runner gave no output on one click pair |
| Gold | Duplicate issue | 3 | Several PRs fixed one issue; the earliest is kept |
| Gold | Question names its fix PR | 3 | Leakage: the issue text links the PR, so it is removed |

All 1230 dropped items are in `data/dropped.jsonl`, with their reasons.

### Questions by library and category

| Library | doc_related | spread_across_files | single_location | Total |
|---|---|---|---|---|
| click | 90 | 4 | 53 | 147 |
| marshmallow | 18 | 0 | 11 | 29 |
| **Total** | **108** | **4** | **64** | **176** |

**Why it looks like this:** click has more linked PRs, and `doc_related` is checked first, so any fix that also edits a docstring lands there, which makes the category broad.

**Split.** Dev 20, test 156, stratified by library and category with a fixed seed. Test file SHA-256: `2708aa21d6767373e189227353c85d8ab272456cbe471ee0d6a880026955581e`. The split will be rebuilt after the human spot check at gate G1.

**Known limits of this gold**, which the spot check will measure:
- Some issues are feature requests rather than behaviour questions (for example click-1075).
- 15 questions fail with an import or attribute error message, which says less about behaviour than an assertion does.
- 43 questions were opened before 2020 and fixed later. The cutoff is on the merge date, because the frozen commit is the fix's base.
- 314 of the 1066 gold ranges are anchors for add-only changes, the nearest line above new code.

---

## 3. Baselines

All systems share one client, model (`gemini-3.1-flash-lite`, temperature 0), tool implementation, sandbox, output schema and starting material. A test asserts that their configs differ only in control-logic keys.

| ID | System | What it isolates | Status |
|---|---|---|---|
| B0 | Closed book: one call, question only | What the model remembers | Run |
| B1 | Direct RAG: one call with the starting material | The value of investigating | Run |
| B2 | ReAct with **every** tool, including `run_probe` and `mutate_and_run`; same limits | The procedure against the tools | Run |
| B2+ | B2 with extra steps | Whether a gain is just more compute | Built; run pending |
| B3 | B2, then Chain-of-Verification by reading | Reading against running | Built, live on toylib; dev run pending |

Limits for every system: 8 investigation steps, 12 probe runs, 12 mutation checks, 25 requests per question.

---

## 4. Ablations

### Zero-cost ablations on toylib (no API calls; in the Docker sandbox)

Toylib is a small library with planted ground truth. Reproduce with `python -m analysis.toylib_ablations`.

**A6 and A11: each planted line under each rule**

| Claim | Line | Ground truth | Any flip | Behavioural | Behavioural + specific | Constants only (A11) | Why it came out this way |
|---|---|---|---|---|---|---|---|
| `clamp(-1, strict=False)` raises | 88 decider | causal | accept | accept | accept | accept | `0 -> -1` stops the exception, and the control is unchanged |
| same | 12 `STRICT_DEFAULT` | not causal | **accept** | reject | reject | reject | Only deleting it changes anything, by breaking an import: breakage that only "any flip" counts |
| same | 16 `_OVERRIDES` | not causal | reject | reject | reject | reject | With `strict=False` passed explicitly, the override is never read |
| `clamp(500, strict=False) == 100` | 20 `LIMIT` | causal | accept | accept | accept | accept | `100 -> 101` changes the claim and not the control |
| same | 91 `return result` | not causal | **accept** | **accept** | reject | reject | Returning None changes the claim and the control too, so only specificity rejects it |
| same | 90 `result = min(...)` | causal | accept | **reject** | **reject** | **reject** | A real false rejection: the only mutation is deleting the line, which is breakage |
| `safe_div(1, 0)` raises | 49 inline guard | not causal alone | reject | reject | reject | reject | A second guard raises the same error, so neither alone decides it |
| same | 50 helper guard | not causal alone | reject | reject | reject | reject | Same reason. Mutating both together is accepted (group mutation) |
| `at_least(18, 18) is True` | 61 comparison | causal | accept | accept | accept | **reject** | The line has no constant, so with constants only there is no mutant at all |

**Agreement with ground truth over the 9 planted lines:** any flip 7, behavioural 7, behavioural + specific 8, specific with constants only 7. **Why:** each weaker rule accepts a line for the reason it was designed to allow, and the one error left in the strict rule is the `min(...)` false rejection.

**Leniency: share of executed lines each rule accepts**

| Claim | Executed lines | Any flip | Behavioural | Behavioural + specific |
|---|---|---|---|---|
| `clamp(-1, strict=False)` raises | 6 | 17% | 17% | 17% |
| `clamp(500, strict=False) == 100` | 8 | 38% | 25% | 0% |
| `safe_div(1, 0)` raises | 2 | 0% | 0% | 0% |
| `at_least(18, 18) is True` | 3 | 67% | 67% | 33% |
| **All** | **19** | **32%** | **26%** | **11%** |

**Why:** each rule removes a further kind of line: first breakage, then lines that every behaviour depends on. The strict rule's 0% on the second claim is partly the planted `min(...)` false rejection: its accepted line, `LIMIT`, is module-level, ran at import, and so is not among traced lines. Toylib is small (19 lines) and hand-made, so this shows the filter filters, not how it behaves on real libraries.

### Must-have ablations on dev

A1 (no execution), A2 (no mutation) and A3 (flag only) ran on the same questions as the full agent. Results are in section 5, where A1 is marked incomplete. A4, A5, A7, A8, A10 and A11 on real questions are built and pending.

---

## 5. Results (preliminary)

**What completed.** The free Gemini quota ended the run: the server returned its daily limit (`GenerateRequestsPerDayPerProjectPerModel-FreeTier = 500`), and the next reset falls after the deadline.

| System | B0 | B1 | Full agent | B2 | A1 | A2 | A3 |
|---|---|---|---|---|---|---|---|
| Dev questions answered, of 20 | 20 | 20 | 15 | 14 | 14 | 14 | 14 |

**Systems are compared only on the 14 questions that all seven completed.** Click questions ran first, so all 14 completed dev questions are from click. The 3 marshmallow dev questions were reached only by B0 and B1, so these results say nothing about marshmallow.

**Judging.** Every system was graded by the same judge: Groq `openai/gpt-oss-120b`, with one fixed checklist prompt that does not reveal which system wrote the answer. The judge hit its own daily limit of 200,000 tokens during grading. When the table below was frozen, B1, B2, the full agent, A2 and A3 were judged on all 14 common questions, and B0 and A1 were **incomplete (judged 7/14 and 12/14)**. Those two rows are shown for the record and are **left out of every comparison**. Grading continued after the table was frozen and has since reached 14/14 for A1 and 12/14 for B0; those later grades are not used in this report. An answer without a judgement is never counted as wrong.

### Main table

| System | n judged | Correct | Partial | Correctness | Causally supported | Fix-location recall | Confident errors | Confident-error rate | Coverage | Requests/q (mean, max) | Tokens/q (mean) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| B1 RAG | 14 | 6 | 5 | 42.9% | 28.6% | 35.7% | 7 | 50.0% | 92.9% | 1.0, 1 | 5,334 |
| B2 ReAct | 14 | 10 | 4 | 71.4% | 42.9% | 64.3% | 4 | 28.6% | 100.0% | 10.6, 25 | 129,220 |
| **Full agent** | 14 | 7 | 4 | 50.0% | 35.7% | 57.1% | 7 | 50.0% | 100.0% | 14.2, 25 | 177,228 |
| A2 no mutation | 14 | 9 | 3 | 64.3% | 35.7% | 57.1% | 5 | 35.7% | 100.0% | 8.9, 13 | 94,742 |
| A3 flag only | 14 | 8 | 5 | 57.1% | 28.6% | 50.0% | 6 | 42.9% | 71.4% | 7.9, 12 | 81,225 |
| B0 closed book: **incomplete (judged 7/14)** | 7 | 1 | 0 | 14.3% | 0.0% | 0.0% | 2 | 28.6% | 50.0% | 1.0, 1 | 1,571 |
| A1 no execution: **incomplete (judged 12/14)** | 12 | 7 | 4 | 58.3% | 33.3% | 50.0% | 5 | 41.7% | 100.0% | 7.3, 11 | 70,548 |

Definitions: *correct* means the judge says correct; *partial* counts as wrong (D-41), fixed before any metric was computed. *Causally supported* means correct, with every claim having at least one citation inside a gold range or labelled causal by the judge. *Fix-location recall* means at least one citation falls on a line the fix changed; it needs no judge. *Confident error* means wrong, neither flagged nor abstained. *Coverage* means neither flagged nor abstained. Requests and tokens are logical: what a run from an empty cache would cost. In the two incomplete rows, the judge-based columns cover only the judged questions, which differ from the other rows, so these rows cannot be read against them.

**Why each system came out this way:**

- **B1, 6 of 14 correct, 35.7% recall.** It has real code but only one shot: it cannot follow a value to where it is set, so it misses causes outside the retrieved chunks.
- **B2, 10 of 14 correct, 64.3% recall.** It ran probes freely: 81 `run_probe` calls, on 13 of 14 questions. So it did verify by running, without being told to. It used `mutate_and_run` on only 2 of 14 questions.
- **Full agent, 7 of 14 correct, 57.1% recall.** All 41 of its claims ended up confirmed, so it never flagged an answer and all 7 wrong answers count as confident errors. Claims were checked as the model wrote them, so a claim that holds can still miss the question's point. On `click-1597`, for example, all its claims were confirmed, yet the judge's reason says the answer describes the intended behaviour and cites formatting code rather than the function the fix changed.
- **A2, 9 of 14 correct.** Same drafts as the full agent through the probing stage, with no mutation. Its 2 more correct answers than the full agent come largely from the judge's inconsistency described next, not from a clearly different answer.
- **A3, 8 of 14 correct, 71.4% coverage.** The largest drop in coverage among the five fully judged systems: it flagged 4 answers because refuted claims are not re-investigated. Those flags reduced confident errors only slightly (6, against 7 for the full agent).
- **B0, incomplete (judged 7/14).** 1 of the 7 judged answers is correct. With no repository, it abstained on 7 of 14 questions, and cited from memory otherwise, never hitting a line the fix changed.
- **A1, incomplete (judged 12/14).** 7 of the 12 judged answers are correct. All its claims were judged supported by reading, so it never flagged an answer.

### Comparisons on the common questions (paired)

B0 and A1 are left out, because their judging is incomplete.

| Comparison (full agent minus other) | n | Only full agent right | Only other right | McNemar p | Difference | 95% bootstrap CI |
|---|---|---|---|---|---|---|
| Correctness, against B2 | 14 | 0 | 3 | 0.25 | −21.4 pts | −42.9 to 0.0 |
| Causally supported, against B2 | 14 | 1 | 2 | 1.00 | −7.1 pts | −28.6 to 14.3 |
| Fix-location recall, against B2 | 14 | 0 | 1 | 1.00 | −7.1 pts | −21.4 to 0.0 |
| Correctness, against A2 | 14 | 1 | 3 | 0.625 | −14.3 pts | −42.9 to 14.3 |
| Correctness, against A3 | 14 | 0 | 1 | 1.00 | −7.1 pts | −21.4 to 0.0 |
| Correctness, against B1 | 14 | 2 | 1 | 1.00 | +7.1 pts | −14.3 to 28.6 |

For confident errors against B2: full agent 7, B2 4, with the full agent worse on 3 questions and better on none (p = 0.25).

**Why these are inconclusive:** with 14 questions a difference needs almost every disagreement to go one way to reach significance, and here only 3 questions separate the full agent from B2. Every CI touches or includes zero. Under the pre-registered rule, such a result is inconclusive, not negative. The direction is still against H1.

**Why the full agent may be behind B2: what the traces show.**

1. **Judge inconsistency is at least as large as the gap.** On `click-1193` and `click-3059`, the full agent and A2 gave nearly identical text and citations, yet the judge labelled the full agent *partial* and A2 *correct*. `click-1075` is similar, with *incorrect* against *correct*. So 3 of the labels separating the full agent from A2 reflect the judge, not the answers. The full agent and B2 are separated by the same number of questions, so this gap may be noise as well. Gate G3 (human labels, kappa rule) exists for exactly this.
2. **Verification did not change what was claimed.** The full agent confirmed every final claim. The checks tested the model's own statements, and did not push it towards the failure the question is really about. This is a real weakness of the current prompts, which were never iterated.
3. **The procedure spends its budget on citations.** 81 mutation checks led to 37 proposed citations, of which 10 were causal. 12 vacuity checks flagged 4 probes. So most re-investigation went to finding a line, not to questioning the answer.
4. **Some of that effort was wasted by a gap in the check.** 23 of the 81 mutation checks found nothing to mutate on the cited line, and the agent treated those lines as non-causal and went looking for another. See the RQ2 table below.

### Feedback loop, tools and safety (full agent, 14 questions)

| Measure | Value | Why |
|---|---|---|
| Probe results | 45 pass, 7 contradicted the claim, 10 broken | The model usually writes a runnable probe; 10 needed repair for errors in the probe itself |
| Refuted claims, then revised | 5 refuted, 5 revised | Each refutation led to a corrected claim, which is the feedback loop working as designed |
| Non-causal citations dropped outright | 2 | A claim with another causal citation keeps only that one |
| Unique lines mutation-checked | 54 | 24 accepted, 19 rejected after real mutants, 11 could not be tested (no operator applies) |
| Valid-call rate, all systems | 100% (0 invalid) | Forced tool calls with schemas leave little room for malformed calls |
| Tool errors (recovered): full agent, B2 | 27 (9), 16 (2) | Full agent: 23 mutation checks with nothing to mutate, 4 blocked probes. B2: 13 calls past its 12-probe budget, 2 blocked probes, 1 other |
| Unsafe attempts blocked: full agent, B2 | 4, 2 | Probes reaching for `subprocess`, writing outside `/tmp`, or using `__code__`. All were blocked before reaching the sandbox; no adversarial test has been run yet |

**Early signal for RQ2 (mutation verdicts against the developer's fix lines):**

| Unique lines the full agent checked | In a gold range | Not in a gold range |
|---|---|---|
| Accepted by the mutation check | 11 | 13 |
| Rejected after real mutants | 4 | 15 |
| Could not be tested: no mutation applies | 3 | 8 |

**Why:** among lines that could really be tested, the check accepted 11 of 15 fix lines (73%) and 13 of 28 other lines (46%), so it leans towards the developer's lines without matching them. Some of the 13 may be truly causal, because a fix location is one causal line but not the only one; human labels at G3 will settle that. The 11 untestable lines (20%) are `for` headers, `def` lines, `else:` and continuation lines, where no operator applies. The agent currently counts them as rejected, which is a flaw: 3 of them are lines the developers changed.

**Predictions against outcomes so far (dev, n too small to conclude):**

| Ablation | Prediction, written in advance | So far | Note |
|---|---|---|---|
| A1 | More confident errors than the full agent on doc-related questions | Not assessed | A1's judging is incomplete, so it is left out of this comparison |
| A2 | Similar correctness, clearly lower citation precision | Correctness similar. Citations in gold: full agent 19 of 44 (43.2%), A2 16 of 41 (39.0%), a small gap | H3 needs human labels: pending |
| A3 | Fewer confident errors, lower correctness than the full agent | Not seen: A3 has 6 errors against 7, and 8 correct against 7 | Judge noise applies here too |

**Cost.** The full agent used 195 real requests on the 14 questions and B2 used 143. A1, A2 and A3 used only 28, 19 and 12 real requests against 337 logical ones, because they reuse the full agent's cached prefix, which saved 82%. CPU seconds per question: full agent 6.33, B2 0.43.

**Measured quota (Google no longer publishes these):** 15 requests per minute, 500 requests per day, 250,000 input tokens per minute. All are in `docs/quota.md`.

---

## 6. Challenges

| Challenge | What happened | Effect |
|---|---|---|
| Daily request limit | 500 requests a day on the only usable free model | 14 of 20 dev questions completed by all systems |
| Run order | Click questions ran first, and the quota ended before the 3 marshmallow dev questions | All 14 completed dev questions are from click |
| Judge's daily limit | 200,000 tokens a day at a mean of 2,729 tokens per must-have answer, so about 73 answers a day | B0 and A1 were incomplete when the results were frozen; judging all 156 test questions does not fit before 15 Nov (section 8) |
| Judge inconsistency | Near-identical answers received different labels | Differences of a few questions cannot be trusted yet |
| Claims too easy to confirm | All 41 of the full agent's final claims were confirmed, none flagged | The checks did not yet catch answers that are true but beside the point |
| Gold quality unknown | No human spot check yet; some issues are feature requests | Some questions may be unfair to every system |
| Untestable citations | 11 of 54 checked lines have no applicable mutation, and the agent treats them as non-causal | Wasted requests on re-investigation, and some false rejections |
| Link fallback found nothing | All 367 links came from keywords, and the PR timeline gave none; the specification names the issue timeline | Fewer pairs than may be possible; 176 is still above the 120 target |
| Model retired | Groq no longer offers the originally planned development judge | Replaced (D-09), and the final judge chosen at P8 (D-37) |
| Bugs found in testing | `specs([])` offered every tool to one-shot baselines; a jedi crash took down a B2 question; undecodable bytes in test output crashed writers and the judge | All fixed, with tests. The tool-list bug was caught before any real run |

---

## 7. Mitigation

| Challenge | Plan |
|---|---|
| Daily request limit | Resume the remaining 6 dev questions after the reset; runs are resumable and free to replay. Section 8 gives the arithmetic: the must-have tier needs 4,580 real requests for all 156 test questions, about 9.2 days at 500 a day |
| Run order | Shuffle question order with a fixed seed from now on, so an early stop still covers every library |
| Judge's daily limit | Keep one judge, Groq `openai/gpt-oss-120b`, as the final judge (D-42). Judge answers as they come in, not all at the end, and choose the test-set size at G2 so that judging fits (section 8) |
| Judge inconsistency | Human labels at G3; below kappa 0.6 the primary comparison uses human labels. Add a repeat-judging check on identical answers |
| Claims too easy to confirm | Prompt iteration on dev only, logged in `docs/prompt_log.md`, with equal effort for all systems: ask for claims and probes that reproduce the scenario in the question, then re-run the pilot. Prompts stay frozen after G2 |
| Gold quality | Spot-check 20% at G1, report the disagreement rate, remove invalid questions, and rebuild the split |
| Feature-request issues | **Planned fix, not yet applied (D-43):** filter out feature-request issues by their GitHub labels, alongside the human spot check, before the split is rebuilt at G1. Measured on the current 176 questions, labels alone would remove none: no question has a feature or enhancement label, because click's labels name topics such as `parsing` and `help output`, and 20 marshmallow questions have no label. GitHub's separate issue-type field marks 6 of the 176 as Feature, so the filter reads that field too. 159 have no type, and `click-1075` has neither, so the human spot check remains the main safeguard |
| Untestable citations | **Planned fix, not yet applied:** during P10, lines with nothing to mutate become *untestable* instead of *not causal*, so they no longer trigger re-investigation and the RQ2 table reports them separately. Also add operators for loops, default arguments and call arguments. Measured through A11 and the RQ2 table |
| Link fallback | Implement the issue-timeline fallback before the rebuild at G1, so the dataset does not change under running experiments |

---

## 8. Timeline to 15 Nov

| Date | Work | Owner |
|---|---|---|
| 31 Oct | Resume the remaining dev questions and judging (Gemini resets at 12:30 IST) | Ameya, Sourav |
| 31 Oct to 2 Nov | P9 spot-check kit, issue-timeline fallback | Sunil |
| 2 to 3 Nov | G1: each member spot-checks their share of the 20% sample; rebuild split | Everyone |
| 3 to 5 Nov | P10: pilot and prompt iteration on dev, for all systems | Ameya |
| By 5 Nov | G2: choose the test-set size to fit both daily limits (below), record SHA-256 and prompt hashes, lock the pre-registration | Ameya, Sourav |
| 5 to 14 Nov | P11: must-have tier on test (full agent, B1, B2, A1-A3), then should-have as quota allows. Answers judged as they come in | Ameya, Aditya, Sourav |
| 8 to 11 Nov | G3: two members label 40-80 blinded answers; compute kappa | Two members, Sourav |
| 11 to 14 Nov | P12 analysis and figures; controlled and adversarial sets if quota allows | Sourav, Aditya |
| 14 to 15 Nov | P13 final bundles, viva preparation, final submission | Everyone |

### Quota arithmetic for the full test set

Two free daily limits apply: 500 Gemini requests for the systems, and 200,000 Groq tokens for the judge. All rates below are measured on the 14 common dev questions, with first-draft prompts.

**Gemini requests per question, for the 6 must-have systems:**

| Full agent | B2 | B1 | A1 | A2 | A3 | Total |
|---|---|---|---|---|---|---|
| 13.93 | 10.21 | 1.00 | 2.00 | 1.36 | 0.86 | **29.36** |

These are real requests. A1, A2 and A3 are low because they reuse the full agent's cached prefix, which requires running the full agent first. Without any cache reuse the total would be 49.93 requests per question, or 7,789 requests and 15.6 days for 156 questions.

**The two limits against the full test set (156 questions):**

| Limit | Cost of one test question | Daily limit | Questions a day | All 156 questions need | Questions possible in 10 days (5 to 14 Nov) |
|---|---|---|---|---|---|
| Gemini requests | 29.36 requests | 500 | 17.0 | 4,580 requests, 9.2 days | 170, so all 156 fit |
| Groq judge tokens | 6 answers × 2,729 tokens = 16,376 tokens | 200,000 | 12.2 | about 2.55 million tokens, 12.8 days | **122** |

**The test-set size is chosen at G2 to fit both limits before 15 Nov.** At these rates judging is the tighter limit, so 156 questions do not fit in the window and about 122 do. G2 uses the rates the pilot re-measures after prompt iteration, and the question count left after the G1 rebuild, so the final number may differ.

**Answers are judged as they come in, not all at the end.** Each day's answers are graded that day, so runs are paced at about 12 questions a day and any shortfall shows while there is still time to act.

**Risk to this timeline:** each day the lock slips costs about 12 questions. 122 questions use all of the judge's tokens in the window and 3,582 of the 5,000 Gemini requests, so should-have systems could still run but could not be judged in this window unless the must-have test set is made smaller. The minimum is 50 questions, with wider CIs reported. With fewer than about 120 questions H1 is under-powered, as stated in advance, so 122 leaves almost no margin.

---

## Reproducing these results

Saved outputs: `results/summary/mid_dev.md`, `results/summary/mid_dev.json`, `results/summary/toylib_ablations.md`, `data/mining_report.md`. Commands are in the README, section 7. Run: `python -m eval.report --run-id mid --split dev`. The saved `mid_dev` files are raw generated output from when the results were frozen: they list every system and include pairwise figures for B0 and A1 that this report does not use. Re-running the command now would also pick up the later B0 and A1 grades.
