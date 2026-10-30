"""The one tool implementation every system shares (CLAUDE.md §2.3).

Each tool has a pydantic model for its arguments, from which its JSON schema is
generated. `ToolRegistry.call` validates arguments, runs the tool, and always
returns a `ToolResult`: invalid arguments and tool failures become an error text
the model can read and recover from, and are counted (a reported tool-use metric).

`tools.probe` and `tools.mutate` belong to later bundles, so they are imported
inside the functions that use them (the import rule in CLAUDE.md §3).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from pydantic import BaseModel, Field, ValidationError

from tools.files import open_file
from tools.history import git_blame, git_log
from tools.search import search_code, search_docs
from tools.static import find_definition, find_references
from tools.tests_finder import find_tests
from tools.workspace import Workspace


class SearchArgs(BaseModel):
    query: str = Field(description="Words to search for")
    k: int = Field(default=5, ge=1, le=10, description="How many results")


class OpenFileArgs(BaseModel):
    path: str = Field(description="Path relative to the repository root, e.g. src/click/core.py")
    start: int = Field(default=1, ge=1, description="First line to show")
    end: int = Field(default=0, ge=0, description="Last line to show; 0 means up to 200 lines from start")


class SymbolArgs(BaseModel):
    symbol: str = Field(description="A Python name, e.g. make_context or Context.invoke")


class GitLogArgs(BaseModel):
    path: str
    n: int = Field(default=10, ge=1, le=30)


class GitBlameArgs(BaseModel):
    path: str
    start: int = Field(ge=1)
    end: int = Field(ge=1)


class RunProbeArgs(BaseModel):
    code: str = Field(description="Claim probe: a Python file defining observe() and test_claim()")
    controls: list[str] = Field(default_factory=list, description="1-2 control probes in the same format")


class MutateArgs(BaseModel):
    path: str = Field(description="The cited file")
    line: int = Field(ge=1, description="The cited line")
    probe: str = Field(description="The claim probe")
    controls: list[str] = Field(default_factory=list, description="1-2 control probes")


class RepoTestArgs(BaseModel):
    node_id: str = Field(description="pytest node id, e.g. tests/test_basic.py::test_basic_functionality")


@dataclass
class ToolResult:
    name: str
    text: str
    ok: bool = True
    invalid: bool = False
    record: dict[str, Any] = field(default_factory=dict)


def inline_schema(model: type[BaseModel]) -> dict[str, Any]:
    """A plain JSON schema: no titles, no $ref, so every provider accepts it."""
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})

    def clean(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return clean(defs[node["$ref"].rsplit("/", 1)[-1]])
            return {k: clean(v) for k, v in node.items() if k != "title"}
        if isinstance(node, list):
            return [clean(v) for v in node]
        return node

    return clean(schema)


def tool_spec(name: str, description: str, model: type[BaseModel]) -> Any:
    from llm.types import ToolSpec  # llm/ is a later bundle (import rule, CLAUDE.md §3)
    return ToolSpec(name=name, description=description, parameters=inline_schema(model))


class Budget:
    """Hard limits per question, identical for every system."""

    def __init__(self, probe_runs: int = 12, mutation_checks: int = 12):
        self.probe_runs = probe_runs
        self.mutation_checks = mutation_checks


class ToolRegistry:
    """Runs tools for one question against one workspace, and counts everything."""

    READ_ONLY = ("search_code", "search_docs", "open_file", "find_definition", "find_references", "find_tests",
                 "git_log", "git_blame")
    EXECUTION = ("run_probe", "mutate_and_run", "run_repo_test")

    def __init__(self, workspace: Workspace, *, budget: Budget | None = None, tracer: Any = None,
                 mutation_operators: tuple[str, ...] | None = None):
        self.ws = workspace
        self.budget = budget or Budget()
        self.tracer = tracer
        self.mutation_operators = mutation_operators
        self.counts = {"total": 0, "invalid": 0, "errors": 0, "recovered": 0, "probe_runs": 0, "mutant_runs": 0,
                       "mutation_checks": 0, "unsafe_attempts": 0, "repo_tests": 0}
        self.mutation_log: dict[tuple[str, int], bool] = {}
        self._failed: set[str] = set()
        self._tools: dict[str, tuple[str, type[BaseModel], Callable[..., ToolResult]]] = {
            "search_code": ("Search the library's source code (BM25). Returns chunks with line numbers.",
                            SearchArgs, self._wrap(lambda a: search_code(self.ws, a.query, a.k))),
            "search_docs": ("Search the library's documentation and docstrings (BM25). Docs can be out of date.",
                            SearchArgs, self._wrap(lambda a: search_docs(self.ws, a.query, a.k))),
            "open_file": ("Show numbered lines of a file in the frozen repository (at most 200).",
                          OpenFileArgs, self._wrap(lambda a: open_file(self.ws, a.path, a.start, a.end))),
            "find_definition": ("Find where a name is defined (static analysis, nothing is run).",
                                SymbolArgs, self._wrap(lambda a: find_definition(self.ws, a.symbol))),
            "find_references": ("Find every line of package code that mentions a name.",
                                SymbolArgs, self._wrap(lambda a: find_references(self.ws, a.symbol))),
            "find_tests": ("Find where a name appears in the repository's own tests.",
                           SymbolArgs, self._wrap(lambda a: find_tests(self.ws, a.symbol))),
            "git_log": ("Commits touching a file, up to the frozen commit.",
                        GitLogArgs, self._wrap(lambda a: git_log(self.ws, a.path, a.n))),
            "git_blame": ("Who last changed each line, as of the frozen commit.",
                          GitBlameArgs, self._wrap(lambda a: git_blame(self.ws, a.path, a.start, a.end))),
            "run_probe": ("Run a claim probe and its control probes against the frozen library in an offline sandbox. "
                          "A probe is Python code defining observe() (returns the observed value; may raise) and "
                          "test_claim() (asserts the claim). Returns what really happened.",
                          RunProbeArgs, self._run_probe),
            "mutate_and_run": ("Test whether a cited line is causal: apply small mutations to it in a throw-away copy "
                               "and re-run the probe and controls. CAUSAL means a mutant changed the claim's outcome "
                               "and left every control unchanged.", MutateArgs, self._mutate),
            "run_repo_test": ("Run one of the repository's own tests in the sandbox by its pytest node id.",
                              RepoTestArgs, self._repo_test),
        }

    # ---------------------------------------------------------------- specs
    def specs(self, names: tuple[str, ...] | list[str] | None = None) -> list[Any]:
        return [tool_spec(n, self._tools[n][0], self._tools[n][1]) for n in (self._tools if names is None else names)]

    # ----------------------------------------------------------------- call
    def call(self, name: str, args: dict[str, Any]) -> ToolResult:
        self.counts["total"] += 1
        if name not in self._tools:
            self.counts["invalid"] += 1
            return ToolResult(name, f"Error: there is no tool named {name!r}.", ok=False, invalid=True)
        _, model, fn = self._tools[name]
        try:
            parsed = model.model_validate(args)
        except ValidationError as exc:
            self.counts["invalid"] += 1
            self._failed.add(name)
            problems = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
            return ToolResult(name, f"Invalid arguments for {name}: {problems}", ok=False, invalid=True)
        result = fn(parsed)
        if result.ok and name in self._failed:
            self._failed.discard(name)
            self.counts["recovered"] += 1
        elif not result.ok:
            self.counts["errors"] += 1
            self._failed.add(name)
        if self.tracer is not None:
            self.tracer.write("tool_call", tool=name, ok=result.ok, args=args, result=result.text[:2000])
        return result

    def _wrap(self, fn: Callable[[Any], str]) -> Callable[[Any], ToolResult]:
        def run(parsed: Any) -> ToolResult:
            try:
                return ToolResult("", fn(parsed))
            except Exception as exc:  # any tool failure is an error the model can read, never a crash of the question
                return ToolResult("", f"Error: {type(exc).__name__}: {exc}", ok=False)
        return run

    # ------------------------------------------------------------- execution
    def _run_probe(self, a: RunProbeArgs) -> ToolResult:
        from tools.probe import render, run_probe
        if self.counts["probe_runs"] >= self.budget.probe_runs:
            return ToolResult("run_probe", f"Probe budget used up ({self.budget.probe_runs} runs).", ok=False,
                              record={"budget": True})
        report = run_probe(self.ws.session, a.code, a.controls, tracer=self.tracer)
        if report.blocked:
            self.counts["unsafe_attempts"] += 1
        else:
            self.counts["probe_runs"] += 1
        return ToolResult("run_probe", render(report), ok=not report.error and not report.blocked,
                          record={"report": report})

    def _mutate(self, a: MutateArgs) -> ToolResult:
        from tools.mutate import ALL_OPERATORS, mutate_and_run, render
        if self.counts["mutation_checks"] >= self.budget.mutation_checks:
            return ToolResult("mutate_and_run", f"Mutation budget used up ({self.budget.mutation_checks} checks).",
                              ok=False, record={"budget": True})
        report = mutate_and_run(self.ws.session, a.path, a.line, a.probe, a.controls,
                                operators=self.mutation_operators or ALL_OPERATORS, tracer=self.tracer)
        if report.blocked:
            self.counts["unsafe_attempts"] += 1
        elif report.error is None:
            self.counts["mutation_checks"] += 1
            self.counts["mutant_runs"] += len(report.mutants)
            self.mutation_log[(a.path, a.line)] = report.causal
        return ToolResult("mutate_and_run", render(report), ok=report.error is None and not report.blocked,
                          record={"report": report})

    def _repo_test(self, a: RepoTestArgs) -> ToolResult:
        if a.node_id.startswith("-") or "::" not in a.node_id and not a.node_id.endswith(".py"):
            return ToolResult("run_repo_test", f"Error: {a.node_id!r} is not a test node id.", ok=False)
        if self.counts["probe_runs"] >= self.budget.probe_runs:
            return ToolResult("run_repo_test", "Probe budget used up.", ok=False, record={"budget": True})
        self.counts["probe_runs"] += 1
        self.counts["repo_tests"] += 1
        out = self.ws.session.run_pytest([a.node_id])
        if out.get("kind") != "pytest":
            return ToolResult("run_repo_test", f"Error: {out.get('type')}: {out.get('msg')}", ok=False)
        tests = out.get("tests", {})
        if not tests:
            return ToolResult("run_repo_test", f"Error: no test found for {a.node_id} (exit {out.get('exit_code')}). "
                                               f"{out.get('output_tail', '')[-200:]}", ok=False)
        lines = [f"{node}: {e['status']}" + (f" ({e['message'][:200]})" if e["message"] else "")
                 for node, e in list(tests.items())[:10]]
        passed = all(e["status"] == "passed" for e in tests.values())
        return ToolResult("run_repo_test", "\n".join(lines), record={"passed": passed})
