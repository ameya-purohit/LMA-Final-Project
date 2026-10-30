# Run It, Then Cite It

LMA Group Project (CL3.410, Monsoon 2026), Team Disco 82:
Ameya Purohit, Aditya Narayan Dwivedi, Sourav Nath, Sunil Kumar.

A research prototype. Developers ask how a library behaves when its
documentation may be wrong. Our agent answers, then checks itself twice:

1. **Run it.** Each behavioural claim in the answer is tested by a tiny
   generated probe, executed in an offline Docker sandbox against the library
   frozen at the commit before the question was asked.
2. **Flip the switch.** A cited line is accepted only if mutating it (in a
   throw-away copy) changes the claim's outcome while leaving control probes
   unchanged.

Failed checks become the agent's next investigation goal. We compare this
against a ReAct agent with the same tools and budget, and against
Chain-of-Verification. The method is specified in
[docs/proposal_v2.md](docs/proposal_v2.md); hypotheses are pre-registered in
[PREREGISTRATION.md](PREREGISTRATION.md); every design choice is logged in
[DECISIONS.md](DECISIONS.md).

## Layout

| Path | What |
|---|---|
| `config/default.yaml` | The one config file every system reads |
| `core/` | Config loading, JSONL helpers, key checks |
| `llm/` | One LLM client (Gemini for systems, Groq/Mistral for the judge), cache, tracing |
| `sandbox/` | Docker image and the trusted probe runner |
| `tools/` | Agent tools: search, files, static analysis, history, probes, mutation; the workspace |
| `retrieval/` | Chunker and BM25 indexes over the frozen repo |
| `data/` | Mining issue-fix pairs, freezing, validation, automatic gold |
| `agent/` | Our agent (claim table, execution and mutation checks) |
| `baselines/` | B0 closed book, B1 RAG, B2 ReAct, B3 CoVe |
| `eval/`, `analysis/` | Judge, metrics, statistics, tables and figures |
| `annotation/` | Human spot-check kit for the automatic gold |
| `docs/explainers/` | One plain-language explainer per component, with viva Q&A |

## Replicating the project, step by step

### 1. Prerequisites

- **Python 3.10 or newer** (`python3 --version`)
- **git** (`git --version`)
- **Docker**, running (`docker info`). Needed from the sandbox phase on; not for the unit tests.
- About 2 GB of free disk for the virtual environment, the sandbox image and the library clones.

### 2. Get the code

```bash
git clone https://github.com/ameya-purohit/LMA-Final-Project.git
cd LMA-Final-Project
```

### 3. Create a virtual environment and install dependencies

The virtual environment (`.venv/`) is local to your machine and is never committed
(it is in `.gitignore`); `requirements.txt` is what recreates it.

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows (PowerShell): .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

*Optional, slow network:* if your system Python already has numpy, scipy and
matplotlib, create the venv with `python3 -m venv --system-site-packages .venv` so
pip reuses them instead of downloading them again.

### 4. Add your API keys

```bash
cp .env.example .env
```

Open `.env` and fill in `GEMINI_API_KEY`, `GROQ_API_KEY` and `GITHUB_TOKEN`
(`MISTRAL_API_KEY` is optional). Where to get each key is written in `.env.example`.
**Never commit `.env` or paste keys anywhere**: the repo is public. `.env` is in
`.gitignore`, and CI fails if anything shaped like a key is committed.

### 5. Check the environment

```bash
python scripts/check_env.py
```

Every line should say `OK`. It checks the tools, that each key is *present*
(never printing it), makes one tiny call per API, and checks the git remote.
Use `--no-network` to skip the API calls.

### 6. Run the tests

```bash
python -m pytest -m "not docker and not live"     # unit tests: no Docker, no API quota
```

Two more markers, run when available:

- `docker`: needs Docker and the sandbox image (`docker build -t rtci-sandbox:py310 sandbox`),
  then `python -m pytest -m docker`.
- `live`: calls the real APIs and uses free-tier quota: `python -m pytest -m live`.

### 7. Run the pipeline

Every step below is resumable and caches its work, so re-running it is free. API calls use your free-tier quota.

```bash
# Build the sandbox image (once)
docker build -t rtci-sandbox:py310 sandbox

# Dataset: mine GitHub, validate each pair by running its tests, build gold, split
python scripts/mine_pairs.py
python data/validate_pairs.py --workers 6
python data/build_gold.py
python data/split.py
python data/validate_questions.py data/questions_dev.jsonl data/questions_test.jsonl

# Zero-cost ablations on the planted library (no API calls)
python -m analysis.toylib_ablations

# Sanity check: one live run on toylib
python scripts/live_toylib.py --systems ours b0 b1 b2

# Experiments on the dev set: run, judge, report
python scripts/run_all.py --by-question --limit 20 --systems ours b2 a2 a3 a1 --split dev --run-id mid
python -m eval.report --run-id mid --split dev
```

Exit code 3 from `run_all.py` means the free daily quota ran out. Finished answers are saved: run the same command
after the reset (midnight Pacific time) to continue. The test set is locked: `eval.run` refuses it without
`--allow-test`, which must not be used before gate G2. Progress is tracked in [docs/progress.md](docs/progress.md).

## How code reaches GitHub

Code is pushed as four member bundles (see `bundles/ownership.yaml` and
`scripts/make_bundles.py`), each from that member's own account, in the order
Sunil, Ameya, Aditya, Sourav. Each zip contains a `PUSH.md` with exact steps.
