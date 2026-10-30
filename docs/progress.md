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
- [ ] P9 Spot-check kit (+ update bundles)
- [ ] G1 Human gate: spot check
- [ ] P10 Pilot
- [ ] G2 Lock
- [ ] P11 Main runs
- [ ] G3 Human gate: labels
- [ ] P12 Analysis
- [ ] P13 Final bundles

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
