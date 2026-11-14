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
| `multiagent/` | Extension: the five-role orchestrator (E1-E6) and its prompts |
| `codegraph/`, `retrieval/hybrid.py` | Extension: call graph, dependences, slicing; BM25 + dense + RRF + reranking |
| `experiments/` | Extension: three-way mutation verdicts, pairwise checks, information-gain selection |
| `mcp_server/` | Extension: optional local MCP server and client for the analysis and execution tools |

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

# Experiments on the dev set (pilot): run, judge, report
python scripts/run_all.py --by-question --limit 20 --systems ours b2 b1 a2 a3 a1 --split dev --run-id pilot_d51
python -m eval.report --run-id pilot_d51 --split dev
```

Exit code 3 from `run_all.py` means the free daily quota ran out. Finished answers are saved: run the same command
after the reset (midnight Pacific time) to continue. Progress is tracked in [docs/progress.md](docs/progress.md).

### 8. Reproduce the final results (test set)

The test set is locked (`PREREGISTRATION.md`, status LOCKED, with the test file's SHA-256). `eval.run` refuses it
unless that file is LOCKED and `--allow-test` is passed. Each command runs, then judges, then reports.

```bash
# Must-have tier: ours, B1, B2 and ablations A1-A3 on all 150 test questions (run id `main`)
python scripts/run_all.py --by-question --limit 150 --systems ours b2 b1 a2 a3 a1 --split test --allow-test --run-id main

# Closed-book baseline B0 on the same questions
python scripts/run_all.py --by-question --limit 150 --systems b0 --split test --allow-test --run-id main

# A10 retrieval ablation (none / oracle) with ours and B2 on the first 50 test questions (run id `sub50`)
python scripts/run_all.py --by-question --limit 50 --systems ours b2 a10none a10oracle --split test --allow-test --run-id sub50

# Adversarial set (15 planted prompt injections built from dev questions; run id `adv`)
python data/adversarial.py
python scripts/run_all.py --by-question --limit 15 --systems ours b2 b1 --split adversarial --run-id adv --no-judge
python -m analysis.adversarial --run-id adv

# Gate G1, spot check: apply the members' verdicts (annotation/spotcheck_<member>_done.jsonl)
python annotation/apply_spotcheck.py

# Gate G3, human labels: export the blinded sample, label it in eval/label.html, then compute kappa
python -m eval.human_export --run-id main --split test
python -m eval.kappa --run-id main

# Every table and figure (hypotheses, ablations, RQ2, tool use, failure taxonomy, kappa rule)
python -m analysis.make_all --run-id main --split test
python -m analysis.make_all --run-id sub50 --split test
```

On our machine the must-have tier took three free-tier quota days (four members' Gemini keys, about 500 requests
per key per day). With the SQLite cache in `.cache/llm.sqlite`, re-running any command replays cached replies at no
quota cost; without it, expect fresh API calls and small differences, because temperature 0 is not fully
deterministic.

### 9. Exploratory extension: multi-agent localization (E1-E6)

Added after the main results, pre-registered separately (PREREGISTRATION.md, "Exploratory extension"); see
[docs/extension_results.md](docs/extension_results.md). It needs the optional dependencies (small local embedding and
reranking models are downloaded on first use, about 150 MB):

```bash
pip install -e ".[extension]"         # networkx, fastembed, faiss-cpu, mcp<2

# Retrieval study R1-R5 on all test questions (no LLM, no quota)
python -m analysis.retrieval_study --split test

# E1-E6 on the 47 sub50 test questions (data/ext_qids.txt); run E1-E5 in order so E4-E6 reuse the cache
for s in e1 e2 e3 e4 e5 e6; do
  python -m eval.run --system $s --split test --allow-test --run-id ext --qids-file data/ext_qids.txt
done
python -m eval.judge --run-id ext --split test --system e1     # optional: correctness, same judge as the study

# Localization, causal-verification and cost tables vs E0 (ours) and B2
python -m analysis.extension --run-id ext
```

## Presentation demo

A Streamlit app shows the idea, a live probe and mutation check on the planted toylib library, all results as charts,
and one question's answers and decision log side by side. It makes no LLM calls and uses no API quota.

```bash
pip install -r demo/requirements.txt
streamlit run demo/app.py        # http://localhost:8501 ; add ?page=live (or idea, results, question)
```

See [demo/README.md](demo/README.md) for what each page needs and a 5-minute demo script.

## Results

The submitted report is [docs/final_report.pdf](docs/final_report.pdf) (8 pages, LaTeX source in
[docs/report/final_report.tex](docs/report/final_report.tex)); a longer version is
[docs/final_report.md](docs/final_report.md), and the detailed numbers are in
[docs/results.md](docs/results.md), generated from `results/summary/analysis_main_test/report.md`. In short, on the
145 test questions left after the spot check, the full procedure **did not beat** the ReAct agent with the same tools
(causally-supported answers: ours 40.0% vs B2 49.7% by the judge; 25.0% vs 41.7% on the 12 human-labelled questions,
which the pre-registered kappa rule makes primary), and the mutation check made citations worse in the humans'
eyes (H3 not supported). Committed summaries:

| Path | What |
|---|---|
| `results/summary/analysis_main_test/` | Main analysis report, JSON and figures |
| `results/summary/analysis_sub50_test/` | A10 retrieval ablation |
| `results/summary/analysis_adv/` | Adversarial set |
| `results/summary/extension.md`, `retrieval_study.md` | Exploratory multi-agent extension and retrieval study |
| `results/summary/human/` | G3 agreement (kappa) |
| `data/mining_report.md` | Dataset funnel and the spot-check results |

Raw answers, traces and the LLM cache are not committed (they are large, and traces contain full prompts).

## How code reaches GitHub

Code is pushed as four member bundles (see `bundles/ownership.yaml` and
`scripts/make_bundles.py`), each from that member's own account, in the order
Sunil, Ameya, Aditya, Sourav. Each zip contains a `PUSH.md` with exact steps.
