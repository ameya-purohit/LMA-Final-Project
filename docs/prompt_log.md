# Prompt log

Every prompt change, on dev questions only (CLAUDE.md §2.2). Changes are made with equal effort for every system: a
change goes into a shared prompt, or the same change goes into each system's own prompt. Test questions are never used.

## Iteration 0: first-draft prompts (pilot, run id `pilot`, 2026-11-07)

The prompts as built in P6 and P7. On the 20 dev questions: ours 11/20 correct, B2 12/20 (summary in
`results/summary/pilot_dev.md`). Failure analysis of every answer the judge did not grade correct (ours 9, B2 8):

- **Wrong deciding line** (most partial answers in both systems: ours `click-2396`, `click-2703`, `click-3449`,
  `marshmallow-2924`; B2 `click-1597`, `click-2396`, `click-2703`, `click-3449`). The behaviour is described
  correctly, but the citation is a caller, a configuration site, or a nearby helper rather than the line that produces it.
- **Intended instead of frozen behaviour** (ours `click-1597`: "describes the intended/fixed behavior").
- **Uncited claims**: ours left 11 of 59 claims without a citation; B2 cited every claim in 18 of 20 answers.
- **Not prompt-fixable**: `click-461` and `click-3099` (both systems wrong or partial) are questions whose failing test
  checks that a new API exists. That is an answer-key problem for the spot check (guide, question 2), not for prompts.
- **Never flagged**: neither system flagged an answer. Not changed in this round: ours flags from its claim table in
  code, B2 decides itself, so a prompt change here could not be made equal.

## Iteration 1 (run id `pilot_it1`, 2026-11-07): the only planned round (decision H4)

Changes, all shared or identical across systems:

1. Shared system prompt (`agent/prompts/system.txt`, used by ours and every baseline):
   - "Describe the behaviour as it is now, including the bug. Do not describe the behaviour a fix would give, or what
     the code should do."
   - "The deciding line is the one whose change would change the behaviour. It is usually inside the function that
     computes the value, formats the output or raises the error, not the caller, the place where an option is
     configured, or the place where the result is printed. Trace from the public call down to where the output is
     produced."
   - "Every claim about behaviour cites at least one line."
2. Shared claim schema (`ClaimIn.citations`, used by ours and the baselines): description "At least one for a
   behavioural claim: the line that decides it".
3. The same one-word change in each system's task prompt, "should cite" → "must cite": `agent/prompts/investigate.txt`
   (ours), `baselines/prompts/react.txt` (B2), `baselines/prompts/rag.txt` (B1).

SHA-256 prefixes after the change: agent/prompts/system.txt `afed327d8bef`; agent/prompts/investigate.txt `ff854e64958d`; baselines/prompts/react.txt `cb7db5f3c590`; baselines/prompts/rag.txt `953335cf4413`; 

Result (20 dev questions, both systems complete and judged; `results/summary/pilot_it1_dev.md`):

| Measure | Ours it0 | Ours it1 | B2 it0 | B2 it1 |
|---|---|---|---|---|
| Correct (judge) | 11/20 | 14/20 | 12/20 | 12/20 |
| Causally supported | 5/20 (25%) | 5/20 (25%) | 7/20 (35%) | 11/20 (55%) |
| Fix-location recall | 45% | 45% | 55% | 65% |
| Confident errors | 9 | 6 | 8 | 8 |
| Coverage | 100% | 95% | 100% | 100% |
| Claims / uncited claims | 59 / 11 | 54 / 8 | 52 / 16 | 41 / 1 |
| Requests per question (mean) | 14.1 | 14.0 | 10.7 | 9.6 |
| Tokens per question (mean) | 175k | 189k | 140k | 124k |

Every quality measure stayed the same or improved for both systems, so iteration 1 is kept. Differences of two or
three questions out of 20 are within run-to-run noise; the clear change is B2 citing every claim (16 uncited → 1).

Why ours stayed at 25% causally supported although 14 answers are correct (9 correct answers miss the primary metric):

- **Uncited claims after a revision.** 6 of ours' 8 uncited claims were rewritten by `revise_claim` after a probe
  refuted them (`click-1287`, `click-1708`, `click-2809` twice, `click-3449` twice). The revised claim came back with no
  citation, the search for a deciding line (`propose_citation`) found only lines the mutation check rejected, and
  rejected *proposed* lines are not kept, while rejected *drafted* lines are (D-35). B2 has no revision step.
- **One non-causal citation in an otherwise causal answer** (`click-1597`, `click-1749`, `click-1821`,
  `click-2703`, `marshmallow-2249`, `marshmallow-2924`): the judge labels one claim's line *on-topic*.
- **More claims per answer.** Ours wrote 54 claims, B2 41. The metric needs every claim to have a causal line, so
  each extra claim is another chance to miss.

Mutation verdict against judge label on ours' citations (an unvalidated judge, so only a preview of RQ2): causal and
judge *causal* 13, causal and judge *on-topic* or *irrelevant* 16; rejected and judge *causal* 11, rejected and judge
*on-topic* 4; untestable 12.

## After iteration 1: a change to ours only (D-51, run id `pilot_d51`)

Not a prompt round. The team approved two changes to our agent, made because of the uncited-claim analysis above:
the `revise_claim` schema gets the shared citation rule it had missed, and a claim left uncited keeps its last
proposed line, marked not causal. B2 does not change.

Result (`results/summary/pilot_d51_dev.md`; B2 rows are the same answers as `pilot_it1` except `click-3449`):

| Measure | Ours it1 | Ours D-51 | B2 it1 | B2 (re-run) |
|---|---|---|---|---|
| Correct (judge) | 14/20 | 13/20 | 12/20 | 12/20 |
| Causally supported | 5/20 (25%) | 6/20 (30%) | 11/20 (55%) | 11/20 (55%) |
| Fix-location recall | 45% | 55% | 65% | 65% |
| Confident errors | 6 | 6 | 8 | 8 |
| Coverage | 95% | 90% | 100% | 100% |
| Claims / uncited claims | 54 / 8 | 54 / 1 | 41 / 1 | 41 / 1 |
| Requests per question (mean) | 14.0 | 14.2 | 9.6 | 9.6 |

Per question, ours changed on five: `click-1287` and `click-2809` became causally supported (the kept line is a fix
line or judged causal; the direct effect of D-51); `marshmallow-1808` went from correct to partial and `click-461`
from partial to incorrect (both re-ran revision steps with fresh model calls, so this is run-to-run variation);
`click-3449` became flagged. The change did what it was meant to (uncited claims 8 → 1); on the primary measure ours
is still well behind B2 on dev (6 against 11 of 20).

**B2 was not fully replayed from the cache.** On `click-3449` the cache missed from call 19 on: a probe printed its own
traceback, and the path in it contains the job directory, which had a random name (`/work/scratch/jobs/e7e17a5942d9/`).
The new answer differs but has the same judge label (partial). Fixed by D-52 (deterministic job and mutant directory
names), so from now on a replay gives the same text. This variation affected all systems equally and is reported, not
corrected, for the pilot.
