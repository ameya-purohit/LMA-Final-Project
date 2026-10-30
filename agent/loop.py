"""Our agent (proposal §6, CLAUDE.md §6.6).

The control flow has a fixed shape; the decisions inside it are the agent's:

  1. Investigate with read-only tools; `submit_draft` gives an answer and atomic claims.
  2. Prioritise: claims supported only by docs come first.
  3. Probe each behavioural claim (`write_probe`, all claims in one call, to save
     requests; then `run_probe`). A broken probe is repaired up to 2 times.
  4. A refutation is first assessed: if the probe's setup differs from the question,
     rewrite it; if it matches, the claim is refuted and the observed output becomes
     the next investigation goal (`revise_claim`).
  5. Each citation of a confirmed claim goes through `mutate_and_run`. If none is
     causal, the goal becomes "find the line that decides this" (`propose_citation`).
  6. A confirmed claim with no causal citation has its probe checked for vacuity.
  7. Grade deterministically. 8. `final_answer` writes the text from the claim table;
     the output schema is assembled in code.

Failed checks therefore steer the investigation; they do not just filter the answer.
Ablation flags come from `config.agent.ablation` and change only this control logic.
"""

from __future__ import annotations

from typing import Any, Callable

from pydantic import BaseModel

from agent.claim_table import (AssessRefutation, Citation, Claim, ClaimTable, Conflict, FinalAnswer, ProposeCitation,
                               ResolveConflict, ReviseClaim, SubmitDraft, VerifyByReading, WriteProbe)
from agent.grades import apply_grades
from agent.output import assemble, load_prompt, starting_material
from agent.stop import FINAL_RESERVE, flagged_uncertain
from agent.toolloop import MeteredClient, OutOfRequests, StepBudget, ToolLoop
from llm.types import Message
from tools.registry import Budget, ToolRegistry

READ_ONLY = ToolRegistry.READ_ONLY
MAX_ROUNDS = 3
TERMINALS: dict[str, tuple[str, type[BaseModel]]] = {
    "submit_draft": ("End the investigation: a draft answer and its atomic claims.", SubmitDraft),
    "write_probe": ("Give probes for the listed claims, all in this one call.", WriteProbe),
    "assess_refutation": ("Compare each probe's setup with the question's scenario.", AssessRefutation),
    "revise_claim": ("Replace a refuted claim with a corrected one.", ReviseClaim),
    "propose_citation": ("Propose the line that decides a confirmed claim.", ProposeCitation),
    "verify_by_reading": ("Give a verdict for each claim, from reading the code.", VerifyByReading),
    "resolve_conflict": ("Say which source the final answer should follow.", ResolveConflict),
    "final_answer": ("Write the final answer from the claim table.", FinalAnswer),
}


def describe_outcome(outcome: dict[str, Any] | None) -> str:
    if not outcome:
        return "no outcome"
    if outcome.get("kind") == "return":
        return f"returned {outcome.get('repr')}"
    return f"raised {outcome.get('type')}: {outcome.get('msg')} (at {outcome.get('innermost_frame')})"


def classify_probe(report: Any, package: str) -> str:
    """'pass', 'fail' (the code contradicts the claim) or 'broken' (the probe itself is at fault).

    The decision rests on the error type (proposal §6.4): an exception raised inside
    the library is an observation about the library; anything else is a probe bug.
    """
    if report is None or getattr(report, "blocked", False) or getattr(report, "error", None):
        return "broken"
    claim = report.claim
    if claim is None or not report.executable:
        return "broken"
    if any((c.message or "").startswith("import failed") for c in report.controls):
        return "broken"
    if claim.status == "pass":
        return "pass"
    if claim.status == "fail":
        return "fail"
    outcome = claim.outcome or {}
    if outcome.get("kind") == "raise" and str(outcome.get("innermost_frame", "")).startswith(package + "/"):
        return "fail"
    return "broken"


class OurAgent:
    def __init__(self, workspace: Any, client: Any, config: dict[str, Any], *, tracer: Any = None,
                 registry: Any = None, material_override: str | None = None,
                 vacuity_check: Callable[..., Any] | None = None):
        self.ws = workspace
        self.config = config
        self.tracer = tracer
        ag = config["agent"]
        self.ab = ag["ablation"]
        self.llm = MeteredClient(client, ag["max_requests_per_question"])
        ops = ("constant",) if self.ab.get("constants_only") else None
        self.registry = registry or ToolRegistry(
            workspace, budget=Budget(ag["max_probe_runs"], ag["max_mutation_checks"]), tracer=tracer, mutation_operators=ops)
        self.loop = ToolLoop(self.llm, self.registry, max_tools_per_turn=ag["max_tools_per_turn"], tracer=tracer)
        self.steps = StepBudget(ag["max_investigation_steps"])
        self.max_repairs = 0 if self.ab.get("no_repair") else ag["max_probe_repairs"]
        self.table = ClaimTable()
        self.history: list[Message] = []
        self.material_override = material_override
        self._vacuity = vacuity_check
        self._gave_up: set[int] = set()

    # ------------------------------------------------------------- llm helpers
    def _ask(self, prompt: str, *terminal_names: str, read_tools: bool = False, reserve: int = FINAL_RESERVE) -> Any:
        """Send one instruction and wait for one of the named terminal tools. None if out of budget."""
        self.history.append(Message(role="user", content=prompt))
        terminals = {n: TERMINALS[n] for n in terminal_names}
        tools = READ_ONLY if read_tools else ()
        try:
            out = self.loop.run(self.history, tools, terminals, self.steps, reserve=reserve)
        except OutOfRequests:
            return None
        return out.parsed

    # -------------------------------------------------------------- the stages
    def answer(self, question: str) -> dict[str, Any]:
        package = getattr(self.ws, "package", "")
        self.history = [Message(role="system", content=load_prompt("system"))]
        material = starting_material(self.ws, question, self.config, override=self.material_override)
        draft = self._ask(load_prompt("investigate").format(question=question, material=material, steps=self.steps.total),
                          "submit_draft", read_tools=True)
        if draft is None:
            return self._finish(abstain_if_no_final=True)
        self._adopt_draft(draft)

        if not self.ab.get("no_execution"):
            self._run_repo_tests()
        for _ in range(MAX_ROUNDS):
            pending = [c for c in self.table.prioritised() if c.id not in self._gave_up]
            if not pending or self.llm.remaining <= FINAL_RESERVE:
                break
            self.table.log("verify_claims", order=[c.id for c in pending], requests_left=self.llm.remaining)
            if self.ab.get("no_execution"):
                self._verify_by_reading(pending)
            else:
                self._probe_and_handle(pending, package)
        if not self.ab.get("no_execution") and not self.ab.get("no_mutation"):
            self._check_citations(package)
        return self._finish()

    def _adopt_draft(self, draft: SubmitDraft) -> None:
        claims = draft.claims[:5]
        if self.ab.get("whole_answer_probe"):
            # A4: no decomposition. One claim holds the whole draft and all its citations.
            merged = claims[0].model_copy(deep=True) if claims else None
            if merged is not None:
                merged.text, merged.behavioural = draft.answer, True
                merged.citations = [x for c in claims for x in c.citations]
                claims = [merged]
        self.table.add_draft(claims)
        if self.ab.get("selective"):
            # A5: verify only claims that rest on documentation alone.
            for c in self.table.claims:
                if c.status == "unverified" and c.source_kind != "doc":
                    c.status = "skipped"
        self.table.log("draft", n_claims=len(self.table.claims), statuses=[c.status for c in self.table.claims])

    def _run_repo_tests(self) -> None:
        """Run any repository test a claim cites; needs no LLM request."""
        for c in self.table.claims:
            if c.test_node and c.test_passed is None:
                out = self.registry.call("run_repo_test", {"node_id": c.test_node})
                c.test_passed = bool(out.record.get("passed")) if out.ok else None

    # ---- check 1: execution
    def _probe_and_handle(self, pending: list[Claim], package: str) -> None:
        refuted = self._write_and_run(pending, "write_probe", package)
        if refuted:
            self._handle_refutations(refuted, package)

    def _claims_text(self, claims: list[Claim]) -> str:
        return "\n".join(f"[{c.id}] ({c.scope}) {c.text}" for c in claims)

    def _write_and_run(self, claims: list[Claim], first_prompt: str, package: str, **fmt: Any) -> list[Claim]:
        """Ask for probes, run them, repair broken ones. Returns the claims the code contradicted."""
        refuted: list[Claim] = []
        to_run = list(claims)
        prompt = load_prompt(first_prompt).format(claims=self._claims_text(to_run), package=package, **fmt)
        while to_run:
            parsed = self._ask(prompt, "write_probe")
            if parsed is None:
                self._gave_up.update(c.id for c in to_run)
                return refuted
            given = {p.claim_id: p for p in parsed.probes}
            broken: list[tuple[Claim, str]] = []
            for c in to_run:
                p = given.get(c.id)
                if p is None:
                    broken.append((c, "no probe was given for this claim"))
                    continue
                c.probe, c.controls = p.code, p.controls[:2]
                out = self.registry.call("run_probe", {"code": c.probe, "controls": c.controls})
                if out.record.get("budget"):
                    c.note = "probe budget used up"
                    self._gave_up.add(c.id)
                    continue
                report = out.record.get("report")
                verdict = classify_probe(report, package)
                self.table.log("probe_result", claim=c.id, verdict=verdict, repairs=c.repairs)
                if verdict == "broken":
                    broken.append((c, out.text))
                    continue
                c.observed_output = describe_outcome(report.claim.outcome)
                if verdict == "pass":
                    c.status = "confirmed"
                else:
                    refuted.append(c)
            to_run = []
            failures = []
            for c, why in broken:
                if c.repairs >= self.max_repairs:
                    c.note = f"probe abandoned after {c.repairs} repairs: {why[:200]}"
                    self._gave_up.add(c.id)
                else:
                    c.repairs += 1
                    to_run.append(c)
                    failures.append(f"[{c.id}] {c.text}\nProblem: {why[:800]}")
            prompt = load_prompt("repair_probe").format(failures="\n\n".join(failures))
        return refuted

    def _handle_refutations(self, claims: list[Claim], package: str) -> None:
        text = "\n\n".join(f"[{c.id}] {c.text}\nObserved: {c.observed_output}\nProbe:\n{c.probe}" for c in claims)
        parsed = self._ask(load_prompt("assess_refutation").format(refutations=text), "assess_refutation")
        verdicts = {a.claim_id: a.setup_matches_question for a in parsed.assessments} if parsed else {}
        rewrite = [c for c in claims if verdicts.get(c.id) is False and c.rewrites < 1]
        final = [c for c in claims if c not in rewrite]
        if rewrite:
            self.table.log("rewrite_probe", claims=[c.id for c in rewrite])
            for c in rewrite:
                c.rewrites += 1
            # A second contradiction after a rewrite is accepted as a refutation.
            final += self._write_and_run(rewrite, "rewrite_probe", package)
        for c in final:
            self._refuted(c)

    def _refuted(self, c: Claim) -> None:
        old_text = c.text
        c.status = "refuted"
        self.table.log("refuted", claim=c.id, observed=c.observed_output[:200])
        if c.source_kind == "doc":
            self.table.conflicts.append(Conflict(doc_says=old_text, execution_shows=c.observed_output))
            if self.ab.get("llm_conflicts"):
                # A7: the LLM decides the conflict instead of the evidence-grade order.
                prompt = load_prompt("resolve_conflict").format(claim_id=c.id, claim=c.text, observed=c.observed_output)
                parsed = self._ask(prompt, "resolve_conflict")
                if parsed is not None and parsed.follow == "docs":
                    c.status = "read_supported"
                    return
        if self.ab.get("flag_only") or c.revisions >= 2:
            return  # A3: a failure only flags the claim
        c.revisions += 1
        prompt = load_prompt("reinvestigate_refuted").format(claim_id=c.id, claim=c.text, observed=c.observed_output,
                                                             steps=self.steps.left)
        parsed = self._ask(prompt, "revise_claim", read_tools=True)
        if parsed is None:
            return
        c.text = parsed.text
        c.behavioural = parsed.behavioural
        c.source_kind = parsed.source_kind
        c.citations = [Citation(x.path, x.line) for x in parsed.citations]
        c.status = "unverified" if parsed.behavioural else "non_behavioural"
        c.probe, c.controls = "", []
        self.table.log("revised", claim=c.id, new_text=c.text[:200])
        if self.table.conflicts and self.table.conflicts[-1].doc_says == old_text and c.citations:
            self.table.conflicts[-1].decided_at = f"{c.citations[0].path}:{c.citations[0].line}"

    def _verify_by_reading(self, pending: list[Claim]) -> None:
        """A1: same procedure, but an LLM reading the code replaces execution."""
        parsed = self._ask(load_prompt("verify_by_reading").format(claims=self._claims_text(pending)), "verify_by_reading")
        if parsed is None:
            self._gave_up.update(c.id for c in pending)
            return
        verdicts = {v.claim_id: v for v in parsed.verdicts}
        for c in pending:
            v = verdicts.get(c.id)
            if v is None:
                self._gave_up.add(c.id)
            elif v.supported:
                c.status = "read_supported"
            else:
                c.observed_output = f"(read, not executed) {v.evidence}"
                self._refuted(c)

    # ---- check 2: mutation
    def _mutate(self, c: Claim, path: str, line: int) -> tuple[bool | None, str]:
        out = self.registry.call("mutate_and_run", {"path": path, "line": line, "probe": c.probe, "controls": c.controls})
        if out.record.get("budget"):
            return None, out.text
        report = out.record.get("report")
        causal = bool(report and report.causal)
        self.table.log("mutation_check", claim=c.id, loc=f"{path}:{line}", causal=causal)
        return causal, out.text

    def _check_citations(self, package: str) -> None:
        for c in self.table.with_status("confirmed"):
            reports = []
            for cit in c.citations:
                cit.causal, text = self._mutate(c, cit.path, cit.line)
                reports.append(text)
            if any(x.causal for x in c.citations):
                # At least one citation decides the claim: drop the ones that do not.
                dropped = [f"{x.path}:{x.line}" for x in c.citations if not x.causal]
                c.citations = [x for x in c.citations if x.causal]
                if dropped:
                    self.table.log("dropped_non_causal", claim=c.id, citations=dropped)
                continue
            if self.ab.get("flag_only"):
                continue  # A3: no re-investigation
            self._find_causal_line(c, reports)
            if not any(x.causal for x in c.citations):
                self._vacuity_step(c, package)

    def _find_causal_line(self, c: Claim, reports: list[str]) -> None:
        for _ in range(2):
            if self.llm.remaining <= FINAL_RESERVE:
                return
            c.proposals += 1
            prompt = load_prompt("reinvestigate_citation").format(
                claim_id=c.id, claim=c.text, report="\n".join(reports)[:1500] or "(no citation was given)",
                steps=self.steps.left)
            parsed = self._ask(prompt, "propose_citation", read_tools=True)
            if parsed is None:
                return
            causal, text = self._mutate(c, parsed.path, parsed.line)
            reports.append(text)
            self.table.log("proposed_citation", claim=c.id, loc=f"{parsed.path}:{parsed.line}", causal=causal)
            if causal:
                c.citations = [Citation(parsed.path, parsed.line, True)]
                return

    def _vacuity_step(self, c: Claim, package: str) -> None:
        """A confirmed claim with no causal citation: does its probe test anything at all?"""
        if c.vacuity_checked or not c.citations or self.llm.remaining <= FINAL_RESERVE:
            return
        c.vacuity_checked = True
        check = self._vacuity
        if check is None:
            from tools.mutate import check_vacuous as check
        try:
            report = check(self.ws.session, c.citations[0].path, c.citations[0].line, c.probe)
        except (ValueError, RuntimeError) as exc:
            self.table.log("vacuity_error", claim=c.id, error=str(exc)[:200])
            return
        c.vacuous = bool(report.vacuous)
        self.table.log("vacuity", claim=c.id, vacuous=c.vacuous)
        if c.vacuous:
            c.status = "unverified"
            refuted = self._write_and_run([c], "regenerate_vacuous", package, claim_id=c.id, claim=c.text)
            for r in refuted:
                r.status = "refuted"
            if c.status == "confirmed":
                for cit in c.citations:
                    cit.causal, _ = self._mutate(c, cit.path, cit.line)

    # ----------------------------------------------------------------- the end
    def _finish(self, abstain_if_no_final: bool = False) -> dict[str, Any]:
        apply_grades(self.table.claims, no_execution=bool(self.ab.get("no_execution")))
        conflicts = "\n".join(f"- docs say: {x.doc_says} | execution shows: {x.execution_shows} | decided at: {x.decided_at}"
                              for x in self.table.conflicts) or "(none)"
        parsed = self._ask(load_prompt("final_answer").format(table=self.table.render(), conflicts=conflicts),
                           "final_answer", reserve=0)
        answer = parsed.answer_text if parsed else ""
        abstained = bool(parsed.abstained) if parsed else (abstain_if_no_final or not self.table.claims)
        claims = [{"text": c.text, "grade": c.grade, "scope": c.scope, "source_kind": c.source_kind, "status": c.status,
                   "citations": [{"path": x.path, "line": x.line, "causal": x.causal} for x in c.citations],
                   "observed_output": c.observed_output} for c in self.table.claims]
        conflicts_out = [{"doc_says": x.doc_says, "execution_shows": x.execution_shows, "decided_at": x.decided_at}
                         for x in self.table.conflicts]
        if self.tracer is not None:
            self.tracer.write("agent_decisions", decisions=self.table.decisions)
        return assemble(answer_text=answer, claims=claims, conflicts=conflicts_out,
                        flagged_uncertain=flagged_uncertain(self.table), abstained=abstained, llm=self.llm,
                        registry=self.registry, steps=self.steps.used, workspace=self.ws,
                        extra={"decisions": self.table.decisions})
