# Explainer: the mutation check and toylib

Owner: Sourav Nath. Files: `tools/mutate.py`, `tests/fixtures/toylib/` (the planted library),
tests in `tests/mutation/`.

## Problem

When an AI assistant says "line 88 causes this behaviour", it often points at code that
*looks* related but does not decide anything, such as a default that is overridden
somewhere else. Today such citations are judged by a person (slow) or by another AI
(unreliable). Code allows an objective test that ordinary text does not: **change the
cited line and see whether the behaviour changes.** This is Check 2 of our method:
"flip the switch".

## How it works (plain words)

To find which switch controls a lamp, you flip it and watch the lamp. Here:

1. **The lamp** is the claim probe: a tiny program whose `observe()` performs the
   claimed scenario, e.g. `clamp(-1, strict=False)`. On the original library we record
   its outcome: it *returned* some value or *raised* some exception.
2. **The switch** is the cited line. We make small changes to it, called *mutants*, each
   in a throw-away copy of the library: change a number (`0 -> -1`), flip `True`/`False`,
   empty a string, negate an `if` condition, swap `<` for `<=`, delete a statement, or make
   a `return` return `None`. One change at a time; the rest of the file stays byte-for-byte
   identical (we use libcst, which keeps comments and formatting). The copies get numbered folder names
   (`0001`, `0002`, ...) from the question's sandbox session, and the mutants are named `m000`, `m001`, ... in a
   fixed order (D-52). So rerunning a question gives the model exactly the same text, and the run is replayed from the
   cache.
3. **Run the probe on each mutant** and compare its outcome with the original outcome.

Two rules stop the test from being too lenient:

- **Rule 1: only behavioural changes count.** If the mutant merely *breaks* the program
  (a SyntaxError, ImportError, NameError, UnboundLocalError, or a TypeError/AttributeError
  raised exactly at the mutated line), that tells us nothing about behaviour. It is
  *breakage*, not a flip.
- **Rule 2: specificity.** The agent also writes 1-2 *control probes*: the same function
  on inputs unrelated to the claim, e.g. `clamp(5, strict=False) == 5`. A mutant counts
  only if it changes the claim probe **and leaves every control unchanged**. Otherwise the
  line is on the path of *everything* (like a `return`), not specifically this behaviour.

A line is **causal** if at least one mutant passes both rules. We also report two weaker
rules from the same runs, for ablation A6: *any flip* (any change at all) and
*behavioural* (Rule 1 only).

Extras:
- **Group mutation.** If two lines both enforce the same rule (redundant guards),
  changing either alone does nothing. `mutate_group` combines one mutant per line.
- **Vacuity check.** If *no* mutant of *any* line in the function changes the probe,
  the probe probably tests nothing (e.g. `assert callable(clamp)`), so it is regenerated.

## Worked example (toylib, the viva demo)

`toylib/core.py` line 12 says `STRICT_DEFAULT = True`, and the docs say "strict is on by
default". But `_OVERRIDES = {"strict": False}` overrides it. Line 88 is
`if strict or x < 0: raise ValueError("negative")`.

Claim: `clamp(-1, strict=False)` raises ValueError. Control: `clamp(5, strict=False) == 5`.

| Cited line | Mutant | Claim probe | Control | Verdict for the mutant |
|---|---|---|---|---|
| 88 | `0 -> -1` (`x < -1`) | returns -1 (changed) | 5 (same) | specific flip: line 88 is **causal** |
| 88 | negate condition | returns -1 (changed) | raises (changed) | not specific |
| 12 | `True -> False` | still raises (same) | same | no change |
| 12 | delete the line | ImportError (changed) | ImportError | breakage |

So line 12 is **rejected** even though the docs point at it, and line 88 is **accepted**.
The "any flip" rule would have accepted line 12 through the ImportError: that is the
leniency Rule 1 removes.

Claim `clamp(500, strict=False) == 100` (control `clamp(5) == 5`): `return result ->
return None` changes both probes, so `return result` is rejected by specificity;
`LIMIT = 100 -> 101` gives 101 for the claim and 5 for the control, so `LIMIT` is
causal; deleting `result = min(...)` raises UnboundLocalError, which is breakage.

## Weaknesses

- **Equivalent mutants.** Some mutations do not change behaviour even on a causal line
  (e.g. `x < 0` to `x <= 0` when the probe uses -1). With several operators per line this
  is rarer, but it can falsely reject a causal line. A11 measures it.
- **Redundancy.** Lines that duplicate each other look non-causal one at a time; group
  mutation helps, but only within a capped number of combinations.
- **Control probes are written by the model.** A badly chosen control (too close to the
  claim) can make a causal line look non-specific.
- **Lines with nothing to mutate.** No operator applies to a `for` header, a `def` line, `else:` or a continuation
  line. In the dev runs this was 11 of 54 checked lines, and the agent counted them as non-causal. Fixed in P10 (D-47):
  such a line is reported as **untestable** (`MutationReport.untestable`), with no verdict either way. It costs no
  mutation check, it never triggers a search for another line, and answers mark it `"untestable": true`, so the RQ2
  table can count it separately. A bare function call can only be deleted, so it gives little evidence too.
- **On the test set it did not match the developers' fix lines (RQ2, measured).** Over 888 checks on 150 test
  questions, every rule's verdict agreed with "is this a line the fix changed?" no better than chance (kappa about 0).
  The `specific` rule that the agent uses rejected 77% of the fix lines it checked. Likely reasons are the ones
  above: equivalent mutants, redundant code, and a probe or control written so that a one-line change doesn't flip
  it. This is the main reason the full agent did not beat B2 (`docs/results.md` §5). The human labels at G3 test
  the same rules against people's judgement.
- **Cost.** Each mutant is a separate process run (about 0.15 s in Docker on toylib;
  more for larger libraries).

## Viva Q&A

1. **Why not just ask another LLM whether the cited line is relevant?**
   An LLM judges by reading, and reading is exactly what fails here: line 12 *reads* like
   it decides strictness. The mutation test is an executed counterfactual: change the line,
   rerun, observe. It does not depend on anyone's opinion. (RQ2 then checks how well it
   agrees with human judgement.)
2. **Why do you need control probes?**
   Without them, lines that every behaviour depends on (a `return`, an import, argument
   parsing) would pass: breaking them changes everything. Requiring the controls to stay
   unchanged keeps only lines that decide *this* behaviour. This is MUSE's idea from mutation-based fault localisation.
3. **Why does a NameError or SyntaxError not count as a change?**
   Because the mutation broke the program instead of changing its logic. If we counted
   breakage, deleting nearly any line on the execution path would "prove" it causal,
   which is what the v1 proposal's rule got wrong.
4. **Why libcst and not Python's `ast` module?**
   `ast.unparse` rewrites the whole file: comments disappear and line numbers move, so
   tracebacks and citations would no longer match the frozen code. libcst changes only the
   mutated node, and our test checks that every other line is byte-identical.
5. **What does toylib prove, and what doesn't it?**
   It proves the rules do what we claim on cases with known ground truth: overridden
   defaults, specificity, breakage, redundant lines, operator-set sensitivity and vacuous
   probes. It does not prove the check works on real libraries; that is what the
   evaluation (H3, RQ2) measures.
