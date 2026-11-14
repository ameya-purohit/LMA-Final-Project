"""E6: the same orchestrator, with every analysis and execution tool sent through a local MCP server, gives the same
result as calling the tools in-process (toylib, trusted local backend, scripted LLM)."""

from pathlib import Path

import pytest

pytest.importorskip("mcp")
pytest.importorskip("networkx")
pytest.importorskip("experiments.engine")
TOYLIB = Path(__file__).resolve().parents[1] / "fixtures" / "toylib"
if not TOYLIB.exists():
    pytest.skip("toylib is in a later bundle", allow_module_level=True)


def test_mcp_backend_matches_in_process():
    from core.config import load_config
    from mcp_server.client import MCPBackend
    from multiagent.orchestrator import MultiAgentSystem
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "orch_helpers", Path(__file__).resolve().parents[1] / "multiagent" / "test_orchestrator_toylib.py")
    helpers = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helpers)
    Scripted, local_factory, script = helpers.Scripted, helpers.local_factory, helpers.script
    from tools.workspace import Workspace

    def once(backend=None):
        cfg = load_config([{"multiagent": {"flags": {"graph": True, "pairs": True, "active": True}}}])
        ws = Workspace("toylib", "toylib", TOYLIB, config=cfg, session_factory=local_factory)
        try:
            return MultiAgentSystem(ws, Scripted(script().replies), cfg, backend=backend).answer("Why?")
        finally:
            ws.close()

    local = once()
    remote = once(MCPBackend(["--toylib"]))
    assert remote["ranking"] == local["ranking"]
    assert [e["verdict"] for e in remote["experiments"]["experiments"]] == \
           [e["verdict"] for e in local["experiments"]["experiments"]]
    assert remote["patch_validation"] == local["patch_validation"]
    assert remote["backend_stats"]["mcp_calls"] >= 5
