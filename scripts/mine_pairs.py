"""Run mining (step 1) and save raw candidates to .cache/candidates.json.

Usage: python scripts/mine_pairs.py [--libraries click marshmallow]
Re-runs are free: every GitHub response is cached. The candidates stay in the
git-ignored cache because they hold raw API text; only validated questions and
counts are committed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import REPO_ROOT, load_config  # noqa: E402
from data.mining.fix_pairs import mine  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--libraries", nargs="*")
    args = ap.parse_args(argv)
    cfg = load_config()
    result = mine(args.libraries, cfg)
    out = REPO_ROOT / cfg["paths"]["cache_dir"] / "candidates.json"
    out.write_text(json.dumps(result), encoding="utf-8")
    print(json.dumps(result["counts"], indent=1), f"\napi_calls={result['api_calls']} candidates={len(result['pairs'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
