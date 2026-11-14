"""The multi-agent system E1-E6 (exploratory extension). A plain Python orchestrator, no agent framework.

Five roles, run in a fixed order. Three are LLM agents, each with its own conversation and its own instructions;
two are deterministic code:

  1. Bug Investigator (LLM, read-only tools): expected vs actual behaviour, a scenario, 2-4 competing hypotheses.
  2. Probe Engineer (LLM): a reproduce probe, 1-2 controls, optional boundary and hypothesis-distinguishing probes;
     run in the sandbox and repaired up to twice if they cannot run.
  3. Code Analyst (LLM, read-only tools; + code graph from E3): ranks suspicious lines. From E3 its ranking is fused
     with a deterministic one from slicing and executed-line spectra.
  4. Experiment Engineer (code, `experiments/`): mutation checks on the ranked lines; pairs from E4; information-gain
     order from E5.
  5. Causal Verifier (LLM): accepts, rejects or leaves open each hypothesis from the evidence, writes the answer and
     an optional one-line patch, which code then validates by re-running the probes.

Agents never exchange free text with each other: the orchestrator passes the typed objects of `multiagent/schemas.py`.
The final ranking of locations and every grade-like field are computed in code, not by a model. Flags in
`config.multiagent.flags` switch on E2-E6 one at a time; everything else is shared with the locked systems (model,
client, cache, sandbox, tools, output schema).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from agent.toolloop import MeteredClient, OutOfRequests, StepBudget, ToolLoop
from llm.types import Message
from multiagent.prompts import load
from multiagent.schemas import Investigation, Probes, Ranking, Verdict
from tools.registry import Budget, ToolRegistry

Loc = tuple[str, int]
CLASS_ORDER = {"accepted": 0, "accepted_pair": 1, "cited": 2, "inconclusive": 3, "untested": 4, "rejected": 5}


class _GraphQuery(BaseModel):
    symbol: str = Field(description="A function or method name, e.g. Option.get_default")


class _SliceQuery(BaseModel):
    path: str
    line: int = Field(ge=1)


def describe(outcome: dict[str, Any] | None) -> str:
    if not outcome:
        return "no outcome"
    if outcome.get("kind") == "return":
        return f"returned {str(outcome.get('repr'))[:300]}"
    return f"raised {outcome.get('type')}: {str(outcome.get('msg'))[:200]} (at {outcome.get('innermost_frame')})"


def probe_status(run: dict[str, Any], package: str) -> str:
    """'reproduced', 'not_reproduced' (ran, but the reported behaviour did not happen) or 'broken' (the probe itself
    failed). Same rule as the locked agent: an exception raised inside the library is an observation."""
    rep = run.get("report") or {}
    results = rep.get("results") or []
    if run.get("blocked") or run.get("error") or not results:
        return "broken"
    claim, controls = results[0], results[1:]
    if (claim.get("message") or "").startswith("import failed") or \
            any((c.get("message") or "").startswith("import failed") for c in controls):
        return "broken"
    if claim["status"] == "pass":
        return "reproduced"
    if claim["status"] == "fail":
        return "not_reproduced"
    o = claim.get("outcome") or {}
    if o.get("kind") == "raise" and str(o.get("innermost_frame", "")).startswith(package + "/"):
        return "not_reproduced"
    return "broken"


class MultiAgentSystem:
    def __init__(self, workspace: Any, client: Any, config: dict[str, Any], *, tracer: Any = None,
                 backend: Any = None):
        self.ws = workspace
        self.config = config
        self.tracer = tracer
        self.ma = config["multiagent"]
        self.flags = self.ma["flags"]
        self.llm = MeteredClient(client, self.ma["max_requests"])
        self.registry = ToolRegistry(workspace, budget=Budget(self.ma["max_probe_runs"], 0), tracer=tracer)
        self.loop = ToolLoop(self.llm, self.registry, max_tools_per_turn=config["agent"]["max_tools_per_turn"],
                             tracer=tracer)
        self.backend = backend or self._make_backend()
        self.local_graph = None
        self.log: list[dict[str, Any]] = []
        self.probe_runs = 0
        self.steps_used = 0

    def _make_backend(self) -> Any:
        if self.flags.get("mcp"):
            from mcp_server.client import MCPBackend
            return MCPBackend.for_workspace(self.ws, self.config)
        from experiments.backend import InProcessBackend
        return InProcessBackend(lambda: self.ws.session, self.ws.tree, self.ws.package, self.ws.source_root,
                                self.config, self.tracer)

    def note(self, decision: str, **info: Any) -> None:
        self.log.append({"decision": decision, **info})

    # --------------------------------------------------------------- helpers
    def norm(self, path: str) -> str:
        """Repository-relative spelling of a package path (`click/core.py` -> `src/click/core.py`)."""
        p = path.strip().lstrip("./")
        root = self.ws.source_root
        if root not in (".", "") and p.startswith(self.ws.package + "/"):
            p = f"{root}/{p}"
        return p

    def valid(self, loc: Loc) -> bool:
        try:
            target = self.ws.resolve(loc[0])
        except ValueError:
            return False
        return target.is_file() and target.suffix == ".py" and f"/{self.ws.package}/" in f"/{loc[0]}"

    def ask(self, history: list[Message], name: str, model: type[BaseModel], description: str, *,
            tools: tuple[str, ...] = (), steps: int = 0, reserve: int = 0) -> Any:
        """One agent turn-loop until it calls its terminal tool. None if the request budget runs out."""
        budget = StepBudget(steps)
        try:
            out = self.loop.run(history, tools, {name: (description, model)}, budget, reserve=reserve)
        except OutOfRequests:
            return None
        finally:
            self.steps_used += budget.used
        return out.parsed

    def run_probe(self, code: str, controls: list[str]) -> dict[str, Any]:
        self.probe_runs += 1
        run = self.backend.run_probe(code, controls)
        if run.get("blocked"):
            self.registry.counts["unsafe_attempts"] += 1
        return run

    # ------------------------------------------------------------ retrieval
    def _setup_retrieval(self, question: str) -> str:
        """Starting material, and in E2+ the hybrid index behind the search tools (same top 5 code + top 3 docs)."""
        from retrieval.index import format_starting_material
        if self.flags.get("graph"):
            from codegraph.graph import CodeGraph
            self.local_graph = CodeGraph(self.ws.tree, self.ws.package, self.ws.source_root)
            self._add_graph_tools()
        if not self.flags.get("hybrid"):
            from agent.output import starting_material
            return starting_material(self.ws, question, self.config)
        from retrieval.hybrid import HybridIndex, test_chunks
        from tools.registry import SearchArgs
        h = HybridIndex(self.ws.index, self.config, tests=test_chunks(self.ws.tree, self.ws.tests_dir),
                        graph=self.local_graph)
        mode = "graph" if self.local_graph is not None else "rerank"
        r = self.config.get("retrieval", {})

        def fmt(hits: list[Any], label: str, query: str) -> str:
            from retrieval.index import format_hit
            return "\n\n".join(format_hit(x, 40) for x in hits) if hits else f"No {label} matched {query!r}."
        self.registry.add_tool("search_code", "Search the library's source code (hybrid: BM25 + embeddings, reranked).",
                               SearchArgs, lambda a: fmt(h.search(a.query, a.k, kind="code", mode=mode), "code", a.query))
        self.registry.add_tool("search_docs", "Search the documentation and docstrings (hybrid). Docs can be out of date.",
                               SearchArgs, lambda a: fmt(h.search(a.query, a.k, kind="doc", mode="rerank"), "documentation", a.query))
        self.registry.add_tool("search_tests", "Search the repository's own test functions (BM25).",
                               SearchArgs, lambda a: fmt(h.search(a.query, a.k, kind="test"), "tests", a.query))
        code, docs = h.starting_material(question, r.get("code_top_k", 5), r.get("doc_top_k", 3), mode=mode)
        return format_starting_material(code, docs)

    def _add_graph_tools(self) -> None:
        g = self.local_graph

        def call_graph(a: _GraphQuery) -> str:
            found = g.find(a.symbol)
            if not found:
                return f"No function named {a.symbol!r} in the package."
            out = []
            for f in found[:3]:
                callers, callees = g.neighbours(f.qualname)
                out.append(f"{f.qualname} at {f.path}:{f.start}-{f.end}\n  called by: {', '.join(callers[:10]) or '-'}"
                           f"\n  calls: {', '.join(callees[:10]) or '-'}")
            return "\n".join(out)

        def static_slice(a: _SliceQuery) -> str:
            sl = g.static_slice(a.path, a.line)
            return ("Lines that can affect it (nearest first): " + ", ".join(f"{p}:{ln}" for p, ln in sl[:30])) \
                if sl else f"{a.path}:{a.line} is not in the package."
        self.registry.add_tool("call_graph", "Callers and callees of a function (static call graph).", _GraphQuery, call_graph)
        self.registry.add_tool("static_slice", "Lines of the enclosing function that can affect a line (backward slice).",
                               _SliceQuery, static_slice)

    def _read_tools(self) -> tuple[str, ...]:
        return tuple(self.registry.read_only)

    # ---------------------------------------------------------------- stages
    def answer(self, question: str) -> dict[str, Any]:
        package = self.ws.package
        system = Message(role="system", content=load("system"))
        material = self._setup_retrieval(question)

        # 1. Bug Investigator
        inv: Investigation | None = self.ask(
            [system, Message(role="user", content=load("investigator").format(
                question=question, material=material, steps=self.ma["investigator_steps"]))],
            "submit_investigation", Investigation, "Report your understanding of the bug and 2-4 competing hypotheses.",
            tools=self._read_tools(), steps=self.ma["investigator_steps"], reserve=3)
        if inv is None:
            self.note("no_investigation")
            return self._finish(None, None, {}, [], {}, None, None)
        hyps = [{"id": h.id, "statement": h.statement, "symbols": h.symbols,
                 "locations": [(self.norm(x.path), x.line) for x in h.locations]} for h in inv.hypotheses]
        self.note("investigation", hypotheses=[h["id"] for h in hyps])
        hyp_text = "\n".join(f"- {h.id}: {h.statement} | blames: "
                             f"{', '.join(f'{x.path}:{x.line}' for x in h.locations) or '-'} {', '.join(h.symbols)} | "
                             f"predicts: {h.predicts}" for h in inv.hypotheses)

        # 2. Probe Engineer
        probes, run, status = self._probes(inv, hyp_text, package)
        if probes is None or status == "broken":
            self.note("no_usable_probe", status=status)
            return self._finish(inv, probes, run or {}, [], {}, None, None, hyp_text=hyp_text)
        observations = self._observations(probes, run)

        # 3. Code Analyst (+ code graph from E3)
        claim_lines = control_lines = raise_site = None
        if self.flags.get("graph"):
            traced = self.backend.trace(probes.reproduce, probes.controls[:2])
            if traced:
                claim_lines, control_lines = traced[0], traced[1:]
            o = (run["report"]["results"][0] or {}).get("outcome") or {}
            frame = str(o.get("innermost_frame") or "")
            if o.get("kind") == "raise" and frame.startswith(package + "/") and ":" in frame:
                p, ln = frame.rsplit(":", 1)
                raise_site = (self.norm(p), int(ln)) if ln.isdigit() else None
        seeds = [loc for h in hyps for loc in h["locations"]]
        graph_text = ""
        graph_ranked: list[Loc] = []
        if self.flags.get("graph"):
            graph_ranked = self.backend.graph_candidates(seeds, claim_lines, control_lines, raise_site, 15)
            lines = [f"  {p}:{ln}  {self.backend.snippet(p, ln, 0).split('  ', 1)[-1].strip()[:100]}" for p, ln in graph_ranked[:12]]
            graph_text = ("\nCode graph analysis (deterministic): lines in the backward slices of the suspects that the "
                          "reproduce probe executed, most suspicious first (lines no control executed come first):\n"
                          + ("\n".join(lines) or "  (none)") + "\nSuspects in the call graph:\n"
                          + (self.backend.graph_summary(seeds) or "  (none)") + "\n")
        ranking: Ranking | None = self.ask(
            [system, Message(role="user", content=load("analyst").format(
                question=question, hypotheses=hyp_text, observations=observations, graph=graph_text,
                steps=self.ma["analyst_steps"]))],
            "rank_candidates", Ranking, "Rank the suspicious lines, most suspicious first.",
            tools=self._read_tools(), steps=self.ma["analyst_steps"], reserve=1)
        analyst = [(self.norm(c.path), c.line) for c in (ranking.candidates if ranking else [])]
        candidates = self._fuse(analyst, hyps, graph_ranked, seeds, claim_lines, control_lines, raise_site)
        self.note("candidates", n=len(candidates), top=[f"{p}:{ln}" for p, ln in candidates[:5]])

        # 4. Experiment Engineer
        policy = {"graph": bool(self.flags.get("graph")), "pairs": bool(self.flags.get("pairs")),
                  "active": bool(self.flags.get("active")), "single_budget": self.ma["single_budget"],
                  "pair_budget": self.ma["pair_budget"], "max_mutants": self.ma["max_mutants"]}
        experiments = self.backend.run_experiments(probes.reproduce, probes.controls[:2], candidates, hyps, policy)
        self.note("experiments", counts=experiments.get("counts"), stop=experiments.get("stop"))

        # 5. Causal Verifier
        verdict = self._verify(question, hyp_text, observations, experiments)
        patch = None
        if verdict is not None and verdict.patch.new_text.strip() and verdict.patch.line > 0:
            patch = self.backend.validate_patch(self.norm(verdict.patch.path), verdict.patch.line, verdict.patch.new_text)
            self.note("patch_validation", **{k: v for k, v in patch.items() if k != "reason"}, reason=patch.get("reason"))
        return self._finish(inv, probes, run, candidates, experiments, verdict, patch, status=status, hyp_text=hyp_text)

    def _probes(self, inv: Investigation, hyp_text: str, package: str) -> tuple[Probes | None, dict | None, str]:
        history = [Message(role="system", content=load("system")),
                   Message(role="user", content=load("probe_engineer").format(
                       expected=inv.expected_behaviour, actual=inv.actual_behaviour, scenario=inv.scenario,
                       hypotheses=hyp_text, package=package))]
        probes: Probes | None = None
        run: dict[str, Any] | None = None
        status = "broken"
        for attempt in range(self.ma["max_probe_repairs"] + 1):
            # Keep two requests for the Code Analyst and the Causal Verifier.
            probes = self.ask(history, "write_probes", Probes, "Give the probes.", reserve=2)
            if probes is None:
                return None, run, status
            run = self.run_probe(probes.reproduce, probes.controls[:2])
            status = probe_status(run, package)
            self.note("probe_result", attempt=attempt, status=status)
            if status != "broken" or attempt == self.ma["max_probe_repairs"] or self.llm.remaining <= 3:
                break
            history.append(Message(role="user", content=load("repair_probes").format(problems=run["text"][:1500])))
        if probes is not None and status != "broken":
            extra = ([probes.boundary] if probes.boundary.strip() else []) + [d.code for d in probes.distinguishing]
            if extra and self.probe_runs < self.ma["max_probe_runs"]:
                run["extra"] = self.run_probe(extra[0], extra[1:3])
        return probes, run, status

    def _observations(self, probes: Probes, run: dict[str, Any]) -> str:
        names = ["reproduce"] + [f"control {i + 1}" for i in range(len(probes.controls[:2]))]
        out = []
        for name, r in zip(names, run["report"]["results"]):
            out.append(f"- {name}: test_claim {r['status']}; observe() {describe(r.get('outcome'))}")
        extra = run.get("extra")
        if extra and extra.get("report", {}).get("results"):
            labels = (["boundary"] if probes.boundary.strip() else []) + \
                     [f"distinguishing {d.hypothesis_id}" for d in probes.distinguishing]
            for name, r in zip(labels, extra["report"]["results"]):
                out.append(f"- {name}: test_claim {r['status']}; observe() {describe(r.get('outcome'))}")
        return "\n".join(out)

    def _fuse(self, analyst: list[Loc], hyps: list[dict[str, Any]], graph_ranked: list[Loc], seeds: list[Loc],
              claim_lines: Any, control_lines: Any, raise_site: Loc | None) -> list[Loc]:
        """RRF of the Code Analyst's ranking, the hypotheses' lines (round robin) and, from E3, the graph ranking
        recomputed with the analyst's top lines as extra seeds."""
        from codegraph.rank import rrf
        by_h = [h["locations"] for h in hyps]
        hyp_rr = [x[i] for i in range(max((len(x) for x in by_h), default=0)) for x in by_h if i < len(x)]
        rankings = [analyst, hyp_rr]
        if self.flags.get("graph"):
            more = self.backend.graph_candidates(analyst[:3] + seeds, claim_lines, control_lines, raise_site, 15)
            rankings.append([tuple(x) for x in more] or graph_ranked)
        fused = [tuple(x) for x in rrf(rankings)]
        return [loc for loc in fused if self.valid(loc)][: self.ma["max_candidates"]]

    def _verify(self, question: str, hyp_text: str, observations: str, experiments: dict[str, Any]) -> Verdict | None:
        rows, snippets = [], []
        for e in experiments.get("experiments", []):
            best = next((m["op"] for m in e.get("mutants", []) if m["flags"].get("specific")), None) or \
                   next((m["op"] for m in e.get("mutants", []) if m["flags"].get("claim_changed")), "")
            rows.append(f"- {' + '.join(e['locs'])} [{e['kind']}]: {e['verdict'].upper()} ({e['reason']})"
                        + (f"; e.g. `{best}`" if best else ""))
        tested = [e for e in experiments.get("experiments", []) if e["kind"] == "single"]
        tested.sort(key=lambda e: {"accepted": 0, "inconclusive": 1, "rejected": 2}.get(e["verdict"], 3))
        for e in tested[:8]:
            p, ln = e["locs"][0].rsplit(":", 1)
            snippets.append(f"{e['locs'][0]} ({e['verdict']}):\n{self.backend.snippet(p, int(ln), 1)}")
        prompt = load("verifier").format(question=question, hypotheses=hyp_text, observations=observations,
                                         experiments="\n".join(rows) or "(no experiment could run)",
                                         snippets="\n\n".join(snippets) or "(none)")
        return self.ask([Message(role="system", content=load("system")), Message(role="user", content=prompt)],
                        "submit_verdict", Verdict, "Give the verdicts, the answer and an optional patch.", reserve=0)

    # ------------------------------------------------------------------ end
    def _finish(self, inv: Investigation | None, probes: Probes | None, run: dict[str, Any], candidates: list[Loc],
                experiments: dict[str, Any], verdict: Verdict | None, patch: dict[str, Any] | None, *,
                status: str = "broken", hyp_text: str = "") -> dict[str, Any]:
        from agent.output import assemble
        verdict_of: dict[Loc, str] = {}
        reason_of: dict[Loc, str] = {}
        for e in experiments.get("experiments", []):
            locs = [(p, int(ln)) for p, ln in (x.rsplit(":", 1) for x in e["locs"])]
            if e["kind"] == "single":
                verdict_of[locs[0]] = e["verdict"]
                reason_of[locs[0]] = e["reason"]
            elif e["kind"] == "pair" and e["verdict"] == "accepted":
                for loc in locs:
                    if verdict_of.get(loc) != "accepted":
                        verdict_of[loc] = "accepted_pair"
        cited = [(self.norm(c.path), c.line) for cl in (verdict.claims if verdict else []) for c in cl.citations]
        ranking = self._final_ranking(candidates, verdict_of, cited)

        def causal(loc: Loc) -> bool | None:
            v = verdict_of.get(loc)
            return True if v in ("accepted", "accepted_pair") else False if v == "rejected" else None
        claims = []
        for cl in (verdict.claims if verdict else []):
            cites = [{"path": self.norm(c.path), "line": c.line, "causal": causal((self.norm(c.path), c.line)),
                      "untestable": reason_of.get((self.norm(c.path), c.line)) == "nothing to mutate on this line"}
                     for c in cl.citations]
            claims.append({"text": cl.text, "grade": None, "scope": "instance", "source_kind": "code",
                           "status": "checked" if cites and any(x["causal"] for x in cites) else "unchecked",
                           "citations": cites, "observed_output": ""})
        any_accepted = any(v in ("accepted", "accepted_pair") for v in verdict_of.values())
        counts = experiments.get("counts", {})
        self.registry.counts["probe_runs"] = self.probe_runs
        self.registry.counts["mutant_runs"] = counts.get("mutant_runs", 0)
        stats = self.backend.stats() if hasattr(self.backend, "stats") else {}
        extra = {
            "architecture": "multiagent", "flags": dict(self.flags),
            "investigation": inv.model_dump() if inv else None,
            "probes": probes.model_dump() if probes else None, "probe_status": status,
            "observations": self._observations(probes, run) if probes and run.get("report") else "",
            "candidates": [f"{p}:{ln}" for p, ln in candidates],
            "experiments": experiments, "verdict": verdict.model_dump() if verdict else None,
            "patch_validation": patch,
            "ranking": ranking,
            "mutation_checks": counts.get("single_checks", 0), "pair_checks": counts.get("pair_checks", 0),
            "decisions": self.log,
        }
        if stats:
            extra["backend_stats"] = stats          # E6: MCP calls and the time they took
            extra["cpu_seconds"] = stats.get("cpu_seconds", 0.0)   # the sandbox lives in the MCP server process
        self.backend.close()
        return assemble(answer_text=verdict.answer_text if verdict else "", claims=claims, conflicts=[],
                        flagged_uncertain=bool(verdict.flagged_uncertain) if verdict and any_accepted else True,
                        abstained=bool(verdict.abstained) if verdict else True, llm=self.llm, registry=self.registry,
                        steps=self.steps_used, workspace=self.ws, extra=extra)

    @staticmethod
    def _final_ranking(candidates: list[Loc], verdict_of: dict[Loc, str], cited: list[Loc]) -> list[dict[str, Any]]:
        """Deterministic ranking used for the localization metrics: accepted lines, lines of an accepted pair, lines
        the verifier cited, inconclusive, untested and rejected lines, each group in candidate order."""
        order = list(dict.fromkeys(candidates + cited))
        rank = {loc: i for i, loc in enumerate(order)}

        def cls(loc: Loc) -> str:
            v = verdict_of.get(loc)
            if v in ("accepted", "accepted_pair", "rejected", "inconclusive"):
                return v
            return "cited" if loc in cited else "untested"
        ranked = sorted(order, key=lambda loc: (CLASS_ORDER[cls(loc)], rank[loc]))
        return [{"path": p, "line": ln, "class": cls((p, ln))} for p, ln in ranked[:10]]


def run(question: str, workspace: Any, client: Any, config: dict[str, Any], tracer: Any = None) -> dict[str, Any]:
    """Entry point used by `eval/run.py` for E1-E6."""
    return MultiAgentSystem(workspace, client, config, tracer=tracer).answer(question)
