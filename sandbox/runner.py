"""Trusted probe runner. Runs inside the sandbox container (or, for the
hand-written toylib fixture only, in a local subprocess).

Usage: python runner.py <job.json>   ->   one JSON document on stdout.

A job is either
  {"kind": "probes", ...}  import each probe file, call observe() and test_claim()
  {"kind": "pytest", ...}  run repo tests by node id (for run_repo_test and pair validation)

Common job fields:
  lib_root      directory of the frozen tree (read-only)
  source_root   the directory under lib_root that contains <package>/__init__.py ("src" or ".")
  package       import name of the library, e.g. "click"
  overlay       optional directory holding a mutated copy of <package>; it is put first on
                sys.path so it shadows the original (used by mutation)
  dist          optional {"name", "version"} for the metadata shim (see below)
  meta_dir      where the shim writes its dist-info (default /tmp/meta)
  timeout_s     per-probe time limit, enforced with signal.alarm

Why call observe()/test_claim() directly instead of running pytest on probes: it is
deterministic, fast and simple to explain (decision D-15). This file must only use
the standard library (plus pytest for "pytest" jobs), because it is copied alone
into the image.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import re
import signal
import sys
import time
import traceback
from typing import Any

MAX_REPR = 2000
MAX_MSG = 500
_ADDRESS = re.compile(r" at 0x[0-9a-fA-F]+")


class ProbeTimeout(BaseException):
    """Raised by the alarm. A BaseException, so a probe's `except Exception` cannot swallow it."""


def _on_alarm(signum, frame):  # pragma: no cover - called by the OS
    raise ProbeTimeout("probe exceeded its time limit")


def normalize(text: str) -> str:
    """Remove memory addresses ("<Foo object at 0x7f...>") so the same behaviour gives the
    same text in every process; otherwise every mutant would look like a behaviour change."""
    return _ADDRESS.sub(" at 0x?", text)


# ----------------------------------------------------------------------- setup
def setup_paths(job: dict[str, Any]) -> list[str]:
    """Put the library (and a mutant overlay, if any) first on sys.path.

    Returns the package base directories, used to tell library frames from probe frames."""
    lib_root = job["lib_root"]
    source_dir = os.path.normpath(os.path.join(lib_root, job.get("source_root", ".")))
    bases = [source_dir]
    sys.path.insert(0, source_dir)
    if job.get("overlay"):
        sys.path.insert(0, job["overlay"])
        bases.insert(0, job["overlay"])
    dist = job.get("dist")
    if dist and dist.get("name") and dist.get("version"):
        install_metadata_shim(dist["name"], dist["version"], job.get("meta_dir", "/tmp/meta"))
    return bases


def install_metadata_shim(name: str, version: str, meta_dir: str) -> None:
    """Libraries often read their own version with importlib.metadata, which fails when they
    are imported from a source tree that was never pip-installed. A minimal dist-info
    directory on sys.path makes `importlib.metadata.version(name)` work (decision D-16)."""
    info = os.path.join(meta_dir, f"{name.replace('-', '_')}-{version}.dist-info")
    os.makedirs(info, exist_ok=True)
    with open(os.path.join(info, "METADATA"), "w", encoding="utf-8") as fh:
        fh.write(f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n")
    sys.path.insert(0, meta_dir)


def rel_to_base(path: str, bases: list[str]) -> str | None:
    """'click/core.py' if `path` is inside one of the package base dirs, else None."""
    real = os.path.realpath(path)
    for base in bases:
        b = os.path.realpath(base)
        if real.startswith(b + os.sep):
            return os.path.relpath(real, b)
    return None


# -------------------------------------------------------------------- outcomes
def raise_outcome(exc: BaseException, bases: list[str]) -> dict[str, Any]:
    """Serialize an exception. The innermost frame is the last traceback frame inside the
    library; if the traceback never enters the library, the last frame overall."""
    frames = traceback.extract_tb(exc.__traceback__)
    innermost = None
    for fr in frames:
        rel = rel_to_base(fr.filename, bases)
        if rel is not None:
            innermost = f"{rel}:{fr.lineno}"
    if innermost is None and frames:
        last = frames[-1]
        innermost = f"{os.path.basename(last.filename)}:{last.lineno}"
    if isinstance(exc, SyntaxError) and innermost is None and exc.filename:
        rel = rel_to_base(exc.filename, bases)
        innermost = f"{rel or os.path.basename(exc.filename)}:{exc.lineno}"
    return {"kind": "raise", "type": type(exc).__name__, "msg": normalize(str(exc))[:MAX_MSG],
            "innermost_frame": innermost}


def return_outcome(value: Any) -> dict[str, Any]:
    try:
        text = repr(value)
    except Exception as exc:  # a broken __repr__ is itself an observation
        text = f"<repr failed: {type(exc).__name__}: {exc}>"
    return {"kind": "return", "repr": normalize(text)[:MAX_REPR]}


@contextlib.contextmanager
def time_limit(seconds: float):
    if seconds and hasattr(signal, "SIGALRM"):
        old = signal.signal(signal.SIGALRM, _on_alarm)
        signal.setitimer(signal.ITIMER_REAL, seconds)
        try:
            yield
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, old)
    else:
        yield


class LineTracer:
    """Records executed line numbers in selected library files with sys.settrace
    (for the leniency study; avoids a dependency on coverage.py)."""

    def __init__(self, rel_paths: list[str], bases: list[str]):
        self.wanted = set(rel_paths)
        self.bases = bases
        self.lines: dict[str, set[int]] = {p: set() for p in rel_paths}
        self._cache: dict[str, str | None] = {}

    def _rel(self, filename: str) -> str | None:
        if filename not in self._cache:
            rel = rel_to_base(filename, self.bases)
            self._cache[filename] = rel if rel in self.wanted else None
        return self._cache[filename]

    def __call__(self, frame, event, arg):
        rel = self._rel(frame.f_code.co_filename)
        if rel is None:
            return None  # do not trace lines of other files
        if event in ("line", "call"):
            self.lines[rel].add(frame.f_lineno)
        return self

    def result(self) -> dict[str, list[int]]:
        return {p: sorted(v) for p, v in self.lines.items()}


# ---------------------------------------------------------------------- probes
def run_probe(spec: dict[str, Any], bases: list[str], timeout_s: float,
              trace_for: list[str]) -> dict[str, Any]:
    name = spec["name"]
    result: dict[str, Any] = {"name": name}
    out, err = io.StringIO(), io.StringIO()
    tracer = LineTracer(trace_for, bases) if trace_for else None
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        # 1. import: an import-time error (e.g. a SyntaxError in a mutated library) is a raise outcome
        module = None
        try:
            with time_limit(timeout_s):
                mod_name = f"_probe_{re.sub(r'[^0-9A-Za-z_]', '_', name)}"
                loader_spec = importlib.util.spec_from_file_location(mod_name, spec["path"])
                module = importlib.util.module_from_spec(loader_spec)
                sys.modules[mod_name] = module
                loader_spec.loader.exec_module(module)
        except BaseException as exc:  # noqa: BLE001 - every failure is an observation
            module = None  # half-imported: do not call observe()/test_claim() on it
            result["outcome"] = raise_outcome(exc, bases)
            result["status"] = "error"
            result["message"] = f"import failed: {type(exc).__name__}: {exc}"[:MAX_MSG]
        if module is not None:
            # 2. observe(): the observed value or exception
            try:
                if tracer:
                    sys.settrace(tracer)
                with time_limit(timeout_s):
                    value = module.observe()
                result["outcome"] = return_outcome(value)
            except BaseException as exc:  # noqa: BLE001
                result["outcome"] = raise_outcome(exc, bases)
            finally:
                sys.settrace(None)
            # 3. test_claim(): pass / fail (AssertionError) / error (anything else)
            try:
                with time_limit(timeout_s):
                    module.test_claim()
                result["status"], result["message"] = "pass", ""
            except AssertionError as exc:
                result["status"], result["message"] = "fail", normalize(str(exc))[:MAX_MSG]
            except BaseException as exc:  # noqa: BLE001
                result["status"] = "error"
                result["message"] = f"{type(exc).__name__}: {normalize(str(exc))}"[:MAX_MSG]
    result["stdout"] = out.getvalue()[:MAX_MSG]
    result["stderr"] = err.getvalue()[:MAX_MSG]
    if tracer:
        result["executed_lines"] = tracer.result()
    return result


def run_probes_job(job: dict[str, Any]) -> dict[str, Any]:
    bases = setup_paths(job)
    timeout_s = float(job.get("timeout_s", 10))
    trace_for = job.get("trace_lines_for") or []
    return {"kind": "probes", "results": [run_probe(p, bases, timeout_s, trace_for) for p in job["probes"]]}


# ----------------------------------------------------------------------- pytest
class _Collector:
    """pytest plugin that records one status per test node id."""

    def __init__(self):
        self.tests: dict[str, dict[str, str]] = {}

    def pytest_runtest_logreport(self, report):
        entry = self.tests.setdefault(report.nodeid, {"status": "passed", "message": ""})
        if report.failed:
            entry["status"] = "failed" if report.when == "call" else "error"
            crash = getattr(report.longrepr, "reprcrash", None)
            entry["message"] = normalize(crash.message if crash else str(report.longrepr))[:MAX_MSG]
        elif report.skipped and entry["status"] == "passed":
            entry["status"] = "skipped"

    def pytest_collectreport(self, report):
        if report.failed:
            self.tests.setdefault(report.nodeid or "<collection>", {
                "status": "error", "message": normalize(str(report.longrepr))[-MAX_MSG:]})


def run_pytest_job(job: dict[str, Any]) -> dict[str, Any]:
    setup_paths(job)
    import pytest  # only needed for this job kind
    os.chdir(job["lib_root"])
    collector = _Collector()
    args = list(job["node_ids"]) + ["-p", "no:cacheprovider", "-q", "--no-header", "-o", "addopts=",
                                    "--basetemp", os.path.join(job.get("tmp_dir", "/tmp"), "pytest-basetemp")]
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = pytest.main(args, plugins=[collector])
    return {"kind": "pytest", "exit_code": int(code), "tests": collector.tests,
            "output_tail": out.getvalue()[-MAX_MSG * 2:]}


def main(argv: list[str]) -> int:
    with open(argv[1], encoding="utf-8") as fh:
        job = json.load(fh)
    real_stdout = sys.stdout
    try:
        if job["kind"] == "probes":
            result = run_probes_job(job)
        elif job["kind"] == "pytest":
            result = run_pytest_job(job)
        else:
            raise ValueError(f"unknown job kind {job['kind']!r}")
    except BaseException as exc:  # noqa: BLE001 - always answer with JSON
        result = {"kind": "runner_error", "type": type(exc).__name__, "msg": str(exc)[:MAX_MSG]}
    result["cpu_s"] = round(time.process_time(), 4)  # CPU seconds of this job (a reported cost metric)
    real_stdout.write(json.dumps(result) + "\n")
    real_stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
