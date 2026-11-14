# Explainer: evaluating the extension (localization and retrieval)  · owner: Sourav

## Problem
The extension localizes causes; the main study graded answers. We need numbers that compare E0 (the locked agent),
B2 and E1-E6 on the same questions, without spending judge quota or inventing labels.

## How it works (plain words)
`eval/localization.py` turns each answer into a ranked list of (file, line): E1-E6 give one directly; for E0 and B2
it is their citations in order. Against the developer's fix lines (`gold_evidence`):
- **Top-1 / Top-3**: is a fix line first / among the first three? **MRR**: 1 / position of the first fix line (0 if
  none in the first 10). **Precision**: share of listed lines that are fix lines. **Recall**: share of the fix's
  separate ranges that some listed line hits. **F1**: their harmonic mean.
- Everything twice: at **line** level (inside a fix range) and **function** level (same function as a fix line).
- **Single vs multi-location** faults: the fix changed one range vs two or more; for the latter, how often two different
  fix ranges appear in the top 5.
- **Causal verification**: of the lines each system mutation-checked, the share accepted among fix lines and among
  other lines (an upper bound on false acceptance, since a non-fix line can be truly causal), and the inconclusive share.
- **Cost**: requests, tokens, mutant runs, probe runs, wall time per question.
`analysis/extension.py` builds the tables and paired comparisons (exact McNemar and a 10,000-resample paired bootstrap
of the difference, as in the main study). `analysis/retrieval_study.py` does the same for retrieval alone (R1-R5:
hit@K, Recall@K, Precision@K, MRR@K for K = 1, 5, 10) on all 145 test questions, with no LLM at all.

## Worked example (`tests/eval/test_localization.py`)
Fix ranges a.py:10-12 and b.py:5. Ranked list: a.py:3, a.py:11, b.py:5, b.py:9. Top-1 = 0 (a.py:3 is not a fix line),
Top-3 = 1, MRR = 1/2, precision = 2/4, recall = 2/2, F1 = 2·0.5·1/1.5 = 0.67; both ranges are in the top 5, so the
multi-location question counts as "found".

## Weaknesses
- Fix lines are one causal reference, not the only one; every rate is a lower bound.
- E0 and B2 were not built to rank locations; their citation order is a proxy for a ranking.
- 47 questions: differences below about 15 points are noise.
- Correctness needs the judge, whose agreement with humans was low in the main study (kappa 0.36).
- Top-k depends on how many lines a system ranks. E1 and E2 rank about 3 lines and E3 to E6 about 8, so a gold line
  the mutation check rejected (sorted last) can sit in E2's top 3 but not in E3's. The ranking diagnosis in
  `analysis/extension.py` reports this directly.

## Viva Q&A
1. **Why lines and functions?** A line-level miss by one line is still useful to a developer; function level shows
   whether a system is in the right place even when the exact line differs.
2. **Why is precision a lower bound?** A line outside the fix can still decide the behaviour (a caller, a default); we
   count it as wrong because we have no independent label for it.
3. **Why McNemar?** Both systems answer the same questions, so the test uses only the questions where they disagree.
4. **How do you know the metrics are right?** A hand-computed mini example is a unit test, and the function-level
   lookup uses the same code graph that is itself tested on toylib.
5. **Why reuse E0 and B2 answers instead of re-running them?** They are the locked runs on exactly these questions;
   re-running would spend quota and could differ only through the cache, which replays them identically.
6. **Why did adding the code graph (E3) lower Top-3?** The graph added candidates, which the mutation check mostly
   called inconclusive. The ranking puts inconclusive above rejected, and the fix lines were mostly rejected, so they
   fell from the top 3 of a 3-line list to ranks 6–10 of an 8-line list. The ranking diagnosis shows E2 had 12 rejected
   gold lines in its top 3 and E3 only 1. The problem is the causal test, not the graph.
