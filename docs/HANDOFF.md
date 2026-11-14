# Handoff: Ameya's machine → Sourav's machine (5 Nov 2026)

Written for the Claude Code agent that continues this project on Sourav Nath's machine. Read it after `CLAUDE.md`, which
stays the authority on rules, method and build. If this file and `CLAUDE.md` disagree, follow `CLAUDE.md` and ask the human.

Read in this order: `CLAUDE.md` → this file → `docs/progress.md` (checklist and log) → `docs/work_split.md` (ownership after
the mid submission; it replaces CLAUDE.md §3's table) → `docs/mid_submission_report.md` (results so far) → `DECISIONS.md`
(D-01 to D-43).

---

## 1. Current state in one screen

- **Phases P0–P8 are done** (foundation, LLM layer, sandbox, mutation, data pipeline, retrieval and tools, agent, baselines,
  evaluation). **Nothing from P9 onward has started.** No gate after G0 has been passed.
- **Mid submission is done and on GitHub.** All four members pushed `*_update_1.zip` on 30 Oct (PRs #5–#8, merged by Ameya).
  Every member's commits are under their own name, and no commit carries AI attribution.
- **This folder's git history is unrelated to GitHub's on purpose.** Code never goes from here to GitHub through git; it
  goes only as member zips (CLAUDE.md §3). There is no common ancestor, so `git merge origin/main` fails with "unrelated
  histories". To sync, copy files: that is how Sunil's Windows path fix in `tools/static.py` was taken on 5 Nov. At commit
  `tools: take Sunil's Windows path fix from main`, the local tree is identical to `origin/main` (`203be38`). After it,
  only `docs/progress.md` and `docs/HANDOFF.md` changed; they are in `sunil_update_2.zip` (section 6).
- **Tests:** 249 unit tests pass (`pytest`, which skips `docker` and `live` by default), plus 17 Docker tests
  (`pytest -m docker`). One unit test skips when the local click tree is missing; it reappears once a workspace has been built.
- **Dataset:** 176 validated questions (click 147, marshmallow 29). Dev 20, test 156. Test file SHA-256
  `2708aa21d6767373e189227353c85d8ab272456cbe471ee0d6a880026955581e`. **The test set has never been run.** `eval.run` refuses
  it without `--allow-test`, which must not be used before gate G2.
- **Preliminary dev results (run id `mid`, first-draft prompts):** all seven systems completed the same 14 dev questions, all
  of them click. Correct: B2 10/14, A2 9/14, A3 8/14, full agent 7/14, B1 6/14. The full agent against B2: p = 0.25, CI −42.9
  to 0.0 points, inconclusive and against H1. B0 and A1 are reported as incomplete (judged 7/14 and 12/14) and left out of
  every comparison. Details are in the report, section 5.
- **`PREREGISTRATION.md` is still DRAFT.** It is locked at G2.

## 2. Setting up on the new machine

1. Unzip `handoff.zip` somewhere. **Quote paths in every shell command**: Ameya's folder name contained a space, and an
   unquoted path broke a script once.
2. Recreate the venv (not shipped): `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`.
   Python 3.10 or newer. Ameya's `.venv` used `--system-site-packages` because of a slow network; you don't need that.
3. Write `.env` from `.env.example` with **Sourav's own keys**: `GEMINI_API_KEY`, `GROQ_API_KEY`, `GITHUB_TOKEN`.
   `MISTRAL_API_KEY` is not needed (D-42). The human types the keys into the file, never into the chat. Check that keys are
   present only (`python scripts/check_env.py`); never print their values.
4. Start Docker and build the sandbox image: `docker build -t rtci-sandbox:py310 sandbox`.
5. Verify: `python -m pytest -q`, which should show 249 passed, then `python -m pytest -q -m docker`, which should show
   17 passed.
6. `git remote -v` should point at `https://github.com/ameya-purohit/LMA-Final-Project.git`. **Never `git push` from this
   folder** (CLAUDE.md §3).

**What ships in the zip and what rebuilds itself:**

| Path | In the zip? | Notes |
|---|---|---|
| `.cache/llm.sqlite` | yes | 592 cached replies plus the daily request counter. Re-running anything already run costs no quota. Keys are not part of the cache key, so the cache works with Sourav's keys |
| `.cache/github/` | yes | Every raw GitHub response (4,279 files), so mining re-runs make no API calls |
| `.cache/candidates.json`, `.cache/validation.jsonl` | yes | Mining candidates and sandbox validation results; validation took hours of Docker time |
| `data/repos/*.git` | yes | Bare clones of click and marshmallow |
| `results/mid/`, `results/traces/` | yes | Raw answers, judgements and JSONL traces of the mid run. Git-ignored |
| `.cache/trees/` | **no** | Frozen trees, rebuilt automatically from `data/repos` by `tools/workspace.py` (`data.freeze.export_tree`) when first needed |
| `.cache/indexes/` | **no** | BM25 indexes, rebuilt automatically per (library, commit) on first use |
| `.env`, `.venv/`, `__pycache__/` | **no** | Make your own |

## 3. Quota status (as of 5 Nov, 21:15 IST)

- **No API call has been made since 30 Oct.** The counter in `.cache/llm.sqlite` (table `daily`) last shows 30 Oct: Gemini 504
  requests, Groq 110 judgements. With Sourav's own keys, both quotas belong to Sourav's own projects and start full.
- **Measured limits** (`docs/quota.md`): Gemini `gemini-3.1-flash-lite`: 15 per minute, **500 per day**, 250,000 input tokens
  per minute. Groq `openai/gpt-oss-120b`: 8,000 tokens per minute, **200,000 tokens per day**.
- **Reset time changed.** Gemini resets at midnight Pacific, and US clocks changed on 1 Nov, so that is now **13:30 IST**
  (it was 12:30 IST in October). `llm/client.py` counts days in `America/Los_Angeles`, so the code handles this itself.
  Groq's daily limit appears to roll over a 24-hour window.
- **Measured costs** (14 dev questions, first-draft prompts): must-have tier = 29.36 real Gemini requests per question
  (full agent 13.93, B2 10.21, B1 1.00, A1 2.00, A2 1.36, A3 0.86; the ablations are cheap only if the full agent runs first),
  and 6 × 2,729 = 16,376 Groq tokens per question for judging. **Groq is the tighter limit:** about 12 test questions a day,
  against about 17 for Gemini.

## 4. Next steps, in order

The timeline in the report, section 8, planned G1 for 2–3 Nov and G2 for 5 Nov. **Neither has happened**, so the schedule
has slipped by about 4 days. Decision H2 in section 7 is the consequence.

1. **(Human) Sunil pushes `sunil_update_2.zip`** (this handoff and `progress.md`). It is optional for the code and only
   keeps GitHub's docs current.
2. **Before P9: dataset fixes that must land before the split is rebuilt** (the test set must not change after G2):
   - The feature-request filter (D-43, already approved by Ameya). Drop an issue whose labels contain `feature` or
     `enhancement`, or whose GitHub issue type is Feature. Log each removal to `data/dropped.jsonl`. Measured: 0 by label
     and 6 by type, of 176. The cached issue JSON in `.cache/github/` already holds `labels` and `type`.
   - The issue-timeline link fallback (report, section 7) only if the human approves (H3). It adds pairs that then need
     sandbox validation, which costs time.
   - Shuffle question order with a fixed seed in the runners, so an early quota stop still covers both libraries (report,
     section 7).
3. **P9: spot-check kit** (CLAUDE.md §6.10): `annotation/sample.py`, `annotation/spotcheck.html`,
   `annotation/apply_spotcheck.py`, `docs/annotation_guide.md`. Then make update zips per `docs/work_split.md`. Not started.
4. **G1 (human gate):** each member checks their share of the 20% sample. Then run `apply_spotcheck.py`, `data/split.py` and
   `data/validate_questions.py`. The dev set may change, so the `mid` results then describe an older dev set.
5. **P10: pilot.**
   - First the fix from P10: a cited line with nothing to mutate is reported as *untestable*, not *not causal*.
     It was 11 of 54 lines on dev (report, section 5).
   - Then iterate prompts on dev only, with equal effort for every system, logging each iteration in `docs/prompt_log.md`.
     The main known weakness is that claims are too easy to confirm: every final claim of the full agent was confirmed.
   - Use a **new run id** (for example `pilot`), and never mix it with `mid`.
   - Measure requests and tokens per question, run `scripts/quota_plan.py`, and write `docs/pilot_report.md`.
6. **G2 (human gate):** the human approves the test-set size, chosen to fit both daily limits before 15 Nov (H2). Then write
   the test SHA-256 and the prompt hashes into `PREREGISTRATION.md`, change DRAFT to LOCKED, and commit.
7. **P11:** the must-have tier on test (full agent first, then B1, B2, A1–A3), **judging each day's answers the same day**.
   Then the should-have tier if quota is left.
8. **G3 (human gate):** two members label 40–80 blinded answers (`eval/human_export.py`); compute kappa (`eval/kappa.py`).
9. **P12** analysis (`analysis/make_all.py`, `docs/results.md`) and **P13** final zips and `docs/viva_prep.md`.
   Final submission is 15 Nov.

## 5. Half-finished work

- **The `mid` dev run stopped on quota.** Unanswered dev questions: full agent 5 (`click-3449`, `click-461` and the 3
  marshmallow questions); B2, A1, A2 and A3 have 6 each (those 5 plus `click-3099`). B0 and B1 answered all 20.
- **Unjudged `mid` answers:** B0 has 8 (2 of them inside the 14 common questions), B1 6, and the full agent 1 (`click-3099`).
  The judge loop was stopped on purpose on 30 Oct. A1's grades on 14/14 exist in `results/mid/judgements/`, but the report
  uses its frozen 12/14.
- **Recommendation: do not finish `mid`.** It ran on first-draft prompts and code that P10 will change. Finishing it would
  cost about 180 Gemini requests and judge tokens in days that are short. If the human wants it finished anyway (H5), resume
  with:

  ```bash
  python scripts/run_all.py --by-question --limit 20 --systems ours b2 a2 a3 a1 --split dev --run-id mid
  python -m eval.judge --run-id mid --split dev --rpm 3 --system <s>     # for each system
  ```

  **Don't run `python -m eval.report --run-id mid` into `results/summary/`.** It would overwrite `mid_dev.md` and `.json`,
  which must stay matching the submitted report. Write to a new run id instead.
- **Planned, not applied:** the untestable-lines fix (P10), the feature-request filter (D-43), seeded shuffling, and the
  issue-timeline fallback (if approved).

## 6. Bundles: who still has to push what

| Zip | Member | Contents | Status |
|---|---|---|---|
| `sunil_scaffold`, `*_mid`, `*_update_1` | all four | P0–P8 and the mid report | **Pushed and merged** (PRs #1–#8) |
| `sunil_update_2.zip` | Sunil | `docs/progress.md`, `docs/HANDOFF.md` | **Due**: built 5 Nov, not pushed |

How to make the next zips: commit locally, `git fetch origin`, then
`python scripts/make_bundles.py --member <m> --name <m>_update_<n> --since origin/main`.

- `--since origin/main` works through file diffs, so the unrelated histories don't matter.
- If one member's zip would break `main` until a later member's zip lands, add `--also <file>`. It copies that file into
  the earlier zip; the later member's zip then holds an identical copy, so it shows no change.
- Push order in every round: Sunil → Ameya → Aditya → Sourav, each pull request merged before the next. Ameya owns the repo
  and merges.
- Before handing zips over, rehearse on a fresh clone of the real `main`:
  1. Disable pushing in the clone: `git remote set-url --push origin DISABLED`.
  2. For each zip, in order: unzip without its PUSH.md, run its own test command, commit, and merge.
  3. Confirm that the unit tests pass after every merge and the Docker tests pass at the end.
  4. Check that the final tree equals this folder's.
  5. Scan the zips for keys, `.env`, caches and raw results.
- Tell the human which zips to push, by whom, and in what order, in plain step-by-step terms. Ameya was new to this workflow.
  Keep building locally; don't wait for pull requests to merge.

## 7. Decisions waiting for a human

| # | Decision | Who | Context, and the agent's recommendation |
|---|---|---|---|
| H1 | **G1 spot check:** each member checks their share of the 20% sample | all four | Needs the P9 kit first. About 35 questions, roughly 9 each |
| H2 | **Test-set size at G2**, given the slip | Ameya, Sourav | See the table below. Groq limits it. Recommendation: lock as early as possible, since each day costs about 12 questions. Shorten P10 rather than miss the minimum of 50 |
| H3 | **Build the issue-timeline fallback or not.** It changes the dataset before G1 | Ameya | It may add pairs but needs mining and validation time. Recommendation: skip it, and log it as a deviation in `PREREGISTRATION.md` and as future work |
| H4 | **How much prompt iteration in P10** | Ameya, Sourav | It must be equal for all systems and logged. Fewer iterations leave more days for test runs |
| H5 | **Finish the `mid` dev run or not** | Ameya | Recommendation: no (section 5) |
| H6 | **Who builds the zips and who merges from now on** | team | Ameya owns the repo and merges pull requests. `docs/work_split.md` still assigns files to all four members, and each member pushes their own zip |
| H7 | **The two G3 labellers** | team | 40–80 blinded answers, plus every citation from the full agent and A2 |
| H8 | **Should-have tier without judge tokens** | Ameya, Sourav | At most test-set sizes, all of Groq's tokens go to the must-have tier. Options: run should-have systems unjudged and report their judge-free metrics only (fix-location recall, coverage, cost), or shrink the must-have test set |

**Test questions affordable from the lock date to 14 Nov** (inclusive; at the measured dev rates, so only a guide until P10
re-measures them; the lower of the two numbers binds):

| Lock and start runs on | Days | Gemini allows (500 / 29.36 per day) | Groq allows (200,000 / 16,376 per day) |
|---|---|---|---|
| 6 Nov | 9 | 153 | **109** |
| 7 Nov | 8 | 136 | **97** |
| 8 Nov | 7 | 119 | **85** |
| 9 Nov | 6 | 102 | **73** |
| 10 Nov | 5 | 85 | **61** |
| 11 Nov | 4 | 68 | **48**, below the minimum of 50 |

Below about 120 questions H1 is under-powered, as stated in advance. Report the CI, and call one that includes zero
inconclusive. G3 labelling and P12 analysis must also fit before 15 Nov.

**Already decided, don't reopen:**
- The final judge is Groq `openai/gpt-oss-120b` with no Mistral key (D-42).
- Partial answers count as wrong (D-41).
- The feature-request filter goes in before the G1 rebuild (D-43).
- Untestable lines become their own class in P10.
- Pre-2020 issues fixed after 2020 are kept.
- B0 and A1 are marked incomplete in the mid report.

## 8. Known issues and gotchas

- **Method weaknesses found on dev:**
  - Claims are too easy to confirm; the full agent never flagged an answer.
  - The judge is inconsistent: near-identical answers got different labels on `click-1075`, `click-1193` and `click-3059`.
  - Untestable lines are counted as non-causal.
  - The strict rule falsely rejects `min(...)`-style lines whose only mutation is deletion. That is breakage, and it is
    documented on toylib.
  - B2 rarely used `mutate_and_run` (2 of 14 questions).
- **Data:**
  - The link fallback found 0 links; all 367 came from keywords.
  - 43 questions were opened before 2020.
  - 15 questions fail with an import or attribute error message.
  - 314 of 1,066 gold ranges are add-only anchors.
  - `click-1075` is a feature request that no metadata filter catches.
  - Question ids sort click first, which is why the dev run never reached marshmallow.
- **Code:**
  - `tools/static.py` holds a commented-out old line next to Sunil's fix (Sunil's file; harmless).
  - jedi can crash on some trees. `find_definition` then falls back to an AST search, and every tool failure reaches the
    model as a readable error.
  - JSONL and the judge prompt use `errors="backslashreplace"` and strip surrogates, because test output can contain
    undecodable bytes.
- **Shell:**
  - Never `pkill -f` a pattern that appears in your own command line; it killed its own shell three times. Kill by PID.
  - Don't name a scratch script after a standard-library module (`types.py` broke `json`).
- **Quota:**
  - `eval.run --daily-guard N` raises the client's own requests-per-day stop. It was used once to learn the server's real
    limit of 500.
  - Exit code 3 means a quota stop: re-run the same command after the reset; finished work is kept.
- **Rules that are easy to break** (all in CLAUDE.md):
  - no AI co-author or "Generated with" line anywhere, even if a tool suggests one (§2.6);
  - never print or commit key values;
  - never run LLM-written code on the host;
  - never tune on test questions;
  - one judge per experiment;
  - never switch models mid-experiment;
  - gold only from fixes and tests, never from an LLM;
  - stop and ask before deleting data or rewriting git history.
