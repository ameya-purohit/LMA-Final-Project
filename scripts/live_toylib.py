"""One live run of a system on a toylib question: the sanity check before any real question.

toylib has planted ground truth, so a sensible answer is easy to recognise: it should
say the docs are wrong, and cite line 88 rather than line 12.

Usage: python scripts/live_toylib.py --systems ours b0 b1 b2 [--qid toylib-1]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import REPO_ROOT, load_config  # noqa: E402
from core.jsonl import read_jsonl  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    from eval.run import SYSTEM_OVERRIDES, get_runner
    from llm.cache import ReplyCache
    from llm.client import LLMClient
    from llm.trace import Tracer
    from tools.workspace import Workspace, docker_session_factory
    ap = argparse.ArgumentParser()
    ap.add_argument("--systems", nargs="+", default=["ours"])
    ap.add_argument("--qid", default="toylib-1")
    args = ap.parse_args(argv)
    toylib = REPO_ROOT / "tests" / "fixtures" / "toylib"
    question = next(q for q in read_jsonl(toylib / "questions.jsonl") if q["qid"] == args.qid)
    out: dict[str, dict] = {}
    for system in args.systems:
        cfg = load_config([SYSTEM_OVERRIDES[system]])
        trace = REPO_ROOT / cfg["paths"]["traces_dir"] / f"toylib_{system}.jsonl"
        client = LLMClient(cfg, cache=ReplyCache(REPO_ROOT / cfg["paths"]["llm_cache"]), tracer=Tracer(trace))
        ws = Workspace("toylib", "toylib", toylib, config=cfg, session_factory=docker_session_factory)
        try:
            with client.tracer.context(qid=args.qid, system=system):
                result = get_runner(system)(question["question_text"], ws, client, cfg, tracer=client.tracer)
        finally:
            ws.close()
        out[system] = result
        print(f"\n=== {system}: requests={result['requests']} (real {result['api_requests']}) tokens={result['tokens']['total']} "
              f"steps={result['steps']} probes={result['probe_runs']} mutants={result['mutant_runs']} "
              f"flagged={result['flagged_uncertain']} tool_calls={result['tool_calls']}")
        print(result["answer_text"])
        for c in result["claims"]:
            print(f"  [{c['grade']}] ({c['status']}) {c['text']} | {[(x['path'], x['line'], x['causal']) for x in c['citations']]} | {c['observed_output'][:120]}")
        print(f"  conflicts: {result['conflicts']}\n  trace: {trace.relative_to(REPO_ROOT)}")
    summary = REPO_ROOT / "results" / "summary" / f"toylib_live_{args.qid}.json"
    summary.parent.mkdir(parents=True, exist_ok=True)
    summary.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
