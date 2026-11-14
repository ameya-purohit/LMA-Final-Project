"""A lightweight code graph of one frozen library tree (exploratory extension, E3+).

What it builds, all from Python's own `ast`, stored in NetworkX graphs:
- **functions**: every module-level function and method, with its file and line range;
- **call graph**: function -> function edges, resolved by name with simple, explainable rules (below);
- **line dependences** inside one function: a *data* edge from the line that assigns a name to a line that reads it,
  and a *control* edge from an `if`/`while`/`for`/`try`/`with` header to every statement nested under it;
- **module constants**: a function that reads a module-level name depends on the line that assigns it.

`static_slice(path, line)` follows those edges backwards: every line that can affect the given line, inside its
function, plus the module constants it reads. That is a classic backward slice, made intra-procedural on purpose.

Why not a full Code Property Graph (Joern and the like): it needs a JVM and a separate service, and our candidates
only need "what can affect this line" and "who calls whom". Plain AST + NetworkX is enough and every step can be
explained in the viva. The price is precision: name-based call resolution guesses, and the slice ignores aliasing,
attribute flow across methods and calls into other functions (listed in docs/explainers/codegraph.md).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

import networkx as nx


@dataclass(frozen=True)
class FunctionInfo:
    qualname: str        # e.g. "core.Context.invoke" (module stem + class + name)
    name: str            # e.g. "invoke"
    path: str            # repository-relative, e.g. "src/click/core.py"
    start: int
    end: int
    class_name: str | None = None


@dataclass
class _LineInfo:
    defs: set[str] = field(default_factory=set)
    uses: set[str] = field(default_factory=set)


def _names(node: ast.AST, ctx: type) -> set[str]:
    """Names (and `self.attr` pseudo-names) in `node` with the given context (Load or Store)."""
    out: set[str] = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ctx):
            out.add(n.id)
        elif isinstance(n, ast.Attribute) and isinstance(n.ctx, ctx) and isinstance(n.value, ast.Name) \
                and n.value.id == "self":
            out.add(f"self.{n.attr}")
    return out


def _header_exprs(stmt: ast.stmt) -> list[ast.AST]:
    """The expressions a compound statement evaluates on its own header line(s)."""
    if isinstance(stmt, (ast.If, ast.While)):
        return [stmt.test]
    if isinstance(stmt, (ast.For, ast.AsyncFor)):
        return [stmt.iter]
    if isinstance(stmt, (ast.With, ast.AsyncWith)):
        return [i.context_expr for i in stmt.items]
    if isinstance(stmt, ast.Try):
        return []
    return [stmt]


def _header_defs(stmt: ast.stmt) -> set[str]:
    if isinstance(stmt, (ast.For, ast.AsyncFor)):
        return _names(stmt.target, ast.Store)
    if isinstance(stmt, (ast.With, ast.AsyncWith)):
        return set().union(*[_names(i.optional_vars, ast.Store) for i in stmt.items if i.optional_vars] or [set()])
    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return {stmt.name}
    if isinstance(stmt, (ast.If, ast.While, ast.Try)):
        return set()
    return _names(stmt, ast.Store)


_COMPOUND = (ast.If, ast.While, ast.For, ast.AsyncFor, ast.With, ast.AsyncWith, ast.Try)


def function_dependences(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> nx.DiGraph:
    """Line-level dependence graph of one function. Edge u -> v means "line u can affect line v";
    edge attribute `kind` is "data" or "control"."""
    g = nx.DiGraph()
    info: dict[int, _LineInfo] = {}
    loops: list[tuple[int, int]] = []
    params = {a.arg for a in fn.args.args + fn.args.kwonlyargs + fn.args.posonlyargs}
    params |= {a.arg for a in (fn.args.vararg, fn.args.kwarg) if a}
    info[fn.lineno] = _LineInfo(defs=params)
    g.add_node(fn.lineno)

    def visit(body: list[ast.stmt], controllers: list[int]) -> None:
        for stmt in body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue  # nested definitions are their own functions
            line = stmt.lineno
            li = info.setdefault(line, _LineInfo())
            for e in _header_exprs(stmt):
                li.uses |= _names(e, ast.Load)
            li.defs |= _header_defs(stmt)
            g.add_node(line)
            for c in controllers:
                if c != line:
                    g.add_edge(c, line, kind="control")
            if isinstance(stmt, _COMPOUND):
                if isinstance(stmt, (ast.For, ast.AsyncFor, ast.While)):
                    loops.append((stmt.lineno, stmt.end_lineno or stmt.lineno))
                inner = controllers + [line]
                for part in ("body", "orelse", "finalbody"):
                    visit(getattr(stmt, part, []) or [], inner)
                for h in getattr(stmt, "handlers", []) or []:
                    hl = info.setdefault(h.lineno, _LineInfo())
                    if h.name:
                        hl.defs.add(h.name)
                    if h.type is not None:
                        hl.uses |= _names(h.type, ast.Load)
                    g.add_edge(line, h.lineno, kind="control")
                    visit(h.body, inner + [h.lineno])

    visit(fn.body, [])
    defs_of: dict[str, list[int]] = {}
    for line, li in info.items():
        for name in li.defs:
            defs_of.setdefault(name, []).append(line)
    for line, li in info.items():
        enclosing_loops = [(a, b) for a, b in loops if a <= line <= b]
        for name in li.uses:
            for d in defs_of.get(name, []):
                # A definition reaches a use if it comes earlier, or if both sit in the same loop (the next iteration).
                if d < line or any(a <= d <= b for a, b in enclosing_loops):
                    if d != line:
                        g.add_edge(d, line, kind="data")
    nx.set_node_attributes(g, {ln: sorted(li.uses) for ln, li in info.items()}, "uses")
    nx.set_node_attributes(g, {ln: sorted(li.defs) for ln, li in info.items()}, "defs")
    return g


class CodeGraph:
    """Call graph, functions and module constants of one frozen package. Built once per (library, commit)."""

    def __init__(self, tree: str | Path, package: str, source_root: str = "."):
        self.tree = Path(tree)
        self.package = package
        self.source_root = source_root
        self.functions: dict[str, FunctionInfo] = {}
        self.by_file: dict[str, list[FunctionInfo]] = {}
        self.constants: dict[str, dict[str, int]] = {}     # path -> {NAME: line}
        self.calls = nx.DiGraph()                            # qualname -> qualname
        self._asts: dict[str, ast.Module] = {}
        self._fn_nodes: dict[str, ast.AST] = {}
        self._deps: dict[str, nx.DiGraph] = {}
        self._build()

    # ------------------------------------------------------------------ build
    def _build(self) -> None:
        pkg = self.tree / self.source_root / self.package
        imports: dict[str, dict[str, str]] = {}
        for file in sorted(pkg.rglob("*.py")):
            rel = file.relative_to(self.tree).as_posix()
            try:
                mod = ast.parse(file.read_text(encoding="utf-8", errors="replace"))
            except (SyntaxError, ValueError):
                continue
            self._asts[rel] = mod
            stem = file.relative_to(pkg).with_suffix("").as_posix().replace("/", ".")
            self.constants[rel] = {}
            imports[rel] = {}
            for stmt in mod.body:
                if isinstance(stmt, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                    for name in _names(stmt, ast.Store):
                        self.constants[rel].setdefault(name, stmt.lineno)
                elif isinstance(stmt, ast.ImportFrom):
                    for a in stmt.names:
                        imports[rel][a.asname or a.name] = a.name
            self._collect(mod.body, rel, stem, None)
        names: dict[str, list[str]] = {}
        for q, f in self.functions.items():
            names.setdefault(f.name, []).append(q)
            self.calls.add_node(q)
        for q, f in self.functions.items():
            for callee in self._resolve_calls(q, f, names, imports.get(f.path, {})):
                self.calls.add_edge(q, callee)

    def _collect(self, body: list[ast.stmt], rel: str, prefix: str, cls: str | None) -> None:
        for stmt in body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                q = f"{prefix}.{stmt.name}"
                start = min([d.lineno for d in stmt.decorator_list] + [stmt.lineno])
                info = FunctionInfo(q, stmt.name, rel, start, stmt.end_lineno or stmt.lineno, cls)
                self.functions[q] = info
                self.by_file.setdefault(rel, []).append(info)
                self._fn_nodes[q] = stmt
                self._collect(stmt.body, rel, q, None)
            elif isinstance(stmt, ast.ClassDef):
                self._collect(stmt.body, rel, f"{prefix}.{stmt.name}", stmt.name)

    def _resolve_calls(self, q: str, f: FunctionInfo, names: dict[str, list[str]], imported: dict[str, str]) -> set[str]:
        """Name-based call resolution, in this order:
        `self.m()` -> method m of the same class; `f()` -> a function f in the same file, else the imported or the
        unique f in the package; `obj.m()` -> every method named m, if there are at most 3 (else too ambiguous)."""
        out: set[str] = set()
        same_file = {g.name: g.qualname for g in self.by_file.get(f.path, [])}
        for node in ast.walk(self._fn_nodes[q]):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            if isinstance(fn, ast.Attribute):
                cands = names.get(fn.attr, [])
                if isinstance(fn.value, ast.Name) and fn.value.id in ("self", "cls") and f.class_name:
                    own = [c for c in cands if self.functions[c].class_name == f.class_name]
                    out.update(own or (cands if len(cands) <= 3 else []))
                elif len(cands) <= 3:
                    out.update(cands)
            elif isinstance(fn, ast.Name):
                if fn.id in same_file:
                    out.add(same_file[fn.id])
                else:
                    target = imported.get(fn.id, fn.id)
                    cands = names.get(target, [])
                    if len(cands) == 1 or (fn.id in imported and cands):
                        out.update(cands[:3])
        out.discard(q)
        return out

    # ---------------------------------------------------------------- queries
    def normalize(self, path: str) -> str | None:
        """Accept 'click/core.py', 'src/click/core.py' or './src/click/core.py'; return the key used here."""
        p = path.lstrip("./")
        for cand in (p, f"{self.source_root}/{p}" if self.source_root not in (".", "") else p, p.removeprefix("src/")):
            if cand in self._asts:
                return cand
        return None

    def function_at(self, path: str, line: int) -> FunctionInfo | None:
        """The innermost function whose range contains the line."""
        rel = self.normalize(path)
        best = None
        for f in self.by_file.get(rel or "", []):
            if f.start <= line <= f.end and (best is None or f.start >= best.start):
                best = f
        return best

    def find(self, symbol: str) -> list[FunctionInfo]:
        """Functions whose qualname ends with the given name, e.g. 'invoke' or 'Context.invoke'."""
        s = symbol.strip().split("(")[0]
        return [f for q, f in self.functions.items() if q == s or q.endswith("." + s)]

    def neighbours(self, qualname: str) -> tuple[list[str], list[str]]:
        """(callers, callees) one hop away in the call graph."""
        if qualname not in self.calls:
            return [], []
        return sorted(self.calls.predecessors(qualname)), sorted(self.calls.successors(qualname))

    def dependences(self, qualname: str) -> nx.DiGraph:
        if qualname not in self._deps:
            self._deps[qualname] = function_dependences(self._fn_nodes[qualname])  # type: ignore[arg-type]
        return self._deps[qualname]

    def static_slice(self, path: str, line: int, max_lines: int = 60) -> list[tuple[str, int]]:
        """Backward slice of (path, line): the lines of its function that can affect it through data or control
        dependences, nearest first, plus the module-level constants they read. Includes the line itself."""
        rel = self.normalize(path)
        f = self.function_at(path, line)
        if rel is None:
            return []
        if f is None:
            return [(rel, line)]
        g = self.dependences(f.qualname)
        # A line with no node of its own (a continuation line, or a decorator above the `def`) is sliced from the
        # nearest statement above it; a decorator line falls back to the `def` line, the graph's first node.
        start = line if line in g else max((n for n in g.nodes if n <= line), default=min(g.nodes))
        dist = nx.single_source_shortest_path_length(g.reverse(copy=False), start)
        lines = sorted(dist, key=lambda n: (dist[n], -n))
        out = [(rel, n) for n in lines]
        used = set().union(*[set(g.nodes[n].get("uses", [])) for n in lines]) if lines else set()
        consts = self.constants.get(rel, {})
        out += [(rel, consts[name]) for name in sorted(used) if name in consts]
        seen: set[tuple[str, int]] = set()
        return [x for x in out if not (x in seen or seen.add(x))][:max_lines]

    def connected(self, a: tuple[str, int], b: tuple[str, int]) -> bool:
        """True if the two lines are linked: one is in the other's slice, they sit in the same function and depend on
        a common line, or their functions call each other. Chooses which pairs are worth mutating together (E4)."""
        sa, sb = self.static_slice(*a), self.static_slice(*b)
        if b in sa or a in sb:
            return True
        fa, fb = self.function_at(*a), self.function_at(*b)
        if fa and fb and fa.qualname == fb.qualname:
            # Same function, sharing a source: e.g. two guards that both test the same argument (redundant checks).
            return bool((set(sa) - {a}) & (set(sb) - {b}))
        if fa and fb:
            return self.calls.has_edge(fa.qualname, fb.qualname) or self.calls.has_edge(fb.qualname, fa.qualname)
        return False

    def package_files(self) -> list[str]:
        """Package files as the sandbox's line tracer names them (relative to the source root, e.g. click/core.py)."""
        root = self.source_root
        return sorted(p if root in (".", "") else p.removeprefix(root + "/") for p in self._asts)

    def to_repo_path(self, traced: str) -> str:
        """'click/core.py' (tracer) -> 'src/click/core.py' (repository-relative)."""
        return traced if self.source_root in (".", "") else f"{self.source_root}/{traced}"
