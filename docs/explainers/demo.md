# Explainer: the presentation demo

Owner: Sourav Nath. Files: `demo/app.py` (the page), `demo/data.py` (all data loading), `demo/requirements.txt`,
`demo/README.md` (how to start it and a 5-minute script), `.streamlit/config.toml` (light theme), tests in `tests/demo/`.

## Problem

The project's results live in Markdown tables and JSON, and its mechanism (run a probe, mutate a line) happens inside a
sandbox that nobody sees. For a presentation we need to *show* both, reliably: no dependence on API quota or the
network, and no number on screen that differs from the report.

## How it works (plain words)

Four pages in a Streamlit app (`streamlit run demo/app.py`):

1. **The idea.** Three cards (draft, run it, flip the switch) and the dataset funnel.
2. **Live.** The toylib source with the cited line highlighted. You pick a claim and a line, then press **Run it** (the
   claim and control probes run in the sandbox) and **Flip the switch** (`tools.mutate.mutate_and_run` on that line).
   The page lists every mutant with the claim's and control's outcomes, the verdict under the three rules, and the
   planted truth. The probes are the hand-written ones from `analysis/toylib_ablations.py`; there is no box to type code.
3. **Results.** Charts and tables read from `results/summary/analysis_main_test/analysis.json`, the same file the report
   is written from: main comparison (judge and human labels), hypotheses, ablations (including A10), RQ2, judge
   validation, safety.
4. **Inside one question.** The issue, the answer key, two systems' answers side by side with the judge's verdict, each
   citation marked if it falls in the developer's fix, the frozen code around it, and our agent's decision log as a
   timeline. This page needs the raw results, which are not in git, so it works on the machine that ran the experiments.

`demo/data.py` does all reading; the page only lays things out. That split is what lets the tests check the numbers
without installing Streamlit.

## Worked example

Live page, claim C1 `clamp(-1, strict=False)` raises ValueError, line 88 (`if strict or x < 0: raise ...`):
7 mutants. `0 → -1` turns the guard into `x < -1`, so `clamp(-1)` returns -1 instead of raising, while the control
`clamp(5)` still returns 5: a specific flip, so the line is **accepted**. `negate if condition` also flips the claim but
changes the control too, so on its own it would not be enough. Line 12 (`STRICT_DEFAULT = True`): `True → False` changes
nothing and deleting the line only breaks the import (NameError), so it is **rejected**, which matches the planted truth.

## Weaknesses

- Page 4 needs local raw results; on a fresh clone it says so instead of showing data.
- The live demo is on toylib only: it shows the mechanism where it works, not the real-code failures (pages 3 and 4
  show those).
- The local runner executes code on the host; it is allowed only because the probes are hand-written and fixed.
- Streamlit is an extra dependency with frequent API changes; `demo/requirements.txt` pins a minimum version.

## Viva Q&A

1. **Why not run the real agent live?** It needs the free Gemini quota and the network, takes a minute or more, and at
   temperature 0 can still differ from the recorded run. The recorded runs, and their decision logs, are on page 4.
2. **Can someone run arbitrary code through the demo?** No. The live page only offers the fixed toylib claims and
   lines. Even then, with Docker available it uses the same no-network sandbox as the experiments.
3. **How do we know the charts match the report?** Both come from the same `analysis.json`, written by
   `analysis/make_all.py`; a test checks the demo's numbers (ours 40.0%, B2 72/145, humans 3/12 and 5/12).
4. **Why does the live demo succeed when the method lost?** toylib has planted ground truth designed for these
   checks. On real code, one line often affects several behaviours, so the specificity rule rejects causal lines; page 3
   shows it agrees with the fix lines no better than chance.
5. **Why Streamlit and not a web framework?** It is plain Python, a page in one file the team can read, and it renders
   tables and Altair charts directly. It is used only for presentation; no experiment depends on it.
