# Viva prep

**Status: 2026-11-11.** The results below are after G1 (the spot check: 145 of the 150 test questions remain) and G3
(the human labels: Aditya and Sourav, 72 answers). Ownership follows `docs/work_split.md` and `bundles/ownership.yaml`.

How to use this file:

- Everyone learns **Part A**: the whole project in five minutes.
- Then each member learns **their own section in Part B**, and reads the explainers listed there end to end.
- Each explainer ends with five viva questions and model answers. This file adds the questions that come from the
  final results, and says where in the code each answer lives.

---

## Part A. What every member must be able to say

### A1. The project in one minute

Developers ask how a library behaves. AI assistants often repeat the documentation, even when the code does something
else, and they cite lines that look related but don't decide the behaviour. We built an agent that checks its own
answers in two ways:

1. **Run it.** It splits the draft answer into claims and tests each claim with a small generated probe. The probe
   runs against the library frozen just before the issue was fixed, inside a Docker sandbox with no network.
2. **Flip the switch.** It accepts a cited line only if changing that line in a throw-away copy (a *mutant*) changes
   the claim's outcome and leaves the control probes unchanged.

A failed check becomes the agent's next goal.

We compared it with a ReAct agent that had **the same tools, model and limits** (B2), and with direct RAG (B1). We
also ran ablations that switch off one part each:

| Ablation | What is switched off |
|---|---|
| A1 | Execution: claims are checked by reading only |
| A2 | Mutation: no citation check |
| A3 | Re-investigation: failures are only flagged |

### A2. The data, in one minute

- **Source.** 170 real GitHub issues from click and marshmallow, each fixed by a merged pull request.
- **What a system sees.** Only the issue text, plus the code at the commit before the fix.
- **The answer key, built by code with no AI involved** (the SWE-bench recipe):
  - the PR's own new test, run on the old code, shows the old behaviour;
  - the lines the fix changed are the gold evidence.
- **Split.** 20 dev questions (for prompt tuning) and 150 test questions, locked with a SHA-256 hash before any test run.
- **Spot check.** We four checked a random 20% (34 questions). We marked 8 invalid (23.5%), nearly all feature requests
  whose test only shows the feature was missing. 5 were test questions, so results are on 145.

### A3. The result

| | B2 (ReAct) | Ours |
|---|---|---|
| Correct | 68.3% | 61.4% |
| Causally supported (primary) | **49.7%** | 40.0% |
| Confident errors | 46 | 43 |

For scale: B0 (question only, no code) is 23.4% correct, and B1 (one call with retrieved code) is 37.9%.

- **H1 is not supported.** B2 beats ours by 9.7 points, with 95% bootstrap CI [−19.3, −0.7] (McNemar p = 0.059).
- **The judge failed validation.** It agreed with our two human labellers only fairly (kappa 0.36 on correctness,
  0.32 on citations; the humans agreed with each other at 0.74 and 0.90). By our pre-registered rule, the primary
  comparison therefore uses the human labels on 12 questions: B2 41.7% causally supported, ours 25.0%. Ours was not
  better than B2 on any of the 12. The judge is lenient on citations, but its differences between systems point the
  same way.
- **H3 is not supported (human labels).** Ours' citations were causal 30.6% of the time, A2's (no mutation) 44.1%,
  CI [−28.6, −1.0]. The mutation check made citations worse.
- **H2 is inconclusive.**
- **Ours against its ablations.** Ours, A1, A2 and A3 are statistically indistinguishable on correctness.
  - A3 (flag only) has significantly fewer confident errors than ours: 20.0% against 29.7%, p = 0.004.
- **Why (RQ2).** The mutation check agrees with the developers' fix lines no better than chance (kappa ≈ 0). The rule
  the agent uses rejects 76% of the fix lines it checks. So "flip the switch" often discarded a correct citation.
  Against the human labels, `specific` is the worst of the three rules (kappa −0.10), though we predicted it would be
  the best.
- **Safety.** No unsafe action was executed. 6.0% of ours' probes were blocked by the policy, most of them trying to
  create files outside `/tmp`.
- **Full numbers:** `docs/results.md`, and `results/summary/analysis_main_test/report.md`.

### A4. Questions anyone may be asked

1. **"Your method lost. Is the project a failure?"**
   No. The hypothesis was pre-registered and the comparison was fair: the same model, tools, limits and starting
   material. 145 questions are enough to tell: ours did not beat B2. We can say *why* it lost, from the ablations and RQ2. A clear
   negative result with a mechanism is a research result. (`PREREGISTRATION.md`, `docs/results.md` §3–5)

2. **"How do you know you didn't tune on the test set?"**
   - Prompts were iterated once, on the 20 dev questions only, with equal effort for every system
     (`docs/prompt_log.md`).
   - The test file's SHA-256 and every prompt's hash were written into `PREREGISTRATION.md` before the first test
     question ran.
   - `eval/run.py` refuses to run on test unless the file says LOCKED.

3. **"Why should we trust an LLM judge?"**
   - It doesn't see which system wrote an answer.
   - It is a different model family from the systems (gpt-oss-120b on Groq, against Gemini).
   - It was validated against two humans at G3. Its kappa was 0.36 and 0.32, below 0.6, so the human labels decide the primary comparison
     (D-48).
   - Citation causality also counts the fix lines, which no model chose.

4. **"Why not just fine-tune?"**
   The research question is whether a better *procedure* helps the *same* model. Changing the model would mix the two
   effects. Fine-tuning was a stretch goal in the approved proposal, and we use the other four capabilities.

5. **"What would you do next?"**
   - Accept a line if *any* behavioural flip happens (the `behavioural` rule), and compare that with humans at G3.
   - Flag failures instead of re-investigating them, as A3 does.
   - Try a stronger model that writes fewer broken probes.
   - Test more libraries.

---

## Part B. Per member

### Sunil Kumar: foundation, data mining, retrieval, tools, pipeline scripts

**Read:** `docs/explainers/data_mining.md`, `retrieval.md`, `tools.md`, `annotation.md`, `foundation.md`.
**Demo:** `python -m pytest -q tests/retrieval tests/tools`, then open `annotation/spotcheck.html` with a spot-check file.

| Likely question | Short answer | Where |
|---|---|---|
| How do you find issue–fix pairs? | List merged PRs since 2020. Link a PR to an issue through "fixes #n" in its title or body, checking that #n is an issue and not a PR. Keep the PR only if it changes source *and* tests. Drop bots, feature requests and refactors touching more than 10 files | `data/mining/fix_pairs.py` (`linked_issue_numbers`, `classify_files`, `is_feature_request`) |
| Why the commit *before* the fix? | Gold is the behaviour the asker saw. This is SWE-bench's convention, checked as an ancestor of the merge | `data/freeze.py` |
| Why BM25 and not embeddings? | Cheap, deterministic, and explainable. Code and docs get separate indexes, and the tokenizer splits snake_case and camelCase. Embeddings are a logged deviation | `retrieval/index.py` (`tokenize`, `RepoIndex.starting_material`) |
| How can no system leak the answer key? | `Workspace` has `__slots__` and reads only the library and commit from the question; a test proves gold fields can't attach | `tools/workspace.py`, `tests/tools/test_tools.py` |
| What happens on a bad tool argument? | Pydantic validates it; the error text goes back to the model and is counted as invalid. Ours made 0 invalid calls out of 3,734 | `tools/registry.py`, `docs/results.md` §6a |
| How was the spot check sampled? | A seeded 20% sample, stratified by library, split evenly across the four of us. Invalid questions are excluded at analysis time, because the test set was locked first. Each of us made our own verdicts; we used an AI tool only to fix the grammar of our notes, and say so in `docs/results.md` §1 | `annotation/sample.py`, `annotation/apply_spotcheck.py`, `analysis/make_all.py` (`spot_check_exclusions`) |
| Extension: what does the code graph give? | Functions, a name-resolved call graph, and per-function data and control dependences from the AST, all in NetworkX. Backward slices and Ochiai spectra (claim vs control probes) rank suspicious lines. It made E3 rank about 8 lines; rejected fix lines then sank below inconclusive ones, so Top-3 fell 55.3% → 36.2% | `codegraph/graph.py` (`static_slice`, `connected`), `codegraph/rank.py`, report §8.3 |
| Extension: did hybrid retrieval help? | Fusing BM25 and dense retrieval with RRF did: hit@5 64.1% → 71.8%, p = 0.035, on 142 questions. Adding the cross-encoder reranker hurt (−11.3 points vs RRF); it was pre-registered for E2–E6, so we kept it rather than tune on test | `retrieval/hybrid.py`, `analysis/retrieval_study.py` |

### Ameya Purohit: LLM layer, the agent, the pilot

**Read:** `docs/explainers/llm_client.md`, `agent.md`, plus `docs/pilot_report.md` and `docs/prompt_log.md`.
**Demo:** `python -m pytest -q tests/agent tests/llm`; walk through one trace in `results/traces/main_ours.jsonl`.

| Likely question | Short answer | Where |
|---|---|---|
| Why no LangChain? | We must explain every line, and the control flow *is* the research. The loop is one short file | `agent/toolloop.py` |
| What exactly does ours do that B2 doesn't? | It always drafts claims, probes each one, mutation-tests each citation, and re-investigates failures. B2 decides freely | `agent/loop.py` (`answer`, `_write_and_run`, `_handle_refutations`, `_check_citations`, `_find_causal_line`) |
| How are thought signatures kept? | The raw Gemini content is stored in the message's `raw` field and replayed unchanged; the smoke test proves it across two turns | `llm/providers/gemini.py`, `scripts/smoke_llm.py` |
| Why does the cache matter? | Temperature 0 plus a SHA-256 key over the request means re-runs are free, and A1–A3 reuse ours' shared prefix (A3 used 0.7 fresh calls per question) | `llm/cache.py` (`cache_key`) |
| How did four keys work without breaking fairness? | Same model and settings on every key. The cache key excludes the API key. Each key has its own daily counter, and the client moves to the next key when one is used up | `llm/client.py` (around line 200), D-50, D-53 |
| What does D-51 change? | A revised claim must cite a line; if no proposed line passes, the last one is kept, marked not causal. It was found on dev, applied to ours only, and disclosed | `agent/loop.py` (`_find_causal_line`), `PREREGISTRATION.md` Deviations |
| Why did re-investigation hurt (A3 vs ours)? | After a failed check, revising turned flagged answers into confident ones without making them right more often | `docs/results.md` §4 |
| Extension: what are the five roles? | Bug Investigator, Probe Engineer, Code Analyst (LLM), Experiment Engineer (code), Causal Verifier (LLM), in a fixed order and passing typed pydantic objects. Budget 12 requests. They halved requests and cut tokens to a sixth, but did not localize better than E0 or B2 | `multiagent/orchestrator.py`, `multiagent/schemas.py`, report §8 |

### Aditya Narayan Dwivedi: sandbox, gold validation, baselines, extra datasets

**Read:** `docs/explainers/sandbox.md`, `gold_validation.md`, `baselines.md`.
**Demo:** `python -m pytest -q -m docker tests/sandbox` (Docker must be running), which shows the network blocked and
`os.system` refused.

| Likely question | Short answer | Where |
|---|---|---|
| What stops a probe doing damage? | The Docker container: no network, read-only file system outside `/tmp`, 1 CPU, 1 GB, 256 processes, non-root. The AST policy is a second layer only | `sandbox/session.py`, `sandbox/policy.py` (`check`) |
| What did the policy block on test? | 41 of ours' 633 probes, mostly directory or file writes outside `/tmp` and a few `subprocess`/`shutil` imports. None ran | `docs/results.md` §6a |
| How is a question validated? | Apply only the PR's test changes and run them: at least one must fail. Then add the source fix: those must pass. The failure message becomes `observed_before` | `data/validate_pairs.py` (`decide`, `validate_one`) |
| How is gold built without AI? | From the diff: changed or deleted lines in the old file, or for pure insertions the line above (`anchor_for_insert`); whitespace and comments ignored. The answer text is a template | `data/build_gold.py` (`evidence_from_hunks`, `gold_answer`) |
| Is B2 really given the same chances? | Same tool registry including `run_probe` and `mutate_and_run`, same 8 steps, 12 probe runs and 25 requests, and the same starting material | `baselines/b2_react.py`, `config/default.yaml` |
| How does the adversarial set work? | Instructions are planted in the issue text or as a trailing comment on the fix line (the AST is unchanged, so behaviour is identical). Each asks for a canary token, so compliance is a string match | `data/adversarial.py`, D-55 |
| Extension: why MCP, and did it change anything? | It exposes the graph, probe, mutation and patch tools as a standard local server (11 tools over stdio). E6 gave identical rankings and answers to E5 on all 47 questions, at no measurable time cost | `mcp_server/server.py`, `mcp_server/client.py`, D-62 |

### Sourav Nath: mutation, evaluation, judging, analysis

**Read:** `docs/explainers/mutation.md`, `evaluation.md`, `analysis.md`, plus `docs/results.md`.
**Demo:** `python -m pytest -q tests/mutation`, which runs toylib: line 88 is accepted, line 12 is rejected, and
`return result` is rejected by specificity. Then `python -m analysis.make_all --run-id main --split test`.

| Likely question | Short answer | Where |
|---|---|---|
| What makes a line "causal"? | Some mutant of it changes the claim probe's outcome while the control probes keep theirs (`specific`). Breakage such as a NameError doesn't count | `tools/mutate.py` (`classify`, `is_breakage`, `verdicts`) |
| Why libcst, not `ast.unparse`? | libcst regenerates the file byte-for-byte apart from the mutated node, so line numbers and comments stay put | `tools/mutate.py` (`generate_mutants`) |
| Why did mutation fail as a measure? | Its kappa with the fix lines is about 0 under all three rules. The likely causes are equivalent mutants, redundant code and probe or control design. Against the human labels it is no better: `specific` has kappa −0.10 on 52 lines | `docs/results.md` §5; `analysis/make_all.py` (`rq2`) |
| What is the primary metric? | An answer is correct *and* every claim has at least one causal citation: inside the fix ranges, or labelled causal by the judge or a human. Partial counts as wrong (D-41) | `eval/metrics.py` (`score_question`, `citation_flags`) |
| Which statistics, and why? | McNemar's exact test, because the outcomes are paired yes/no on the same questions. A paired bootstrap with 10,000 resamples for the CIs. Both are tested against known values | `eval/stats.py`, `tests/eval/` |
| What is the kappa rule? | Cohen's kappa between the judge and the human consensus; below 0.6, the human labels decide the primary comparison. Ours: 0.36 and 0.32, so the human labels decide | `eval/kappa.py`, D-48 |
| Can one command rebuild all results? | Yes: `analysis/make_all.py` regenerates every table and figure from stored files, and nothing is typed in by hand | `analysis/make_all.py` |
| Extension: what is new in the experiment engine? | Three verdicts (accepted, inconclusive, rejected); pairs of dependent lines (0 of 95 accepted); expected-information-gain order with early stopping, which cut mutant runs 15.2 → 11.4 per question at the same Top-3 | `experiments/engine.py`, `experiments/selection.py`, `eval/localization.py`, `analysis/extension.py` |

---

## Part C. Before the viva (checklist)

- [ ] Each member has read their explainers and can run their demo command on their own laptop.
- [ ] Everyone can give A1–A3 from memory, and the H1 numbers.
- [ ] Each member has pushed their final bundle from their own GitHub account (`PUSH.md` in their zip).
- [x] Numbers here are updated after G1.
- [x] Numbers here are updated after G3.
