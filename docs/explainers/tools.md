# Explainer: tools

Owner: Sunil Kumar. Files: `tools/workspace.py`, `tools/registry.py`, `tools/search.py`, `tools/files.py`,
`tools/static.py`, `tools/tests_finder.py`, `tools/history.py`, tests in `tests/tools/`. (`tools/probe.py` is
Aditya's; `tools/mutate.py` is Sourav's.)

## Problem

The agents investigate code by calling functions. The course asks us to show that tool calls are valid, that errors
are recovered from, and that nothing unsafe happens. For fairness, all systems must use one implementation. And no tool
may ever reveal the fix or any gold field.

## How it works (plain words)

- **Workspace.** What a system may see for one question: the frozen tree and the git history up to the frozen commit.
  It is built from the library name and commit only, and uses `__slots__`, so a gold field cannot even be attached to it.
- **Registry.** `ToolRegistry.call(name, args)` is the single entry point. It validates arguments with a pydantic model,
  runs the tool, and always returns text. Invalid arguments or a failure become an error message the model can read
  and act on. It counts total, invalid, errors and recovered calls, which are reported metrics. It also enforces the
  probe-run and mutation-check budgets.
- **The read-only tools:**

  | Tool | What it does |
  |---|---|
  | `search_code`, `search_docs` | BM25 over the separate indexes |
  | `open_file` | Numbered lines, at most 200, confined to the tree |
  | `find_definition` | jedi, which parses without running code |
  | `find_references` | Whole-word search over package code |
  | `find_tests` | Where a name appears in the repo's tests |
  | `git_log`, `git_blame` | Run on the bare clone AT the frozen commit |

- **Execution tools** (`run_probe`, `mutate_and_run`, `run_repo_test`) always run in the Docker sandbox.

## Worked example

The model calls `open_file(path="../../etc/passwd")`: the workspace refuses it, the model receives `Error: ... is outside
the repository`, and the error is counted. It calls `open_file(start="abc")`: pydantic rejects it, and the model
receives `Invalid arguments for open_file: path: Field required; start: Input should be a valid integer`. If its next
`open_file` call succeeds, that counts as a recovery. `git_log` on a file shows only commits up to the frozen commit, so
a later fix is invisible; a test creates a later commit and checks that.

## Weaknesses

- **`find_references` over-reports** for common names (it is capped at 40 results).
- **jedi can miss** definitions created dynamically, such as attributes set in a loop.
- **The model chooses tools freely**, so a poor choice costs a step. Tool-choice quality is measured by hand.

## Viva Q&A

1. **How can a tool not leak the answer?**
   The workspace never receives the gold, by construction, and a tripwire test fails if anything but the library and
   commit is read from the question. The tree has no fix, and history stops at the frozen commit.
2. **What happens when the model passes bad arguments?**
   It gets a readable error instead of a crash, the call is counted as invalid, and if it succeeds next time that
   counts as a recovery. The course asks us to report exactly these.
3. **Is it safe to run jedi on a name the model supplied?**
   Yes. jedi parses source code without importing or running it, and we check that the name is a valid identifier first.
4. **Why a word search for references, not a type-aware one?**
   Behaviour is often overridden through dynamic attributes, which a type-aware search misses. A word search over-reports
   rather than misses, and the model can filter the results.
5. **Why is one registry important for the research?**
   B2 and ours must have identical tools, or a difference in results could come from the tools themselves. Sharing one
   implementation makes that a fact rather than a promise.
