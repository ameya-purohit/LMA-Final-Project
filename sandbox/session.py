"""Run jobs (probes, mutants, repo tests) in the Docker sandbox, one warm container per question.

`SandboxSession` starts a container with no network, CPU/memory/pid limits, a
read-only root filesystem, a tmpfs /tmp, the frozen tree mounted read-only at
/work/lib and a host scratch dir mounted read-only at /work/scratch. The host
writes job files (and, for mutation, mutant copies) into the scratch dir; the
container only reads them and answers on stdout.

`LocalBackend` runs the same runner in a local subprocess. It is ONLY for the
hand-written, trusted toylib fixture in unit tests (CLAUDE.md §2.5) and refuses
to start unless `trusted=True` is passed.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

RUNNER = Path(__file__).resolve().parent / "runner.py"
CONTAINER_LIB = "/work/lib"
CONTAINER_SCRATCH = "/work/scratch"
CONTAINER_RUNNER = "/opt/runner/runner.py"


class SandboxError(RuntimeError):
    """The sandbox itself failed (Docker missing, container died, unreadable output)."""


def detect_source_root(tree: Path, package: str) -> str:
    """'src' or '.': whichever directory holds <package>/__init__.py (CLAUDE.md §6.2)."""
    for cand in ("src", "."):
        if (tree / cand / package / "__init__.py").is_file():
            return cand
    raise SandboxError(f"cannot find {package}/__init__.py under {tree} (looked in src/ and .)")


_VERSION_PATTERNS = [
    (Path("{root}/{pkg}/__init__.py"), r"""__version__\s*=\s*["']([^"']+)["']"""),
    (Path("pyproject.toml"), r"""(?m)^version\s*=\s*["']([^"']+)["']"""),
    (Path("setup.cfg"), r"""(?m)^version\s*=\s*([^\s]+)"""),
    (Path("setup.py"), r"""version\s*=\s*["']([^"']+)["']"""),
]


def detect_version(tree: Path, package: str, source_root: str) -> str:
    """Best-effort version string for the metadata shim; '0.0.0' if none is written down."""
    for rel, pattern in _VERSION_PATTERNS:
        path = tree / str(rel).format(root=source_root, pkg=package)
        if path.is_file():
            m = re.search(pattern, path.read_text(encoding="utf-8", errors="replace"))
            if m and not m.group(1).startswith(("attr:", "file:")):
                return m.group(1)
    return "0.0.0"


class _BaseSession:
    """Shared job plumbing. Subclasses define `_exec(job_container_path, timeout)` and path mapping."""

    lib_path: str
    scratch: Path

    def __init__(self, tree: str | Path, package: str, *, dist_name: str | None = None,
                 config: dict[str, Any] | None = None):
        self.tree = Path(tree).resolve()
        self.package = package
        sb = (config or {}).get("sandbox", {})
        self.probe_timeout_s = sb.get("probe_timeout_s", 10)
        self.job_timeout_s = sb.get("job_timeout_s", 120)
        self.source_root = detect_source_root(self.tree, package)
        self.dist = {"name": dist_name or package, "version": detect_version(self.tree, package, self.source_root)}
        self.cpu_seconds = 0.0
        self.jobs_run = 0

    # path helpers ----------------------------------------------------------
    def to_inner(self, host_path: Path) -> str:
        raise NotImplementedError

    def job_dir(self) -> tuple[Path, str]:
        """A fresh directory for one job's files: (host path, path as the runner sees it)."""
        d = self.scratch / "jobs" / uuid.uuid4().hex[:12]
        d.mkdir(parents=True)
        os.chmod(d, 0o755)
        return d, self.to_inner(d)

    def write(self, directory: Path, name: str, text: str) -> str:
        path = directory / name
        path.write_text(text, encoding="utf-8")
        os.chmod(path, 0o644)
        return self.to_inner(path)

    # jobs -----------------------------------------------------------------
    def run_job(self, job: dict[str, Any]) -> dict[str, Any]:
        """Fill in library defaults, write the job file, run it, and parse the JSON answer."""
        full = {"lib_root": self.lib_path, "source_root": self.source_root, "package": self.package,
                "dist": self.dist, "timeout_s": self.probe_timeout_s, **job}
        d, inner = self.job_dir()
        job_inner = self.write(d, "job.json", json.dumps(full))
        out = self._exec(job_inner, self.job_timeout_s)
        self.jobs_run += 1
        try:
            result = json.loads(out.strip().splitlines()[-1])
        except (json.JSONDecodeError, IndexError) as exc:
            raise SandboxError(f"runner gave no JSON: {out[-500:]!r}") from exc
        self.cpu_seconds += float(result.get("cpu_s", 0.0))
        return result

    def run_probes(self, probes: list[tuple[str, str]], *, overlay: str | None = None,
                   trace_lines_for: list[str] | None = None) -> dict[str, Any]:
        """Run [(name, code), ...] in one process (claim and its controls run together)."""
        d, _ = self.job_dir()
        specs = [{"name": name, "path": self.write(d, f"{name}.py", code)} for name, code in probes]
        job: dict[str, Any] = {"kind": "probes", "probes": specs}
        if overlay:
            job["overlay"] = overlay
        if trace_lines_for:
            job["trace_lines_for"] = trace_lines_for
        return self.run_job(job)

    def run_pytest(self, node_ids: list[str], *, lib_root: str | None = None) -> dict[str, Any]:
        """Run repo tests by node id; `lib_root` may point at a patched tree copy inside scratch."""
        job: dict[str, Any] = {"kind": "pytest", "node_ids": list(node_ids)}
        if lib_root:
            job["lib_root"] = lib_root
        return self.run_job(job)

    def _exec(self, job_inner: str, timeout: float) -> str:
        raise NotImplementedError

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.close()

    def start(self) -> None:  # pragma: no cover - overridden
        pass

    def close(self) -> None:  # pragma: no cover - overridden
        pass


class SandboxSession(_BaseSession):
    """One warm, locked-down Docker container for one question."""

    def __init__(self, tree: str | Path, package: str, *, image: str | None = None,
                 dist_name: str | None = None, config: dict[str, Any] | None = None):
        super().__init__(tree, package, dist_name=dist_name, config=config)
        sb = (config or {}).get("sandbox", {})
        self.image = image or sb.get("image", "rtci-sandbox:py310")
        self.limits = {"cpus": str(sb.get("cpus", 1)), "memory": sb.get("memory", "1g"),
                       "pids": str(sb.get("pids_limit", 256))}
        self.lib_path = CONTAINER_LIB
        self.scratch = Path(tempfile.mkdtemp(prefix="rtci-scratch-"))
        os.chmod(self.scratch, 0o755)
        self.container: str | None = None

    def to_inner(self, host_path: Path) -> str:
        rel = Path(host_path).resolve().relative_to(self.scratch.resolve())
        return f"{CONTAINER_SCRATCH}/{rel.as_posix()}"

    def docker_run_args(self) -> list[str]:
        # Run as the host user's uid (never root) so the container can read the host's files.
        uid = os.getuid() if hasattr(os, "getuid") else 10001
        user = f"{uid}:{os.getgid()}" if uid != 0 else "10001:10001"
        return ["docker", "run", "-d", "--rm", "--name", f"rtci-{uuid.uuid4().hex[:10]}",
                "--network", "none", "--cpus", self.limits["cpus"], "--memory", self.limits["memory"],
                "--pids-limit", self.limits["pids"], "--read-only", "--tmpfs", "/tmp:rw,size=256m",
                "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--user", user,
                "-v", f"{self.tree}:{CONTAINER_LIB}:ro", "-v", f"{self.scratch}:{CONTAINER_SCRATCH}:ro",
                self.image, "sleep", "infinity"]

    def start(self) -> None:
        if shutil.which("docker") is None:
            raise SandboxError("docker CLI not found")
        p = subprocess.run(self.docker_run_args(), capture_output=True, text=True, timeout=120)
        if p.returncode != 0:
            raise SandboxError(f"docker run failed: {p.stderr.strip()[:500]}")
        self.container = p.stdout.strip()

    def exec_raw(self, argv: list[str], timeout: float = 60) -> subprocess.CompletedProcess:
        """Run a command in the container (used by tests to probe the sandbox itself)."""
        return subprocess.run(["docker", "exec", self.container, *argv], capture_output=True, text=True,
                              timeout=timeout)

    def _exec(self, job_inner: str, timeout: float) -> str:
        if not self.container:
            raise SandboxError("session not started")
        try:
            p = self.exec_raw(["python", CONTAINER_RUNNER, job_inner], timeout=timeout)
        except subprocess.TimeoutExpired:
            # The runner hung past its own alarms (e.g. inside C code): replace the container.
            self.close()
            self.start()
            return json.dumps({"kind": "runner_error", "type": "JobTimeout",
                               "msg": f"job exceeded {timeout}s; container restarted"})
        if p.returncode != 0 and not p.stdout.strip():
            raise SandboxError(f"runner exited {p.returncode}: {p.stderr.strip()[-500:]}")
        return p.stdout

    def close(self) -> None:
        if self.container:
            subprocess.run(["docker", "rm", "-f", self.container], capture_output=True, timeout=60)
            self.container = None

    def cleanup(self) -> None:
        """Delete the scratch dir (mutant copies and job files are throw-away)."""
        self.close()
        shutil.rmtree(self.scratch, ignore_errors=True)


class LocalBackend(_BaseSession):
    """The same runner in a local subprocess. Trusted toylib code only."""

    def __init__(self, tree: str | Path, package: str, *, trusted: bool = False,
                 dist_name: str | None = None, config: dict[str, Any] | None = None):
        if trusted is not True:
            raise PermissionError("LocalBackend runs code on the host; it is only for the hand-written, "
                                  "trusted toylib fixture. Pass trusted=True to confirm. "
                                  "LLM-generated code must run in SandboxSession.")
        super().__init__(tree, package, dist_name=dist_name, config=config)
        self.lib_path = str(self.tree)
        self.scratch = Path(tempfile.mkdtemp(prefix="rtci-local-"))

    def to_inner(self, host_path: Path) -> str:
        return str(Path(host_path).resolve())

    def run_job(self, job: dict[str, Any]) -> dict[str, Any]:
        job = {"meta_dir": str(self.scratch / "meta"), "tmp_dir": str(self.scratch), **job}
        return super().run_job(job)

    def _exec(self, job_inner: str, timeout: float) -> str:
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0", "TZ": "UTC"}
        p = subprocess.run([sys.executable, str(RUNNER), job_inner], capture_output=True, text=True,
                           timeout=timeout, env=env, cwd=str(self.scratch))
        if p.returncode != 0 and not p.stdout.strip():
            raise SandboxError(f"runner exited {p.returncode}: {p.stderr.strip()[-500:]}")
        return p.stdout

    def cleanup(self) -> None:
        shutil.rmtree(self.scratch, ignore_errors=True)
