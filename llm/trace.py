"""JSONL trace of every LLM call.

Why: traces are research data. Tool-use metrics, token counts, failure
taxonomy and qualitative examples (proposal §10) are all computed from them,
so every call is written down with its context (run, system, question).
Keys are never written: providers receive them from the environment, and
nothing here touches them.
"""

from __future__ import annotations

import contextlib
import time
from pathlib import Path
from typing import Any, Iterator

from core.jsonl import append_jsonl


class Tracer:
    """Appends one record per event to a JSONL file.

    `context(...)` adds tags (e.g. qid, system) to every record written inside it.
    A Tracer with `path=None` keeps records in memory (used by tests).
    """

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else None
        self.records: list[dict[str, Any]] = []
        self._tags: dict[str, Any] = {}

    @contextlib.contextmanager
    def context(self, **tags: Any) -> Iterator[None]:
        old = dict(self._tags)
        self._tags.update(tags)
        try:
            yield
        finally:
            self._tags = old

    def write(self, event: str, **fields: Any) -> dict[str, Any]:
        record = {"ts": round(time.time(), 3), "event": event, **self._tags, **fields}
        if self.path is None:
            self.records.append(record)
        else:
            append_jsonl(self.path, record)
        return record
