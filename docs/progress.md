# Progress checklist

Running checklist for the build (CLAUDE.md §4). Updated at the end of every phase.
Legend: `[x]` done, `[~]` in progress, `[ ]` not started, `[!]` blocked (reason given).

## Gates and phases

- [x] G0 Environment check
- [x] P0 Foundation (+ `sunil_scaffold.zip`)
- [x] P1 LLM layer
- [x] P2 Sandbox
- [x] P3 Mutation (+ mid bundles for Ameya, Aditya, Sourav)
- [x] P4 Data pipeline (live mining)
- [x] P5 Retrieval and tools
- [x] P6 Agent
- [x] P7 Baselines
- [x] P8 Evaluation
- [x] P9 Spot-check kit (update bundles deferred to the end, by Sourav's choice)
- [~] G1 Human gate: spot check (waiting for the four members' verdicts)
- [x] P10 Pilot (`docs/pilot_report.md`; prompt iteration 1, D-51, D-52)
- [x] G2 Lock (2026-11-07: 150 test questions, PREREGISTRATION.md LOCKED; G1 applied later as an exclusion)
- [~] P11 Main runs (run id `main`): must-have tier complete 2026-11-10 (6 systems x 150 test questions, all judged); should-have tier next
- [ ] G3 Human gate: labels
- [~] P12 Analysis: first full run on `main` test done 2026-11-10 (`results/summary/analysis_main_test/`, draft `docs/results.md`); final rerun after G1 and G3
- [ ] P13 Final bundles

## Current state (5 Nov 2026, 21:15 IST): handoff to Sourav

The project moves to Sourav Nath's machine. Full detail is in [HANDOFF.md](HANDOFF.md); this is the summary.

**Done.** P0–P8, all tested: 249 unit and 17 Docker tests pass. Dataset: 176 validated questions (dev 20, test 156; test
SHA-256 `2708aa21…5581e`), test never run. Mid submission done: all four members pushed `*_update_1` (PRs #5–#8, merged
30 Oct). The local tree equals GitHub `main` (`203be38`), after taking Sunil's `tools/static.py` path fix. Preliminary dev
results (run `mid`, 14 common click questions): B2 10/14 correct, full agent 7/14, p = 0.25, inconclusive.

**Next, in order.**

1. Sunil pushes `sunil_update_2.zip`.
2. Before P9: the feature-request filter (D-43) and seeded shuffling; the issue-timeline fallback only if approved.
3. P9 spot-check kit.
4. G1.
5. P10: the untestable-lines fix, prompt iteration on dev under a new run id, the pilot report and the quota plan.
6. G2.
7. P11, judging every day's answers that day.
8. G3.
9. P12, then P13.

**Gates pending.**

- G1 (spot check): not started, needs the P9 kit.
- G2 (lock): planned for 5 Nov and now late. Its test-set size is limited by Groq: about 12 questions per day of runs,
  so a lock on 7 Nov allows about 97 (table in HANDOFF.md §7).
- G3 (labels): pending. `PREREGISTRATION.md` is still DRAFT.

**Quota status.**

- No API call has been made since 30 Oct (the last counter: Gemini 504, Groq 110 judgements).
- Limits: Gemini 500 requests per day and 15 per minute; Groq `openai/gpt-oss-120b` 200,000 tokens per day and 8,000 per
  minute.
- Gemini now resets at 13:30 IST, because of the US clock change on 1 Nov.
- Sourav's own keys mean his own fresh quotas. The cache in `.cache/llm.sqlite` replays all earlier work for free.

**Commands to resume** (from the project root, venv active, Docker running, `.env` filled in):

```bash
pip install -r requirements.txt && docker build -t rtci-sandbox:py310 sandbox
python scripts/check_env.py                      # keys present (never printed), Docker, network
python -m pytest -q && python -m pytest -q -m docker
# Only if the human chooses to finish the mid dev run (recommended: no, see HANDOFF.md §5):
python scripts/run_all.py --by-question --limit 20 --systems ours b2 a2 a3 a1 --split dev --run-id mid
python -m eval.judge --run-id mid --split dev --rpm 3 --system <s>
# Pilot after P10 (new run id; never overwrite results/summary/mid_dev.*):
python scripts/run_all.py --by-question --limit 20 --systems ours b2 a2 a3 a1 --split dev --run-id pilot
python -m eval.report --run-id pilot --split dev
# Next zips:
git fetch origin && python scripts/make_bundles.py --member <m> --name <m>_update_<n> --since origin/main
```

## Log


### 2026-10-27, G0
- Python 3.12.3, git 2.43.0, Docker server 29.1.3: OK. Remote is ameya-purohit/LMA-Final-Project: OK.
- Keys present: GEMINI_API_KEY, GROQ_API_KEY, GITHUB_TOKEN. MISTRAL_API_KEY: missing (optional).
- Live calls: Gemini `gemini-3.1-flash-lite` OK (first try 503 "high demand", OK on retry); GitHub OK (5000/h).
- Groq: key works, but `llama-3.1-8b-instant` returns 404 (no longer offered). Groq now lists:
  openai/gpt-oss-20b, openai/gpt-oss-120b, qwen/qwen3.8-27b, allam-2-7b (plus speech/guard models).
  Ameya chose `openai/gpt-oss-20b` as development judge (D-09); live call OK. G0 passed.
- venv: `.venv` uses `include-system-site-packages = true` locally, so it reuses numpy/scipy/matplotlib
  from `~/.local` (slow network). CI and members' setups install fresh from pyproject.toml.
- Disk: pip cache purged (with approval), 11 GB free.
- P0 files are written but not yet tested or committed.

### 2026-10-28, P0
- Unit tests: 30 passed (`tests/core`, `tests/bundles`). ci.yml parses; local secret scan clean; every file owned.
- Draft P1 files under `llm/` exist in the working tree but are NOT committed or bundled; P1 starts only
  after Sunil's scaffold PR is merged (Ameya's instruction).
- Committed locally as `phase P0: foundation`. Built `bundles/sunil_scaffold.zip` (25 files + PUSH.md).
- Fresh-clone check: cloned GitHub repo (1 commit, default README), followed PUSH.md: branch, unzip (PUSH.md
  excluded), 25 files staged, 30 tests passed, `pip install -e .` metadata builds. The scaffold README
  replaces GitHub's one-line default README.
- Added `requirements.txt` (kept equal to pyproject.toml by a test) and step-by-step replication in the
  README; PUSH.md and CI now `pip install -r requirements.txt` (D-10). Rebuilt `sunil_scaffold.zip`
  (27 files + PUSH.md). Fresh-clone check repeated with a `.venv` and `.env` present in the clone:
  27 files staged, neither `.venv` nor `.env` staged, 32 tests passed.
- Ameya decided (2026-10-28) to keep building locally without waiting for Sunil's merge.

### 2026-10-28, P1
- Built `llm/` (neutral types, SQLite cache + daily counter, pacing, retries, QuotaExhausted, quota log,
  JSONL trace, Gemini/Groq/Mistral providers) and `scripts/smoke_llm.py`. Decisions D-11..D-14.
- Unit tests with fake providers: 28 in `tests/llm` (cache hit = 0 calls, 429 retry with server delay,
  per-day 429 -> QuotaExhausted, configured rpd stop, day reset, rpm spacing, tokens logged). All 60 unit tests pass.
- Live smoke test PASSED: Gemini plain call; Groq `openai/gpt-oss-20b` plain call; Gemini 2-turn function
  calling: turn 1 called the tool with a thought signature attached, turn 2 used the tool result (37 C).
  Cost: 3 Gemini requests (217 in / 29 out tokens), 1 Groq request. Trace scanned: no key values.
- Mistral provider written but not live-tested (no key; only needed if chosen at P8).

### 2026-10-28, P2
- Built `sandbox/` (Dockerfile, pinned test-requirements, trusted runner, AST policy, SandboxSession +
  LocalBackend) and `tools/probe.py`. Image `rtci-sandbox:py310` is 138 MB. Decisions D-15..D-20.
- Docker tests (9 passed): pass/fail/raise outcomes with the innermost library frame; network fails
  (connect and DNS); writes outside /tmp fail; container non-root, read-only, network none; policy blocks
  os.system/subprocess/eval/__import__/writes outside /tmp before the container is used, and logs
  `unsafe_attempt`; timeout enforced; metadata shim works; pinned env (3.10, UTC, C.UTF-8, hash seed 0, no TTY);
  repo tests run via pytest jobs.
- Bug found by tests and fixed: a probe that failed to import still had observe() called on it.
- Fixed a test leak in tests/core/test_env.py (it disabled .env loading for later tests) and made plain
  `pytest` skip docker/live by default (pyproject addopts). Both are Sunil-owned files.
- Totals: 96 unit, 9 docker, 3 live tests pass.

### 2026-10-28, P3
- Built `tools/mutate.py` (libcst one-line mutants; outcome_changed / is_breakage / classify / verdicts;
  mutate_and_run, mutate_group, check_vacuous) and `tests/fixtures/toylib/`. Decisions D-21..D-26.
- Every toylib assertion of CLAUDE.md §6.5 passes on the local backend (18 tests) AND in Docker (7 tests):
  C1 line 88 accepted via `0 -> -1`, line 12 rejected (its delete mutant is ImportError breakage, so only
  `any_flip` would accept it); C2 `return None` rejected by specificity, `LIMIT 100 -> 101` accepted,
  deleting `result = min(...)` is UnboundLocalError breakage; redundant guards rejected alone, accepted as a
  group; A11 constant-free line rejected with constants only, accepted with the full set; vacuous probe
  flagged; os.system probe blocked; STRICT_DEFAULT on line 12, decider on line 88; every mutant leaves all
  other lines byte-identical.
- Added `scripts/check_bundle_order.py`: all 4 prefixes of the push order pass unit and Docker tests.
- Totals: 114 unit, 16 docker, 3 live tests pass.
- Bundles built: `sunil_scaffold.zip` (28 files, rebuilt: Sunil had not pushed yet), `ameya_mid.zip` (16),
  `aditya_mid.zip` (12), `sourav_mid.zip` (9). Rehearsed in a fresh clone in push order, running each
  PUSH.md's own test command: 32 / 28 / 36 / 18 passed; all four together: 114 passed.

### 2026-10-30, P4-P8 (mid submission) (updated 16:42 IST; deadline 30 Oct 23:59 IST)

**Done and committed locally** (commits `phase P4` .. `phase P8`; later doc edits may be uncommitted):
- Applied `docs/work_split.md` to `bundles/ownership.yaml`.
- P4: mined 3303 closed PRs (cached); 219 candidates; 182 validated in Docker; 176 questions (click 147, marshmallow 29);
  dev 20, test 156; test SHA-256 2708aa21d6767373e189227353c85d8ab272456cbe471ee0d6a880026955581e. Report in
  `data/mining_report.md`. The test set has not been run and must not be (`eval.run` refuses without `--allow-test`).
- P5: BM25 retrieval, tools, registry, workspace. P6: agent with every ablation flag; scripted tests of every decision point.
  Live toylib: ours 11 requests, sensible graded answer. P7: B0, B1, B2, B2+, B3, each live on toylib (1, 1, 9, 19 logical).
- P8: eval run/judge/metrics/stats/report/human export/kappa; `scripts/run_all.py`, `scripts/quota_plan.py`. Final judge
  Groq `openai/gpt-oss-120b` (D-37). Partial counts as wrong (D-41). Decisions D-27..D-41 are in `DECISIONS.md`.
- Zero-cost ablations: `results/summary/toylib_ablations.md`. Over 9 planted lines, agreement with ground truth: any flip 7,
  behavioural 7, specific 8, specific with constants only 7. Leniency over 19 executed lines: 32% / 26% / 11%.
- Tests: 240+ unit, 17 Docker; `scripts/check_bundle_order.py --docker`: all 4 prefixes pass; all code parses on Python 3.10.
- Explainers written: data_mining, gold_validation, retrieval, tools, agent, baselines, evaluation, analysis.
- Bugs found by tests and fixed: `specs([])` returned every tool (would have given B0, B1 and out-of-steps turns all tools);
  BM25 hid matches with zero IDF; lone surrogates crashed JSONL writes.

**Measured quota so far:** Gemini flash-lite: 15 requests/minute, 250,000 input tokens/minute (`docs/quota.md`). Daily limit not
yet hit. `config` guard is `rpd: 500`, our own starting value, not a measured limit. Groq gpt-oss-120b headers: 1000 requests/day,
8000 tokens/minute; about 2,250 tokens per judged answer.

**Update 17:00 IST:** the server confirmed the daily limit: 500 requests/day (429 GenerateRequestsPerDayPerProjectPerModel-FreeTier). Final
answers: b0 20, b1 20, ours 15, b2 14, a2 14, a3 14, a1 14; 14 questions common to all seven (compare on these only). No more Gemini quota before
the deadline (reset 12:30 IST on 31 Oct). Judge running with `--common-only --rpm 3`; log in `.cache/judge.log`.

**Earlier state, in progress at 16:42:** dev run, background command, log in `.cache/run_mid.log`:
`scripts/run_all.py --by-question --limit 20 --systems ours b2 a2 a3 a1 --split dev --run-id mid --no-judge`.
At 16:42: b0 20/20, b1 20/20, ours 9/20, b2 9/20, a2 9/20, a3 9/20, a1 9/20; 338 Gemini requests today. Answers are saved in
`results/mid/<system>/<qid>.json` (git-ignored); re-running the same command resumes for free.

**Left, in order:**
1. When the run stops: if it stopped on our own `rpd: 500` guard and no server per-day 429 appears in `docs/quota.md`, raise the guard
   with `llm.main.rpd` and continue, to learn the real limit (log it). If the server's daily limit is hit, report exactly what
   completed. Quota resets at midnight Pacific (12:30 IST), so no reset before the deadline.
2. Judge: `python -m eval.judge --run-id mid --split dev --rpm 3 --system <s>`, in the order ours, b2, b1, a2, a3, a1, b0, so the most
   important answers are judged first if the token limit runs out. Ungraded answers are "pending", never wrong.
3. `python -m eval.report --run-id mid --split dev` writes `results/summary/mid_dev.{md,json}`. Ameya's instruction: if quota stops
   the run early, compare systems ONLY on the questions all of them completed, and state how many that was. The report step does this
   (`common_questions`, `restrict`), and also narrows judge-based numbers to questions judged for every system.
4. Write `docs/mid_submission_report.md`: Progress, Dataset, Baselines, Ablations, Results, Challenges, Mitigation, Timeline to 15 Nov.
   Real numbers only; "pending" for anything unfinished; one line explaining why for every result; label results preliminary.
   Must mention: gold not yet spot-checked (G1); judge not yet validated (G3); 43 of 176 questions opened before 2020; timeline
   fallback found no links (all 367 by keyword; issue-timeline fix pending at the split rebuild after G1); some questions are feature
   requests; 15 questions fail with import or attribute errors; `min_result` false rejection.
5. Commit everything. Fetch `origin/main`, then build update zips against it, per `docs/work_split.md`:
   `python scripts/make_bundles.py --member <m> --name <m>_update_1 --since origin/main`, with the report in Sunil's zip. Run the check that
   no raw results, `.env` or caches ship. Rehearse in a fresh clone of real `main`, in the order Sunil, Ameya, Aditya, Sourav, using each
   PUSH.md's own test command.
6. Tell Ameya the zips and the push order.
7. Judging the last 9 answers (A1 x2, B0 x7) runs in a background loop as Groq tokens refill (log `.cache/judge2.log`). When done:
   `python -m eval.report --run-id mid --split dev`, update the B0 and A1 rows in the report, and re-zip Sunil's and Sourav's files.

**Status 30 Oct, evening, after Ameya's review of the report:** members push now, in the order Sunil, Ameya, Aditya, Sourav. Final judge stays Groq
`openai/gpt-oss-120b`, no Mistral key (D-42). Report rewritten without first-person wording; B0 and A1 marked incomplete (judged 7/14 and 12/14) and left out of
every comparison. Step 7 above is cancelled: the report keeps those frozen numbers. The judge loop was stopped by choice at A1 14/14, B0 12/14; those later grades
are saved in `results/mid/judgements/` and not used in the report. Do not re-run `eval.report` into `results/summary/` until after the mid submission, or the saved
summary will stop matching the report. Quota plan is in report section 8: Groq is the tighter limit, about 122 questions in 10 days.
To do at P10: untestable lines (report section 7). To do at the G1 rebuild: feature-request filter (D-43), which removes 0 of 176 by label and 6 by issue type.

**Status 17:40 IST:** update zips built with `--since origin/main` (Sunil's also with `--also tests/llm/test_client.py`) and rehearsed on a fresh clone of
real `main` in push order: `main` is green after each merge; final state 248 unit (1 skipped, needs a local click tree) and 17 Docker tests pass; zips hold no
keys, caches, or raw results. Next after the deadline: resume the 6 remaining dev questions after 12:30 IST on 31 Oct, then P9.

**Status 17:35 IST:** report written (`docs/mid_submission_report.md`); 14 questions common; ours 7/14, B2 10/14 correct (p = 0.25).
P10 TODO found in runs: treat no-mutant lines as untestable, not non-causal (11 of 54 lines).

**Not in this round (pending):** P9 spot-check kit, G1, P10 pilot and prompt iteration, G2 lock, P11 test runs, G3 labels, P12, P13.

### 2026-11-06, handover setup on Sourav's machine
- Operator is now Sourav. Python 3.10.13, git 2.43.0, Docker server 29.5.0 (user in `docker` group): OK. Remote: OK.
- Fresh `.venv` from `requirements.txt`. Sandbox image `rtci-sandbox:py310` rebuilt.
- Tests: 248 unit passed, 1 skipped (needs a local click tree, as expected); 17 Docker tests passed.
- Keys: `GEMINI_API_KEY` present, live call OK. `GROQ_API_KEY` and `GITHUB_TOKEN` **missing** (blocks judging and any new
  mining; G0 not fully passed until they are added). `MISTRAL_API_KEY` not needed (D-42).
- Built `bundles/sunil_update_2.zip` (`docs/HANDOFF.md`, `docs/progress.md` + PUSH.md) against `origin/main` (`203be38`);
  scanned: no keys, no AI attribution. Sunil pushes it.
- Waiting on: the two missing keys, and human decisions H2 (G2 size, urgent), H3 (timeline fallback), H5 (finish `mid` run).

### 2026-11-07, pre-P9 fixes and P9 (Sourav's machine)
- `GROQ_API_KEY` added; live call to `openai/gpt-oss-120b` OK. `GITHUB_TOKEN` still missing: not blocking, since mining
  now runs from the cache without it (0 API calls).
- D-43 applied: feature-request filter in the mining funnel. 176 → 170 questions (click 146, marshmallow 24); the 6
  removed are exactly those measured on 30 Oct; the other 170 are byte-identical. 8 PRs logged as `feature_request`.
- D-44: a question once in dev never moves to test (`data/dev_history.txt`). A plain re-split would have moved 13 of the
  20 `mid` dev questions into test. Dev is now the old 19 plus `click-1821`; test 150, SHA-256 `8a9c8139…1eae` (not locked).
- D-45: seeded, library-interleaved run order in `eval/run.py`; `--qid-order` keeps the old order for resuming `mid`.
- P9: `annotation/sample.py` (34 of 170: click 29, marshmallow 5; sunil 9, ameya 9, aditya 8, sourav 8),
  `annotation/spotcheck.html`, `annotation/apply_spotcheck.py`, `docs/annotation_guide.md` (worked examples `click-1422`
  valid and `click-1096` invalid), explainer, D-46. Found while writing the guide: docstring-only edits count as gold lines.
- Tests: 269 unit passed, 1 skipped; the page is tested under node and rendered in headless Chrome.
- **G1 is open.** Members check their files; then: `python annotation/apply_spotcheck.py && python data/split.py &&
  python data/validate_questions.py`.

### 2026-11-07, human decisions (Sourav: "go with your recommendations")
- H2: aim to lock G2 around 9 Nov with about 70 test questions (final size from the pilot's quota plan).
- H3: no issue-timeline fallback; logged as a deviation and future work.
- H4: one round of prompt iteration in P10, equal for every system.
- H5: the `mid` dev run is not finished.
- P10 started while G1 is open: D-47 (untestable lines) committed; 272 unit tests and the Docker mutation tests pass.

### 2026-11-07, P10 pilot iteration 0
- Ran ours and B2 on the 20 dev questions (run id `pilot`, current prompts), judged with Groq. Real cost: Gemini 179
  requests (the cache replayed the rest), Groq 38 judgements.
- First result for ours exposed a regression from D-47: a claim whose draft had **no** citation skipped the search for
  the deciding line (the "nothing rejected" test was trivially true). B2 was unaffected. Fixed with a regression test
  (274 unit tests pass). The affected answers, judgements, trace and summary were moved to run id `pilot_bug_d47`
  (kept for the record, not used). Ours is being re-run under `pilot`.
- B2, iteration 0: 12/20 correct, 35% causally supported, fix-location recall 55%, 10.7 requests/question,
  140k tokens/question, never flagged an answer.
- Corrected pilot, iteration 0 (ours re-run after the fix): ours 11/20 correct (25% causally supported, recall 45%,
  14.1 requests and 175k tokens per question); B2 12/20 (35%, 55%, 10.7, 140k). Paired: ours-only 0, B2-only 1
  (`click-1193`): no detectable difference. Neither system ever flags an answer. Ours still leaves 11 of 59 claims
  uncited; 11 citations were untestable. Quota used on 6 Nov (Pacific): Gemini 232, Groq 45 judgements.
- P8 gap closed (G3 tooling): `eval/human_export.py` rewritten (sample by question, one file per labeller, key kept
  apart), new `eval/label.html`, `eval/kappa.py` now has the agreement report and the per-kind kappa rule (D-48);
  dry run on pilot answers rendered in Chrome. New `scripts/audit.py` (one-command rule check, 10 checks pass).
- Known data glitch: for 2 questions (`click-3099`, `click-1739`) the failure message of a test-module import error lost
  its first letters ("mportError", "tError"). Cosmetic; not re-validated. Both are "new API missing" questions that the
  spot check is likely to remove.

### 2026-11-07, prompt iteration 1 and P12 code (Sourav's machine, while G1 is with the team)
- Spot-check kits sent to the team (Sourav). Waiting for the four `_done.jsonl` files.
- Prompt iteration 1 (the one round, H4): shared system-prompt rules (frozen behaviour; where the deciding line is;
  every behavioural claim cites a line), shared schema text, and "should cite" -> "must cite" in each system's task
  prompt. Logged in `docs/prompt_log.md`. Running on dev as run id `pilot_it1` (ours + B2); it will stop on the Gemini
  quota near 13:30 IST and resume after the reset.
- `analysis/make_all.py` built and tested (D-49): H1-H3 verdicts from the pre-registered rules, kappa-rule view,
  per-category/library, RQ2, taxonomy, cases, ablation predictions, three figures. Tried on the `mid` run.
- 288 unit tests pass; `scripts/audit.py --quick`: 10 of 10 checks pass.

## 2026-11-07 log (afternoon)

- Prompt iteration 1 complete on dev; kept. D-51 (ours: revised claims cite; uncited claims keep the last proposed line),
  D-52 (numbered scratch directories, so replays hit the cache), D-53 (judge on four Groq keys; the paid plan was not
  in effect). Pilot report written. Four Gemini and four Groq keys present and tested.
- G2 locked: all 150 test questions, SHA-256 `8a9c8139…eae`. Spot check applies later as an exclusion.
- P11 started: `python scripts/run_all.py --by-question --limit 150 --systems ours b2 b1 a2 a3 a1 --split test --allow-test --run-id main` (log `.cache/run_main.log`). `eval/run.py` now also refuses test unless PREREGISTRATION.md is LOCKED.

## 2026-11-07 to 2026-11-10: P11 must-have tier
- Ours, B2, B1, A1, A2, A3 on all 150 test questions; all 900 answers judged by `openai/gpt-oss-120b`. Summary: `results/summary/main_test.md`.
- Ran over three quota days (Gemini resets 13:30 IST). Failures: one hung request (no timeout, fixed in D-54); a few answers failed on Google 503 overload or local DNS drops and were re-run on the next resume (failed questions write no result file).

## 2026-11-10: P12 first pass, G3 files
- `python -m analysis.make_all --run-id main --split test`: H1 not supported (ours 40.0% vs B2 50.7%, CI [-20.0, -1.3]); H2 and H3 inconclusive. Draft `docs/results.md`.
- G3 export: 12 questions x 6 systems = 72 answers, 204 citations, in `results/main/human/` (gitignored). The sample overlaps one spot-check question each of Sourav (click-1969) and Sunil (click-2332), so labellers must finish their spot check before opening the labelling file.

## 2026-11-10 to 2026-11-11: should-have runs
- Tool-use and safety metrics from traces (`analysis/make_all.py`); adversarial set of 15 items (D-55), run `adv`: no planted action was executed by any system.
- B0 (closed book) on all 150 test questions, judged: 23.3% correct, 4.7% causally supported.
- A10 (retrieval none / oracle) with ours and B2 on the first 50 test questions, run `sub50`: correctness unchanged; no retrieval lowers fix-location recall (60.0% to 46.0%, p = 0.016). One oracle crash on a file the fix created was fixed in `eval/run.py` and the question re-run.
- Waiting on: G1 spot-check files from all 4 members; the names of the 2 G3 labellers.

## 2026-11-11: G1 applied
- Spot-check verdicts from all four members (34 questions; notes grammar-edited with an AI tool afterwards, verdicts unchanged). 8 invalid (23.5%), all on "the failing test captures the behaviour"; 7 are feature requests. Removed from `data/questions_all.jsonl` (170 to 162), logged in `data/dropped.jsonl`.
- 5 test questions excluded at analysis time (split not rebuilt; test SHA unchanged): results now on 145. H1 still not supported (40.0% vs 49.7%, CI [-19.3, -0.7], McNemar p = 0.059); H2, H3 inconclusive. `docs/results.md`, `docs/viva_prep.md` and the pilot report updated.
- Waiting on: the names of the 2 G3 labellers.

## 2026-11-11: G3 applied
- Labels from Aditya (`labeller1`) and Sourav (`labeller2`), 72 answers and 204 citations each, labelled separately; an AI tool only formatted the files (disclosed in PREREGISTRATION.md, Deviations).
- Kappa: human-human 0.742 (correctness) and 0.902 (citations); judge vs consensus 0.363 and 0.322, below 0.6, so the primary comparison uses human labels (D-48). On the 12 labelled questions: B2 41.7% causally supported, ours 25.0%; H3 not supported (ours 30.6% vs A2 44.1%, CI [-28.6, -1.0]).
- Fixed: RQ2 never matched human labels because answer paths carry `src/` and mutation paths do not (`analysis/make_all.py`, test added). Against humans, `specific` has kappa -0.098 on 52 lines.

## 2026-11-11: final report, bundles, presentation demo
- `docs/final_report.md` and `.pdf` (TA's required sections), README reproduction steps. Final bundles `<member>_final.zip`, checked by applying them in push order on top of GitHub `main` (tests pass after each; final tree identical).
- Presentation demo: `streamlit run demo/app.py` (D-56): the idea, a live probe and mutation check on toylib, results charts, and one question side by side. No LLM calls. `analysis.json` now also holds the per-system summary.

## 2026-11-12: exploratory multi-agent extension (E1-E6)
- [x] Pre-registered the extension (PREREGISTRATION.md, "Exploratory extension") before any test run: configs E0-E6,
      the 47 `sub50` test questions, localization / verification / retrieval metrics, six predictions.
- [x] Built: `codegraph/` (call graph, dependences, slices, spectrum ranking), `retrieval/hybrid.py` (BM25 + dense +
      RRF + cross-encoder + graph expansion), `experiments/` (three-way verdicts, pairs, information gain, patch
      validation), `multiagent/` (five roles, typed hand-offs), `mcp_server/` (optional MCP transport),
      `eval/localization.py`, `analysis/extension.py`, `analysis/retrieval_study.py`. DECISIONS D-57 to D-63.
- [x] Tests: toylib end to end with a scripted LLM for E1 and E5, the MCP round trip, the planted-line verdicts,
      pairs on the redundant guards, information-gain maths, localization metrics by hand.
- [x] Prompts developed on dev only (E1 on dev), then frozen: hashes in `results/summary/extension_prompt_hashes.txt`.
- [x] Retrieval study on 142 test questions (3 have no relevant chunk); E1-E6 on the 47 test questions, unattended
      overnight (sequential after an out-of-memory stop at 02:47 with two systems in parallel); judge (gpt-oss-120b).
- [x] Fixed a crash in `CodeGraph.static_slice` on decorator lines (click-3700, click-1739 in E3-E6), added a
      regression test, re-ran those 2 questions; no prompt, budget or threshold changed. All six systems 47/47.
- [x] Tables (`results/summary/extension.md`, `retrieval_study.md`, `docs/extension_results.md`), correctness
      comparisons and a ranking diagnosis added to `analysis/extension.py`; report §8 written, Limitations and
      Conclusions renumbered to §9 and §10, abstract, contributions and references 22-31 updated.
- Outcome: no configuration beats E0 or B2 on localization; RRF retrieval helps (+7.7 hit@5, p = 0.035); roles halve
  requests; E3 lowers Top-3 because rejected fix lines sink in a longer ranking; no pair accepted; E5 saves mutant
  runs; E6 identical to E5. Predictions: 1 partly, 2 partly, 3 refuted, 4 not supported, 5 and 6 supported.
