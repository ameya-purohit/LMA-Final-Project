"""How many questions can each configuration afford before a deadline?

Takes measured requests per question for each system (from a pilot), the daily
limit and the days left, and prints an affordable plan, must-have first. Numbers
are computed from what you give it; nothing is estimated here.

Usage: python scripts/quota_plan.py --requests ours=14 b2=12 b1=1 --daily 500 --days 15 [--questions 100]
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

MUST_HAVE = ["ours", "b1", "b2", "a1", "a2", "a3"]
SHOULD_HAVE = ["a6", "b2plus", "b0", "b3", "a4", "a5", "a10none", "a10oracle"]


def plan(requests: dict[str, float], daily: int, days: int, questions: int | None = None) -> dict[str, Any]:
    """Allocate the total budget to systems in priority order, each up to `questions` questions."""
    budget = daily * days
    order = [s for s in MUST_HAVE + SHOULD_HAVE if s in requests] + [s for s in requests if s not in MUST_HAVE + SHOULD_HAVE]
    must = [s for s in MUST_HAVE if s in requests]
    must_cost = sum(requests[s] for s in must)
    affordable_all_must = int(budget // must_cost) if must_cost else None
    target = questions if questions is not None else affordable_all_must
    rows = []
    left = float(budget)
    for s in order:
        cost = requests[s]
        n = min(target if target is not None else 0, int(left // cost)) if cost > 0 else (target or 0)
        left -= n * cost
        rows.append({"system": s, "requests_per_question": cost, "questions": n, "requests": n * cost})
    return {"budget": budget, "must_have_questions_affordable": affordable_all_must, "rows": rows, "left": left}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--requests", nargs="+", required=True, help="system=requests_per_question")
    ap.add_argument("--daily", type=int, required=True)
    ap.add_argument("--days", type=int, required=True)
    ap.add_argument("--questions", type=int)
    args = ap.parse_args(argv)
    requests = {k: float(v) for k, v in (item.split("=") for item in args.requests)}
    p = plan(requests, args.daily, args.days, args.questions)
    print(f"Total requests available: {p['budget']}. Must-have tier affords {p['must_have_questions_affordable']} questions.")
    for r in p["rows"]:
        print(f"  {r['system']:10s} {r['requests_per_question']:6.1f} req/q  {r['questions']:4d} questions  {r['requests']:7.0f} requests")
    print(f"Left over: {p['left']:.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
