"""Run one system on one question set. Resumable; exits with code 3 on QuotaExhausted.

Each finished answer is written to `results/<run_id>/<system>/<qid>.json` at once,
so a run that hits the daily quota loses nothing: re-running skips finished
questions, and the LLM cache replays partial work without using quota.

Usage: python -m eval.run --system ours --split dev [--limit N] [--run-id mid]
Systems: b0 b1 b2 b2plus b3 ours a1 a2 a3 a4 a5 a7 a8 a10none a10oracle a11
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

from core.config import REPO_ROOT, config_hash, deep_merge, load_config
from core.jsonl import read_jsonl
from llm.cache import ReplyCache
from llm.client import LLMClient
from llm.trace import Tracer
from llm.types import QuotaExhausted
from tools.workspace import Workspace, docker_session_factory

EXIT_QUOTA = 3

# Each ablation is a config override: only control logic differs between systems (fairness, §2.3).
SYSTEM_OVERRIDES: dict[str, dict[str, Any]] = {
    "b0": {}, "b1": {}, "b2": {}, "b3": {}, "ours": {},
    "b2plus": {"baselines": {"b2_extra_steps": 8}},
    "a1": {"agent": {"ablation": {"no_execution": True}}},
    "a2": {"agent": {"ablation": {"no_mutation": True}}},
    "a3": {"agent": {"ablation": {"flag_only": True}}},
    "a4": {"agent": {"ablation": {"whole_answer_probe": True}}},
    "a5": {"agent": {"ablation": {"selective": True}}},
    "a7": {"agent": {"ablation": {"llm_conflicts": True}}},
    "a8": {"agent": {"ablation": {"no_repair": True}}},
    "a10none": {"agent": {"ablation": {"retrieval": "none"}}},
    "a10oracle": {"agent": {"ablation": {"retrieval": "oracle"}}},
    "a11": {"agent": {"ablation": {"constants_only": True}}},
}


def get_runner(system: str) -> Callable[..., dict[str, Any]]:
    """Baselines and the agent are imported here so eval has one small entry point."""
    if system == "b0":
        from baselines.b0_closed import run
        return run
    if system == "b1":
        from baselines.b1_rag import run
        return run
    if system in ("b2", "b2plus"):
        from baselines.b2_react import run
        return run
    if system == "b3":
        from baselines.b3_cove import run
        return run

    def run_agent(question: str, workspace: Any, client: Any, config: dict[str, Any], tracer: Any = None,
                  material_override: str | None = None) -> dict[str, Any]:
        from agent.loop import OurAgent
        return OurAgent(workspace, client, config, tracer=tracer, material_override=material_override).answer(question)
    return run_agent


def oracle_material(question: dict[str, Any], workspace: Workspace) -> str:
    """A10 oracle: the whole gold files as starting material. Built on the evaluation side,
    so the workspace itself still has no access to gold."""
    parts = []
    for path in question["fix_source_files"]:
        text = workspace.resolve(path).read_text(encoding="utf-8", errors="replace").splitlines()
        parts.append(f"[code] {path}\n" + "\n".join(f"{i:5d}  {ln}" for i, ln in enumerate(text[:800], 1)))
    return "\n\n".join(parts)


def git_sha() -> str:
    p = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True)
    return p.stdout.strip() or "unknown"


def run_question(system: str, question: dict[str, Any], config: dict[str, Any], client: LLMClient, tracer: Tracer,
                 session_factory: Callable[[Workspace], Any] = docker_session_factory) -> dict[str, Any]:
    workspace = Workspace.for_question(question, config, session_factory=session_factory)
    runner = get_runner(system)
    started = time.time()
    try:
        with tracer.context(qid=question["qid"], system=system):
            kwargs: dict[str, Any] = {}
            if system == "a10oracle":
                kwargs["material_override"] = oracle_material(question, workspace)
            result = runner(question["question_text"], workspace, client, config, tracer=tracer, **kwargs)
    finally:
        workspace.close()
    result.update({"qid": question["qid"], "system": system, "config_hash": config_hash(config),
                   "wall_seconds": round(time.time() - started, 1),
                   "environment": {**client.environment(), "project_commit": git_sha(),
                                   "library_commit": question["frozen_commit"]}})
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--system", required=True, choices=sorted(SYSTEM_OVERRIDES))
    ap.add_argument("--split", default="dev", choices=["dev", "test"])
    ap.add_argument("--limit", type=int)
    ap.add_argument("--run-id", default="mid")
    ap.add_argument("--allow-test", action="store_true", help="required to touch the test set (locked until G2)")
    ap.add_argument("--daily-guard", type=int, help="override our own requests-per-day guard, to learn the server's real limit")
    args = ap.parse_args(argv)
    if args.split == "test" and not args.allow_test:
        print("The test set is locked until gate G2. Refusing to run on it.", file=sys.stderr)
        return 2
    config = load_config([SYSTEM_OVERRIDES[args.system]])
    questions = read_jsonl(REPO_ROOT / "data" / f"questions_{args.split}.jsonl")[: args.limit]
    out_dir = REPO_ROOT / config["paths"]["results_dir"] / args.run_id / args.system
    out_dir.mkdir(parents=True, exist_ok=True)
    trace_path = REPO_ROOT / config["paths"]["traces_dir"] / f"{args.run_id}_{args.system}.jsonl"
    # The guard only affects when the client stops, not any system's behaviour, so it stays out of the result's config hash.
    client_config = deep_merge(config, {"llm": {"main": {"rpd": args.daily_guard}}}) if args.daily_guard else config
    client = LLMClient(client_config, cache=ReplyCache(REPO_ROOT / config["paths"]["llm_cache"]), tracer=Tracer(trace_path))
    done = failed = 0
    for q in questions:
        path = out_dir / f"{q['qid']}.json"
        if path.exists():
            done += 1
            continue
        try:
            result = run_question(args.system, q, config, client, client.tracer)
        except QuotaExhausted as exc:
            print(f"QUOTA EXHAUSTED after {done} of {len(questions)} questions: {str(exc)[:300]}", flush=True)
            return EXIT_QUOTA
        except Exception as exc:  # one question's crash is reported, never hidden, and does not stop the batch
            failed += 1
            print(f"{args.system} {q['qid']}: FAILED {type(exc).__name__}: {str(exc)[:300]}", flush=True)
            client.tracer.write("question_failed", qid=q["qid"], system=args.system, error=f"{type(exc).__name__}: {exc}"[:500])
            continue
        path.write_text(json.dumps(result, indent=1, default=str), encoding="utf-8")
        done += 1
        print(f"{args.system} {q['qid']}: requests={result['requests']} api={result['api_requests']} "
              f"flagged={result['flagged_uncertain']} claims={len(result['claims'])} ({done}/{len(questions)})", flush=True)
    print(f"{args.system}: {done} of {len(questions)} done, {failed} failed", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
