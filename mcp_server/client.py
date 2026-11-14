"""MCP client for E6: the same methods as `experiments.backend.InProcessBackend`, sent to `mcp_server/server.py`.

The orchestrator is synchronous; the MCP SDK is asynchronous. So the client runs one asyncio event loop in a
background thread, and a single long-lived task in it opens the stdio connection, serves calls from a queue, and
closes the connection at the end. (The SDK's connection objects must be opened and closed in the same task.)
Each method call blocks until the server answers.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import os
import sys
import threading
import time
from typing import Any

from core.config import REPO_ROOT

Loc = tuple[str, int]


class MCPBackend:
    def __init__(self, server_args: list[str], *, timeout_s: float = 900.0):
        self.server_args = server_args
        self.timeout_s = timeout_s
        self.calls = 0
        self.seconds = 0.0
        self._loop = asyncio.new_event_loop()
        self._ready: concurrent.futures.Future = concurrent.futures.Future()
        self._queue: asyncio.Queue | None = None
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._ready.result(timeout=180)

    @classmethod
    def for_workspace(cls, ws: Any, config: dict[str, Any]) -> "MCPBackend":
        args = ["--library", ws.library, "--commit", ws.commit]
        if getattr(ws, "variant", None):
            args += ["--variant", ws.variant]
        return cls(args)

    # ------------------------------------------------------------ plumbing
    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._serve())
        except BaseException as exc:  # noqa: BLE001 - report a failed start to the waiting constructor
            if not self._ready.done():
                self._ready.set_exception(exc)

    async def _serve(self) -> None:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        env = {**os.environ, "PYTHONPATH": str(REPO_ROOT)}
        params = StdioServerParameters(command=sys.executable, args=["-m", "mcp_server.server", *self.server_args],
                                       env=env, cwd=str(REPO_ROOT))
        self._queue = asyncio.Queue()
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                self._ready.set_result(True)
                while True:
                    item = await self._queue.get()
                    if item is None:
                        break
                    name, args, fut = item
                    try:
                        fut.set_result(await session.call_tool(name, args))
                    except BaseException as exc:  # noqa: BLE001
                        fut.set_exception(exc)

    def _call(self, name: str, **args: Any) -> Any:
        fut: concurrent.futures.Future = concurrent.futures.Future()
        start = time.time()
        self._loop.call_soon_threadsafe(self._queue.put_nowait, (name, args, fut))
        res = fut.result(timeout=self.timeout_s)
        self.calls += 1
        self.seconds += time.time() - start
        text = "".join(getattr(c, "text", "") for c in res.content)
        if res.isError:
            raise RuntimeError(f"MCP tool {name} failed: {text[:300]}")
        return json.loads(text)

    def close(self) -> None:
        if self._queue is not None and self._thread.is_alive():
            self._loop.call_soon_threadsafe(self._queue.put_nowait, None)
            self._thread.join(timeout=60)

    # ------------------------------------------------- the backend methods
    def run_probe(self, code: str, controls: list[str]) -> dict[str, Any]:
        return self._call("run_probe", code=code, controls=list(controls))

    def trace(self, claim: str, controls: list[str]) -> list[dict[str, list[int]]]:
        return self._call("trace", claim=claim, controls=list(controls))

    def graph_candidates(self, seeds: list[Loc], claim_lines: dict | None, control_lines: list[dict] | None,
                         raise_site: Loc | None, limit: int = 15) -> list[Loc]:
        out = self._call("graph_candidates", seeds=[list(s) for s in seeds], claim_lines=claim_lines,
                         control_lines=control_lines, raise_site=list(raise_site) if raise_site else None, limit=limit)
        return [(p, int(ln)) for p, ln in out]

    def graph_summary(self, locs: list[Loc]) -> str:
        return self._call("graph_summary", locs=[list(x) for x in locs])

    def run_experiments(self, claim: str, controls: list[str], candidates: list[Loc], hypotheses: list[dict],
                        policy: dict[str, Any]) -> dict[str, Any]:
        hyps = [{**h, "locations": [list(x) for x in h.get("locations", [])]} for h in hypotheses]
        return self._call("run_experiments", claim=claim, controls=list(controls),
                          candidates=[list(c) for c in candidates], hypotheses=hyps, policy=policy)

    def validate_patch(self, path: str, line: int, new_text: str) -> dict[str, Any]:
        return self._call("validate_patch", path=path, line=int(line), new_text=new_text)

    def snippet(self, path: str, line: int, context: int = 2) -> str:
        return self._call("snippet", path=path, line=int(line), context=context)

    def stats(self) -> dict[str, Any]:
        s = self._call("stats")
        return {**s, "mcp_calls": self.calls, "mcp_seconds": round(self.seconds, 2)}
