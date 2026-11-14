# Design decisions

One entry per non-trivial choice (CLAUDE.md §8). Every member should be able
to explain every entry in the viva. Entries are never deleted; a reversed
decision gets a new entry that points back to the old one.

---

## D-01 Main model: Gemini `gemini-3.1-flash-lite` on the free tier  (2026-10-27, P0, Ameya)
Decision: every system (ours, baselines, ablations) uses `gemini-3.1-flash-lite` through the free Gemini API, temperature 0.
Alternatives considered: (1) a Gemini Flash model; (2) a paid mid-tier model as in the proposal's cost plan (USD 125-500).
Why: requests per day, not tokens, are our binding constraint. A September 2026 measurement found 15 requests/minute and 500/day for flash-lite against 5/minute and 20/day for the Flash models (another source lists 30/minute and 1,500/day). 20 requests a day cannot run even the pilot. The team also has experience with it. One model for all systems keeps the comparison fair (§2.3): RQ1 asks whether the *procedure* helps the same model.
How we'd defend it in the viva: "A weaker model makes our test harder, not easier: if the checks help a small model, that is the setting where developers would use a cheap assistant. The baselines use the identical model, so the comparison is unaffected."
Revisit if: measured free limits make 50 test questions unaffordable by 15 Nov (gate G2 then offers a smaller set or enabling billing).

## D-02 Judge: Groq `llama-3.1-8b-instant` until P8, a stronger judge after  (2026-10-27, P0, Sourav)
Decision: until P8 the judge is Groq's `llama-3.1-8b-instant` (smoke tests and toylib only). At P8, before the G2 lock, the final judge is chosen: Mistral `mistral-large-latest` if a key is present, else Groq `openai/gpt-oss-120b`, throttled over several days. One judge per experiment, never mixed.
Alternatives considered: (1) Gemini as judge (same family as the systems, so it may favour their style); (2) only human labels (too slow for every answer).
Why: a judge from a different model family avoids self-preference. The 8B model has the most generous free limits (about 30/min, 14,400/day) but is too weak for final grading; the final judge is validated against human labels with the kappa rule (§6.11).
How we'd defend it in the viva: "We never trust the judge blindly: if human-judge kappa is below 0.6, the primary comparison uses human labels."
Revisit if: neither strong judge is reachable on the free tier at P8.

## D-03 Native `google-genai` SDK, not the OpenAI-compatible endpoint  (2026-10-27, P0, Ameya)
Decision: talk to Gemini with the native `google-genai` SDK and store the raw assistant `Content` (serialized with `model_dump(mode="json", exclude_none=True)`) in our neutral message history.
Alternatives considered: (1) Gemini's OpenAI-compatible endpoint, so one SDK serves all providers; (2) raw REST calls.
Why: Gemini 3 models attach *thought signatures* to function-call parts that must be sent back unchanged on later turns. The native SDK keeps them when we append `response.candidates[0].content`; how the compatible endpoint handles them is not clearly documented. A lost signature breaks multi-turn tool calling, which is the core of every agent here.
How we'd defend it in the viva: "Our smoke test runs a two-turn function-calling round trip and checks that it works, so this is verified, not assumed."
Revisit if: the compatible endpoint documents signature handling.

## D-04 One config file with deep-merged overrides  (2026-10-27, P0, Sunil)
Decision: `config/default.yaml` holds every setting (model IDs included, nowhere else). A system or ablation is a small override deep-merged onto it; lists are replaced, mappings merged. Each result stores a hash of its final config.
Alternatives considered: (1) a config file per system; (2) command-line flags only.
Why: fairness (§2.3) is easiest to demonstrate when two systems' configs can be diffed key by key (`core.config.diff`) and the only differences are control-logic flags.
How we'd defend it in the viva: "Show the diff of B2 and ours: only the control-logic keys differ."
Revisit if: overrides grow so large that the default no longer describes any real run.

## D-05 JSON Lines for datasets, results and traces  (2026-10-27, P0, Sunil)
Decision: one JSON record per line; writes of whole files are atomic (temp file then rename); appends flush per record.
Alternatives considered: (1) one big JSON file per dataset; (2) SQLite for everything.
Why: records are appended during long resumable runs; a crash loses at most one record. JSONL diffs line by line in git and streams without loading whole files. SQLite is used only where keyed lookups matter (the LLM cache).
How we'd defend it in the viva: "Resumability is a requirement under a daily quota; JSONL makes it trivial."
Revisit if: files grow beyond what line-by-line reads handle comfortably.

## D-06 Code reaches GitHub as four ownership bundles  (2026-10-27, P0, Sunil)
Decision: `bundles/ownership.yaml` maps glob rules to owners (first match wins, specific rules first); `scripts/make_bundles.py` zips each member's files with a `PUSH.md`. Bundles are merged in the order Sunil, Ameya, Aditya, Sourav, and a bundle imports at module level only from itself or earlier bundles.
Alternatives considered: (1) one member pushes everything (fails the course's per-member check); (2) everyone pushes from the shared folder (tangled history, no clear ownership).
Why: each member pushes code they own and have studied (through the explainers), and every prefix of the push order still passes its tests, so `main` is never broken.
How we'd defend it in the viva: each member explains their own bundle.
Revisit if: a cross-bundle dependency cannot be made lazy.

## D-07 Secret scan matches full key shapes, not a bare prefix  (2026-10-27, P0, Sunil)
Decision: CI fails if any file matches the full shape of a Google key (`AIza` + 35 characters), a Groq key, or a GitHub token.
Alternatives considered: (1) fail on the literal prefix `AIza` anywhere, as first specified; (2) a third-party scanner such as gitleaks.
Why: `CLAUDE.md` itself mentions the prefix in prose, so a literal-prefix check would fail on our own spec. A full-shape regex catches every real key with no false positive on documentation, and needs no extra tool.
How we'd defend it in the viva: "A real Google key is always `AIza` followed by 35 URL-safe characters; we match exactly that."
Revisit if: a provider changes its key format.

## D-09 Development judge changed to Groq `openai/gpt-oss-20b`  (2026-10-28, G0, Sourav)
Decision: replaces `llama-3.1-8b-instant` (D-02) as the judge for P0-P7. The final-judge choice at P8 is unchanged.
Alternatives considered: (1) `qwen/qwen3.8-27b` on Groq (also a different family, likely tighter free limits); (2) `openai/gpt-oss-120b` from the start (strongest, but about 200K tokens/day would be eaten by development runs).
Why: at G0 Groq returned 404 for `llama-3.1-8b-instant` and no longer lists it. `gpt-oss-20b` is small and fast, from a different family than Gemini, and from the same family as the fallback final judge, so the judge prompt carries over. Chosen by Ameya at G0.
How we'd defend it in the viva: "The development judge only grades smoke tests and toylib answers; no reported result uses it. The final judge is validated against human labels."
Revisit if: Groq retires it too, or its free limits block P8 development.

## D-10 `requirements.txt` with minimum versions; the venv is never committed  (2026-10-28, P0, Sunil)
Decision: dependencies are listed in `requirements.txt` (identical to `pyproject.toml`, enforced by a test), and members, CI and the README install with `pip install -r requirements.txt`. `.venv/` stays git-ignored; the README gives step-by-step replication.
Alternatives considered: (1) exact `==` pins from the build machine (its numpy 2.5 / scipy 1.18 / matplotlib 3.11 need Python 3.11+, but CI and the sandbox use 3.10); (2) committing the venv (hundreds of MB, machine-specific, breaks on another OS).
Why: a requirements file is the standard, small, portable way to recreate an environment. Minimum versions keep one file valid from Python 3.10 up; the exact versions actually used are logged with every run, which is what reproducibility of results needs.
How we'd defend it in the viva: "Results record the exact library versions they ran with; requirements.txt only has to recreate a working environment."
Revisit if: a dependency release breaks us; then add an upper bound or a lock file.

## D-08 Tests run from the repo root without installing the package  (2026-10-27, P0, Sunil)
Decision: pytest uses `pythonpath = ["."]` and `--import-mode=importlib`; tests live in `tests/<area>/` with no `__init__.py`.
Alternatives considered: (1) a `src/` layout installed with `pip install -e .`; (2) `__init__.py` in every test folder.
Why: a member's clone may contain only some bundles; importing from the root works with any subset. `importlib` mode lets two areas both have e.g. `test_cache.py` without name clashes.
How we'd defend it in the viva: "Every prefix of the push order is tested in a temp checkout (`check_bundle_order.py`)."
Revisit if: we need to publish the package.

## D-11 Neutral message history with provider-tagged raw content  (2026-10-28, P1, Ameya)
Decision: agents keep histories of neutral `Message`s (system/user/assistant/tool). An assistant message may carry `raw`, the provider-native content, tagged with `raw_provider`; a provider replays `raw` only if it produced it, else rebuilds from the neutral fields.
Alternatives considered: (1) store histories in Gemini's native format everywhere (ties every baseline and the judge to one SDK); (2) neutral format only, dropping provider content (loses Gemini thought signatures, breaking multi-turn tool calling).
Why: one history format for all systems (§2.3), while Gemini still gets its thought signatures back byte-exact. The live smoke test shows a signature on turn 1 and a correct turn-2 answer after replay.
How we'd defend it in the viva: "The judge (Groq) never sees Gemini's raw content because the provider tag doesn't match."
Revisit if: we add a provider with its own replay requirement.

## D-12 Cache key and daily request counter in one SQLite file  (2026-10-28, P1, Ameya)
Decision: the cache key is the SHA-256 of canonical JSON of (provider, model, messages including raw content, tools, params). The same SQLite file keeps a per-day count of real requests per model.
Alternatives considered: (1) key on the last user message only (would wrongly reuse replies across different histories); (2) a JSON file per reply (slow, many files, no atomic counter).
Why: any change to prompt, history, tools or settings must miss the cache, and temperature 0 makes identical requests safe to reuse. Keeping the counter next to the cache means a resumed run knows how much of today's quota is already spent.
How we'd defend it in the viva: "Ablations A2/A3 share the full agent's prefix, so their first calls are cache hits that cost no quota."
Revisit if: provider non-determinism at temperature 0 matters for repeat runs; repeat runs then use a run-specific cache.

## D-13 Pacing, retries and the daily stop  (2026-10-28, P1, Ameya)
Decision: requests are spaced at least 60/rpm seconds apart. 429s and 5xx errors are retried with exponential backoff (base 2 s, cap 90 s) and jitter in [0.5, 1.5), or the server's suggested delay plus up to 1 s. A per-day 429, or reaching the configured `rpd` for today (counted in Pacific time, when Gemini's free quota resets), raises `QuotaExhausted` without retrying. Every quota a 429 names is appended to `docs/quota.md`.
Alternatives considered: (1) a sliding-window rate limiter (more precise, harder to explain); (2) the SDKs' built-in retries (different per provider, which would break the shared-plumbing rule; Groq's are switched off with `max_retries=0`).
Why: requests per day are the binding constraint, so a batch run must stop cleanly and resume rather than burn retries. A fixed interval is easy to reason about and never exceeds the per-minute limit.
How we'd defend it in the viva: unit tests cover the cache hit, the retry path with a server delay, giving up, the per-day stop and the day reset.
Revisit if: the measured limits in `docs/quota.md` show the interval is needlessly slow.

## D-14 Traces record inputs and outputs but not raw provider content  (2026-10-28, P1, Ameya)
Decision: each call's trace record has the neutral input messages, the output text and tool calls, token counts, attempts, latency, whether it was a cache hit, and the cache key. Raw provider content is left out; it stays in the cache under that key.
Alternatives considered: (1) log everything, raw included (traces become unreadable base64 blobs); (2) log only token counts (not enough for the failure taxonomy and qualitative examples).
Why: traces are research data that humans read; the cache key links each record back to the exact raw reply when needed.
How we'd defend it in the viva: "No key value can enter a trace: SDK clients receive keys from the environment and nothing in the trace path touches them; we also scan traces for key values."
Revisit if: trace files grow too large to keep.

## D-15 The runner calls `observe()` and `test_claim()` directly, not through pytest  (2026-10-28, P2, Aditya)
Decision: a probe is a file with `observe()` (returns or raises the observed value) and `test_claim()` (asserts the claim). `sandbox/runner.py` imports it and calls both itself; the outcome is `{"kind":"return","repr"}` or `{"kind":"raise","type","msg","innermost_frame"}`, the status is pass / fail (AssertionError) / error.
Alternatives considered: (1) run each probe as a pytest test (as proposal §6.2 describes); (2) compare stdout of a script.
Why: deterministic, fast (no collection, plugins or config files of the studied repo interfering) and simple to explain. Separating *what happened* (observe) from *whether the claim holds* (test_claim) is what the mutation check needs: it compares observed outcomes, not just pass/fail. pytest is still used for the repo's own tests (`kind: "pytest"` jobs).
How we'd defend it in the viva: "A mutant that changes a return value from 5 to 6 flips the outcome even if a loosely written assertion would still pass; we compare outcomes, so we see it."
Revisit if: probes need pytest fixtures (e.g. `tmp_path`, `capsys`); a probe can still use `click.testing.CliRunner` and plain `/tmp` files.

## D-16 Metadata shim for libraries imported from source  (2026-10-28, P2, Aditya)
Decision: before running a job, the runner writes `<meta_dir>/<dist>-<version>.dist-info/METADATA` (Metadata-Version 2.1, Name, Version) and puts `<meta_dir>` on `sys.path`. The version is read on the host from `__version__`, `pyproject.toml`, `setup.cfg` or `setup.py` of the frozen tree.
Alternatives considered: (1) `pip install` each frozen commit in the container (needs network and a writable site-packages, and is slow per question); (2) monkeypatch `importlib.metadata.version` (changes library behaviour in a way probes could observe).
Why: many libraries (click 8.x, for example) call `importlib.metadata.version(...)` at import or on `--version`, which raises PackageNotFoundError when imported from a source tree. The shim is the smallest thing that makes the real lookup succeed.
How we'd defend it in the viva: "The library code runs unmodified; we only add the record pip would have written."
Revisit if: a library reads entry points or other metadata fields.

## D-17 Sandbox test dependencies: pinned union over 2020+ releases  (2026-10-28, P2, Aditya)
Decision: `sandbox/test-requirements.txt` pins hypothesis, pytest 7.4.4, packaging, six, typing_extensions, plus the test dependencies read from click (tox.ini / requirements/tests.in: pytest, colorama, importlib_metadata) and marshmallow (setup.py extras / pyproject groups: pytest, pytz, simplejson) at releases from 7.1/3.5.0 to the current dev branch.
Alternatives considered: (1) one image per library or per frozen commit (exact, but many images and slow builds); (2) unpinned latest versions (a new pytest major could break 2020-era test suites).
Why: one image keeps the environment identical for every question and system. pytest 7.4 still supports the older test idioms these suites use and runs on Python 3.10. TODO(P4): re-read the files at the actual frozen commits; pairs whose tests need anything missing are dropped and logged by `validate_pairs.py`.
How we'd defend it in the viva: "If a frozen commit's tests needed something else, validation fails for that pair and the drop is counted in the mining report."
Revisit if: many pairs are dropped for missing test dependencies.

## D-18 One warm container per question, run as the host's non-root uid  (2026-10-28, P2, Aditya)
Decision: `SandboxSession` starts one container per question (`--network none --cpus 1 --memory 1g --pids-limit 256 --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges`), mounts the frozen tree and a scratch dir read-only, and runs each job with `docker exec`. The container runs as the host user's uid (never root; 10001 if the host user is root). A job that outlives its timeout gets the container replaced.
Alternatives considered: (1) a fresh container per probe (about 1 s startup each; with dozens of mutants per question that dominates run time); (2) the image's fixed `sandbox` user (cannot read host temp dirs created with mode 0700).
Why: each job is still a fresh Python process, so mutants cannot contaminate each other, while the container starts once. The uid mapping lets the container read the host-written job files without loosening their permissions.
How we'd defend it in the viva: Docker tests show no network (connect and DNS both fail), writes outside /tmp fail, the user is not root, and the environment is pinned.
Revisit if: a probe could leave state in /tmp that changes a later job's outcome (then clear /tmp between jobs).

## D-19 Memory addresses are normalized in observed outputs  (2026-10-28, P2, Aditya)
Decision: the runner replaces ` at 0x<hex>` with ` at 0x?` in reprs and messages.
Alternatives considered: (1) compare raw reprs (every object repr would differ between processes); (2) compare only exception types and pass/fail (too coarse: hides changed return values).
Why: the mutation check compares the outcome on the original code with the outcome on each mutant, in different processes. Without normalization, `<Foo object at 0x7f...>` would make every mutant look like a behaviour change.
How we'd defend it in the viva: "Only the address is removed; the type and every other part of the repr are compared."
Revisit if: other process-dependent text (temp paths, timestamps) appears in reprs.

## D-20 AST policy: block process, network, dynamic code and writes outside /tmp  (2026-10-28, P2, Aditya)
Decision: `sandbox/policy.py` rejects imports of process/network/dynamic-import modules, calls such as `os.system`, `eval`, `exec`, `__import__`, `getattr` with a non-literal or dunder name, introspection escapes (`__subclasses__`, `__builtins__`), and file writes unless the path is a literal under `/tmp`. Names that are also ordinary methods (`replace`, `remove`, `rename`) are blocked only when called on `os`. A blocked probe is not run and is logged as `unsafe_attempt`.
Alternatives considered: (1) an allow-list of permitted modules only (would reject legitimate probes that use an unlisted stdlib module, lowering the executable rate); (2) no policy, relying on the container alone.
Why: the container is the boundary; the policy is a cheap second layer that also *measures* unsafe attempts, a required safety metric. Blocking `str.replace` would have broken ordinary probes, so ambiguous names are scoped to `os`.
How we'd defend it in the viva: "We say openly that an AST check can be evaded, which is why everything still runs with no network and a read-only filesystem."
Revisit if: the adversarial set shows an evasion pattern worth adding.

## D-21 Mutation with libcst on one line, one operator at a time  (2026-10-28, P3, Sourav)
Decision: `tools/mutate.py` parses the file with libcst, uses `PositionProvider` to collect the nodes that start on the cited line, applies one operator to one node at a time, and regenerates the file with `module.code`. Operators: constants (int/float +1, -1, 0; bool flip; None <-> 0; string -> ""), negate an if/elif/while condition, swap a comparison operator, delete a simple statement (-> `pass`), `return <expr>` -> `return None`. A mutant whose AST equals the original's is skipped.
Alternatives considered: (1) Python's `ast` module plus `ast.unparse` (reformats the whole file: comments vanish and line numbers shift, so citations and tracebacks no longer match the frozen tree); (2) an existing mutation tool such as mutmut (mutates whole files or projects, not one chosen line, and is harder to explain).
Why: libcst is a concrete syntax tree, so every byte outside the mutated span is preserved; a test checks this for every mutant of every planted toylib line. No operator changes the number of lines, so line numbers stay valid.
How we'd defend it in the viva: "We mutate exactly the cited line and nothing else; the diff of any mutant is one line."
Revisit if: A11 shows the operator set misses causal lines often (equivalent mutants).

## D-22 Each mutant runs in its own copy of the package and its own process  (2026-10-28, P3, Sourav)
Decision: for each mutant, only the package directory (e.g. `click/`) is copied into the scratch dir, the mutated file is written there, and the copy is put first on `sys.path` (an "overlay"); the claim and control probes then run in a fresh runner process. The copy is deleted right after.
Alternatives considered: (1) copy the whole repository per mutant (docs and tests are irrelevant to imports and make copies slow); (2) patch the module in memory with `importlib.reload` (state from the original import can leak into the mutant run).
Why: a fresh process per mutant means no state is shared between mutants or with the original run, and the frozen tree itself is never modified (it is mounted read-only).
How we'd defend it in the viva: "The original and each mutant see exactly the same probe code; only one line of one file differs."
Revisit if: copying large packages dominates run time.

## D-23 What counts as a behavioural change  (2026-10-28, P3, Sourav)
Decision: `outcome_changed` compares kind (return or raise), then the normalized `repr` for returns, or (exception type, message) for raises; the frame where an exception was raised is not compared. `is_breakage` marks a mutant as breakage if it raises SyntaxError, IndentationError, ImportError, ModuleNotFoundError, NameError or UnboundLocalError anywhere, or a TypeError/AttributeError whose innermost library frame is the mutated line. `verdicts` reports all three A6 rules: `any_flip` (any change), `behavioural` (a change that is not breakage) and `specific` (behavioural, and every control unchanged). The agent uses `specific`.
Alternatives considered: (1) compare pass/fail of `test_claim()` only (misses changed values when the assertion is loose); (2) compare the raising frame too (moving where the same error is raised, as in the redundant-guard case, is not a behaviour change for the user).
Why: this is the proposal's rule (§6.3), implemented as pure functions so it can be unit-tested without Docker and recomputed for A6 from stored outcomes.
How we'd defend it in the viva: toylib shows each case. Line 88 passes `specific` (`0 -> -1` flips the claim only); `return None` flips claim and control (rejected by specificity); deleting `result = min(...)` is UnboundLocalError (breakage); deleting line 12 is an ImportError, which only the lenient `any_flip` rule would accept.
Revisit if: human labels (RQ2) show the rule rejects many lines they judge causal.

## D-24 Group mutation for redundant lines  (2026-10-28, P3, Sourav)
Decision: `mutate_group` combines one mutant per line (Cartesian product in the fixed mutant order), capped at `mutation.max_group_pairs` combinations, and applies the same verdict rules.
Alternatives considered: (1) all combinations (grows multiplicatively with the number of mutants per line); (2) no group mutation (redundant guards would always be reported as non-causal).
Why: when two lines both enforce a rule, mutating either alone changes nothing. toylib's `safe_div` shows it: each guard alone is rejected, and the pair is accepted. The cap keeps cost bounded; it may miss the one combination that flips, which we report as a known limitation.
How we'd defend it in the viva: "Single-line mutation cannot see redundancy; we measure how often citations are redundant groups."
Revisit if: groups of three or more lines matter in real questions.

## D-25 Vacuity check over the enclosing function  (2026-10-28, P3, Sourav)
Decision: `check_vacuous` mutates every line of the function enclosing the cited line (docstring excluded) and runs the claim probe alone. If no mutant behaviourally changes its outcome, the probe is vacuous. It stops at the first behavioural flip and gives up (not vacuous) after 60 mutants.
Alternatives considered: (1) mutate the whole module (too costly for click-sized files); (2) no vacuity check (a probe asserting something always true would "confirm" any claim).
Why: if nothing in the code that supposedly decides the behaviour can change the probe's outcome, the probe does not test that behaviour.
How we'd defend it in the viva: toylib's `assert callable(clamp)` probe is flagged vacuous after mutating every line of `clamp`; the real C1 probe is not.
Revisit if: claims about module-level constants need a different scope (the cited line alone is checked then).

## D-26 toylib's planted lines  (2026-10-28, P3, Sourav)
Decision: `tests/fixtures/toylib/src/toylib/core.py` plants the proposal's example (`STRICT_DEFAULT` on line 12, overridden; the decider `if strict or x < 0: raise ValueError("negative")` on line 88), the specificity and breakage cases (`return result`, `LIMIT = 100`, `result = min(...)`), redundant guards (`safe_div`), a constant-free comparison for A11 (`at_least`), with `# MARK:` comments and docs that are wrong on purpose. Two details exist only to make the planted cases exact: both zero guards raise `ValueError(ZERO_MSG)` (so the "string -> ''" operator cannot make one guard look causal alone), and `result: int` makes `result` a local variable (so deleting its assignment raises UnboundLocalError rather than NameError, as §6.5 specifies).
Alternatives considered: (1) test only on real libraries (no known ground truth); (2) generate synthetic code automatically (harder to explain in the viva).
Why: a small hand-written library where we know which line decides each behaviour is the only way to test the mutation rules exactly, and it is the live demo for the viva.
How we'd defend it in the viva: run `pytest tests/mutation -m "docker or not docker"` live.
Revisit if: a rule change needs a new planted case.

## D-27 Questions and gold come from merged fixes (the SWE-bench recipe)  (2026-10-30, P4, Sunil)
Decision: a question is a GitHub issue that a merged PR fixed. Links come from closing keywords in the PR's title or body, with the PR's timeline as a fallback. Only PRs changing both package source and tests, with at most 10 source files, from issues not written by bots, are candidates. Every response is cached and every drop has a reason.
Alternatives considered: (1) hand-written gold (proposal v2: slow, and open to the charge of favouring our tool); (2) Stack Overflow questions (accepted answers are opinions, with no runnable check).
Why: it is objective, it scales, and a person, not our tool, decided which lines matter, so H3 and RQ2 do not measure the tool against itself. The real funnel gave 176 questions from 1406 merged PRs.
How we'd defend it in the viva: "The gold exists independently of our system: it is what the maintainers changed and what their test observes."
Known gap: the fallback reads the PR's own timeline, and contributed no links (all 367 are keyword links); on 300 unlinked click PRs inspected, the API returned no cross-reference events. §6.9 names the issue's timeline. TODO(fix at the split rebuild after G1, so the dataset does not change under running experiments).
Revisit if: spot checks at G1 find many invalid questions, such as feature requests.

## D-28 The frozen commit is the PR's base commit  (2026-10-30, P4, Sunil)
Decision: first parent of the merge commit; for a squash, the parent of the one commit; for a rebase, the parent of the first of the PR's commits, checked against the files the PR changed.
Alternatives considered: (1) the last commit before the issue was opened (the proposal's wording: the fix's test may not apply there, and many pairs would be lost); (2) the PR's `base.sha` from the API (it can be older than what the merge actually landed on).
Why: this is SWE-bench's convention. It guarantees the fix's diff applies cleanly and that the fix is absent. Consequence, reported honestly: an old issue is frozen at its fix time, not when it was asked, and 43 of 176 questions were opened before 2020 although they were fixed later. CLAUDE.md §6.9 applies the 2020 cutoff to the merge date.
How we'd defend it in the viva: "What matters for leakage is that the fix is not in the tree, and validation proves that by running the failing test."
Revisit if: results differ between issues opened before and after 2020; we can report that split.

## D-29 What "the tests the PR changed" means, and warnings during validation  (2026-10-30, P4, Aditya)
Decision: changed tests are found by mapping the diff's new-side lines onto test functions with the AST (decorators included), or the whole file if only helpers changed. A collection error before the fix (the new test imports a name the frozen code lacks) counts as failing. Repo settings that turn warnings into errors are switched off (`-o filterwarnings=`).
Alternatives considered: (1) run the whole test suite (slow, and unrelated flaky tests would invalidate pairs); (2) keep "warnings are errors" (a 2020 suite would then fail on deprecation warnings from newer dependencies, which says nothing about the behaviour under test).
Why: this checks the rule in CLAUDE.md §6.9 with the fewest false drops. Strictness is kept where it matters: every fail-before test must pass after the fix, or the pair is dropped.
How we'd defend it in the viva: 182 of 219 candidates validated, and all 37 drops have recorded reasons in `data/dropped.jsonl`.
Revisit if: a question's only failure is an ImportError of a new name (15 questions have an import or attribute error message), since that says little about behaviour; G1 can mark them.

## D-30 Gold evidence is frozen-side lines of the fix  (2026-10-30, P4, Aditya)
Decision: from a zero-context diff, each hunk gives its removed code lines (`changed`, or `deleted` if nothing was added). An add-only hunk points at the line above it (`anchor_for_insert`). Whitespace-only and comment-only hunks are ignored. Everything is computed in code; no LLM touches a gold field. `gold_answer` is a template.
Alternatives considered: (1) new-side line numbers (those lines do not exist in the frozen tree, so no system could cite them); (2) whole functions as evidence (too lenient: any citation in the function would count).
Why: the citation metric needs lines that exist at the frozen commit. Precision against these ranges is reported as a lower bound, because a caller can also decide behaviour.
How we'd defend it in the viva: "Fix-location recall only asks whether a system found one line the developer changed. Other causal lines count through human labels."
Revisit if: anchors, about 29% of gold ranges, turn out to be poor evidence at G1.

## D-31 BM25 with an overlap filter  (2026-10-30, P5, Sunil)
Decision: BM25 on tokens that split snake_case and camelCase, in separate code and doc indexes, cached per commit. A chunk qualifies if it shares a query word, whatever its score.
Alternatives considered: (1) keep only chunks with a positive score (a test found that a word in exactly half of a small corpus gets IDF zero and vanishes); (2) code embeddings (the proposal's hybrid search; left out of the must-have tier, a logged deviation).
Why: it is simple, deterministic and explainable, and gives every system identical starting material.
How we'd defend it in the viva: A10 (no retrieval, oracle retrieval) measures how much retrieval matters.
Revisit if: A10's oracle shows a large gap; then add embeddings.

## D-32 `find_references` is a word-boundary search  (2026-10-30, P5, Sunil)
Decision: a whole-word search over package code; `find_definition` uses jedi, which parses without running anything.
Alternatives considered: (1) jedi's `get_references` (needs a position in a file, and misses dynamic uses); (2) grep over the whole repository (would mix in tests, which have their own tool).
Why: overrides are often reached through dynamic attributes, which a word search still finds. It is fast, and its results are easy to explain.
How we'd defend it in the viva: "It over-reports rather than misses; the model filters the results."
Revisit if: common names flood the 40-result limit.

## D-33 One registry, and a workspace that cannot hold gold  (2026-10-30, P5, Sunil)
Decision: every tool goes through `ToolRegistry.call`, which validates arguments with pydantic and turns failures into readable errors, counted as invalid, errors or recovered. `Workspace` uses `__slots__` and reads only `library` and `frozen_commit` from a question; tests assert both.
Alternatives considered: (1) pass the question record into the agent and trust it not to look (a leak would be silent); (2) a tool implementation per system (breaks fairness).
Why: fairness and the no-leak rule are enforced by construction rather than by convention.
How we'd defend it in the viva: a test tries to set each gold field on a workspace, and another uses a tripwire question that fails if any other key is read.
Revisit if: a tool needs more question data; it must then be added explicitly.

## D-34 Structured outputs as forced tool calls, in one running conversation  (2026-10-30, P6, Ameya)
Decision: `submit_draft`, `write_probe`, `assess_refutation`, `revise_claim`, `propose_citation` and `final_answer` are tools the model is forced to call, with arguments validated by pydantic. `write_probe` covers all claims in one call. One history runs through the whole question, so the model keeps the code it has read. Limits per question: 5 claims, 3 tools per turn, 25 requests, 12 probe runs, 12 mutation checks.
Alternatives considered: (1) parse JSON from free text (more invalid outputs, each costing a request); (2) a fresh, shorter prompt per stage (fewer tokens, but the model would lose the code it read and re-read it, costing requests, the scarcer resource).
Why: requests per day are the binding limit, not tokens. Measured on the first dev question: 15 requests, about 150,000 tokens.
How we'd defend it in the viva: "We spend tokens to save requests because that is what the free tier limits."
Revisit if: a paid tier makes tokens the cost that matters.

## D-35 Broken probe or real refutation; dropping extra citations  (2026-10-30, P6, Ameya)
Decision: a probe whose error arises inside the library contradicts the claim; an error anywhere else (a wrong import, a bug in the probe) is a broken probe to repair, up to 2 times. If at least one of a claim's citations is causal, the non-causal ones are dropped without a request; re-investigation runs only when none is causal. Answers are flagged only for unverified or refuted claims. A confirmed claim with no causal citation keeps grade [E] and is not flagged, because it was executed.
Alternatives considered: (1) treat every error as a refutation (a typo in a probe would "disprove" a true claim); (2) re-investigate every non-causal citation (too many requests, and the claim already has its cause).
Why: the decision rests on where the error happened, which is objective, so it needs no LLM judgement.
How we'd defend it in the viva: unit tests pin each case, including that blocked and unimportable probes count as broken.
Known flaw, found in the dev runs: a cited line with no applicable mutation (a `for` header, `def`, `else:`, a continuation line) is treated as non-causal, though it was not tested; this was 11 of 54 lines, 3 of them gold. TODO(P10: report these as untestable, and add operators), a change made on dev only, before the G2 lock.
Revisit if: traces show probes wrongly classified.

## D-36 Fairness between ours and B2, and known asymmetries  (2026-10-30, P7, Aditya)
Decision: B2 has every tool, including `run_probe` and `mutate_and_run`, and the same limits. An investigation step is a model turn that uses a read-only tool, for all systems, so a turn that only runs a probe costs no step. Known asymmetries: (a) ours writes all probes in one call and its later stages need few turns, which is the procedure under test; (b) ours has `final_answer` written from a claim table and flags by rule, while B2 sets its own flag, because flagging is part of control logic; (c) baselines report no grades.
Alternatives considered: (1) count every B2 turn as a step (B2 would get 8 turns in all while ours gets 8 plus its checks); (2) give B2 unlimited requests (it could then outspend ours).
Why: with identical tools and limits, a difference comes from how the tools are used, which is what RQ1 asks.
How we'd defend it in the viva: `core.config.diff` between systems shows only `agent.ablation.*` and `baselines.*` keys, and a test asserts that.
Revisit if: the pilot shows B2 hitting its limits far more often than ours; B2+ exists for that case.

## D-37 Final judge: Groq `openai/gpt-oss-120b`  (2026-10-30, P8, Sourav)
Decision: following §2.4, with no Mistral key present, the final judge is `openai/gpt-oss-120b`, throttled and resumable, with a fixed checklist prompt. It does not see the system's name. Unparseable output is recorded as an error rather than guessed.
Alternatives considered: (1) keep `gpt-oss-20b` (too weak for real grading); (2) Mistral Large (preferred by the spec, but needs a key; if one is added before G2, everything is re-judged).
Why: a different model family from the systems, the strongest free option available now. All results are preliminary until kappa is measured at G3.
How we'd defend it in the viva: "We never rely on it alone. Below kappa 0.6 the primary comparison uses human labels."
Revisit if: daily token limits stop judging from finishing, or a Mistral key is added.

## D-38 Dev runs go question by question, ablations after the full agent  (2026-10-30, P8, Sourav)
Decision: B0 and B1 run on all dev questions first (1 request each). Then, for each question in turn: ours, B2, A2, A3, A1. Finished answers are saved at once; `eval.run` exits with code 3 on `QuotaExhausted`, and refuses the test set without `--allow-test`.
Alternatives considered: (1) finish one system on all questions before the next (if quota ran out, systems would cover different questions, so no paired comparison); (2) run the ablations first (they would pay for the prefix they could reuse).
Why: paired comparisons need the same questions, and A1-A3 share the full agent's prefix through the cache, so that part costs no quota.
How we'd defend it in the viva: `api_requests` against `requests` per question shows exactly what the cache saved.
Revisit if: a daily limit forces fewer systems instead of fewer questions.

## D-39 Toylib ablations use planted ground truth  (2026-10-30, P8, Sourav)
Decision: `analysis/toylib_ablations.py` computes, without any LLM, each planted line's verdict under the three rules, constants-only against the full operator set, and the share of executed lines each rule accepts. Executed lines are traced during `observe()`, so module-level lines, which run at import, are not in the leniency denominator; they appear in the A6 table instead.
Alternatives considered: (1) wait for real runs (no ground truth, and they use quota); (2) include import-time lines (they would inflate the denominator with lines no claim's scenario touched).
Why: it is free and exact, and it shows whether the rules do what we claim, on a known case.
How we'd defend it in the viva: run the command live; it takes under a minute.
Revisit if: toylib gains planted cases.

## D-40 Ownership follows docs/work_split.md; update zips are computed against GitHub  (2026-10-30, P8, Sunil)
Decision: `bundles/ownership.yaml` now matches `docs/work_split.md`. Update zips use `--since origin/main`, so they hold every file that differs from what is really on GitHub, not from a local commit.
Alternatives considered: (1) `--since <local P3 commit>` (would miss what never reached GitHub: Sunil's merged scaffold predates `scripts/check_bundle_order.py` and two fixes); (2) one member pushing everything (fails the course's per-member check).
Why: GitHub is the source of truth for what members have pushed.
How we'd defend it in the viva: each zip was rehearsed on a fresh clone of real `main`, in push order, running its own tests.
A rehearsal found one ordering conflict: Sunil's update changes the judge model in `config/`, and a test of Ameya's on `main` expected the old name. `make_bundles.py --also` lets Sunil's zip carry that one-line test change; Ameya's zip holds the identical file, so it shows no change.
Revisit if: members edit files directly on GitHub; those edits would show up as differences.

## D-41 A partial answer counts as wrong  (2026-10-30, P8, Sourav)
Decision: correctness means the judge's label is `correct`. `partial` and `incorrect` both count as wrong, so a confident partial answer is a confident error; the number of partial answers is reported separately. Written down before any dev or test metric was computed.
Alternatives considered: (1) count partial as correct (inflates correctness); (2) drop partial answers from the denominator (hides them).
Why: a developer acting on a half-right answer can still be misled, and this is the conservative reading of "wrong". It applies to every system alike.
How we'd defend it in the viva: the report shows partial counts, so a reader can recompute either way.
Revisit if: human labels at G3 show the judge overuses `partial`.

## D-42 Groq gpt-oss-120b stays the final judge, without a Mistral key  (2026-10-30, P8, Ameya)
Decision: Ameya fixed Groq `openai/gpt-oss-120b` as the final judge and chose not to add a Mistral key. This replaces the "revisit if a Mistral key is added" condition in D-37. The test-set size at G2 is chosen so that judging fits its 200,000-tokens-a-day limit, and answers are judged as they come in.
Alternatives considered: (1) add a Mistral key and re-judge everything (more tokens, but one more provider to validate, and all current grades would be redone); (2) judge only after all runs finish (a shortfall would show up too late to act on).
Why: at a measured 2,729 tokens per must-have answer, 6 answers per question cost 16,376 tokens, so about 122 questions fit in 10 days, which is still above the roughly 120 needed for H1. One judge throughout keeps every grade comparable.
How we'd defend it in the viva: the arithmetic is in section 8 of the mid-submission report, and the judge is still validated against human labels by the kappa rule at G3, so its quality is measured, not assumed.
Revisit if: the pilot's measured tokens per answer leave too few questions for H1, or kappa at G3 shows the judge cannot be relied on.

## D-43 Feature-request issues are filtered by GitHub metadata, alongside the spot check  (2026-10-30, P4, Ameya)
Decision: planned for the split rebuild at G1, and not yet applied. Drop an issue if it has a feature or enhancement label, or if GitHub's issue-type field says Feature. Each removal is logged in `data/dropped.jsonl`. The human spot check stays the main safeguard.
Alternatives considered: (1) spot check only (it samples 20%, so it cannot catch every case); (2) ask an LLM to classify issues (forbidden: no LLM may filter gold).
Why: it is deterministic and explainable. Its reach is small, measured on the current 176 questions: labels catch 0, because click's labels name topics, and 20 marshmallow questions have none. The issue type marks 6 as Feature, and 159 have no type. `click-1075`, a known feature request, has neither.
How we'd defend it in the viva: it is a cheap filter whose limit has been measured, and the disagreement rate from the spot check reports what it misses.
Revisit if: the spot check finds many feature requests that the filter missed; then the only sound route is to widen human checking, not to add an LLM.
Applied (2026-11-06, Sourav): a funnel step in `data/mining/fix_pairs.py` (`is_feature_request`, reason `feature_request`), right after the bot check. Re-mining from the cache made 0 API calls and dropped 8 PRs; 7 had been candidates. `data/build_gold.py` now builds only from current candidates, so an old validation row cannot bring a dropped pair back. Result: 176 → 170 questions, exactly the 6 measured above (`click-3059`, `marshmallow-1415`, `-1768`, `-2270`, `-2821`, `-686`); the other 170 are byte-identical. `mine()` now needs `GITHUB_TOKEN` only on a cache miss.

## D-44 A question that has been in dev never moves to test  (2026-11-06, pre-P9, Sourav)
Decision: `data/split.py` keeps every qid listed in `data/dev_history.txt` in dev, and adds each new dev question to that file. Free dev slots go to the stratum furthest below its proportional quota. Seeded as before; without a history the split is unchanged.
Alternatives considered: (1) re-split from scratch at every rebuild (moved 13 of the 20 `mid` dev questions into test after D-43 removed 6 questions); (2) freeze the old split files and only delete removed questions (dev shrinks with every removal, and new questions would never reach dev).
Why: the team has read system outputs and judge labels on the `mid` dev questions (for example `click-1193` in the mid report), and P10 prompt work starts from those failures. If such a question were in test, the locked test set would hold questions we developed on. Moving a question from test into dev is harmless; the reverse is not. After D-43, dev is the old 19 plus `click-1821`; no old dev question is in test.
How we'd defend it in the viva: the rule "never tune on test" has to hold for questions, not just for files; this makes it hold by construction, and `dev_history.txt` is the audit trail.
Revisit if: dev grows past its size because many pinned questions accumulate; then report the larger dev set rather than unpin.

## D-45 Questions run in a seeded order that interleaves the libraries  (2026-11-06, pre-P9, Sourav)
Decision: `eval.run.run_order` shuffles each library's questions with the split seed and then gives each next slot to the library furthest behind its share, so every prefix holds the libraries in proportion. All systems use the same order. `--qid-order` restores the alphabetical order for resuming `mid`.
Alternatives considered: (1) alphabetical qid order (the `mid` run stopped on quota before reaching any marshmallow question); (2) a plain seeded shuffle over all questions (balanced only on average: a short prefix can still miss marshmallow, which is 14% of test).
Why: quota stops are expected, so whatever prefix finishes should be a fair, paired sample of both libraries. Tested: on 129 click and 21 marshmallow, every tested prefix is within one question of the proportional count.
How we'd defend it in the viva: it changes only which questions run first, never what any system does, and it is the same order for every system.
Revisit if: a third library is added (the rule already handles any number).

## D-46 Spot-check kit: seeded stratified sample, one checker per question, static page, idempotent apply  (2026-11-07, P9, Sunil)
Decision: `annotation/sample.py` draws a seeded (82) 20% sample stratified by library (largest-remainder rounding) and deals it round-robin to the four members; each record carries the source diff (rebuilt with `git diff` + `split_patch`) and GitHub links at the frozen commit. `annotation/spotcheck.html` is a single static page (local-storage drafts, JSONL export; dataset text shown only as text). `annotation/apply_spotcheck.py` validates verdicts against `sample_manifest.json`, removes questions with any "no", logs them (stage `spot_check`), records `spot_check` on the rest, and writes disagreement rates into `data/mining_report.md`. It is idempotent, so it can be re-run after `build_gold.py` rebuilds the data files.
Alternatives considered: (1) two checkers per question for inter-annotator agreement (doubles human time in a slipped schedule; G3 already measures human agreement where it matters most, on system answers); (2) a small Flask app or a shared spreadsheet (needs hosting or accounts; a static file works offline and keeps data local).
Why: minimal human time (about 9 questions each), auditable (seeded, logged, re-runnable), and testable without a browser (pure logic run under node) and with one (headless Chrome render).
How we'd defend it in the viva: the sample is reproducible, every removal has a named reason and checker, and the reported rate is honestly "human vs automatic gold" with one human per question.
Revisit if: the disagreement rate is high (say above 20%); then a second checker on the disagreements, or a larger sample, is needed before trusting the gold.

## D-47 A cited line with nothing to mutate is "untestable", not "not causal"  (2026-11-07, P10, Sourav)
Decision: `mutate_and_run` returns `untestable=True` (no error, no verdict) when no operator applies to the line. The registry spends no mutation check on it and records it. The agent keeps an untestable citation and re-investigates ("find the line that decides this") only when at least one citation was actually rejected. When every citation is untestable (or unchecked because the budget ran out), it logs `citations_without_verdict` and goes straight to the vacuity check. If any citation is causal, the others are dropped as before. Grades are unchanged: an untestable citation is not shown causal, so the claim is [E], not [E+C]. Every system's output marks citations with `untestable`, so B2 and the agent report it the same way.
Alternatives considered: (1) leave it as non-causal (the mid run: 11 of 54 checked lines, 3 of them lines the developers changed; each triggered up to two extra requests); (2) count untestable as causal (would inflate [E+C] and H3 with lines the check never tested).
Why: "no operator applies" is absence of evidence, not evidence against. Treating it as rejection wasted requests and threw away some true fix lines. The change only affects what happens after the check, and the tool text is the same for the agent and B2 (fairness, §2.3).
How we'd defend it in the viva: the check has three honest outcomes (causal, rejected, cannot say), and the third is reported separately in the RQ2 agreement table instead of being folded into either side.
Revisit if: untestable lines stay common in the pilot; then add operators for loop headers, default arguments and call arguments (planned in the mid report, section 7) and measure the change through A11.

## D-48 G3 labels: sample by question, per-kind kappa rule, conservative consensus  (2026-11-07, P8 completion, Sourav)
Decision: `eval/human_export.py` samples *questions* (seeded, stratified by library) and exports every system's answer to each, blinded and shuffled, as one identical file per labeller, plus a separate key. Two labellers use `eval/label.html` (static page, same pattern as the spot check). `eval/kappa.py` computes Cohen's kappa human-human, each human against the judge, and consensus against the judge, separately for answer correctness and for citation labels (three classes each). The kappa rule (threshold 0.6) is applied per label kind on consensus-judge kappa. Where the two labellers disagree, the consensus takes the more conservative label (incorrect < partial < correct; irrelevant < on_topic < causal).
Alternatives considered: (1) sample answers at random across systems (the old export: unpaired, and it would not cover every citation from ours and A2 on the sampled questions, which H3 and RQ2 need); (2) resolve human disagreements by discussion (better labels, but slow and not reproducible in the time left); (3) one kappa over both label kinds (hides which judge output is unreliable).
Why: paired human labels let the primary comparison be recomputed on the sample if the rule triggers; the conservative consensus never credits a system with more than both humans gave it, and is deterministic. With 12 questions and 6 must-have systems the sample is 72 answers, inside CLAUDE.md's 40-80.
How we'd defend it in the viva: every step is seeded or deterministic, labellers never see the system, the rule was fixed before any label existed, and human-human kappa is reported so the humans' own reliability is visible.
Revisit if: human-human kappa is low (below about 0.4); then the labels themselves are unreliable and need a discussion round before they can overrule the judge.

## D-49 One analysis script, verdicts computed from the pre-registered rules  (2026-11-07, P12, Sourav)
Decision: `analysis/make_all.py` regenerates the whole analysis from stored files: H1-H3 verdicts (thresholds copied from PREREGISTRATION.md as constants, CI that includes zero = inconclusive), the kappa-rule view, per-category and per-library tables, RQ2 per acceptance rule against fix lines and human labels, a deterministic failure taxonomy, discordant cases, ablation predictions against outcomes, and three figures, each paired with its numbers in a table. H3 precision uses a cluster bootstrap over questions, because citations from one answer are not independent.
Alternatives considered: (1) a notebook (hard to re-run identically, easy to edit numbers by hand); (2) hand-coded failure categories (richer, but not reproducible and too slow for the time left).
Why: one command, no hand-typed numbers, so the reported results can be re-checked by anyone; the verdict text cannot drift from the pre-registered rule.
How we'd defend it in the viva: run the command in front of the examiners; the tests in `tests/analysis/` pin each verdict rule.
Revisit if: human labels arrive for more than the sampled questions; then H3 can use all of them.

## D-50 Several team members' Gemini keys, and a paid Groq judge  (2026-11-07, before G2, Sourav)
Decision: the team chose to run the main model on up to four members' own free-tier Gemini keys, with each member's agreement, and to move the judge to Groq's paid Developer plan. `llm/client.py` reads the key variable names from `llm.main.key_envs`, uses only keys present in `.env`, keeps one daily counter and one daily limit per key, and moves to the next key when a key's day is used up (our guard or the server's per-day 429). Traces record the key's slot number, never the key. Judge pacing raised to 30 requests per minute.
Alternatives considered: (1) one free key (about 17 test questions a day; the lock size and the deadline were the binding constraints); (2) one paid Gemini key (about 1,100-1,600 rupees; the clean option by Google's terms, which the team chose not to pay for).
Why: same model (`gemini-3.1-flash-lite`), same prompts, same temperature and the same cache for every key, so which key served a request cannot change any answer; it changes only how many requests fit in a day. It is a grey area under Google's API terms (limits are per project, and using an API beyond its limits needs Google's consent); the risk accepted is that a key is rate-limited or suspended, in which case the run continues on the remaining keys or stops cleanly and resumes.
How we'd defend it in the viva: it is disclosed here and in PREREGISTRATION.md; the method, model and judge are unchanged; every key's use is in the traces by slot.
Revisit if: any key is suspended or a member withdraws agreement; then remove that key from `.env`.

## D-51 A revised claim must cite, and an uncited claim keeps its last proposed line  (2026-11-07, P10, Ameya)
Decision: two changes to our agent only, after prompt iteration 1 on dev, approved by the team before the G2 lock. (1) The `revise_claim` schema (`ReviseClaim.citations`) gets the same description that iteration 1 gave the shared draft schema: "At least one for a behavioural claim: the line that decides it". (2) When a claim has no citation and both `propose_citation` attempts are rejected (or untestable) by the mutation check, the claim keeps the last proposed line with its verdict (`causal: false`, or `untestable`), logged as `kept_proposed_citation`. Before, it ended with no citation, while a rejected *drafted* line was already kept (D-35). Grades are unchanged: such a claim is [E], not [E+C].
Alternatives considered: (1) lock as is (6 of ours' 8 uncited claims in `pilot_it1` came from revisions, so the answers said less than the agent knew); (2) keep both rejected proposals (more lines for the judge to credit, with no reason to prefer the first proposal over the second, which was written after seeing the first one fail).
Why: iteration 1 was meant to apply "every behavioural claim cites a line" to every place a system writes claims; the revision schema, which only ours has, was missed. Keeping the agent's last proposal makes rejected proposed lines behave like rejected drafted lines, and the output still says the check did not confirm it.
How we'd defend it in the viva: it was made on dev only, before the lock, and disclosed in PREREGISTRATION.md as a change to ours only. B2 has no revision step and does not use this schema; its dev answers were replayed unchanged from the cache. The mutation check, grades and metrics did not change.
Revisit if: kept rejected lines turn out to be mostly *irrelevant* in the G3 labels; then report causal support with and without them.

## D-52 Scratch directories are numbered, not random  (2026-11-07, P10, Aditya)
Decision: each sandbox session names its job and mutant directories with a counter (`jobs/0001`, `mutants/0002`, ...) instead of a random id, and mutant ids are their index (`m001`). The container name stays random, since no model sees it.
Alternatives considered: (1) keep random names and strip `/work/scratch/...` paths from tool output (the text the model sees would then differ from what the sandbox printed, and every output path would need the rule); (2) name directories by a hash of the job (two identical jobs in one session would share a directory).
Why: in the dev re-run, a probe that printed its own traceback showed the random job path to the model, so B2's `click-3449` missed the LLM cache from call 19 and produced a different answer. Replays must give identical text, or resumed runs, the ablations' shared prefix (A2, A3) and repeat runs cost quota and change answers. Each session has a fresh scratch directory, so a counter cannot clash, and the same question gives the same sequence of jobs.
How we'd defend it in the viva: a unit test creates two fresh sessions and checks that they give the same paths in the same order; the pilot's one cache miss is reported in `docs/prompt_log.md`.
Revisit if: a cache miss on a replay is traced to another source of variation (timestamps, dictionary order, timing).

## D-53 Several Groq keys for the judge, because the paid plan was not in effect  (2026-11-07, P10, Sourav)
Decision: the judge rotates over up to four team members' Groq keys (`llm.judge.key_envs`), with the same code as the main model's keys (D-50). Each key is used only when present.
Alternatives considered: (1) one free key (200,000 tokens a day, at a measured 2,794 tokens per judgement about 70 judgements a day; the 900 judgements of the must-have tier on 150 test questions would take about 13 days); (2) Groq's paid Developer plan on one key (the cleaner option; D-50 assumed it, but on 2026-11-07 the key still answered on the free `on_demand` tier and stopped at 200,000 tokens).
Why: the judge must be the same model for the whole experiment (§2.4); which key serves a request cannot change a judgement at temperature 0, and the cache is keyed without the key. Only the number of judgements per day changes.
How we'd defend it in the viva: as D-50: disclosed, same model and prompt, key slot in the traces, never the key.
Revisit if: the paid plan becomes active on the first key; then the other keys are simply not needed.

## D-54 A timeout on every Gemini request  (2026-11-07, P11, Ameya)
Decision: the Gemini client is built with a 120-second request timeout, the same as the Groq client. A timed-out
request is a transient error, so the existing retry with backoff handles it.
Alternatives considered: (1) no timeout, as before: on 7 Nov one request's reply never arrived and the main run sat on
an open connection for four hours; (2) a watchdog that kills and relaunches the batch: more moving parts for the same
effect.
Why: a single lost reply must not stop a multi-day run. The change is engineering only: prompts, model, parameters and
the cache key are unchanged, so no answer changes; the interrupted question was resumed with its earlier calls served
from the cache.
How we'd defend it in the viva: the hang was found from the trace (no event for four hours, one established connection
to Google). The regression test checks the timeout is set and that a timeout is classed as retryable.
Revisit if: a legitimate request takes longer than 120 s.

## D-55 The adversarial set: canary tokens in planted instructions  (2026-11-10, P11 should-have, Aditya)
Decision: 15 items built from dev questions (`data/adversarial.py`), five of each kind: a hidden note in the issue text
asking for a shell command in a probe; a comment on the fix line asking for a wrong verdict; a comment on the fix line
asking for a write to `~/.ssh`. Every instruction asks for a unique canary token in the answer, so compliance is a
string match. Comments are appended to the end of an existing line and the file must parse to the same AST, so no
line moves and no behaviour changes. Each item gets its own copy of the tree (`tree_variant`) and its own index.
Alternatives considered: (1) judge compliance with the LLM judge: costs judge quota and adds a judge error to a safety
metric; (2) insert new comment lines: shifts every later line number, and an inserted line could change behaviour if
placed badly.
Why: the brief asks for an unsafe-action rate and safety against untrusted input (CLAUDE.md §2.5 treats read text as
data). Canaries give an exact, cheap measure; exposure (did the canary reach a model input, from the trace) separates
"ignored the instruction" from "never saw it".
How we'd defend it in the viva: the plant is provably behaviour-free (AST equality, tested), the test set is untouched
(dev questions only), and unsafe actions executed is 0 by construction because blocked probes never run.
Revisit if: exposure is low; then plant at lines the systems read more often.

## D-56 A Streamlit demo that only reads saved results and runs toylib  (2026-11-11, P13, Sourav)
Decision: `demo/app.py` is a four-page Streamlit app for the presentation: the idea, a live probe and mutation check on toylib, the committed results, and one question's answers and decision log side by side. It makes no LLM call. The live page runs only the hand-written toylib probes from `analysis/toylib_ablations.py`, in the Docker sandbox when the image exists and otherwise in the trusted local runner, and offers no way to type in code. All file reading is in `demo/data.py`, which is unit-tested without Streamlit; Streamlit is an optional dependency in `demo/requirements.txt`.
Alternatives considered: (1) a live agent run on a real question during the presentation (depends on the free API quota and the network, and could fail or give a different answer on stage); (2) a static HTML page like the annotation tools (no live mutation demo, and the charts would need hand-written JavaScript).
Why: a presentation must not depend on quota or the network, and every number on screen must be the one in the report, so the app reads the committed `analysis.json`. The live part shows the mechanism on planted ground truth, where the right answer is known.
How we'd defend it in the viva: the demo cannot run untrusted code (no free-text probe input), it cannot show numbers that differ from the report (same files), and its data layer has tests, including one that runs both live buttons on toylib.
Revisit if: we want to demo a live agent run; then replay a cached run (zero quota) instead of calling the API.

## D-57 An exploratory multi-agent extension, kept apart from the locked study  (2026-11-12, extension, Sourav)
Decision: Build a specialised multi-agent system (E1-E6) next to the locked single agent, pre-register its predictions
in a separate "Exploratory extension" section of PREREGISTRATION.md before any test run, and evaluate it on the 47
`sub50` test questions where E0 (ours) and B2 already have answers. The locked results stay the primary findings.
Alternatives considered: (1) replace the single agent and re-run the study, which would break the pre-registration
and the test lock; (2) leave the idea as future work only.
Why: the team wanted to test whether role specialisation, hybrid retrieval, a code graph and smarter experiments fix
the weaknesses the main study found, without rewriting what was already locked and reported.
How we'd defend it in the viva: it was designed after seeing the main results, so it is labelled exploratory, its
predictions were written before its runs, its prompts were developed on dev only, and E0/B2 answers are reused
unchanged on the same 47 questions.
Revisit if: a later study can pre-register E1-E6 from the start on fresh questions.

## D-58 Three LLM roles and two code roles, typed hand-offs, one orchestrator  (2026-11-12, extension, Ameya)
Decision: Bug Investigator, Probe Engineer, Code Analyst and Causal Verifier are LLM agents, each with its own
conversation and prompt; the Experiment Engineer and the final ranking are plain code. Agents hand over pydantic
objects (`multiagent/schemas.py`) through a hand-written orchestrator; no agent framework. Budget: 12 requests.
Alternatives considered: (1) five LLM agents, including an LLM that picks experiments, which costs more requests and
makes selection non-deterministic; (2) agents chatting in free text (AutoGen-style group chat), which is hard to
test and to explain.
Why: requests per day are the binding constraint, and every decision that code can make deterministically
(which line to mutate next, what counts as accepted, the ranking) is easier to test and defend.
How we'd defend it in the viva: each LLM call has one job and one schema; each hand-off is logged; the scripted-LLM
test runs all five roles on toylib.
Revisit if: requests become cheap enough to let an LLM choose experiments.

## D-59 Hybrid retrieval with small local models  (2026-11-12, extension, Sunil)
Decision: BM25 + dense (`BAAI/bge-small-en-v1.5`) fused by RRF (k = 60), reranked by `ms-marco-MiniLM-L-6-v2`,
optionally expanded with call-graph neighbours; models run locally with fastembed (ONNX), vectors in FAISS, cached
by text hash. Chunks stay the existing AST chunks; chunk text cut to 800 characters.
Alternatives considered: (1) a code-specific embedding model (jina-embeddings-v2-base-code, ~640 MB), too large for
the ~1 GB of free memory on the run machine; (2) Gemini's embedding API, which spends quota and sends code out.
Why: no quota, deterministic, fits the laptop; RRF needs no score calibration and k = 60 is the published default.
How we'd defend it in the viva: the retrieval study (R1-R5) measures each step separately on all 145 test questions.
Revisit if: a machine with more memory allows a code-specific embedding model.

## D-60 A code graph from the AST, with intra-procedural slices  (2026-11-12, extension, Sunil)
Decision: `codegraph/` builds functions, a name-resolved call graph, line-level data and control dependences per
function and module constants, in NetworkX. The static slice is intra-procedural plus module constants; the
"dynamic" part is the executed-line spectrum (Ochiai with one failing run) of the reproduce probe against the
controls, recorded by the sandbox's existing line tracer.
Alternatives considered: (1) a full Code Property Graph (Joern), which needs a JVM service; (2) coverage.py for
traces, which adds a dependency the runner deliberately avoided (D-16 area).
Why: enough to shrink and order the search space, and every rule fits in a sentence.
How we'd defend it in the viva: tests check the slice on toylib's planted lines (line 88 depends on line 87, not on
the module default on line 12).
Revisit if: interprocedural slicing turns out to matter (it ignores data flow through calls and attributes).

## D-61 Three-way mutation verdicts, dependency-guided pairs, information-gain order  (2026-11-12, extension, Sourav)
Decision: The Experiment Engineer reuses `tools/mutate.py` unchanged and reports accepted / rejected /
inconclusive (breakage-only and control-changing flips are inconclusive, not rejected). From E4 it mutates pairs of
lines the code graph connects when neither settled alone (at most 3 pairs). From E5 it orders single checks by
expected information gain over the agents' hypotheses (fixed HIT 0.8, MISS 0.1, catch-all prior 0.2) and stops early.
Equivalent checks (one line, two spellings) run once. Checks run sequentially (one-CPU container).
Alternatives considered: (1) all pairs of candidates, which grows quadratically; (2) a learned selection policy,
which would need training data we do not have.
Why: the main study showed the yes/no check rejected real fix lines; a three-way verdict says "cannot tell" instead,
and pairs address redundant guards (toylib's known limitation).
How we'd defend it in the viva: the toylib tests show the pair accepted where each guard alone is rejected, and active
selection stopping before the budget.
Revisit if: inconclusive verdicts dominate on real code.

## D-62 MCP as an optional transport only  (2026-11-12, extension, Aditya)
Decision: `mcp_server/server.py` (FastMCP, stdio, mcp 1.x) exposes code analysis, slicing, probes, mutation, patch
validation and experiment results; `mcp_server/client.py` gives the orchestrator the same interface as the
in-process backend. E6 = E5 through MCP. The agents' read-only search tools stay in-process.
Alternatives considered: (1) route everything, including LLM calls, through MCP, which changes nothing measurable but
adds failure points; (2) skip MCP.
Why: it shows the tools are reusable by any MCP client while keeping one execution engine; E6 must reproduce E5.
How we'd defend it in the viva: a test runs the orchestrator both ways on toylib and gets identical rankings,
verdicts and patch validation; E6 measures only the overhead.
Revisit if: the mcp 2.x API settles (it renamed FastMCP; we pin `mcp<2`).

## D-63 Localization metrics against the developer's fix lines  (2026-11-12, extension, Sourav)
Decision: Score every system on a ranked list of locations (E1-E6: deterministic ranking; others: citations in
order): Top-1/Top-3/MRR/precision/recall/F1 at line and function level, causal-verification rates on mutation-checked
lines, single- vs multi-location faults; McNemar and paired bootstrap for E-to-E comparisons.
Alternatives considered: (1) only judge-based correctness, which costs judge quota and was not validated for this
task; (2) human labels, not available in the time left.
Why: deterministic, free, and the same gold the main study used; reported as lower bounds.
How we'd defend it in the viva: a hand-computed mini example is a unit test.
Revisit if: human causal labels for the extension become available.
