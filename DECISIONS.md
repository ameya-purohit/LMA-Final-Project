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
