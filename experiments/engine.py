"""The Experiment Engineer (exploratory extension): plain code that runs causal experiments in the sandbox.

No LLM here. Given the probes the Probe Engineer wrote and the ranked candidate lines from the Code Analyst, it:
- traces which library lines each probe executes (for the executed-line spectrum, E3+);
- runs single-line mutation checks (`tools/mutate.py`, unchanged) on candidates, in rank order (E1-E4) or by
  information gain with early stopping (E5);
- runs dependency-guided pairwise checks (E4+): two lines that the code graph connects, mutated together, when
  neither settled the question alone (the redundant-guard case from toylib);
- validates a proposed one-line patch by re-running the claim probe and the controls on the patched copy.

Each line gets one of three verdicts, a refinement of the locked agent's yes/no:
- **accepted**: some mutant changes the claim's outcome and leaves every control unchanged (the `specific` rule);
- **rejected**: at least one mutant kept the program working, and none changed the claim's outcome (mutants that
  only break the program, e.g. a NameError, say nothing either way and are ignored);
- **inconclusive**: nothing to mutate, the check failed, every mutant broke the program, or the claim changed only
  together with a control.
Results are cached per line, and a line that two candidates name in different spellings (`click/core.py` vs
`src/click/core.py`) is checked once. Checks run one after another: the sandbox container has one CPU, so running
them in parallel would not be faster and would make timings harder to compare.
"""

from __future__ import annotations

import itertools
import shutil
import time
from dataclasses import dataclass, field
from typing import Any

Loc = tuple[str, int]


@dataclass
class Experiment:
    kind: str                      # single | pair | patch
    locs: list[str]
    verdict: str                   # accepted | rejected | inconclusive
    reason: str
    n_mutants: int = 0
    mutants: list[dict[str, Any]] = field(default_factory=list)
    seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "locs": self.locs, "verdict": self.verdict, "reason": self.reason,
                "n_mutants": self.n_mutants, "mutants": self.mutants[:12], "seconds": round(self.seconds, 2)}


def verdict_of(report: Any) -> tuple[str, str]:
    """Three-way verdict from a MutationReport."""
    if report.blocked:
        return "inconclusive", "probe blocked by the sandbox policy"
    if report.error:
        return "inconclusive", f"check failed: {report.error[:150]}"
    if getattr(report, "untestable", False) or not report.mutants:
        return "inconclusive", "nothing to mutate on this line"
    flags = [m.flags for m in report.mutants]
    if any(f["specific"] for f in flags):
        return "accepted", "a mutant changed the claim's outcome and no control"
    if any(f["behavioural"] for f in flags):
        return "inconclusive", "mutants changed the claim but also a control (not specific)"
    if all(f["breakage"] for f in flags):
        return "inconclusive", "mutants only broke the program"
    return "rejected", "no mutant that kept the program working changed the claim's outcome"


class ExperimentEngine:
    def __init__(self, session: Any, claim_probe: str, controls: list[str], *, graph: Any = None,
                 single_budget: int = 8, pair_budget: int = 3, max_mutants: int = 12, max_pairs_per_check: int = 6,
                 tracer: Any = None):
        self.session = session
        self.claim = claim_probe
        self.controls = list(controls)
        self.graph = graph
        self.single_budget = single_budget
        self.pair_budget = pair_budget
        self.max_mutants = max_mutants
        self.max_pairs_per_check = max_pairs_per_check
        self.tracer = tracer
        self.experiments: list[Experiment] = []
        self.by_loc: dict[Loc, Experiment] = {}
        self.counts = {"single_checks": 0, "pair_checks": 0, "mutant_runs": 0, "skipped_untestable": 0,
                       "cache_hits": 0, "patch_checks": 0}
        self.selection_log: list[dict[str, Any]] = []

    # ------------------------------------------------------------ helpers
    def _key(self, loc: Loc) -> Loc | None:
        """One spelling per line (repository path, line), or None if the path is not in the package."""
        from tools.mutate import normalize_rel_path
        try:
            rel = normalize_rel_path(self.session, loc[0])
        except ValueError:
            return None
        root = self.session.source_root
        return (rel if root in (".", "") else f"{root}/{rel}", int(loc[1]))

    def mutable(self, loc: Loc) -> bool:
        """Has the line anything to mutate? Checked in-process (no sandbox run), so untestable lines cost nothing."""
        from tools.mutate import _read, generate_mutants, normalize_rel_path
        try:
            rel = normalize_rel_path(self.session, loc[0])
            return bool(generate_mutants(_read(self.session, rel), int(loc[1]), rel, limit=1))
        except Exception:  # noqa: BLE001 - a line that cannot even be parsed is not mutable
            return False

    # --------------------------------------------------------- experiments
    def trace(self, files: list[str]) -> list[dict[str, list[int]]]:
        """Executed library lines of the claim probe and of each control: [claim, control_1, ...]."""
        named = [("claim", self.claim)] + [(f"control_{i + 1}", c) for i, c in enumerate(self.controls)]
        from tools.probe import check_policy
        if check_policy(named):
            return []
        raw = self.session.run_probes(named, trace_lines_for=files)
        if raw.get("kind") != "probes":
            return []
        return [r.get("executed_lines", {}) for r in raw["results"]]

    def single(self, loc: Loc) -> Experiment | None:
        """Mutation check of one line. None if the budget is spent or the line is outside the package."""
        from tools.mutate import mutate_and_run
        key = self._key(loc)
        if key is None:
            return None
        if key in self.by_loc:
            self.counts["cache_hits"] += 1
            return self.by_loc[key]
        if not self.mutable(key):
            self.counts["skipped_untestable"] += 1
            exp = Experiment("single", [f"{key[0]}:{key[1]}"], "inconclusive", "nothing to mutate on this line")
            self.by_loc[key] = exp
            self.experiments.append(exp)
            return exp
        if self.counts["single_checks"] >= self.single_budget:
            return None
        t = time.time()
        report = mutate_and_run(self.session, key[0], key[1], self.claim, self.controls,
                                max_mutants=self.max_mutants, tracer=self.tracer)
        verdict, reason = verdict_of(report)
        exp = Experiment("single", [f"{key[0]}:{key[1]}"], verdict, reason, len(report.mutants),
                         [{"op": m.description, "flags": m.flags} for m in report.mutants], time.time() - t)
        self.counts["single_checks"] += 1
        self.counts["mutant_runs"] += len(report.mutants)
        self.by_loc[key] = exp
        self.experiments.append(exp)
        return exp

    def pair(self, a: Loc, b: Loc) -> Experiment | None:
        from tools.mutate import mutate_group
        ka, kb = self._key(a), self._key(b)
        if ka is None or kb is None or ka == kb or self.counts["pair_checks"] >= self.pair_budget:
            return None
        if not (self.mutable(ka) and self.mutable(kb)):
            return None
        t = time.time()
        try:
            report = mutate_group(self.session, [ka, kb], self.claim, self.controls,
                                  max_combinations=self.max_pairs_per_check, tracer=self.tracer)
        except (ValueError, IndexError) as exc:
            return Experiment("pair", [f"{ka[0]}:{ka[1]}", f"{kb[0]}:{kb[1]}"], "inconclusive", f"check failed: {exc}")
        verdict, reason = verdict_of(report)
        exp = Experiment("pair", [f"{ka[0]}:{ka[1]}", f"{kb[0]}:{kb[1]}"], verdict, reason, len(report.mutants),
                         [{"op": m.description, "flags": m.flags} for m in report.mutants], time.time() - t)
        self.counts["pair_checks"] += 1
        self.counts["mutant_runs"] += len(report.mutants)
        self.experiments.append(exp)
        return exp

    # ----------------------------------------------------------- policies
    def run_ranked(self, candidates: list[Loc]) -> None:
        """E1-E4: single-line checks in rank order until the budget is spent."""
        for loc in candidates:
            if self.counts["single_checks"] >= self.single_budget:
                break
            self.single(loc)

    def run_active(self, candidates: list[Loc], hypotheses: list[dict[str, Any]]) -> str:
        """E5: information-gain order with early stopping. Returns why it stopped."""
        from experiments.selection import Belief, pick_next, should_stop
        blames = self._blame_fn(hypotheses)
        keyed = [k for k in (self._key(c) for c in candidates) if k is not None]
        keyed = list(dict.fromkeys(keyed))
        belief = Belief.start([h["id"] for h in hypotheses], blames)
        done: set[Loc] = set()
        accepted = False
        while True:
            if self.counts["single_checks"] >= self.single_budget:
                why = "single-check budget spent"
                break
            loc, gain = pick_next(belief, keyed, done)
            if loc is None:
                why = "no candidates left"
                break
            stop = should_stop(belief, accepted, gain)
            if stop:
                why = stop
                break
            done.add(loc)
            exp = self.single(loc)
            if exp is None:
                why = "budget spent"
                break
            belief.update(loc, exp.verdict)
            accepted = accepted or exp.verdict == "accepted"
            self.selection_log.append({"loc": f"{loc[0]}:{loc[1]}", "gain": round(gain, 4), "verdict": exp.verdict,
                                       "weights": {h: round(w, 3) for h, w in belief.weights.items()}})
        self.selection_log.append({"stop": why, "weights": {h: round(w, 3) for h, w in belief.weights.items()}})
        return why

    def _blame_fn(self, hypotheses: list[dict[str, Any]]):
        """Does hypothesis h blame line loc? Yes if loc is in a function h names, or within 2 lines of a line it names."""
        named: dict[str, list[Loc]] = {}
        fns: dict[str, set[str]] = {}
        for h in hypotheses:
            locs = [k for k in (self._key(tuple(x)) for x in h.get("locations", [])) if k is not None]
            named[h["id"]] = locs
            if self.graph is not None:
                fns[h["id"]] = {f.qualname for f in (self.graph.function_at(*x) for x in locs) if f}
                for sym in h.get("symbols", []):
                    fns[h["id"]].update(f.qualname for f in self.graph.find(sym))

        def blames(h: str, loc: Loc) -> bool:
            if any(p == loc[0] and abs(ln - loc[1]) <= 2 for p, ln in named.get(h, [])):
                return True
            if self.graph is not None and fns.get(h):
                f = self.graph.function_at(*loc)
                return bool(f and f.qualname in fns[h])
            return False
        return blames

    def run_pairs(self, ranked: list[Loc]) -> None:
        """E4+: pairs of tested lines that neither settled alone and that the code graph connects, best ranks first."""
        if self.graph is None:
            return
        rank = {k: i for i, k in enumerate(k for k in (self._key(c) for c in ranked) if k is not None)}
        open_ = [k for k, e in self.by_loc.items() if e.verdict != "accepted" and k in rank]
        open_.sort(key=lambda k: rank[k])
        pairs = [(a, b) for a, b in itertools.combinations(open_[:6], 2) if self.graph.connected(a, b)]
        pairs.sort(key=lambda ab: rank[ab[0]] + rank[ab[1]])
        for a, b in pairs:
            if self.counts["pair_checks"] >= self.pair_budget:
                break
            self.pair(a, b)

    # -------------------------------------------------------------- patch
    def validate_patch(self, path: str, line: int, new_text: str) -> dict[str, Any]:
        """Replace one line (keeping its indentation) in a throw-away copy, then re-run the claim probe and controls.

        Validated means the claim's outcome changed (the behaviour the issue describes is gone) and every control's
        outcome stayed the same. Runs in the sandbox, like every other piece of model-written code."""
        from tools.mutate import _make_overlay, _outcomes, _probes, _read, normalize_rel_path, outcome_changed
        from tools.probe import check_policy
        self.counts["patch_checks"] += 1
        if "\n" in new_text.strip("\n"):
            return {"validated": False, "reason": "a patch must be a single line"}
        try:
            rel = normalize_rel_path(self.session, path)
        except ValueError as exc:
            return {"validated": False, "reason": str(exc)}
        named = _probes(self.claim, self.controls)
        if check_policy(named):
            return {"validated": False, "reason": "probe blocked by the sandbox policy"}
        lines = _read(self.session, rel).split("\n")
        if not 1 <= line <= len(lines):
            return {"validated": False, "reason": "line out of range"}
        old = lines[line - 1]
        indent = old[: len(old) - len(old.lstrip())]
        lines[line - 1] = indent + new_text.strip()
        try:
            orig_claim, orig_controls = _outcomes(self.session.run_probes(named))
            host, inner = _make_overlay(self.session, {rel: "\n".join(lines)})
            try:
                claim, controls = _outcomes(self.session.run_probes(named, overlay=inner))
            finally:
                shutil.rmtree(host, ignore_errors=True)
        except Exception as exc:  # noqa: BLE001 - a failed validation is a result, not a crash
            return {"validated": False, "reason": f"run failed: {type(exc).__name__}: {str(exc)[:150]}"}
        changed = outcome_changed(orig_claim, claim)
        controls_same = not any(outcome_changed(a, b) for a, b in zip(orig_controls, controls))
        return {"validated": changed and controls_same, "claim_changed": changed, "controls_unchanged": controls_same,
                "reason": "ok" if changed and controls_same else
                ("claim unchanged" if not changed else "a control changed too")}

    def summary(self) -> dict[str, Any]:
        return {"counts": dict(self.counts), "experiments": [e.to_dict() for e in self.experiments],
                "selection": self.selection_log}
