# Explainer: the sandbox and the probe tool

Owner: Aditya Narayan Dwivedi. Files: `sandbox/Dockerfile`, `sandbox/test-requirements.txt`,
`sandbox/runner.py`, `sandbox/policy.py`, `sandbox/session.py`, `tools/probe.py`, tests in `tests/sandbox/`.

## Problem

Check 1 of our method is "run it": every behavioural claim in an answer is tested by a
tiny program (a *probe*) that the language model writes. Running code written by a
language model on our own machine would be dangerous: it could delete files, read keys
or reach the internet, whether by mistake or because a planted instruction in a docstring
told it to. We also need every run to be **reproducible**: the same probe on the same
frozen library must give the same result every time, on every machine, for every system.

## How it works (plain words)

- **The box** (`sandbox/Dockerfile`). A Docker image with Python 3.10 and a pinned set of
  packages (pytest, hypothesis, plus the libraries' own test dependencies). The
  environment is fixed: `TZ=UTC`, `LANG=C.UTF-8`, `PYTHONHASHSEED=0`, no terminal.
- **One container per question** (`sandbox/session.py`). `SandboxSession` starts a
  container that has **no network**, at most 1 CPU, 1 GB memory and 256 processes, a
  **read-only** filesystem except a small `/tmp`, no Linux capabilities, and a
  non-root user. The frozen library is mounted read-only at `/work/lib`. The host writes
  each job (probe files plus a `job.json`) into a scratch folder that is also mounted
  read-only. The host runs `docker exec ... runner.py job.json` and reads one JSON answer.
- **The runner** (`sandbox/runner.py`, trusted code we wrote). For each probe file it:
  1. imports it; an import error (for example a SyntaxError in a mutated library)
     becomes a `raise` outcome;
  2. calls `observe()` and records what happened: `return` plus the value's `repr`, or
     `raise` plus the exception type, message and the **innermost library line** where it
     was raised (for example `click/core.py:88`);
  3. calls `test_claim()`: **pass**, **fail** (AssertionError) or **error** (anything else).

  Each step has a time limit (`signal.alarm`). Memory addresses in reprs are blanked out,
  so two runs of the same code print the same text. The claim probe and its control
  probes run in one process. It can also record which library lines ran (`trace_lines_for`)
  and run the repo's own tests (`kind: "pytest"`).
- **Metadata shim.** Libraries imported from a source folder (not pip-installed) often
  crash when they ask `importlib.metadata` for their own version. The runner writes a
  tiny fake "installed" record (`click-8.1.3.dist-info/METADATA`) so that lookup works.
- **Policy check** (`sandbox/policy.py`). Before anything runs, the host parses each probe
  and refuses anything that tries to start processes (`os.system`, `subprocess`), open
  sockets, run code dynamically (`eval`, `exec`, `__import__`), escape through
  introspection (`__subclasses__`), or write files outside `/tmp`. A refused probe is
  never run, and an `unsafe_attempt` record is written to the trace. This is a second
  layer only: the container is the real safety boundary.
- **The tool** (`tools/probe.py`). `run_probe(session, code, controls)` does the policy
  check, runs everything, and returns a `ProbeReport`. `render(report)` turns it into
  plain text for the model.
- **Local backend.** `LocalBackend` runs the same runner in a normal subprocess, for our
  hand-written toylib tests only. It refuses to start unless called with `trusted=True`.

## Worked example

Probe (written by the model for the claim "double(-1) raises ValueError"):

```python
import fakelib

def observe():
    return fakelib.double(-1)

def test_claim():
    fakelib.double(-1)      # (a well-written probe would use pytest.raises)
```

The runner reports:

```json
{"name": "claim", "status": "error",
 "outcome": {"kind": "raise", "type": "ValueError", "msg": "negative input",
             "innermost_frame": "fakelib/__init__.py:10"}}
```

`innermost_frame` points at the library line that raised, not the probe line; Check 2
(mutation) uses it to tell real behaviour changes from breakage. A probe containing
`os.system("id")` comes back as `BLOCKED by the sandbox policy; nothing was run`, and the
Docker container is never touched.

## Weaknesses

- **The policy can be evaded** (for example by building a module name from strings in
  ways the AST check does not follow). That is why everything still runs in the locked
  container; we say so in the write-up.
- **One image for all frozen commits.** If an old commit's tests need a package version we
  do not have, that question fails validation and is dropped (and counted).
- **Shared process for claim and controls.** A probe that changes global state could affect
  the next probe in the same job. Different jobs (for example different mutants) never
  share a process.
- **`signal.alarm` cannot interrupt some C code.** A job-level timeout then replaces the
  whole container.
- **Probes cannot use pytest fixtures** like `tmp_path`, because the runner calls the
  functions directly; they can use plain `/tmp` paths instead.

## Viva Q&A

1. **Why Docker and not just a Python subprocess with restrictions?**
   A subprocess shares our filesystem, network and keys. Docker lets the operating system
   enforce the limits: no network device at all, a read-only filesystem, a non-root user,
   and CPU/memory/process caps. Our tests check each one from inside the container.
2. **If the container is safe, why have an AST policy at all?**
   Two reasons: defence in depth (if a container setting were ever wrong, obvious
   attacks are still stopped), and measurement. The course asks for an unsafe-action
   rate, and counting blocked probes gives it. The adversarial set with planted
   instructions makes that number meaningful.
3. **Why call `observe()` and `test_claim()` yourselves instead of using pytest?**
   It is deterministic and fast, it does not depend on the studied repo's pytest
   settings, and it separates *what happened* from *whether the claim holds*. The mutation
   check compares what happened (the outcome) between the original and a mutant.
4. **Why record the innermost library frame of an exception?**
   Mutation must ignore breakage. A TypeError raised exactly at the line we mutated
   means we broke the code, not that we changed its behaviour. Comparing
   `innermost_frame` with the mutated line tells the two apart.
5. **How do you make sure the same probe gives the same answer everywhere?**
   A pinned image (Python 3.10, fixed package versions), fixed environment variables
   (time zone, locale, hash seed, no TTY), the frozen library mounted read-only,
   memory addresses removed from outputs, and a fresh Python process per job.
