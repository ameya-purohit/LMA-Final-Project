"""`run_probe`: run a claim probe and its control probes in the sandbox.

A probe is a Python file with two functions (CLAUDE.md §6.3):
    observe()     performs the scenario and returns the observed value (may raise)
    test_claim()  asserts the claim
The claim probe and its 1-2 controls run in one process. Before anything runs,
every file passes the AST policy check (sandbox/policy.py); a violation blocks
the whole run and is logged as an unsafe attempt.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from sandbox import policy


@dataclass
class ProbeResult:
    name: str
    outcome: dict[str, Any] | None   # {"kind": "return", "repr"} or {"kind": "raise", "type", "msg", "innermost_frame"}
    status: str                      # pass | fail | error
    message: str = ""
    stdout: str = ""
    executed_lines: dict[str, list[int]] | None = None


@dataclass
class ProbeReport:
    blocked: bool = False
    violations: list[dict[str, Any]] = field(default_factory=list)
    results: list[ProbeResult] = field(default_factory=list)
    error: str | None = None         # the sandbox itself failed (not the probe)
    cpu_s: float = 0.0

    @property
    def claim(self) -> ProbeResult | None:
        return self.results[0] if self.results else None

    @property
    def controls(self) -> list[ProbeResult]:
        return self.results[1:]

    @property
    def executable(self) -> bool:
        """The claim probe imported and ran (it may still pass or fail)."""
        c = self.claim
        return bool(c and not self.blocked and not self.error and not c.message.startswith("import failed"))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def check_policy(codes: list[tuple[str, str]]) -> list[dict[str, Any]]:
    """Policy violations over all probe files, each tagged with its probe name."""
    out = []
    for name, code in codes:
        out.extend({"probe": name, **v.to_dict()} for v in policy.check(code))
    return out


def run_probe(session: Any, code: str, controls: list[str] | tuple[str, ...] = (), *, tracer: Any = None,
              overlay: str | None = None, trace_lines_for: list[str] | None = None) -> ProbeReport:
    """Policy-check, then run the claim probe and its controls together in `session`."""
    named = [("claim", code)] + [(f"control_{i + 1}", c) for i, c in enumerate(controls)]
    violations = check_policy(named)
    if violations:
        if tracer is not None:
            tracer.write("unsafe_attempt", tool="run_probe", violations=violations)
        return ProbeReport(blocked=True, violations=violations)
    raw = session.run_probes(named, overlay=overlay, trace_lines_for=trace_lines_for)
    return parse_runner_output(raw)


def parse_runner_output(raw: dict[str, Any]) -> ProbeReport:
    if raw.get("kind") != "probes":
        return ProbeReport(error=f"{raw.get('type', 'error')}: {raw.get('msg', raw)}", cpu_s=raw.get("cpu_s", 0.0))
    results = [ProbeResult(name=r["name"], outcome=r.get("outcome"), status=r["status"],
                           message=r.get("message", ""), stdout=r.get("stdout", ""),
                           executed_lines=r.get("executed_lines")) for r in raw["results"]]
    return ProbeReport(results=results, cpu_s=raw.get("cpu_s", 0.0))


def describe_outcome(outcome: dict[str, Any] | None) -> str:
    if not outcome:
        return "no outcome"
    if outcome["kind"] == "return":
        return f"returned {outcome['repr']}"
    return f"raised {outcome['type']}: {outcome['msg']} (at {outcome.get('innermost_frame')})"


def render(report: ProbeReport) -> str:
    """Plain-text summary for the model. Observed outputs are reported literally."""
    if report.blocked:
        lines = ["BLOCKED by the sandbox policy; nothing was run. Violations:"]
        lines += [f"- {v['probe']} line {v['line']}: {v['rule']} ({v['detail']})" for v in report.violations]
        lines.append("Probes may only import the library and safe standard modules, and write only under /tmp.")
        return "\n".join(lines)
    if report.error:
        return f"SANDBOX ERROR (not a probe result): {report.error}"
    lines = []
    for r in report.results:
        lines.append(f"{r.name}: test_claim {r.status.upper()}"
                     + (f" ({r.message})" if r.message else "") + f"; observe() {describe_outcome(r.outcome)}")
    return "\n".join(lines)
