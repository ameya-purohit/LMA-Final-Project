# Explainer: gold validation

Owner: Aditya Narayan Dwivedi. Files: `data/validate_pairs.py`, `data/build_gold.py`, and the dataset files
`data/questions_*.jsonl`, `data/dropped.jsonl`, `data/mining_report.md`. Tests in `tests/gold/`.

## Problem

A PR that says "fixes #12" and touches a test does not prove that the test detects the behaviour. Maybe the test
already passed, or fails for unrelated reasons. And gold must never come from an AI model, or the evaluation would
be circular. So every pair has to be proved by running it, and every gold field must be computed by plain code.

## How it works (plain words)

**Validate by running** (`validate_pairs.py`, in the Docker sandbox):

1. Copy the frozen tree and apply only the **test part** of the fix. Run the tests the PR added or changed. At least
   one must **fail**: those are `fail_to_pass`, and their messages are `observed_before`, the real old behaviour.
2. Apply the **source part** too and run them again. Every `fail_to_pass` test must **pass**.

If either condition fails, or the run times out, the pair is dropped with a reason. Which tests "the PR changed" is
found by mapping the diff's line numbers onto test functions with the AST.

**Build gold** (`build_gold.py`, deterministic):

- `gold_evidence`: the lines in the **frozen** file that the fix modified or deleted. A hunk that only adds lines
  points at the nearest existing line above it (`anchor_for_insert`), because the new lines do not exist in the frozen
  tree. Hunks that only change whitespace or comments are ignored.
- `gold_answer`: a template filled from the test's failure message and the diff.
- `category`: `doc_related` if the issue mentions docs or the PR edits `docs/` or docstrings; otherwise
  `spread_across_files` if more than one source file changed; otherwise `single_location`.

## Worked example

For click #1075 (PR #1081): with only the test patch applied, `test_formatting_usage_multiline_option_padding`
fails with an assertion about the help text. With the source patch too, it passes. The fix changes
`click/formatting.py` line 208, so the gold evidence is that line, and the template gives: "On the frozen version,
`tests/test_formatting.py::test_formatting_usage_multiline_option_padding` fails: AssertionError ... The behaviour is
decided in `click/formatting.py` lines 208-208, which the merged fix (PR #1081) changed."

## Weaknesses

- **Gold evidence is one causal location, not all of them.** A caller can decide the behaviour too. That is why
  precision against gold is reported as a lower bound, and why human labels also count.
- **ImportError failures.** If a new test imports a name the frozen code lacks, it "fails" without showing much about
  behaviour. 15 of 176 questions have an import or attribute error message; G1 can mark them.
- **Category is coarse.** Docstring edits make a question `doc_related` even when docs were not the point, which is why
  108 of 176 are in that category.
- **Strict rule, some good pairs lost.** One flaky changed test drops the whole pair (7 pairs).

## Viva Q&A

1. **How do you know a question's gold is right?**
   The fix's own test fails on the frozen code and passes with the fix, both run in the sandbox. That is evidence from
   execution rather than opinion. Humans also spot-check 20% at gate G1 and we report their disagreement rate.
2. **Why is gold the behaviour before the fix?**
   Because the question is about what the frozen code does. If the code has a bug, the correct answer describes the
   bug, not the intended behaviour.
3. **Can an LLM touch the gold anywhere?**
   No. Evidence comes from git diffs, behaviour from test runs, the answer from a template, the category from a
   rule. There is no LLM import in these files.
4. **Why do add-only hunks use an anchor line?**
   Lines that only exist after the fix cannot be cited at the frozen commit. The line above the insertion is the nearest
   thing a system could point at, and it is marked as an anchor so its quality can be studied.
5. **Why switch off a repo's "warnings are errors" setting during validation?**
   An old test suite would fail on deprecation warnings from newer dependencies. That would say nothing about the
   behaviour under test, and it would wrongly drop good pairs. The strict pass/fail rule is unchanged.
