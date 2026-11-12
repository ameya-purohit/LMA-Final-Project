# Explainer: the spot-check kit (`annotation/`)

Owner: Sunil. Files: `annotation/sample.py`, `annotation/spotcheck.html`, `annotation/apply_spotcheck.py`,
`docs/annotation_guide.md`, tests in `tests/annotation/`.

## Problem

All gold in this project is built automatically from GitHub issues, their fixing pull requests and the PRs' tests
(CLAUDE.md §6.9). That is objective and scales, but code cannot tell some things:

- whether an issue is really a question about behaviour, or a feature request;
- whether the PR's test shows the behaviour the issue asks about, rather than failing only because a new helper doesn't
  exist yet;
- whether the changed lines decide that behaviour.

So humans check a random 20% of the questions (gate G1). Questions they reject are removed and the removals are logged.
The disagreement rate is reported as a quality measure of the automatic gold. Humans *check* the gold; they never write it.

## How it works (plain words)

1. **`sample.py` draws the sample.**
   - It takes 20% of `data/questions_all.jsonl`, stratified by library: each library gives 20% of its own questions,
     rounded so the total is exact.
   - It uses a fixed seed (82), so anyone re-running it gets the same 34 questions.
   - It deals them round-robin to the four members (8 or 9 each, mixing libraries) and writes
     `annotation/spotcheck_<member>.jsonl` and `annotation/sample_manifest.json`.
   - Each record also carries what the checker needs: the source part of the fix diff, rebuilt with `git diff` on the
     bare clone and the same `split_patch` that validation used, and GitHub links to each gold range at the frozen
     commit.
2. **`spotcheck.html` is the checking page.**
   - It is one self-contained file: no server and no network, apart from the links.
   - A member opens their file and sees one card per question, then answers three yes/no questions with optional notes.
   - Answers are saved in the browser's local storage. **Export verdicts** downloads `spotcheck_<member>_done.jsonl`.
   - All dataset text is shown with `textContent`, never `innerHTML`, because issue bodies are untrusted data.
3. **`apply_spotcheck.py` applies the verdicts.**
   - It validates every verdict: `valid` must mean "all three answers are yes", each question must belong to that
     member, and there must be no duplicates and no missing verdicts.
   - It removes invalid questions and logs each removal in `data/dropped.jsonl` (stage `spot_check`, with the member's
     notes), and marks passing questions `spot_check.valid = true`.
   - It writes the disagreement rates into `data/mining_report.md`.
   - It is idempotent, because `build_gold.py` rebuilds the data files from scratch: re-running it after a rebuild gives
     the same result.
   - Then `data/split.py` rebuilds dev/test. Dev questions stay in dev (D-44).

## Worked example

`sample.py` on 170 questions (146 click, 24 marshmallow):

- 20% gives 29.2 click and 4.8 marshmallow. Largest-remainder rounding makes that 29 and 5, which totals 34, i.e.
  round(0.2 × 170).
- Dealt out, that is sunil 9, ameya 9, aditya 8 and sourav 8.

Suppose Sunil marks `click-1096` with *test captures behaviour = no* ("fails on a missing new helper"), and everyone else
says yes to everything:

- `apply_spotcheck.py` removes `click-1096` from `questions_all.jsonl`.
- It logs `{"stage": "spot_check", "reason": "spot_check_invalid", "detail": "test_captures_behaviour: no (fails on a missing new helper)", "checked_by": "sunil"}`.
- It reports an overall disagreement of 1/34 = 2.9%, and 2.9% for that check.

## Weaknesses

- **One checker per question.** That gives no human–human agreement on the gold itself. The disagreement rate is
  human against automatic gold, not inter-annotator agreement.
- **20% is a sample.** Problems in the other 80% stay. The rate estimates how common they are; it does not remove them.
- **Members know the project.** They might be lenient towards the gold. The guide asks for a concrete reason with every
  *no*, and for doubts to be written in the notes either way.
- **The page keeps drafts in one browser's local storage.** Switching browsers loses the draft, though the exported file
  is safe.
- **Docstring-only edits count as gold lines** (found while writing the guide, `click-1096`). Q3 only asks that *at least
  one* range decides the behaviour, so extra ranges don't remove a question. They do lower precision against gold, which
  is already reported as a lower bound.

## Viva Q&A

1. **Why not let humans write the gold instead of checking it?** Writing gold for 170 questions by hand would be slow and
   subjective. Gold from merged fixes is decided by the library's own developers, independently of our tool, which
   matters for H3. Humans are better used where code is blind: judging whether the question and the test fit.
2. **Why stratify by library?** Click is 86% of the data. A plain 20% sample could hold almost no marshmallow questions,
   and the rate would describe click only. Stratifying makes each library's share match the dataset.
3. **How do you know the sample was not cherry-picked?** It is seeded (seed 82) and the code is deterministic. Re-running
   `sample.py` gives the same `sample_manifest.json`, and `tests/annotation` checks that the result is seeded and
   independent of input order.
4. **What happens to a question marked invalid?** It is removed from `questions_all.jsonl` and logged in
   `data/dropped.jsonl` with the member and their reason. The rate goes into `mining_report.md`, and then the split is
   rebuilt. Nothing is deleted silently, and re-running the script gives the same result.
5. **Why is the page a static HTML file rather than a small web app?** Members open it by double-clicking; there is
   nothing to install or host, and no data leaves their machine. The logic is in a separate `<script id="logic">` block
   of pure functions, so the tests run it with node and check that its export is valid input for `apply_spotcheck.py`.
   A headless-Chrome test renders a real member file.
