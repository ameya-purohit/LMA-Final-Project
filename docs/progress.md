# Progress checklist

Running checklist for the build (CLAUDE.md §4). Updated at the end of every phase.
Legend: `[x]` done, `[~]` in progress, `[ ]` not started, `[!]` blocked (reason given).

## Gates and phases

- [x] G0 Environment check
- [x] P0 Foundation (+ `sunil_scaffold.zip`): waiting for Sunil's PR to merge before P1
- [ ] P1 LLM layer
- [ ] P2 Sandbox
- [ ] P3 Mutation (+ mid bundles for Ameya, Aditya, Sourav)
- [ ] P4 Data pipeline (live mining)
- [ ] P5 Retrieval and tools
- [ ] P6 Agent
- [ ] P7 Baselines
- [ ] P8 Evaluation
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
- PAUSED: P1 starts after Ameya confirms Sunil's PR is merged.
