"""Read and write JSON Lines files (one JSON object per line).

Why JSONL: questions, results, dropped items and traces are all lists of
records that grow over time. JSONL lets us append one record at a time
(crash-safe for long, resumable runs), diff files line by line in git, and
stream large traces without loading them whole.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable, Iterator


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    """Read every record. Blank lines are skipped; a bad line raises with its number."""
    return list(iter_jsonl(path))


def iter_jsonl(path: str | Path) -> Iterator[dict[str, Any]]:
    with open(path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{lineno}: invalid JSON: {exc}") from exc


def write_jsonl(path: str | Path, records: Iterable[dict[str, Any]]) -> int:
    """Write records atomically (temp file, then rename). Returns the count.

    Atomic so that an interrupted write never leaves a half-written dataset
    file that a later step would silently read.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    count = 0
    with open(tmp, "w", encoding="utf-8") as fh:
        for record in records:
            fh.write(dumps(record) + "\n")
            count += 1
    os.replace(tmp, path)
    return count


def append_jsonl(path: str | Path, record: dict[str, Any]) -> None:
    """Append one record and flush, so a crash loses at most the current record."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(dumps(record) + "\n")
        fh.flush()


def dumps(record: Any) -> str:
    """Compact, key-sorted JSON so the same record always serializes the same way."""
    return json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
