"""Gate G1, step 1: draw the spot-check sample and split it across the members.

Humans check the automatically built gold; they never write it (CLAUDE.md §6.10).
This draws a seeded random 20% of `data/questions_all.jsonl`, stratified by
library, and deals it out evenly to the four members as
`annotation/spotcheck_<member>.jsonl`. Each record carries everything the
checking page shows: the issue text, the PR link, the source part of the fix
diff, the failing test's message on the frozen code, and GitHub links to the gold
lines at the frozen commit.

Why seeded and stratified: a re-run gives the same sample (anyone can audit it),
and each library is represented in proportion, so the disagreement rate is not
dominated by click alone.

Usage: python annotation/sample.py [--fraction 0.2] [--seed 82]
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import REPO_ROOT, load_config  # noqa: E402
from core.jsonl import read_jsonl, write_jsonl  # noqa: E402

ANNOTATION_DIR = REPO_ROOT / "annotation"


def members_in_order() -> list[str]:
    """The four members, in push order (from `bundles/ownership.yaml`)."""
    data = yaml.safe_load((REPO_ROOT / "bundles" / "ownership.yaml").read_text(encoding="utf-8"))
    return list(data["push_order"])


def stratified_sample(questions: list[dict[str, Any]], fraction: float, seed: int) -> list[dict[str, Any]]:
    """A seeded `fraction` of the questions, stratified by library.

    Each library gets `fraction * size` questions; largest-remainder rounding makes
    the total exactly `round(fraction * total)`. Questions are sorted by qid before
    the seeded shuffle, so the input order does not matter.
    """
    by_lib: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for q in sorted(questions, key=lambda q: q["qid"]):
        by_lib[q["library"]].append(q)
    rng = random.Random(seed)
    for lib in sorted(by_lib):
        rng.shuffle(by_lib[lib])
    target = round(fraction * len(questions))
    quotas = {lib: fraction * len(v) for lib, v in by_lib.items()}
    take = {lib: int(q) for lib, q in quotas.items()}
    for lib in sorted(quotas, key=lambda l: (-(quotas[l] - take[l]), l))[: target - sum(take.values())]:
        take[lib] += 1
    out: list[dict[str, Any]] = []
    for lib in sorted(by_lib):
        out += by_lib[lib][: take[lib]]
    return out


def assign(sample: list[dict[str, Any]], members: list[str], seed: int) -> dict[str, list[dict[str, Any]]]:
    """Deal the sample out evenly (sizes differ by at most one), mixing libraries.

    The sample is shuffled once more with the seed, then dealt round-robin, so no
    member gets only one library.
    """
    order = sorted(sample, key=lambda q: q["qid"])
    random.Random(seed + 1).shuffle(order)
    shares: dict[str, list[dict[str, Any]]] = {m: [] for m in members}
    for i, q in enumerate(order):
        shares[members[i % len(members)]].append(q)
    return {m: sorted(v, key=lambda q: q["qid"]) for m, v in shares.items()}


def gold_links(q: dict[str, Any], spec: dict[str, Any]) -> list[dict[str, Any]]:
    """GitHub links to each gold range, pinned to the frozen commit (lines as they were before the fix)."""
    base = f"https://github.com/{spec['owner']}/{spec['repo']}/blob/{q['frozen_commit']}"
    out = []
    for ev in q["gold_evidence"]:
        a, b = ev["line_start"], ev["line_end"]
        anchor = f"#L{a}" if a == b else f"#L{a}-L{b}"
        out.append({**ev, "url": f"{base}/{ev['path']}{anchor}"})
    return out


def source_diff(q: dict[str, Any], spec: dict[str, Any], config: dict[str, Any]) -> str:
    """The source part of the fix diff (frozen commit → merge commit), as validation computed it."""
    from data import freeze  # Sunil's own data-pipeline files
    from data.patch import split_patch

    repo = freeze.repo_path(q["library"], config)
    diff = freeze.git(repo, "diff", "--no-renames", q["frozen_commit"], q["fix_merge_commit"])
    return split_patch(diff, spec["package"], spec["tests_dir"]).source


def record(q: dict[str, Any], member: str, config: dict[str, Any],
           diff_fn: Callable[[dict[str, Any], dict[str, Any], dict[str, Any]], str] = source_diff) -> dict[str, Any]:
    """One question as the checking page needs it. Only facts from the dataset and git; nothing is generated."""
    spec = config["data"]["libraries"][q["library"]]
    return {
        "qid": q["qid"], "member": member, "library": q["library"], "category": q["category"],
        "issue_url": q["issue_url"], "question_text": q["question_text"],
        "fix_pr_url": q["fix_pr_url"], "fix_pr_number": q["fix_pr_number"],
        "frozen_commit": q["frozen_commit"], "fix_merge_commit": q["fix_merge_commit"],
        "fail_to_pass": q["fail_to_pass"], "observed_before": q["observed_before"],
        "gold_evidence": gold_links(q, spec), "gold_answer": q["gold_answer"],
        "source_diff": diff_fn(q, spec, config),
    }


def main(argv: list[str] | None = None) -> int:
    cfg = load_config()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", default=str(REPO_ROOT / "data" / "questions_all.jsonl"))
    ap.add_argument("--fraction", type=float, default=0.2)
    ap.add_argument("--seed", type=int, default=cfg["data"]["split_seed"])
    args = ap.parse_args(argv)
    questions = read_jsonl(args.input)
    sample = stratified_sample(questions, args.fraction, args.seed)
    members = members_in_order()
    shares = assign(sample, members, args.seed)
    for member, qs in shares.items():
        write_jsonl(ANNOTATION_DIR / f"spotcheck_{member}.jsonl", [record(q, member, cfg) for q in qs])
    manifest = {"input": Path(args.input).name, "questions": len(questions), "fraction": args.fraction,
                "seed": args.seed, "sampled": len(sample),
                "assignment": {m: [q["qid"] for q in qs] for m, qs in shares.items()}}
    (ANNOTATION_DIR / "sample_manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    libs = defaultdict(int)
    for q in sample:
        libs[q["library"]] += 1
    print(f"sampled {len(sample)} of {len(questions)} ({dict(libs)}); "
          + ", ".join(f"{m}: {len(qs)}" for m, qs in shares.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
