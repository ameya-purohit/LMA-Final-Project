"""SQLite cache of LLM replies, plus a per-day request counter.

Why a cache: the free tier allows a few hundred requests a day. At
temperature 0 with identical inputs, a repeated request is answered from the
cache and costs no quota. This makes re-runs and resumed runs free, and lets
ablations A2/A3 reuse the full agent's shared prefix (CLAUDE.md §2.4).

The key is a SHA-256 of (provider, model, messages, tools, params) in a
canonical JSON form, so any change to the prompt, tools or settings misses.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from llm.types import Reply


def cache_key(provider: str, model: str, messages: list[dict[str, Any]],
              tools: list[dict[str, Any]] | None, params: dict[str, Any]) -> str:
    payload = {"provider": provider, "model": model, "messages": messages,
               "tools": tools or [], "params": params}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ReplyCache:
    """Key-value store of serialized `Reply`s, and daily request counts.

    The request counter lives here too because it must survive restarts:
    a resumed batch run needs to know how much of today's quota is used.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(self.path), check_same_thread=False)
        self._db.execute("CREATE TABLE IF NOT EXISTS replies (key TEXT PRIMARY KEY, reply TEXT NOT NULL, created REAL)")
        self._db.execute("CREATE TABLE IF NOT EXISTS daily (day TEXT, provider TEXT, model TEXT, n INTEGER, "
                         "PRIMARY KEY (day, provider, model))")
        self._db.commit()

    def get(self, key: str) -> Reply | None:
        with self._lock:
            row = self._db.execute("SELECT reply FROM replies WHERE key = ?", (key,)).fetchone()
        if row is None:
            return None
        reply = Reply.from_dict(json.loads(row[0]))
        reply.from_cache = True
        return reply

    def put(self, key: str, reply: Reply) -> None:
        data = reply.to_dict()
        data["from_cache"] = False
        with self._lock:
            self._db.execute("INSERT OR REPLACE INTO replies VALUES (?, ?, ?)",
                             (key, json.dumps(data, ensure_ascii=False), time.time()))
            self._db.commit()

    def count_request(self, day: str, provider: str, model: str) -> int:
        """Increment and return today's real-request count for this model."""
        with self._lock:
            self._db.execute("INSERT INTO daily VALUES (?, ?, ?, 1) ON CONFLICT(day, provider, model) "
                             "DO UPDATE SET n = n + 1", (day, provider, model))
            self._db.commit()
            return self.requests_on(day, provider, model)

    def requests_on(self, day: str, provider: str, model: str) -> int:
        row = self._db.execute("SELECT n FROM daily WHERE day = ? AND provider = ? AND model = ?",
                               (day, provider, model)).fetchone()
        return row[0] if row else 0

    def __len__(self) -> int:
        return self._db.execute("SELECT COUNT(*) FROM replies").fetchone()[0]

    def close(self) -> None:
        self._db.close()
