"""Read-only data access for the presentation demo (`demo/app.py`).

Why a separate module: the Streamlit page should only lay things out. Everything it shows comes from files the
pipeline already wrote, read here by small functions that the unit tests can call without Streamlit installed.

What the demo reads, and where it comes from:
- committed summaries in `results/summary/` (always present in a clone of the repo);
- raw answers and judgements in `results/<run>/` and frozen trees in `.cache/trees/` (only on the machine that ran
  the experiments; the pages that need them say so when they are missing);
- the toylib fixture and its hand-written claims (`analysis/toylib_ablations.py`) for the live probe and mutation demo.

Nothing here calls an LLM or spends API quota.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from core.config import REPO_ROOT

SUMMARY = REPO_ROOT / "results" / "summary"
SYSTEM_NAMES = {
    "b0": "B0 · closed book",
    "b1": "B1 · direct RAG",
    "b2": "B2 · ReAct, same tools",
    "ours": "Ours · run it + flip the switch",
    "a1": "A1 · no execution",
    "a2": "A2 · no mutation",
    "a3": "A3 · flag only",
    "a10none": "A10 · no retrieval",
    "a10oracle": "A10 · oracle retrieval",
}
ORDER = ["b0", "b1", "b2", "ours", "a1", "a2", "a3", "a10none", "a10oracle"]
# Two worked examples from the final report (§7.7): one where the procedure worked, one where mutation hurt.
FEATURED = {
    "click-1422": "Worked: probes refuted two claims, the agent revised them, and mutation confirmed the fix line",
    "click-2099": "Hurt: the mutation check rejected the developer's own fix line, and the agent dropped it",
}


def read_json(path: Path) -> Any | None:
    """The parsed file, or None if it does not exist (the demo then shows what is missing)."""
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def analysis(name: str = "main_test") -> dict[str, Any] | None:
    """A committed `analysis/make_all.py` result, e.g. `main_test` (145 test questions) or `sub50_test` (A10)."""
    return read_json(SUMMARY / f"analysis_{name}" / "analysis.json")


def agreement() -> dict[str, Any] | None:
    """G3: kappa between the two human labellers and between the judge and the humans."""
    return read_json(SUMMARY / "human" / "agreement.json")


def adversarial() -> dict[str, Any] | None:
    return read_json(SUMMARY / "analysis_adv" / "adversarial.json")


def toylib_ablations() -> dict[str, Any] | None:
    return read_json(SUMMARY / "toylib_ablations.json")


def summary_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    """One row per system, in the report's order, with the headline metrics as fractions."""
    rows = []
    for s in [s for s in ORDER if s in result.get("summary", {})]:
        m = result["summary"][s]
        rows.append({"system": s, "label": SYSTEM_NAMES.get(s, s), "n": m["n"],
                     "correct": m["correctness"], "causally_supported": m["causally_supported"],
                     "fix_location_recall": m["fix_location_recall"], "confident_errors": m["n_confident_errors"],
                     "coverage": m["coverage"], "requests": m["requests_mean"], "tokens": m["tokens_mean"]})
    return rows


def human_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Per-system rates on the human-labelled questions (the primary comparison under the kappa rule)."""
    hv = result.get("human") or {}
    out = []
    for s in [s for s in ORDER if s in hv.get("scores", {})]:
        rows = list(hv["scores"][s].values()) if isinstance(hv["scores"][s], dict) else hv["scores"][s]
        n = len(rows)
        out.append({"system": s, "label": SYSTEM_NAMES.get(s, s), "n": n,
                    "correct": sum(bool(r.get("correct")) for r in rows) / n if n else 0.0,
                    "causally_supported": sum(bool(r.get("causally_supported")) for r in rows) / n if n else 0.0})
    return out


# ------------------------------------------------------------------ one question (local runs only)
def questions(split: str = "test") -> dict[str, dict[str, Any]]:
    path = REPO_ROOT / "data" / f"questions_{split}.jsonl"
    if not path.exists():
        return {}
    return {q["qid"]: q for q in (json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip())}


def spot_check_removed() -> set[str]:
    """Questions the G1 spot check marked invalid; the results exclude them, so the demo does too."""
    path = REPO_ROOT / "data" / "dropped.jsonl"
    if not path.exists():
        return set()
    rows = (json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip())
    return {r["qid"] for r in rows if r.get("stage") == "spot_check"}


def answer(run: str, system: str, qid: str) -> dict[str, Any] | None:
    return read_json(REPO_ROOT / "results" / run / system / f"{qid}.json")


def judgement(run: str, system: str, qid: str) -> dict[str, Any] | None:
    return read_json(REPO_ROOT / "results" / run / "judgements" / system / f"{qid}.json")


def answered(run: str, system: str) -> set[str]:
    d = REPO_ROOT / "results" / run / system
    return {p.stem for p in d.glob("*.json")} if d.is_dir() else set()


def in_gold(path: str, line: int, gold: list[dict[str, Any]]) -> bool:
    from eval.metrics import in_gold as _in_gold
    return _in_gold(path, line, gold)


def frozen_snippet(question: dict[str, Any], path: str, line: int, context: int = 4) -> str | None:
    """Numbered lines around `line` in the frozen tree, or None if the tree is not cached on this machine."""
    tree = REPO_ROOT / ".cache" / "trees" / question["library"] / question["frozen_commit"]
    target = (tree / path.lstrip("./")).resolve()
    if not str(target).startswith(str(tree.resolve())) or not target.is_file():
        return None
    lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    lo, hi = max(1, line - context), min(len(lines), line + context)
    return "\n".join(f"{'>' if i == line else ' '} {i:5d}  {lines[i - 1]}" for i in range(lo, hi + 1))


def github_link(question: dict[str, Any], path: str, a: int, b: int | None = None) -> str:
    repo = {"click": "pallets/click", "marshmallow": "marshmallow-code/marshmallow"}.get(question["library"], "")
    anchor = f"#L{a}" + (f"-L{b}" if b and b != a else "")
    return f"https://github.com/{repo}/blob/{question['frozen_commit']}/{path}{anchor}"


def timeline(ans: dict[str, Any]) -> list[dict[str, str]]:
    """Ours' decision log as readable steps: (icon, title, detail). Unknown decisions are shown as they are."""
    steps = []
    for d in ans.get("decisions", []):
        k = d.get("decision")
        if k == "draft":
            steps.append({"icon": "📝", "title": f"Draft with {d.get('n_claims')} claim(s)", "detail": ""})
        elif k == "verify_claims":
            steps.append({"icon": "🧭", "title": f"Verify claims {d.get('order')}",
                          "detail": f"{d.get('requests_left')} requests left"})
        elif k == "probe_result":
            icon = {"pass": "✅", "fail": "❌", "broken": "🛠️"}.get(d.get("verdict"), "•")
            steps.append({"icon": icon, "title": f"Run it · claim {d.get('claim')}: probe {d.get('verdict')}",
                          "detail": f"repairs: {d.get('repairs', 0)}"})
        elif k == "refuted":
            steps.append({"icon": "🔁", "title": f"Claim {d.get('claim')} refuted", "detail": f"observed: {d.get('observed')}"})
        elif k == "revised":
            steps.append({"icon": "✏️", "title": f"Claim {d.get('claim')} revised", "detail": d.get("new_text", "")})
        elif k == "mutation_check":
            ok = d.get("causal")
            steps.append({"icon": "🎯" if ok else "🚫",
                          "title": f"Flip the switch · {d.get('loc')}: {'causal' if ok else 'not causal'}",
                          "detail": f"claim {d.get('claim')}"})
        elif k == "proposed_citation":
            steps.append({"icon": "🔎", "title": f"New citation proposed: {d.get('loc')}",
                          "detail": "causal" if d.get("causal") else "not causal"})
        elif k == "dropped_non_causal":
            steps.append({"icon": "🗑️", "title": f"Dropped non-causal citation(s) of claim {d.get('claim')}",
                          "detail": ", ".join(d.get("citations", []))})
        else:
            steps.append({"icon": "•", "title": str(k), "detail": json.dumps({x: y for x, y in d.items() if x != "decision"})[:200]})
    return steps


# ------------------------------------------------------------------ multi-agent extension (E1-E6)
EXT_NAMES = {
    "E0": "E0 · locked agent (ours)",
    "B2": "B2 · ReAct, same tools",
    "E1": "E1 · five roles",
    "E2": "E2 · + hybrid retrieval",
    "E3": "E3 · + code graph",
    "E4": "E4 · + pair mutation",
    "E5": "E5 · + information gain",
    "E6": "E6 · E5 via MCP",
}
EXT_ORDER = list(EXT_NAMES)
RETRIEVAL_NAMES = {
    "R1": "R1 · BM25 (main study)",
    "R2": "R2 · dense (bge-small)",
    "R3": "R3 · BM25 + dense, RRF",
    "R4": "R4 · R3 + cross-encoder rerank",
    "R5": "R5 · R4 + call-graph expansion",
}
# Two worked examples: one where the roles found the developer's own line, one where a convincing story missed it.
EXT_FEATURED = {
    "click-2124": "Worked: the developer's fix line is ranked first, accepted by mutation, and the patch validates",
    "click-1139": "Missed: a convincing, validated explanation, but the developer fixed a different place",
}
# Report §8.6, written before any test run; outcome and a one-word status for the chip.
EXT_PREDICTIONS = [
    ("R4 (fusion + rerank) beats BM25 on Recall@5; dense alone does not", "partly",
     "Rerank did not help (−3.5, p = 0.52); dense alone did not, as predicted. Unpredicted: fusion without rerank wins"),
    ("E1 (roles) is not worse than E0 on line Top-3, with fewer requests", "partly",
     "Fewer requests (7.6 vs 14.9); Top-3 inconclusive (−10.6 [−23.4, +2.1])"),
    ("E3 (code graph) beats E2 on line Top-3", "refuted", "−19.1 [−34.0, −4.3], p = 0.035"),
    ("E4 finds ≥ 2 fix ranges on more multi-location questions than E3", "not supported",
     "21.2% for both; 0 of 95 pairs accepted"),
    ("E5 needs fewer mutant runs than E4 for a Top-3 within 5 points", "supported", "11.4 vs 15.2 mutant runs; same Top-3"),
    ("E6 (MCP) gives the same answers as E5 at a small time cost", "supported", "Identical on 47 of 47; 62 s vs 65 s"),
]


def extension() -> dict[str, Any] | None:
    """`analysis/extension.py` output: localization, verification and cost per configuration (47 test questions)."""
    return read_json(SUMMARY / "extension.json")


def retrieval_study() -> dict[str, Any] | None:
    """`analysis/retrieval_study.py` output: R1-R5 on the test questions (no LLM)."""
    return read_json(SUMMARY / "retrieval_study.json")


def ext_answered(system: str, run: str = "ext") -> set[str]:
    return answered(run, system.lower())


def ext_answer(system: str, qid: str, run: str = "ext") -> dict[str, Any] | None:
    return answer(run, system.lower(), qid)


def loc_in_gold(loc: str, gold: list[dict[str, Any]]) -> bool:
    """`path:line` (as the extension stores it) inside one of the developer's fix ranges."""
    path, _, line = loc.rpartition(":")
    return bool(path) and line.isdigit() and in_gold(path, int(line), gold)


def ext_rows(ext: dict[str, Any]) -> list[dict[str, Any]]:
    """One row per configuration in the report's order, with the headline localization and cost numbers."""
    rows = []
    for s in [s for s in EXT_ORDER if s in ext.get("table", {})]:
        t, v = ext["table"][s], ext.get("verification", {}).get(s, {})
        rows.append({"system": s, "label": EXT_NAMES[s], "line_top1": t["line_top1"], "line_top3": t["line_top3"],
                     "line_mrr": t["line_mrr"], "fn_top3": t["fn_top3"], "correct": t.get("correct"),
                     "requests": t.get("requests"), "tokens": t.get("tokens"), "mutant_runs": t.get("mutant_runs"),
                     "acceptance_on_gold": v.get("acceptance_on_gold"), "acceptance_on_other": v.get("acceptance_on_other"),
                     "inconclusive_rate": v.get("inconclusive_rate")})
    return rows


# ------------------------------------------------------------------ toylib live demo
def toylib_source() -> list[str]:
    from analysis.toylib_ablations import CORE
    return CORE.read_text(encoding="utf-8").splitlines()


def toylib_claims() -> list[dict[str, Any]]:
    """The hand-written claims, control probes and planted lines (with their ground truth) of the toylib ablations."""
    from analysis.toylib_ablations import CLAIMS, mark_line
    return [{**c, "planted": [{"mark": m, "line": mark_line(m), "causal": truth} for m, truth in c["lines"].items()]}
            for c in CLAIMS]


def docker_ready(image: str = "rtci-sandbox:py310") -> bool:
    """True if Docker runs and the sandbox image is built, so the demo can use the real sandbox."""
    if not shutil.which("docker"):
        return False
    try:
        return subprocess.run(["docker", "image", "inspect", image], capture_output=True, timeout=10).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def toylib_session(use_docker: bool):
    """A sandbox for the toylib demo. The local backend is allowed only because every probe the demo runs is one of
    the hand-written toylib probes (CLAUDE.md §2.5); the page offers no way to type in code."""
    from analysis.toylib_ablations import TOYLIB
    from core.config import load_config
    from sandbox.session import LocalBackend, SandboxSession
    cfg = load_config()
    session = SandboxSession(TOYLIB, "toylib", config=cfg) if use_docker else LocalBackend(TOYLIB, "toylib", trusted=True, config=cfg)
    session.start()
    return session


def describe_outcome(outcome: dict[str, Any] | None) -> str:
    if not outcome:
        return "no outcome"
    if outcome.get("kind") == "return":
        return f"returns {outcome.get('repr')}"
    return f"raises {outcome.get('type')}({outcome.get('msg')!r})"


def explain_verdict(report: Any) -> str:
    """One sentence on why the strictest rule (`specific`, the one the agent uses) accepted or rejected the line."""
    if getattr(report, "untestable", False):
        return "No mutation operator applies to this line, so the check cannot say (untestable)."
    if report.error:
        return f"The check could not run: {report.error}"
    flags = [m.flags for m in report.mutants]
    if not flags:
        return "No mutant was generated for this line."
    if any(f["specific"] for f in flags):
        return "Accepted: at least one mutant changes the claim's outcome and leaves the control probe unchanged."
    if any(f["behavioural"] for f in flags):
        return "Rejected: mutants change the claim, but every one of them also changes the control probe (not specific)."
    if any(f["claim_changed"] for f in flags):
        kinds = sorted({(m.claim or {}).get("type") or "an error" for m in report.mutants if m.flags.get("breakage")})
        return (f"Rejected: mutants only break the program ({', '.join(kinds) or 'an error'}), "
                "which is not a behavioural change.")
    return "Rejected: no mutant of this line changes the claim's outcome at all."
