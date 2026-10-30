"""Step 6 of the data pipeline: split questions into dev and test.

Stratified by library and category with a fixed seed, so a re-run gives the same
split. Prints the SHA-256 of the test file, which gate G2 records in
PREREGISTRATION.md. Test questions are never used for tuning.

Usage: python data/split.py [--dev-size 20] [--input data/questions_all.jsonl]
"""

from __future__ import annotations

import argparse
import hashlib
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import REPO_ROOT, load_config  # noqa: E402
from core.jsonl import read_jsonl, write_jsonl  # noqa: E402


def stratified_split(questions: list[dict[str, Any]], dev_size: int, seed: int) -> tuple[list[dict], list[dict]]:
    """Each (library, category) stratum gives dev questions in proportion to its size.

    Largest-remainder rounding makes the dev size exact. Within a stratum the
    order is a seeded shuffle of the questions sorted by qid, so the result
    does not depend on the input order.
    """
    strata: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for q in sorted(questions, key=lambda q: q["qid"]):
        strata[(q["library"], q["category"])].append(q)
    rng = random.Random(seed)
    for key in sorted(strata):
        rng.shuffle(strata[key])
    total = len(questions)
    dev_size = min(dev_size, total)
    quotas = {k: dev_size * len(v) / total for k, v in strata.items()} if total else {}
    take = {k: int(q) for k, q in quotas.items()}
    leftover = dev_size - sum(take.values())
    for k in sorted(quotas, key=lambda k: (-(quotas[k] - take[k]), k))[:leftover]:
        take[k] += 1
    dev: list[dict] = []
    test: list[dict] = []
    for key in sorted(strata):
        dev += strata[key][: take[key]]
        test += strata[key][take[key]:]
    return sorted(dev, key=lambda q: q["qid"]), sorted(test, key=lambda q: q["qid"])


def sha256_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    cfg = load_config()
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=str(REPO_ROOT / "data" / "questions_all.jsonl"))
    ap.add_argument("--dev-size", type=int, default=cfg["data"]["dev_size"])
    args = ap.parse_args(argv)
    dev, test = stratified_split(read_jsonl(args.input), args.dev_size, cfg["data"]["split_seed"])
    data_dir = REPO_ROOT / "data"
    write_jsonl(data_dir / "questions_dev.jsonl", dev)
    write_jsonl(data_dir / "questions_test.jsonl", test)
    print(f"dev={len(dev)} test={len(test)}\ntest SHA-256: {sha256_file(data_dir / 'questions_test.jsonl')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
