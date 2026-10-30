# Explainer: evaluation

Owner: Sourav Nath. Files: `eval/run.py`, `eval/judge.py`, `eval/metrics.py`, `eval/stats.py`, `eval/report.py`,
`eval/human_export.py`, `eval/kappa.py`, tests in `tests/eval/`.

## Problem

We must run every system under the same conditions on a free API with a daily limit, grade thousands of words of answers
fairly, and produce numbers a sceptical reader can check. The course also warns against relying on an LLM judge alone.

## How it works (plain words)

- **Running** (`eval/run.py`). Each system is the same config plus a small override, so only control logic differs. A
  finished answer is saved at once. On a daily-quota error it exits with code 3; re-running skips finished questions and
  replays partial work from the cache. It refuses to touch the test set without an explicit flag.
- **Judging** (`eval/judge.py`). A model from a different family grades each answer with a fixed checklist. It sees the
  question, the gold answer, the observed behaviour, the fix's source diff and each cited snippet, but not which system
  wrote the answer. It labels correctness (correct, partial, incorrect) and each citation (causal, on-topic, irrelevant).
- **Metrics** (`eval/metrics.py`). Pure functions, checked against a hand-computed example:
  - **Correct:** labelled correct. Partial counts as wrong, and is reported separately.
  - **Covered:** neither flagged nor abstained. **Confident error:** wrong and covered.
  - **Citation counts as causal:** it falls inside a gold range, or is labelled causal.
  - **Causally supported (primary):** correct, and every claim has at least one causal citation.
  - **Fix-location recall:** at least one citation falls inside a gold range.
- **Statistics** (`eval/stats.py`). McNemar's exact test on questions where two systems disagree, and a paired bootstrap
  with 10,000 resamples for a confidence interval. Both are checked against known values.
- **Humans** (`eval/human_export.py`, `eval/kappa.py`). A blinded sample is exported for labelling. If human-judge kappa is
  below 0.6, the primary comparison uses human labels.

## Worked example

Five answers: (1) correct, cites a gold line; (2) correct, cites elsewhere, judge says on-topic; (3) partial, unflagged;
(4) incorrect, flagged; (5) incorrect, unflagged, cites a gold line. By hand: correctness 2/5; causally supported 1/5
(only answer 1); confident errors 2/5 (answers 3 and 5); coverage 4/5; fix-location recall 2/5. `tests/eval` checks that
the code gives exactly these numbers.

## Weaknesses

- **The judge is unvalidated until G3.** Every number that depends on it is preliminary.
- **Citation labels depend on the judge** when a citation is outside the gold ranges.
- **Small dev set.** With 20 questions, confidence intervals are wide, so differences mean little.
- **Daily token limits** may stop judging before all answers are graded; ungraded answers are reported as pending, never
  counted as wrong.

## Viva Q&A

1. **Why can't we just trust the LLM judge?**
   Because it could share the same blind spots as the systems. That is why it comes from a different family, is blind to
   the system, and is checked against human labels with a pre-declared rule.
2. **Why McNemar rather than comparing two percentages?**
   The same questions go to both systems, so the data are paired. Only questions where they disagree carry information
   about which is better, and McNemar's test uses exactly those.
3. **What does a confidence interval that includes zero mean?**
   Inconclusive, not negative. We state this in advance, and with about 120 questions an 8-point effect has only about 50%
   power.
4. **Why count a partial answer as wrong?**
   A developer acting on a half-right answer can still be misled. We fixed this before computing any metric, and report
   partial counts so anyone can recompute it the other way.
5. **What protects the test set?**
   `eval.run` refuses it without `--allow-test`, the SHA-256 of the test file is recorded at G2, and all prompt iteration
   happens on dev.
