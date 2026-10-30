"""Check 2, "flip the switch": is a cited line causal for a claim?

A cited line is accepted only if some small semantic mutation of it, in a
throw-away copy of the library, *behaviourally* changes the claim probe's
outcome while leaving every control probe's outcome unchanged (proposal §6.3).

Pieces:
- `generate_mutants(source, line)`: libcst finds the nodes that start on the
  line and applies one operator at a time; `module.code` regenerates the file,
  so every byte outside the mutated span is unchanged. (Never `ast.unparse`,
  which would reformat the whole file and shift other lines.)
- Pure rule functions over serialized outcomes, testable without Docker:
  `outcome_changed`, `is_breakage`, `classify`, `verdicts` (the three A6 rules).
- `mutate_and_run`: run the claim probe and controls on the original and on
  each mutant (each in its own package copy and process) and report the verdicts.
- `mutate_group`: one mutant per line combined, for redundant lines.
- `check_vacuous`: a probe no mutation of its function can flip tests nothing.
"""

from __future__ import annotations

import ast
import itertools
import shutil
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

import libcst as cst
from libcst.metadata import MetadataWrapper, ParentNodeProvider, PositionProvider

from tools.probe import check_policy

ALL_OPERATORS = ("constant", "negate_condition", "swap_comparison", "delete_statement", "return_none")
BREAKAGE_TYPES = {"SyntaxError", "IndentationError", "ImportError", "ModuleNotFoundError", "NameError",
                  "UnboundLocalError"}
LOCAL_BREAKAGE_TYPES = {"TypeError", "AttributeError"}

_SWAPS: dict[type, type] = {
    cst.LessThan: cst.LessThanEqual, cst.LessThanEqual: cst.LessThan,
    cst.GreaterThan: cst.GreaterThanEqual, cst.GreaterThanEqual: cst.GreaterThan,
    cst.Equal: cst.NotEqual, cst.NotEqual: cst.Equal,
    cst.In: cst.NotIn, cst.NotIn: cst.In,
    cst.Is: cst.IsNot, cst.IsNot: cst.Is,
}
_SYMBOL = {cst.LessThan: "<", cst.LessThanEqual: "<=", cst.GreaterThan: ">", cst.GreaterThanEqual: ">=",
           cst.Equal: "==", cst.NotEqual: "!=", cst.In: "in", cst.NotIn: "not in", cst.Is: "is", cst.IsNot: "is not"}


# =========================================================== mutant generation
@dataclass
class Mutant:
    """One mutated version of one file. `code` is the whole new file."""
    rel_path: str
    line: int
    operator: str
    description: str
    code: str

    @property
    def loc(self) -> str:
        return f"{self.rel_path}:{self.line}"


def _number_node(value: int | float) -> cst.BaseExpression:
    text = repr(value)
    if value < 0:
        inner = cst.Integer(text[1:]) if isinstance(value, int) else cst.Float(text[1:])
        return cst.UnaryOperation(operator=cst.Minus(), expression=inner)
    return cst.Integer(text) if isinstance(value, int) else cst.Float(text)


def _swap_operator(op: cst.BaseCompOp) -> cst.BaseCompOp:
    new_cls = _SWAPS[type(op)]
    before = getattr(op, "whitespace_before", cst.SimpleWhitespace(" "))
    after = getattr(op, "whitespace_after", cst.SimpleWhitespace(" "))
    if new_cls in (cst.NotIn, cst.IsNot):
        return new_cls(whitespace_before=before, whitespace_between=cst.SimpleWhitespace(" "),
                       whitespace_after=after)
    return new_cls(whitespace_before=before, whitespace_after=after)


def _is_docstring(node: cst.CSTNode, parents: dict) -> bool:
    return isinstance(parents.get(node), cst.Expr)


def _candidates(wrapper: MetadataWrapper, line: int, operators: Iterable[str]) -> list[tuple[str, str, cst.CSTNode, cst.CSTNode]]:
    """(operator, description, old_node, new_node) for every applicable mutation of `line`."""
    pos = wrapper.resolve(PositionProvider)
    parents = wrapper.resolve(ParentNodeProvider)
    on_line = [n for n, p in pos.items() if p.start.line == line]
    ordered = sorted(on_line, key=lambda n: (pos[n].start.column, -pos[n].end.line, -pos[n].end.column))
    ops = set(operators)
    out: list[tuple[str, str, cst.CSTNode, cst.CSTNode]] = []

    if "constant" in ops:
        for n in ordered:
            if isinstance(n, (cst.Integer, cst.Float)):
                v = ast.literal_eval(n.value)
                for new in (v + 1, v - 1, type(v)(0)):
                    if new != v:
                        out.append(("constant", f"{n.value} -> {new!r}", n, _number_node(new)))
                if v == 0:
                    out.append(("constant", f"{n.value} -> None", n, cst.Name("None")))
            elif isinstance(n, cst.Name) and n.value in ("True", "False"):
                flipped = "False" if n.value == "True" else "True"
                out.append(("constant", f"{n.value} -> {flipped}", n, cst.Name(flipped)))
            elif isinstance(n, cst.Name) and n.value == "None":
                out.append(("constant", "None -> 0", n, cst.Integer("0")))
            elif isinstance(n, cst.SimpleString) and not _is_docstring(n, parents):
                prefix = n.prefix
                quote = n.quote
                if n.raw_value != "":
                    out.append(("constant", f"{n.value[:30]} -> {prefix}{quote}{quote}", n,
                                cst.SimpleString(f"{prefix}{quote}{quote}")))

    if "negate_condition" in ops:
        for n in ordered:
            if isinstance(n, (cst.If, cst.While)):
                test = n.test
                if not test.lpar:
                    test = test.with_changes(lpar=[cst.LeftParen()], rpar=[cst.RightParen()])
                negated = cst.UnaryOperation(operator=cst.Not(), expression=test)
                kw = "while" if isinstance(n, cst.While) else "if"
                out.append(("negate_condition", f"negate {kw} condition", n, n.with_changes(test=negated)))

    if "swap_comparison" in ops:
        for n in ordered:
            if isinstance(n, cst.Comparison):
                for i, target in enumerate(n.comparisons):
                    if type(target.operator) in _SWAPS:
                        new_target = target.with_changes(operator=_swap_operator(target.operator))
                        comps = list(n.comparisons)
                        comps[i] = new_target
                        out.append(("swap_comparison",
                                    f"{_SYMBOL[type(target.operator)]} -> {_SYMBOL[_SWAPS[type(target.operator)]]}",
                                    n, n.with_changes(comparisons=comps)))

    if "delete_statement" in ops:
        for n in ordered:
            if isinstance(n, cst.BaseSmallStatement) and not isinstance(n, cst.Pass):
                if isinstance(n, cst.Expr) and isinstance(n.value, (cst.SimpleString, cst.ConcatenatedString)):
                    continue  # docstrings and bare strings do nothing
                code = cst.Module(body=[]).code_for_node(n).strip()
                out.append(("delete_statement", f"delete `{code[:40]}`", n, cst.Pass(semicolon=n.semicolon)))

    if "return_none" in ops:
        for n in ordered:
            if isinstance(n, cst.Return) and n.value is not None and not (
                    isinstance(n.value, cst.Name) and n.value.value == "None"):
                out.append(("return_none", "return <expr> -> return None", n, n.with_changes(value=cst.Name("None"))))
    return out


def _same_ast(a: str, b: str) -> bool:
    try:
        return ast.dump(ast.parse(a)) == ast.dump(ast.parse(b))
    except SyntaxError:
        return False


def generate_mutants(source: str, line: int, rel_path: str = "<file>", *,
                     operators: Iterable[str] = ALL_OPERATORS, limit: int | None = None) -> list[Mutant]:
    """All mutants of one line, in a fixed order (operator, then position on the line).

    A mutant whose AST equals the original's is skipped: it cannot change behaviour.
    """
    wrapper = MetadataWrapper(cst.parse_module(source))
    order = {op: i for i, op in enumerate(ALL_OPERATORS)}
    cands = sorted(_candidates(wrapper, line, operators), key=lambda c: order[c[0]])
    mutants: list[Mutant] = []
    for operator, desc, old, new in cands:
        code = wrapper.module.deep_replace(old, new).code
        if code == source or _same_ast(code, source):
            continue
        mutants.append(Mutant(rel_path, line, operator, desc, code))
        if limit and len(mutants) >= limit:
            break
    return mutants


def enclosing_function_lines(source: str, line: int) -> tuple[str, list[int]] | None:
    """(qualified name, body line numbers) of the innermost def containing `line`."""
    tree = ast.parse(source)
    best: tuple[str, ast.AST] | None = None

    def visit(node: ast.AST, prefix: str) -> None:
        nonlocal best
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = f"{prefix}{child.name}"
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and \
                        child.lineno <= line <= child.end_lineno:
                    best = (name, child)
                visit(child, name + ".")

    visit(tree, "")
    if best is None:
        return None
    name, fn = best
    body = fn.body
    if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) \
            and isinstance(body[0].value.value, str):
        body = body[1:]  # skip the docstring
    lines = sorted({ln for stmt in body for node in ast.walk(stmt) if hasattr(node, "lineno")
                    for ln in [node.lineno]})
    return name, lines


# ============================================================== pure rules
def outcome_changed(a: dict[str, Any] | None, b: dict[str, Any] | None) -> bool:
    """Compare kind first; then the repr for returns, or (type, message) for raises."""
    if a is None or b is None:
        return a != b
    if a.get("kind") != b.get("kind"):
        return True
    if a["kind"] == "return":
        return a.get("repr") != b.get("repr")
    return (a.get("type"), a.get("msg")) != (b.get("type"), b.get("msg"))


def is_breakage(outcome: dict[str, Any] | None, mutated_loc: str | Iterable[str]) -> bool:
    """The mutation broke the program rather than changing its behaviour:
    a SyntaxError/ImportError/NameError/... anywhere, or a TypeError/AttributeError
    raised exactly at the mutated line."""
    if not outcome or outcome.get("kind") != "raise":
        return False
    if outcome.get("type") in BREAKAGE_TYPES:
        return True
    locs = {mutated_loc} if isinstance(mutated_loc, str) else set(mutated_loc)
    return outcome.get("type") in LOCAL_BREAKAGE_TYPES and outcome.get("innermost_frame") in locs


def classify(orig_claim: dict | None, orig_controls: list[dict | None], mut_claim: dict | None,
             mut_controls: list[dict | None], mutated_loc: str | Iterable[str]) -> dict[str, bool]:
    """Per-mutant flags, and which acceptance rules this one mutant satisfies."""
    claim_changed = outcome_changed(orig_claim, mut_claim)
    breakage = claim_changed and is_breakage(mut_claim, mutated_loc)
    controls_changed = any(outcome_changed(o, m) for o, m in zip(orig_controls, mut_controls)) or \
        len(orig_controls) != len(mut_controls)
    behavioural = claim_changed and not breakage
    return {"claim_changed": claim_changed, "breakage": breakage, "controls_changed": controls_changed,
            "any_flip": claim_changed, "behavioural": behavioural,
            "specific": behavioural and not controls_changed}


def verdicts(flags: list[dict[str, bool]]) -> dict[str, bool]:
    """A line passes a rule if at least one of its mutants does (A6 compares the three)."""
    return {rule: any(f[rule] for f in flags) for rule in ("any_flip", "behavioural", "specific")}


# ============================================================= running
@dataclass
class MutantResult:
    id: str
    locs: list[str]
    operators: list[str]
    description: str
    claim: dict[str, Any] | None
    controls: list[dict[str, Any] | None]
    flags: dict[str, bool]


@dataclass
class MutationReport:
    locs: list[str]
    original_claim: dict[str, Any] | None = None
    original_controls: list[dict[str, Any] | None] = field(default_factory=list)
    mutants: list[MutantResult] = field(default_factory=list)
    verdicts: dict[str, bool] = field(default_factory=lambda: {"any_flip": False, "behavioural": False,
                                                                "specific": False})
    blocked: bool = False
    violations: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None

    @property
    def causal(self) -> bool:
        """The agent uses the strictest rule: behavioural and specific."""
        return self.verdicts["specific"]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["causal"] = self.causal
        return d


def normalize_rel_path(session: Any, path: str) -> str:
    """Accept 'toylib/core.py', 'src/toylib/core.py' or './src/toylib/core.py';
    return the path relative to the source root, checked to be inside the package."""
    p = Path(path.lstrip("./")) if not path.startswith("../") else Path(path)
    root = session.source_root
    if root not in (".", "") and p.parts and p.parts[0] == root:
        p = Path(*p.parts[1:])
    rel = p.as_posix()
    if not rel.startswith(session.package + "/") or ".." in p.parts:
        raise ValueError(f"{path!r} is not a file inside the {session.package} package")
    if not (session.tree / root / rel).is_file():
        raise ValueError(f"{path!r} does not exist in the frozen tree")
    return rel


def _read(session: Any, rel_path: str) -> str:
    return (session.tree / session.source_root / rel_path).read_text(encoding="utf-8")


def _outcomes(raw: dict[str, Any]) -> tuple[dict | None, list[dict | None]]:
    if raw.get("kind") != "probes":
        raise RuntimeError(f"sandbox error: {raw.get('type')}: {raw.get('msg')}")
    outs = [r.get("outcome") for r in raw["results"]]
    return outs[0], outs[1:]


def _make_overlay(session: Any, files: dict[str, str]) -> tuple[Path, str]:
    """Copy only the package directory into scratch, then write the mutated files."""
    host = session.scratch / "mutants" / uuid.uuid4().hex[:12]
    src_pkg = session.tree / session.source_root / session.package
    shutil.copytree(src_pkg, host / session.package, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for rel, code in files.items():
        (host / rel).write_text(code, encoding="utf-8")
    for p in [host, *host.rglob("*")]:
        p.chmod(0o755 if p.is_dir() else 0o644)
    return host, session.to_inner(host)


def _probes(claim_probe: str, controls: list[str]) -> list[tuple[str, str]]:
    return [("claim", claim_probe)] + [(f"control_{i + 1}", c) for i, c in enumerate(controls)]


def _run_variants(session: Any, report: MutationReport, variants: list[tuple[dict[str, str], list[str], list[str], str]],
                  named: list[tuple[str, str]], tracer: Any) -> MutationReport:
    raw = session.run_probes(named)
    report.original_claim, report.original_controls = _outcomes(raw)
    flags_all = []
    for files, locs, ops, desc in variants:
        host, inner = _make_overlay(session, files)
        try:
            claim, controls = _outcomes(session.run_probes(named, overlay=inner))
        finally:
            shutil.rmtree(host, ignore_errors=True)
        flags = classify(report.original_claim, report.original_controls, claim, controls, locs)
        flags_all.append(flags)
        report.mutants.append(MutantResult(uuid.uuid4().hex[:8], locs, ops, desc, claim, controls, flags))
    report.verdicts = verdicts(flags_all)
    if tracer is not None:
        tracer.write("mutation_check", locs=report.locs, n_mutants=len(report.mutants), verdicts=report.verdicts)
    return report


def mutate_and_run(session: Any, rel_path: str, line: int, claim_probe: str, controls: list[str] | tuple = (), *,
                   operators: Iterable[str] = ALL_OPERATORS, max_mutants: int | None = None,
                   tracer: Any = None) -> MutationReport:
    """Mutate one cited line and report whether it is causal for the claim.

    `session` is a SandboxSession (or, for trusted toylib tests, a LocalBackend)
    holding the frozen tree."""
    controls = list(controls)
    named = _probes(claim_probe, controls)
    try:
        rel = normalize_rel_path(session, rel_path)
    except ValueError as exc:
        return MutationReport(locs=[f"{rel_path}:{line}"], error=str(exc))
    report = MutationReport(locs=[f"{rel}:{line}"])
    violations = check_policy(named)
    if violations:
        if tracer is not None:
            tracer.write("unsafe_attempt", tool="mutate_and_run", violations=violations)
        report.blocked, report.violations = True, violations
        return report
    source = _read(session, rel)
    mutants = generate_mutants(source, line, rel, operators=operators, limit=max_mutants)
    if not mutants:
        report.error = f"no mutants: nothing on {rel}:{line} can be mutated (blank, comment, or unsupported)"
        return report
    variants = [({rel: m.code}, [m.loc], [m.operator], m.description) for m in mutants]
    return _run_variants(session, report, variants, named, tracer)


def mutate_group(session: Any, locs: list[tuple[str, int]], claim_probe: str, controls: list[str] | tuple = (), *,
                 operators: Iterable[str] = ALL_OPERATORS, max_combinations: int = 6,
                 tracer: Any = None) -> MutationReport:
    """Redundant lines: combine one mutant per line (at most `max_combinations` combinations).

    Mutations never change the number of lines, so after mutating one line the
    others keep their line numbers and can be mutated in turn."""
    controls = list(controls)
    named = _probes(claim_probe, controls)
    rels = [(normalize_rel_path(session, p), ln) for p, ln in locs]
    report = MutationReport(locs=[f"{r}:{ln}" for r, ln in rels])
    violations = check_policy(named)
    if violations:
        report.blocked, report.violations = True, violations
        return report
    per_line = [list(range(len(generate_mutants(_read(session, r), ln, r, operators=operators)))) for r, ln in rels]
    variants = []
    for combo in itertools.islice(itertools.product(*per_line), max_combinations):
        files: dict[str, str] = {}
        ops, descs = [], []
        for (rel, ln), idx in zip(rels, combo):
            current = files.get(rel, _read(session, rel))
            m = generate_mutants(current, ln, rel, operators=operators)[idx]
            files[rel] = m.code
            ops.append(m.operator)
            descs.append(f"{rel}:{ln} {m.description}")
        variants.append((files, report.locs, ops, " + ".join(descs)))
    if not variants:
        report.error = "no mutant combinations"
        return report
    return _run_variants(session, report, variants, named, tracer)


@dataclass
class VacuityReport:
    vacuous: bool
    function: str | None
    lines_checked: list[int]
    mutants_run: int
    flipped_by: str | None = None


def check_vacuous(session: Any, rel_path: str, line: int, claim_probe: str, *,
                  operators: Iterable[str] = ALL_OPERATORS, max_mutants: int = 60) -> VacuityReport:
    """Is the claim probe vacuous? It is if no mutant of any line of the function
    enclosing `line` behaviourally changes its outcome (proposal §6.3). Stops at the
    first behavioural flip."""
    rel = normalize_rel_path(session, rel_path)
    source = _read(session, rel)
    found = enclosing_function_lines(source, line)
    name, lines = found if found else (None, [line])
    named = [("claim", claim_probe)]
    if check_policy(named):
        raise ValueError("probe violates the sandbox policy")
    orig, _ = _outcomes(session.run_probes(named))
    run = 0
    for ln in lines:
        for m in generate_mutants(source, ln, rel, operators=operators):
            if run >= max_mutants:
                return VacuityReport(False, name, lines, run)  # budget hit: cannot call it vacuous
            host, inner = _make_overlay(session, {rel: m.code})
            try:
                claim, _ = _outcomes(session.run_probes(named, overlay=inner))
            finally:
                shutil.rmtree(host, ignore_errors=True)
            run += 1
            if outcome_changed(orig, claim) and not is_breakage(claim, m.loc):
                return VacuityReport(False, name, lines, run, flipped_by=f"{m.loc} {m.description}")
    return VacuityReport(True, name, lines, run)


def render(report: MutationReport) -> str:
    """Plain-text summary for the model."""
    if report.blocked:
        return "BLOCKED by the sandbox policy; nothing was run."
    if report.error:
        return f"MUTATION ERROR: {report.error}"
    where = ", ".join(report.locs)
    verdict = "CAUSAL (a mutant changed the claim's outcome and left every control unchanged)" if report.causal \
        else "NOT CAUSAL"
    lines = [f"{where}: {verdict}. {len(report.mutants)} mutants."]
    for m in report.mutants:
        f = m.flags
        tag = ("specific flip" if f["specific"] else "flip but controls changed" if f["behavioural"]
               else "breakage" if f["breakage"] else "no change")
        lines.append(f"- {m.description}: {tag}")
    return "\n".join(lines)
