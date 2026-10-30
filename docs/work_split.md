# Work split after the mid submission

This file **replaces the ownership table in CLAUDE.md §3** for all work after the mid-submission bundles (P0–P3). It does not change the mid-submission zips. When you read this file, update `bundles/ownership.yaml` to match it, and use it for every later update bundle.

**The work is split equally.** Each member owns about a quarter of the total effort, before and after the mid submission. Keep it that way: if a phase grows, or new work appears, give it to whoever currently has the least, and record the change in `DECISIONS.md`.

| Member | Files they own | Explainers |
|---|---|---|
| **Sunil Kumar**: foundation, data mining, retrieval, tools, pipeline scripts | `pyproject.toml`, `config/`, `core/`, `.gitignore`, `.env.example`, `README.md`, `CLAUDE.md`, `DECISIONS.md`, `PREREGISTRATION.md`, `docs/` (except explainers owned by others), `.github/`, `data/mining/`, `data/freeze.py`, `data/patch.py`, `data/schema.py`, `data/validate_questions.py`, `data/split.py`, `retrieval/`, `tools/` (except `probe.py` and `mutate.py`), `annotation/`, `scripts/run_all.py`, `scripts/quota_plan.py`, `bundles/`, `scripts/make_bundles.py`, `scripts/check_bundle_order.py` | data_mining, retrieval, tools, annotation |
| **Ameya Purohit**: LLM layer, the agent, the pilot | `llm/`, `agent/`, `scripts/smoke_llm.py`, `docs/pilot_report.md`, `docs/prompt_log.md` | llm_client, agent, pilot |
| **Aditya Narayan Dwivedi**: sandbox, gold validation, baselines, extra datasets | `sandbox/`, `tools/probe.py`, `data/validate_pairs.py`, `data/build_gold.py`, `data/controlled.py`, `data/adversarial.py`, the dataset files (`data/questions_*.jsonl`, `data/dropped.jsonl`, `data/mining_report.md`), `baselines/` | sandbox, gold_validation, baselines |
| **Sourav Nath**: mutation, evaluation, judging, analysis | `tools/mutate.py`, `tests/fixtures/toylib/`, `eval/`, `analysis/`, `results/` summaries, `docs/results.md` | mutation, evaluation, analysis |

**Phase owners and approximate share of the effort:**

| Phase | Owner | Share |
|---|---|---|
| P0 Foundation | Sunil | 5% |
| P1 LLM layer | Ameya | 5% |
| P2 Sandbox | Aditya | 8% |
| P3 Mutation and toylib | Sourav | 8% |
| P4 Data pipeline: mining, freezing, patch splitting, schema, split | Sunil | 6% |
| P4 Data pipeline: validation by running, building gold | Aditya | 6% |
| P5 Retrieval and tools | Sunil | 7% |
| P6 Agent | Ameya | 12% |
| P7 Baselines | Aditya | 5% |
| P8 Evaluation: metrics, judge, statistics, human export, kappa | Sourav | 8% |
| P8 Pipeline scripts: `run_all.py`, `quota_plan.py` | Sunil | 2% |
| P9 Spot-check kit | Sunil | 3% |
| P10 Pilot and prompt iteration | Ameya | 5% |
| P11 Main runs: ours and ablations | Ameya | 5% |
| P11 Main runs: baselines | Aditya | 3% |
| P11 Judging all answers | Sourav | 2% |
| Should-have controlled and adversarial sets | Aditya | 3% |
| P12 Analysis and figures | Sourav | 5% |
| G1, G3, P13 and viva prep | Everyone | 7% |
| **Total: Sunil ≈ 23%, Ameya ≈ 27%, Aditya ≈ 25%, Sourav ≈ 23%, plus shared work** | | |

Tests live under `tests/<area>/` and belong to the owner of the code they test. Each owner's explainer covers every phase they own, so they can defend it alone in the viva.

**Import rule for the split data pipeline.** `data/schema.py` and `data/patch.py` (Sunil) come before `data/validate_pairs.py` and `data/build_gold.py` (Aditya) in the push order, so Aditya's files may import them directly. `scripts/run_all.py` (Sunil) imports the agent, baselines and evaluation only inside its functions.

**Push order is unchanged:** Sunil, then Ameya, then Aditya, then Sourav. The import rule in CLAUDE.md §3 still applies.
