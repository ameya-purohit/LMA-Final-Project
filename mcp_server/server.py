"""A local MCP server exposing the extension's analysis and execution tools (E6; optional).

Model Context Protocol (MCP) is a standard way for an AI application to call tools that live in another process.
This server holds one question's frozen tree, its Docker sandbox session and its code graph, and offers:

  code analysis   graph_summary, call_graph, static_slice, graph_candidates, snippet
  execution       run_probe, trace, run_experiments (mutation checks), validate_patch
  results         experiment_results, stats

Every tool is a thin wrapper over the same Python functions E1-E5 call in-process (`experiments/backend.py`), so MCP
is only a transport: it does not replace the execution engine, and switching it on must not change any result.
Results are returned as JSON text. The server speaks MCP over stdin/stdout, so nothing else may print to stdout.

Run (normally started by `mcp_server/client.py`):
    python -m mcp_server.server --library click --commit <sha>
    python -m mcp_server.server --toylib            # tests only: trusted local backend on the toylib fixture
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from core.config import REPO_ROOT, load_config

TOYLIB = REPO_ROOT / "tests" / "fixtures" / "toylib"
mcp = FastMCP("rtci-tools")
STATE: dict[str, Any] = {}


def _backend() -> Any:
    return STATE["backend"]


def _j(x: Any) -> str:
    return json.dumps(x, default=str)


@mcp.tool()
def run_probe(code: str, controls: list[str]) -> str:
    """Run a claim probe and its control probes in the offline sandbox. Returns the report as JSON."""
    return _j(_backend().run_probe(code, controls))


@mcp.tool()
def trace(claim: str, controls: list[str]) -> str:
    """Executed library lines of the claim probe and of each control, as JSON [claim, control_1, ...]."""
    return _j(_backend().trace(claim, controls))


@mcp.tool()
def graph_candidates(seeds: list[list], claim_lines: dict | None = None, control_lines: list[dict] | None = None,
                     raise_site: list | None = None, limit: int = 15) -> str:
    """Suspicious lines from the backward slices of the seeds, ordered by the executed-line spectrum."""
    out = _backend().graph_candidates([tuple(s) for s in seeds], claim_lines, control_lines,
                                      tuple(raise_site) if raise_site else None, limit)
    return _j([list(x) for x in out])


@mcp.tool()
def graph_summary(locs: list[list]) -> str:
    """Each line's function, callers, callees and backward slice, as text."""
    return _j(_backend().graph_summary([tuple(x) for x in locs]))


@mcp.tool()
def call_graph(symbol: str) -> str:
    """Callers and callees of a function in the static call graph."""
    g = _backend().graph
    return _j([{"function": f.qualname, "path": f.path, "lines": [f.start, f.end],
                "callers": g.neighbours(f.qualname)[0], "callees": g.neighbours(f.qualname)[1]} for f in g.find(symbol)[:3]])


@mcp.tool()
def static_slice(path: str, line: int) -> str:
    """Lines of the enclosing function that can affect the given line (backward slice), nearest first."""
    return _j([list(x) for x in _backend().graph.static_slice(path, line)])


@mcp.tool()
def run_experiments(claim: str, controls: list[str], candidates: list[list], hypotheses: list[dict],
                    policy: dict) -> str:
    """Mutation experiments on the candidate lines under the given policy (ranked or active; pairs on or off)."""
    hyps = [{**h, "locations": [tuple(x) for x in h.get("locations", [])]} for h in hypotheses]
    return _j(_backend().run_experiments(claim, controls, [tuple(c) for c in candidates], hyps, policy))


@mcp.tool()
def experiment_results() -> str:
    """The experiments run so far for this question, with their verdicts."""
    eng = _backend().engine
    return _j(eng.summary() if eng else {"experiments": []})


@mcp.tool()
def validate_patch(path: str, line: int, new_text: str) -> str:
    """Replace one line in a throw-away copy and re-run the claim probe and controls."""
    return _j(_backend().validate_patch(path, line, new_text))


@mcp.tool()
def snippet(path: str, line: int, context: int = 2) -> str:
    """Numbered lines of the frozen code around a line."""
    return _j(_backend().snippet(path, line, context))


@mcp.tool()
def stats() -> str:
    """Sandbox CPU seconds and jobs run so far."""
    s = STATE.get("session")
    return _j({"cpu_seconds": round(float(getattr(s, "cpu_seconds", 0.0)), 3), "jobs": getattr(s, "jobs_run", 0)})


def setup(args: argparse.Namespace) -> None:
    from experiments.backend import InProcessBackend
    config = load_config()
    if args.toylib:
        # Trusted, hand-written toylib probes only (CLAUDE.md §2.5): used by the unit test of the MCP round trip.
        from sandbox.session import LocalBackend
        session = LocalBackend(TOYLIB, "toylib", trusted=True, config=config)
        session.start()
        tree, package, root = TOYLIB, "toylib", "src"
    else:
        from tools.workspace import Workspace, docker_session_factory
        q = {"library": args.library, "frozen_commit": args.commit}
        if args.variant:
            q["tree_variant"] = args.variant
        ws = Workspace.for_question(q, config, session_factory=docker_session_factory)
        STATE["workspace"] = ws
        session = ws.session
        tree, package, root = ws.tree, ws.package, ws.source_root
    STATE["session"] = session
    STATE["backend"] = InProcessBackend(lambda: session, Path(tree), package, root, config)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--library")
    ap.add_argument("--commit")
    ap.add_argument("--variant")
    ap.add_argument("--toylib", action="store_true")
    args = ap.parse_args(argv)
    if not args.toylib and not (args.library and args.commit):
        ap.error("give --library and --commit, or --toylib")
    setup(args)
    try:
        mcp.run(transport="stdio")
    finally:
        session = STATE.get("session")
        cleanup = getattr(session, "cleanup", None)
        if cleanup:
            cleanup()
    return 0


if __name__ == "__main__":
    sys.exit(main())
