# Explainer: the Experiment Engineer (E1-E5)  · owner: Sourav

## Problem
Mutation checks are the expensive, decisive step. The locked agent checked whatever lines it cited, one at a time,
with a yes/no verdict. It rejected real fix lines when their mutants only broke the program or also changed the
control, it could not see two lines that only matter together, and it spent checks on lines that told it little.

## How it works (plain words)
`experiments/engine.py` reuses `tools/mutate.py` unchanged and adds:
- **Three verdicts.** *Accepted*: some mutant changes the reproduce probe's outcome and no control's. *Rejected*: at
  least one mutant kept the program working and none changed the outcome. *Inconclusive*: nothing to mutate, every
  mutant broke the program, or the change also hit a control.
- **No wasted checks.** A line with nothing to mutate is detected in-process and costs nothing; the same line named
  two ways is checked once.
- **Pairs (E4).** After single checks, pairs of unsettled lines that the code graph connects (one in the other's
  slice, or same function with a shared source, or a call edge) are mutated together, at most 3 pairs.
- **Information gain (E5)** (`experiments/selection.py`). Each hypothesis blames some lines. Checking line l is
  expected to be accepted with probability 0.8 under a hypothesis that blames it and 0.1 otherwise (a catch-all
  hypothesis keeps 0.2 of the weight). The next check is the one with the largest expected reduction in entropy over
  hypotheses; after each result Bayes' rule updates the weights. Stop when one hypothesis has 0.8 of the weight and a
  line was accepted, or no check is informative, or the budget is spent.
- **Patch validation.** A one-line patch from the verifier is applied to a throw-away copy; validated if the
  reproduce outcome changes and every control stays the same.

## Worked example (toylib, `tests/experiments/test_engine_toylib.py`)
`safe_div(1, 0)` has two guards that raise the same error. Mutating either alone changes nothing (the other still
raises): both lines are rejected. They depend on the same argument, so the graph connects them, and the pair check
mutates both at once: the claim changes and the control `safe_div(6, 3)` does not, so the pair is accepted. With
hypotheses H1 (line 12) and H2 (line 88), active selection checks line 88 or 12 first, updates, and stops before
spending all four checks.

## Weaknesses
- The probabilities 0.8 / 0.1 / 0.2 are fixed guesses, not fitted; they were set before any test run.
- Pairs only fix two-line redundancy; three or more interacting lines are out of reach.
- Inconclusive is honest but unhelpful: a fix line that only "breaks" under mutation is still not confirmed.
- Sequential runs: one CPU per container, so no parallelism.

## Viva Q&A
1. **Why three verdicts?** The main study showed "not causal" mixed two things: "changing it changes nothing" and "I could
   not change it without breaking the program". Only the first is evidence against the line.
2. **Why not all pairs?** n candidates give n(n-1)/2 pairs, each several sandbox runs. The graph keeps only pairs that
   can interact, and the budget caps them at 3.
3. **Explain expected information gain in one sentence.** It is how much, on average, the result of a check would reduce
   our uncertainty about which hypothesis is right, computed from what each hypothesis predicts.
4. **Is the patch validation a fix?** No. It shows that changing that one line removes the reported behaviour without
   changing the controls, which is more evidence that the line decides it.
5. **Does the information-gain order find more fix lines?** That is prediction 5 in the pre-registration; the E5 vs E4
   row of `results/summary/extension.md` answers it.
