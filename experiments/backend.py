"""One interface to the deterministic analysis and execution tools, used by the multi-agent orchestrator.

`InProcessBackend` calls the Python functions directly (E1-E5). `mcp_server.client.MCPBackend` offers the same
methods but sends every call to a local MCP server (E6). The orchestrator only sees this interface, so E5 and E6 run
identical control logic and differ only in how a tool call travels. All results are plain JSON-able dicts, so
they cross the MCP boundary unchanged.
"""

from __future__ import annotations

from typing import Any, Protocol

Loc = tuple[str, int]


class Backend(Protocol):
    def run_probe(self, code: str, controls: list[str]) -> dict[str, Any]: ...
    def trace(self, claim: str, controls: list[str]) -> list[dict[str, list[int]]]: ...
    def graph_candidates(self, seeds: list[Loc], claim_lines: dict | None, control_lines: list[dict] | None,
                         raise_site: Loc | None, limit: int) -> list[Loc]: ...
    def graph_summary(self, locs: list[Loc]) -> str: ...
    def run_experiments(self, claim: str, controls: list[str], candidates: list[Loc], hypotheses: list[dict],
                        policy: dict[str, Any]) -> dict[str, Any]: ...
    def validate_patch(self, path: str, line: int, new_text: str) -> dict[str, Any]: ...
    def snippet(self, path: str, line: int, context: int) -> str: ...
    def close(self) -> None: ...


class InProcessBackend:
    """The tools as plain function calls on this question's sandbox session and code graph."""

    def __init__(self, session_getter: Any, tree: Any, package: str, source_root: str, config: dict[str, Any],
                 tracer: Any = None):
        self._session_getter = session_getter    # called on first use, so a question that never runs code starts no container
        self.tree, self.package, self.source_root = tree, package, source_root
        self.config = config
        self.tracer = tracer
        self._graph = None
        self.engine = None
        self.cpu_seconds = 0.0

    @property
    def session(self) -> Any:
        return self._session_getter()

    @property
    def graph(self) -> Any:
        if self._graph is None:
            from codegraph.graph import CodeGraph
            self._graph = CodeGraph(self.tree, self.package, self.source_root)
        return self._graph

    def run_probe(self, code: str, controls: list[str]) -> dict[str, Any]:
        from tools.probe import render, run_probe
        report = run_probe(self.session, code, controls, tracer=self.tracer)
        return {"report": report.to_dict(), "text": render(report), "blocked": report.blocked, "error": report.error,
                "executable": report.executable}

    def trace(self, claim: str, controls: list[str]) -> list[dict[str, list[int]]]:
        from experiments.engine import ExperimentEngine
        return ExperimentEngine(self.session, claim, controls).trace(self.graph.package_files())

    def graph_candidates(self, seeds: list[Loc], claim_lines: dict | None, control_lines: list[dict] | None,
                         raise_site: Loc | None, limit: int = 15) -> list[Loc]:
        from codegraph.rank import graph_candidates, spectrum
        g = self.graph
        seeds = [(g.normalize(p) or p, int(ln)) for p, ln in seeds if g.normalize(p)]
        spec = spectrum(claim_lines, control_lines or [], g.to_repo_path) if claim_lines else None
        rs = (g.normalize(raise_site[0]), int(raise_site[1])) if raise_site and g.normalize(raise_site[0]) else None
        return [tuple(x) for x in graph_candidates(g, seeds, spectrum_scores=spec, raise_site=rs, limit=limit)]

    def graph_summary(self, locs: list[Loc]) -> str:
        """For the Code Analyst: each suspect's function, its callers and callees, and its backward slice."""
        g = self.graph
        out = []
        for p, ln in locs[:4]:
            f = g.function_at(p, int(ln))
            if f is None:
                continue
            callers, callees = g.neighbours(f.qualname)
            sl = [x[1] for x in g.static_slice(f.path, int(ln))][:15]
            out.append(f"- {f.path}:{ln} in {f.qualname} (lines {f.start}-{f.end}); callers: {', '.join(callers[:5]) or '-'}; "
                       f"callees: {', '.join(callees[:8]) or '-'}; lines that can affect it: {sl}")
        return "\n".join(out)

    def run_experiments(self, claim: str, controls: list[str], candidates: list[Loc], hypotheses: list[dict],
                        policy: dict[str, Any]) -> dict[str, Any]:
        from experiments.engine import ExperimentEngine
        use_graph = policy.get("graph", False)
        self.engine = ExperimentEngine(self.session, claim, controls, graph=self.graph if use_graph else None,
                                       single_budget=policy.get("single_budget", 8),
                                       pair_budget=policy.get("pair_budget", 3),
                                       max_mutants=policy.get("max_mutants", 12), tracer=self.tracer)
        stop = None
        cands = [(p, int(ln)) for p, ln in candidates]
        if policy.get("active"):
            stop = self.engine.run_active(cands, hypotheses)
        else:
            self.engine.run_ranked(cands)
        if policy.get("pairs"):
            self.engine.run_pairs(cands)
        return {**self.engine.summary(), "stop": stop}

    def validate_patch(self, path: str, line: int, new_text: str) -> dict[str, Any]:
        if self.engine is None:
            return {"validated": False, "reason": "no experiments were run"}
        return self.engine.validate_patch(path, int(line), new_text)

    def snippet(self, path: str, line: int, context: int = 2) -> str:
        g = self.graph
        rel = g.normalize(path)
        if rel is None:
            return ""
        lines = (self.tree / rel).read_text(encoding="utf-8", errors="replace").splitlines()
        lo, hi = max(1, line - context), min(len(lines), line + context)
        return "\n".join(f"{i:5d}  {lines[i - 1]}" for i in range(lo, hi + 1))

    def close(self) -> None:
        pass
