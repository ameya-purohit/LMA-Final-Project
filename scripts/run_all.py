"""One command for the whole evaluation pipeline: run, judge, report.

Must-have systems run first, and the full agent runs before its ablations, so
A1-A3 reuse its cached shared prefix and cost less quota. Exit code 3 means the
daily quota ran out: finished work is saved, so re-run this command after the
reset (midnight Pacific time) to continue.

Usage: python scripts/run_all.py --split dev --run-id mid [--systems b0 b1 ours b2 a2 a3 a1] [--limit N]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DEFAULT_ORDER = ["b1", "b0", "ours", "b2", "a2", "a3", "a1"]


def main(argv: list[str] | None = None) -> int:
    # Imported here: these belong to later bundles (import rule, CLAUDE.md §3).
    from eval import judge, report, run
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", default="dev")
    ap.add_argument("--run-id", default="mid")
    ap.add_argument("--systems", nargs="*", default=DEFAULT_ORDER)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--no-judge", action="store_true")
    ap.add_argument("--by-question", action="store_true",
                    help="finish every system on question 1, then question 2, ...: if the quota runs out, "
                         "all systems have answered the same questions, so comparisons stay paired")
    ap.add_argument("--start", type=int, default=1, help="with --by-question: first limit to run")
    ap.add_argument("--daily-guard", type=int, help="override our own requests-per-day guard, to learn the server's real limit")
    args = ap.parse_args(argv)
    status = 0
    limits = range(args.start, (args.limit or 20) + 1) if args.by_question else [args.limit]
    for limit in limits:
        for system in args.systems:
            extra = ["--limit", str(limit)] if limit else []
            extra += ["--daily-guard", str(args.daily_guard)] if args.daily_guard else []
            if run.main(["--system", system, "--split", args.split, "--run-id", args.run_id, *extra]) == run.EXIT_QUOTA:
                status = run.EXIT_QUOTA
                break
        if status:
            break
    if not args.no_judge:
        code = judge.main(["--run-id", args.run_id, "--split", args.split])
        status = status or code
    report.main(["--run-id", args.run_id, "--split", args.split])
    return status


if __name__ == "__main__":
    sys.exit(main())
