# Explainer: data mining

Owner: Sunil Kumar. Files: `data/mining/fix_pairs.py`, `data/freeze.py`, `data/patch.py`, `data/schema.py`,
`data/validate_questions.py`, `data/split.py`, `scripts/mine_pairs.py`, tests in `tests/data_mining/`.

## Problem

To evaluate an assistant that explains library behaviour, we need real developer questions with known correct
answers, and with the code as it stood before the answer existed. Writing gold answers by hand is slow, and a
reader could suspect us of favouring our own tool. We need a source of truth that exists independently of us.

## How it works (plain words)

We follow SWE-bench: **an issue is the question; the merged fix and its test are the answer key.**

1. **Mine** (`fix_pairs.py`). Ask GitHub for every closed PR, then narrow down step by step, recording the
   count at each step and a reason for each drop: merged since 2020 → linked to an issue (a phrase such as
   "fixes #12"; the PR's timeline is a fallback, which found none, see Weaknesses) → issue not written by a bot → changes both package code and
   tests → at most 10 source files. Every API response is cached, so a re-run makes no API calls.
2. **Freeze** (`freeze.py`). Make a bare clone of the library. The frozen commit is the state just before the fix
   landed: the first parent of the merge commit (or the parent of the first commit for a rebase). `git archive`
   exports that version as plain files. No system can see the fix, because it is not in those files.
3. **Split the patch** (`patch.py`). Divide the fix's diff into a test part and a source part. Later steps apply
   them separately, which is how we prove the test really detects the fix.
4. **Check and split** (`validate_questions.py`, `split.py`). Check the schema, check that the question does not
   name its fix, and check that gold lines exist. Then split into dev and test, stratified by library and
   category, with a fixed seed. The SHA-256 of the test file is recorded at gate G2.

Running the tests and building gold is Aditya's part: see `gold_validation.md`.

## Worked example

Issue click #1075 asks for newlines between options in help text. PR #1081 fixes it, and its body links the
issue. The PR changes `click/formatting.py` and `tests/test_formatting.py`, so it passes the funnel. The frozen
commit is the first parent of the merge. `split_patch` puts the formatting change in the source part and the test
change in the test part. The question text is the issue's title and opening post only, never its comments, which
often contain the answer.

## Weaknesses

- **Linking misses pairs.** Of 1406 merged PRs, 1039 had no linked issue. This is the biggest loss in the funnel.
  The fallback as built reads the PR's own timeline, which contributed no links: all 367 came from keywords. The
  specification names the *issue's* timeline. Fixing that is pending, and belongs at the split rebuild after G1.
- **An issue is not always a question.** Some are feature requests. Humans check a 20% sample at gate G1.
- **Old issues.** The cutoff is on the merge date, so 43 questions were opened before 2020. The frozen commit
  is from fix time, so the code may differ from what the reporter saw.
- **API results can change.** The cache keeps our run reproducible, but a fresh run later would see new PRs.

## Viva Q&A

1. **Why not write questions and answers yourselves?**
   Because then a reader must trust our judgement of which lines matter. Here the maintainers decided, before our
   tool existed, so measuring our citations against their fix is not circular.
2. **How do you prevent a system from seeing the answer?**
   The frozen tree does not contain the fix, the question text is only the opening post, a check rejects questions
   that name their fix PR, and the workspace object cannot hold gold fields at all.
3. **Why is the frozen commit the PR's base and not the commit before the issue was opened?**
   The fix's patch and test are guaranteed to apply to the base. Going back to the issue's date would lose many pairs
   to conflicts. It is SWE-bench's convention, and running the failing test proves the fix is absent.
4. **Why stratify the split?**
   So dev and test have the same mix of libraries and categories. With a random split, a 20-question dev set could
   easily miss marshmallow, which is only about 16% of the data.
5. **What does the funnel tell you?**
   Most merged PRs are not linked to an issue (1039 of 1406), and only 219 of 367 linked PRs change both source and
   tests. Those two filters remove far more than validation does, which rejects only 37 of 219.
