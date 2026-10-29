# Explainer: the foundation (config, JSONL, keys, bundles, CI)

Owner: Sunil Kumar. Files: `pyproject.toml`, `requirements.txt`, `config/default.yaml`, `core/config.py`,
`core/jsonl.py`, `core/env.py`, `bundles/ownership.yaml`, `scripts/make_bundles.py`,
`scripts/check_env.py`, `.github/workflows/ci.yml`, `.gitignore`, `.env.example`.

## Problem

Every other part of the project leans on a few shared needs:

1. **Fairness.** Our agent and every baseline must use the same model, limits and
   settings, so differences come only from control logic. That needs one source of
   settings that can be compared between systems.
2. **Records that survive crashes.** Runs last days, because the free API quota resets
   daily. Datasets, results and traces must be written so an interrupted run loses
   almost nothing and can resume.
3. **Secrets in a public repo.** API keys must never be printed, logged or committed.
4. **Per-member pushes.** The course checks that each member pushed code, but the code
   is built in one folder. It must be split by owner, and `main` must stay working
   after each member's pull request.

## How it works (plain words)

- **`config/default.yaml`** is the single settings file: model IDs, rate limits, sandbox
  limits, step and probe budgets, ablation switches. `core/config.py` loads it and
  applies *overrides*, small dicts or YAML files merged on top. Nested sections are
  merged key by key; lists are replaced whole. `config_hash` gives each final config a
  short fingerprint, stored with every result. `diff(a, b)` lists exactly the keys that
  differ between two configs, which is how we show that B2 and ours differ only in control logic.
- **`core/jsonl.py`** reads and writes JSON Lines (one JSON record per line). Whole-file
  writes go to a temp file and are then renamed, so a crash never leaves half a file.
  Appends flush after each record, so a crash loses at most one record.
- **`core/env.py`** loads `.env` and answers only "present" or "missing" for each key.
  `require_key` hands a value to an SDK client and nothing else. Error messages name the
  key, never its value.
- **`bundles/ownership.yaml`** lists glob rules such as `llm/** -> ameya`. The first
  matching rule wins, so specific exceptions (`tools/probe.py -> aditya`) come before
  broad rules (`tools/** -> sunil`). **`scripts/make_bundles.py`** lists every file git
  would commit (so `.env` and caches are never included), checks that each has an owner,
  and zips one member's files with a `PUSH.md` of exact commands. `--since <rev>` builds
  an update bundle containing only the files changed since then.
- **`requirements.txt`** lists the dependencies with minimum versions (the same list as
  `pyproject.toml`; a test checks they match). `.venv/` is never committed: anyone recreates
  it with `pip install -r requirements.txt`, step by step in the README.
- **CI** has three jobs: a secret scan (fails on anything shaped like a real Google, Groq
  or GitHub key), the unit tests (`-m "not docker and not live"`), and a Docker job that
  builds the sandbox image and runs the Docker tests once `sandbox/` exists.
- **`scripts/check_env.py`** is gate G0: it checks the tools, that each key is present,
  makes one tiny live call per API, and checks the git remote.

## Worked example

Ablation A2 (no mutation check) is our agent with one switch flipped:

```python
from core.config import load_config, diff, config_hash
ours = load_config()
a2 = load_config([{"agent": {"ablation": {"no_mutation": True}}}])
diff(ours, a2)          # {'agent.ablation.no_mutation': (False, True)}
config_hash(ours) != config_hash(a2)   # True: results from the two are never mixed up
```

A bundle: `python scripts/make_bundles.py --member sunil --name sunil_scaffold` writes
`bundles/sunil_scaffold.zip` with Sunil's files and a `PUSH.md`.

## Weaknesses

- Overrides are untyped dicts, so a typo in a key (`no_mutaton`) silently adds a new key
  instead of failing. The config diff makes this visible, but nothing rejects it.
- Ownership globs depend on rule order; a broad rule placed too early would steal files.
  A test pins the owner of representative paths to catch that.
- The secret scan only knows three key formats. A key from another provider would not
  be caught, so `.env` must stay git-ignored.
- JSONL has no schema of its own; the schemas live in pydantic models elsewhere
  (`data/schema.py`).

## Viva Q&A

1. **Why one config file instead of one per system?**
   Fairness has to be shown, not claimed. With one base file and small overrides,
   `config.diff` prints exactly what differs between two systems. With separate files,
   any accidental difference (a step limit, a temperature) would hide among duplicated settings.
2. **Why are lists replaced rather than merged in an override?**
   So an override means the same thing whatever the base contains. If lists were
   concatenated, `mutation.operators: [constant]` (ablation A11) would *add* to the full
   operator set instead of restricting it.
3. **What happens if the machine crashes in the middle of writing results?**
   Appends are flushed per record, so at most the record being written is lost.
   Whole-file writes go to a temp file and are renamed, which is atomic on one filesystem,
   so the old file stays intact until the new one is complete.
4. **How do you guarantee keys never reach GitHub?**
   Three layers: `.env` is git-ignored, so it is never listed for a commit or a bundle
   (`make_bundles.py` uses git's own file list); code reports keys only as
   present or missing; and CI fails if any file contains a string shaped like a real key.
5. **Why must bundles be merged in a fixed order?**
   Later bundles import code from earlier ones (everything uses `core/config.py`). If
   Ameya's bundle landed before Sunil's, `main` would fail to import. A bundle imports
   at module level only from its own or earlier bundles; anything later is imported
   inside the function that needs it, so every prefix of the order still passes its tests.
