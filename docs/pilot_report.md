# Pilot report (P10)

All numbers are measured on the 20 dev questions (`data/questions_dev.jsonl`). No test question has been run.
Run ids: `pilot` (iteration 0), `pilot_it1` (prompt iteration 1), `pilot_d51` (iteration 1 plus the change to ours
in D-51, and the first dev run of B1 and A1–A3 with the current prompts). Summaries are in `results/summary/`.

## 1. What changed during the pilot

| Step | What | Systems affected | Record |
|---|---|---|---|
| Iteration 0 | First-draft prompts | all | `docs/prompt_log.md` |
| D-47 | A line with nothing to mutate is "untestable", not "not causal"; plus a regression fix | ours, B2 output format | DECISIONS.md |
| Iteration 1 | The only prompt round (decision H4): describe frozen behaviour, trace to the deciding line, every behavioural claim cites a line | all, identically | `docs/prompt_log.md` |
| D-51 | Revised claims must cite; an uncited claim keeps its last proposed line, marked not causal | ours only (disclosed) | DECISIONS.md, PREREGISTRATION.md |
| D-52 | Scratch directories numbered, not random, so replays hit the cache | all (sandbox) | DECISIONS.md |
| D-50, D-53 | Main model and judge rotate over four members' keys; same models | none (quota only) | DECISIONS.md, PREREGISTRATION.md |

## 2. Results on dev (`pilot_d51`)

All six must-have configurations, 20 dev questions each, all judged (`results/summary/pilot_d51_dev.md`):

| System | Correct | Partial | Causally supported | Fix-location recall | Confident errors | Coverage |
|---|---|---|---|---|---|---|
| B1 (direct RAG) | 9 | 7 | 6 (30%) | 35% | 11 | 100% |
| B2 (ReAct, same tools) | 12 | 4 | 11 (55%) | 65% | 8 | 100% |
| **Ours** | 13 | 3 | 6 (30%) | 55% | 6 | 90% |
| A1 (no execution) | 15 | 3 | 7 (35%) | 60% | 5 | 100% |
| A2 (no mutation) | 15 | 4 | 8 (40%) | 60% | 4 | 90% |
| A3 (flag only, no re-investigation) | 13 | 4 | 10 (50%) | 55% | 6 | 65% |

**What dev suggests, stated before the test runs:** the full agent is not better than its own ablations on dev. A2 and
A1 are more often correct (15 against 13), and A3, which flags failures instead of re-investigating them, has more
causally supported answers (10 against 6). The likeliest reading is that re-investigation after a failed check often
rewrites claims that were right, or replaces lines the judge accepts. On 20 development questions these differences
are 2–4 questions and not significant. They were **not** acted on: the single prompt round is used up (H4), and
changing the procedure to fit these numbers would be tuning on results. The test runs decide; if the pattern holds,
it is a main finding (the checks cost accuracy), reported as such.

Ours against B2, per question:

| | Ours only | B2 only | Both |
|---|---|---|---|
| Correct | 3 | 2 | 10 |
| Causally supported (primary) | 1 | 6 | 5 |

On dev, ours is behind B2 on the primary measure (6 against 11 of 20). The dev set is small and was used for
development, so this is not a test of H1, but it is the honest expectation going into the test runs.

Why ours misses the primary measure on correct answers (from `docs/prompt_log.md`): it writes more claims than B2
(54 against 41), the metric needs a causal line for every claim, and in 6 correct answers one claim's line is judged
*on-topic*. The mutation check and the judge often disagree on ours' lines (preview of RQ2, judge not yet validated).

## 3. Cost per question

Measured on `pilot_d51`. "Requests" counts every model call; "fresh" counts calls that reached the API (the rest came
from the cache). On test every call of ours, B2 and B1 is fresh; A1–A3 run after ours and share its cached prefix.

| System | Requests / q (mean) | Max | Fresh API / q when run after ours | Tokens / q (mean) | Sandbox CPU s / q | Probe runs / q | Mutant runs / q |
|---|---|---|---|---|---|---|---|
| ours | 14.2 | 23 | (all fresh) | 191,479 | 8.2 | 4.0 | 9.6 |
| B2 | 9.6 | 25 | (all fresh) | 123,902 | 0.5 | 3.8 | 0.5 |
| B1 | 1.0 | 1 | 1.0 | 5,190 | 0 | 0 | 0 |
| A1 | 7.5 | 11 | 2.2 | 80,324 | 0 | 0 | 0 |
| A2 | 9.7 | 21 | 1.0 | 118,807 | – | 3.5 | 0 |
| A3 | 7.7 | 12 | 0.7 | 85,885 | – | 2.8 | 4.2 |

Ours is within the 25-requests target (mean 14.2, max 23). Thinking tokens are 0 (thinking level left unset).

Judge: 2,794 tokens per judgement (mean of 87 fresh calls; max 4,644), one judgement per answer.

## 4. Quota

Measured limits (`docs/quota.md`): Gemini `gemini-3.1-flash-lite` free tier, 500 requests a day and 15 a minute per
key (project); Groq `openai/gpt-oss-120b` free tier, 200,000 tokens a day and 8,000 a minute per key. Both reset daily
(Gemini at midnight Pacific, 13:30 IST). With four members' keys each (D-50, D-53): **2,000 Gemini requests and
800,000 judge tokens a day** (about 285 judgements).

## 5. Quota plan (`scripts/quota_plan.py`)

Must-have tier (ours, B1, B2, A1, A2, A3) on all 150 test questions, 4 days at 2,000 requests a day:

| Assumption | Gemini requests | Days of Gemini quota | Judgements | Days of judge quota |
|---|---|---|---|---|
| Realistic: A1–A3 reuse ours' cached prefix (fresh rates above) | 4,305 | 2.2 | 900 | 3.2 |
| Conservative: no cache reuse | 7,455 | 3.7 | 900 | 3.2 |

`quota_plan.py --daily 2000 --days 4 --questions 150`: the must-have tier affords 278 questions (realistic) or 160
(conservative). **All 150 test questions fit**, so the test set does not need to be cut. The judge is the slower of the
two; judging runs alongside, question by question.

Run order (D-38): ours first, then B2 and B1, then A2, A3, A1 (sharing ours' cache), each judged the same day. Then the
should-have tier in CLAUDE.md §2.7 order as quota allows until 13 Nov; anything not run is reported as future work.

| Day (IST, quota day starts 13:30) | Planned |
|---|---|
| 7–8 Nov | lock (G2), then ours and B2 on test |
| 8–9 Nov | finish ours and B2; B1, A1–A3 |
| 9–11 Nov | finish judging; should-have tier (B0, B3, B2+, A6, repeat runs, …) |
| by 12 Nov | spot-check files back (G1), applied as an exclusion |
| 12–13 Nov | G3 labels (two members), kappa |
| 14–15 Nov | analysis, results, final bundles |

## 6. Questions in the spot-check sample

Six dev questions are in the G1 sample. If any is marked invalid, its pilot results are dropped from this report.

**G1 applied on 2026-11-11.** Three of the six were marked invalid (`click-1844`, `click-2396`, `marshmallow-2924`):
in each, the failing test checks a new feature or an unrelated change, not the behaviour the issue asks about. The
table in §2 is kept as it stood when the prompt and lock decisions were made. Without those three questions, the pilot
reads as follows (`python -m analysis.make_all --run-id pilot_d51 --split dev`):

| System (17 dev questions) | Correct | Causally supported | Fix-location recall | Confident errors | Coverage |
|---|---|---|---|---|---|
| B1 | 8 (47.1%) | 29.4% | 29.4% | 9 | 100% |
| B2 | 11 (64.7%) | 58.8% | 64.7% | 6 | 100% |
| **Ours** | 12 (70.6%) | 35.3% | 52.9% | 4 | 88.2% |
| A1 | 14 (82.4%) | 41.2% | 58.8% | 3 | 100% |
| A2 | 13 (76.5%) | 41.2% | 58.8% | 3 | 88.2% |
| A3 | 12 (70.6%) | 58.8% | 52.9% | 4 | 58.8% |

The reading in §2 does not change: ours is behind B2 on the primary measure and not better than its own ablations.
