# Presentation demo

A Streamlit app that shows the project in five pages. It makes **no LLM calls and uses no API quota**: it reads the
saved results and runs the live part on the toylib fixture.

## Start it

```bash
source .venv/bin/activate
pip install -r demo/requirements.txt      # once
streamlit run demo/app.py                 # opens http://localhost:8501
```

Docker is optional. If the sandbox image is built (`docker build -t rtci-sandbox:py310 sandbox`), the live page can
use the real no-network container; otherwise it uses the trusted local runner, which is allowed only because the
demo runs hand-written toylib probes and offers no way to type in code (CLAUDE.md §2.5).

## What each page needs

| Page | Needs | Works on a fresh clone? |
|---|---|---|
| 1 · The idea | nothing | yes |
| 2 · Live: run it, flip the switch | toylib (in the repo); Docker optional | yes |
| 3 · Results | `results/summary/` (committed) | yes |
| 4 · Inside one question | `results/main/` and `.cache/trees/` (not in git) | only on the machine that ran the experiments |
| 5 · Multi-agent extension | `results/summary/extension.json`, `retrieval_study.json` (committed); the walk-through tab also needs `results/ext/` (not in git) | yes, except the walk-through tab |

## A 7-minute demo script

1. **The idea** (30 s). Three cards: draft, run it, flip the switch. The dataset comes from real GitHub issues, and
   the answer key is the developer's own fix.
2. **Live** (2 min). Claim *C1: `clamp(-1, strict=False)` raises ValueError*.
   - Click **① Run it**: both probes pass. The docs say strict is on by default, but the claim is about the actual
     code path.
   - Pick **line 88 (decider)**, click **② Flip the switch**: 7 mutants. Changing `0 → -1` (so `x < -1`) or deleting
     the `raise` makes `clamp(-1)` stop raising, while `clamp(5)` still returns 5, so the line is **accepted** as causal.
     Point out the mutants that are *not* enough: `negate if condition` also changes the control.
   - Pick **line 12 (STRICT_DEFAULT)**, flip again: `True → False` changes nothing, and deleting the line only breaks
     the import (NameError), so it is **rejected**. The default the docs talk about does not decide the behaviour.
   - Optional: claim *C2*, line `return_result`: every mutant also changes the control, so it is rejected as **not
     specific**.
3. **Results** (1.5 min). Main comparison: B0 → B1 → B2 shows tools matter; ours does not beat B2. Hypotheses tab:
   H1 and H3 not supported. "Does mutation find causal lines?" tab: kappa ≈ 0 against fix lines, and the agent's rule is
   the worst against humans. That is *why* the method lost.
4. **Inside one question** (1 min). ⭐ `click-2099`: the decision log shows the mutation check rejecting the
   developer's own fix line 2722, and the agent dropping it. ⭐ `click-1422`: probes refute two claims, the agent
   revises them, and the mutation check confirms the fix line.

5. **Multi-agent extension** (2 min). Show the five roles. In *Walk through one question*, ⭐ `click-2124` with E5:
   the Investigator's hypothesis H1 is accepted, the Experiment Engineer's mutation accepts line 1633 (the developer's
   own fix line), it is ranked first, and the patch validates. ⭐ `click-1139` is the counter-example: a convincing,
   validated explanation, but the developer fixed a different place. Then *Localization* (the code graph lowered Top-3),
   *Retrieval study* (RRF fusion is the one clear win) and *Cost* (roles use half the requests).

The honest message: the checks work as designed on planted code (page 2), but on real libraries mutation is a poor
test of causality, and acting on it hurt (pages 3 and 4).
