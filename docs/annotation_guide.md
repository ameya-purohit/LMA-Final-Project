# Annotation guide

Two human tasks use this guide:

- **Gate G1, the spot check:** you check the *automatically built gold* for a sample of questions.
- **Gate G3, the labels:** you label citations in system answers as *causal*, *on-topic but not causal* or *irrelevant*.

In both tasks, decide yourself. **Do not ask an AI tool**: the point is an independent human check (CLAUDE.md §2.2).

---

## Part 1. The G1 spot check

### What you are checking

Every question in our dataset was built by code, with no human or AI writing it:

- the **question** is a GitHub issue (its title and opening post);
- the **answer key** is the merged pull request that fixed it;
- the **gold behaviour** is how the PR's own new test fails on the *frozen* code, the commit just before the fix;
- the **gold lines** are the source lines that the fix changed, in the frozen version of the file.

Automatic gold can be wrong in ways code cannot see. A random 20% of the 170 questions (34) is split between the four of
us, 8 or 9 each. Your answers decide whether each question stays, and the share of "no" answers is reported as the quality
of the automatic gold.

### How to do it (about 5–10 minutes per question)

1. Find your file: `annotation/spotcheck_<your name>.jsonl` (`sunil`, `ameya`, `aditya` or `sourav`).
2. Open `annotation/spotcheck.html` in Chrome or Firefox. Double-clicking it works; it needs no server or internet,
   except for the GitHub links.
3. Click **Open my file…** and choose your file. Each question appears as a card:
   - the issue text,
   - the failing test and its message on the frozen code,
   - the gold lines, as links to GitHub at the frozen commit,
   - the source part of the fix diff,
   - the gold answer (a template filled in by code).
4. Answer the three questions on each card. If you answer **no**, write in the note *why*, in one sentence.
5. Your answers are saved in this browser as you go. You can close the page and reopen the same file later, in the same
   browser.
6. When the counter says all are answered, click **Export verdicts**. It downloads `spotcheck_<your name>_done.jsonl`.
   Send that file to Sourav, or put it in the `annotation/` folder. Don't edit it by hand.

### The three questions

**1. Is the issue a genuine question about how the library behaves?**

- *Yes* if the issue describes, or asks about, what the library currently does: a bug report ("X raises when it
  shouldn't"), surprising output, or a "why does…" question. A bug report counts even though it is not phrased as a
  question, because "what does click do here, and why?" has an answer on the frozen code.
- *No* if there is no current behaviour to ask about. Examples: a pure request for a new API or option, a packaging, CI
  or typing-only complaint, or a documentation typo.

**2. Does the failing test capture the behaviour the issue asks about?**

Look at the failure message on the frozen code.

- *Yes* if the failure shows the behaviour the issue describes, for example the wrong output, or the exception the issue
  complains about.
- *No* if the test fails for an unrelated reason. The common case: it fails only because a *new* name the fix added
  doesn't exist yet (`ImportError`, or `AttributeError: module ... has no attribute '_new_helper'`). That proves the
  helper is new, not how the library behaved. Also *no* if the test checks something other than what the issue asks.

  Careful: an `AttributeError` is *not* automatically a no. If the issue itself complains about that AttributeError, the
  test captures it.

**3. Do the gold lines decide that behaviour?**

Open the gold-line links. They show the frozen file, at the lines the fix touched.

- *Yes* if **at least one** gold range is where the behaviour is decided, meaning changing those lines is what changed
  the behaviour. For an `anchor_for_insert` range, the fix *inserted* code just below that line; ask whether the inserted
  code is what changes the behaviour.
- Extra ranges that don't matter, such as imports, docstrings or a refactor alongside, are not a reason for *no*.
  Mention them in the note.
- *No* if none of the ranges decides the behaviour, for example when the real change is in a file that isn't listed.

A question is kept only if all three answers are *yes*. Answer *no* only when you can say why. If you are torn, answer
*yes* and explain your doubt in the note; the note is recorded either way.

### Worked example 1: `click-1422`, valid (yes, yes, yes)

*Not in anyone's sample.*

- **Issue:** "Generated help with aliased group shows abbreviated command in usage." With an alias group, typing `pu`
  for `push` makes the help's usage line say `root pu` instead of `root push`.
- **Failing test on the frozen code:** `test_aliased_command_canonical_name` fails because the output starts with
  `Usage: root pu [OPTIONS]`, not `Usage: root push [OPTIONS]`.
- **Gold line:** `src/click/core.py` line 1349 (changed). The fix replaced `return cmd_name, cmd, args[1:]` with
  `return cmd.name, cmd, args[1:]`.

Answers:

1. **Yes.** The issue reports what click does now: the usage line shows the abbreviation.
2. **Yes.** The failure message shows exactly that output.
3. **Yes.** Line 1349 returns the name the user typed instead of the command's real name, and the sub-context uses that
   name in its usage line. Changing this one line changes the behaviour.

### Worked example 2: `click-1096`, invalid (yes, no, yes)

*Not in anyone's sample.*

- **Issue:** "Expand globs in arguments on Windows?" On Windows the shell doesn't expand `*.txt`, so click checks the
  literal path `*.txt` and fails with `Path "*.txt" does not exist`.
- **Failing test on the frozen code:** `test_expand_args` fails with
  `AttributeError: module 'click.utils' has no attribute '_expand_args'`.
- **Gold lines:**
  - `src/click/core.py` 32: an anchor for a new import.
  - `src/click/core.py` 906–907: deleted, but they are docstring lines in `main()`.
  - `src/click/core.py` 928: an anchor inside the same docstring.
  - `src/click/core.py` 935: an anchor at `args = sys.argv[1:]`.
  - `src/click/utils.py` 2 and 484: anchors where the new helper is added.

Answers:

1. **Yes.** It is part feature request, but it describes current behaviour that the frozen code decides: globs are not
   expanded, so `Path(exists=True)` rejects `*.txt`.
2. **No.** The test fails only because the new helper `_expand_args` doesn't exist on the frozen code. It never shows
   the glob behaviour the issue asks about. Note: "fails on a missing new helper, not on glob behaviour."
3. **Yes.** The anchor at line 935, right after `args = sys.argv[1:]`, is where the fix inserts the glob expansion, so it
   decides the behaviour. Note: "906–907 and 928 are docstring lines; 32 is an import."

Because of answer 2, this question would be removed. It also shows a known weakness of the automatic gold: docstring
edits count as changed lines.

---

## Part 2. G3 citation labels

At G3, two members label a blinded sample of answers. Systems are hidden behind ids. For each answer you mark correctness
(*correct*, *partial*, *incorrect*), and for each cited line one of three labels.

**How:**
1. Open `eval/label.html` in Chrome or Firefox and click **Open my file…**.
2. Choose `labels_<your name>.jsonl`, which the operator sends you.
3. Label every answer and every citation. Both labellers get the same items.
4. Click **Export labels** and send back `labels_<your name>_done.jsonl`.

Allow about 3–4 hours. Each card shows exactly what the AI judge saw: the question, the gold answer, the failing test, the
fix and the cited code. You see each citation's snippet with the cited line highlighted (`>>`).

| Label | Meaning | toylib example (`tests/fixtures/toylib/src/toylib/core.py`) |
|---|---|---|
| **causal** | Changing this line would change the claimed behaviour; it decides it | For "`clamp(-1, strict=False)` raises ValueError": line 88, `if strict or x < 0: raise ValueError(...)` |
| **on-topic but not causal** | About the same feature, but changing it would not change this behaviour | Line 12, `STRICT_DEFAULT = True`: it looks like it decides strictness, but `_effective_strict()` overrides it, and the claim passes `strict=False` anyway |
| **irrelevant** | Unrelated to the claim | A line in an unrelated function |

Rules of thumb:

- Judge the line against **the claim it is cited for**, not against the whole question.
- A line that is needed only in the sense that "the program would crash without it" (an import, or `return result`) is
  *on-topic but not causal*, unless the claim is specifically about it.
- Partial answers count as wrong in the metrics (D-41), but label them *partial* anyway, so the record is exact.
