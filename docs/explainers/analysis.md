# Explainer: analysis

Owner: Sourav Nath. Files: `analysis/toylib_ablations.py`, `analysis/make_all.py`, `results/summary/`, tests in
`tests/analysis/`.

## Problem

Some questions about our method can be answered without spending any API quota. Does the mutation rule do what we claim?
Are the extra rules worth having? Is the filter actually filtering? A library where we planted the answers gives exact
results, for free.

## How it works (plain words)

`analysis/toylib_ablations.py` runs in the Docker sandbox, with no LLM involved:

- **A6: acceptance rules.** For each planted line and its claim, it reports the verdict under three rules: *any flip* (any
  change to the outcome), *behavioural* (a change that is not breakage), and *behavioural + specific* (and the controls did
  not change). We compare each with the known ground truth.
- **A11: operator set.** The strict rule again, using only constant-changing mutations.
- **Leniency.** It traces which lines a claim's probe executes, mutates each, and reports the share each rule accepts. If a
  rule accepts nearly everything that ran, it is not filtering.

Results are written to `results/summary/toylib_ablations.md` and `.json`.

### The final analysis: `analysis/make_all.py` (P12)

Run it with `python -m analysis.make_all --run-id <run> --split test`. It reads the stored answers, judgements, traces and,
after G3, the human labels, then writes `results/analysis/<run>_<split>/report.md` plus three figures. Every number comes
from code over files, so anyone can re-run it and get the same report. Its sections:

- **Hypothesis verdicts**, using the thresholds and rules written in `PREREGISTRATION.md`:
  - **H1:** ours minus B2 on the causally-supported answer rate, needing at least +8 points with a CI above zero. A CI
    that includes zero is called "inconclusive", never "negative". It also shows correctness on its own, the
    decomposition.
  - **H2:** a confident-error rate at least 40% lower than B2's, with coverage no more than 10 points lower.
  - **H3:** ours minus A2 on causal-citation precision, with a cluster bootstrap over questions. It uses human labels
    once G3 is done, and until then the judge's labels, marked provisional.
- **The kappa rule:** if G3 says to, the main comparison is recomputed on the labelled questions with the human labels.
- **Breakdowns:** per question category and per library, then RQ2, where each mutation acceptance rule (any flip /
  behavioural / specific) is compared with fix-line membership, and with human labels once they exist. Untestable lines
  are counted separately (D-47).
- **Failure taxonomy:** deterministic classes from the judge label and whether a citation hit a fix line, for example
  "right behaviour, wrong place".
- **Examples and predictions:** the discordant cases between ours and B2, and each ablation prediction next to what was
  observed.

## Worked example

Line 12 (`STRICT_DEFAULT = True`) for the claim "`clamp(-1, strict=False)` raises": *any flip* accepts it, because deleting
the line breaks an import. *Behavioural* and *specific* reject it, which is right: it does not decide the behaviour.
`return result` for "`clamp(500) == 100`": *any flip* and *behavioural* accept it, since returning None changes the result,
but *specific* rejects it, because the control changes too. Each rule removes a distinct kind of false acceptance.

**`make_all` on the October dev run** (13 questions, provisional judge labels):
- H1 is *inconclusive*: ours minus B2 is −7.7 points, with CI [−30.8, +15.4].
- The `specific` rule accepted fix lines with 51.9% precision against fix lines; this is a lower bound.

## Weaknesses

- **Toylib is small and hand-made** (9 planted lines). It shows the rules work on known cases, not on real libraries.
- **Ground truth is our own reading** of our own code, though on a small file with planted cases.
- **The check can still be wrong.** `result = min(x, LIMIT)` does decide the result, but its only applicable mutation is
  deleting the line, which is breakage, so even the strict rule rejects it. That is a real false rejection, and we report it.
- **Leniency excludes import-time lines,** because tracing covers `observe()` only.
- **The failure taxonomy is coarse.** It is computed, not hand-coded, so it is reproducible, but it can't tell, for
  example, a misunderstood question from a wrong probe. The discordant cases section gives the detail for a human to read.
- **RQ2 against fix lines is a lower bound.** A line outside the fix can be truly causal, so rejecting it counts as an
  error that isn't one. Human labels at G3 settle this.

## Viva Q&A

1. **Why bother with toylib when you have real questions?**
   Real questions have no complete ground truth for every line. Toylib does, so it is the only place where we can say
   exactly when each rule is right or wrong, and it costs no quota.
2. **What did A6 show?**
   Over 9 planted lines, the strict rule matched ground truth more often than the two weaker rules (see the table). Each
   weaker rule accepted a line it should not have, for the reason the rule was designed to remove.
3. **What does leniency measure, and why does it matter?**
   The share of executed lines each rule accepts. The v1 proposal's rule accepted almost anything on the execution path; a
   filter that accepts everything is useless, so we measure it instead of assuming it.
4. **Does the strict rule ever make mistakes?**
   Yes. It rejects `result = min(x, LIMIT)` because no operator can change that line without breaking it. We report this
   false rejection, and A11 shows the same effect is worse with fewer operators.
5. **Could you have fooled yourselves by choosing easy planted lines?**
   The cases come from the specification written before the code, and the false rejection above is left in the results.
   The real test is on human labels (H3, RQ2) on real questions.
