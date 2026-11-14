"""The multi-agent orchestrator end to end on toylib with a scripted LLM: real probes, real mutation, local backend.

The scripted replies stand in for the three LLM agents, so every hand-off and every deterministic stage runs for real.
toylib, the sandbox and the experiment engine are in later bundles, so this skips in an earlier prefix (CLAUDE.md §3).
"""

from pathlib import Path

import pytest

from core.config import load_config
from llm.types import Reply, ToolCall, Usage
from tools.workspace import Workspace

pytest.importorskip("tools.mutate")
pytest.importorskip("experiments.engine")
pytest.importorskip("networkx")
TOYLIB = Path(__file__).resolve().parents[1] / "fixtures" / "toylib"
if not TOYLIB.exists():
    pytest.skip("toylib is in a later bundle", allow_module_level=True)
from analysis.toylib_ablations import CLAIMS  # noqa: E402
from multiagent.orchestrator import MultiAgentSystem, probe_status  # noqa: E402

CORE = "src/toylib/core.py"


def call(name, **args):
    return Reply(text="", tool_calls=[ToolCall(id=name, name=name, arguments=args)], usage=Usage(1, 1, 0, 0, 2),
                 provider="gemini", model="fake")


class Scripted:
    def __init__(self, replies):
        self.replies = list(replies)
        self.seen = []

    def complete(self, messages, tools, **params):
        self.seen.append(params.get("allowed_tools"))
        return self.replies.pop(0)


def local_factory(ws):
    from sandbox.session import LocalBackend
    return LocalBackend(ws.tree, ws.package, trusted=True, config=ws.config)


def script(patch_text='if strict: raise ValueError("negative")'):
    return Scripted([
        call("submit_investigation", expected_behaviour="strict is on by default, so negatives raise",
             actual_behaviour="clamp(-1, strict=False) raises ValueError",
             scenario="clamp(-1, strict=False)",
             hypotheses=[{"id": "H1", "statement": "the module default decides it",
                          "locations": [{"path": CORE, "line": 12}]},
                         {"id": "H2", "statement": "the guard in clamp raises for negatives",
                          "locations": [{"path": "toylib/core.py", "line": 88}], "symbols": ["clamp"]}]),
        call("write_probes", reproduce=CLAIMS[0]["claim"], controls=[CLAIMS[0]["control"]]),
        call("rank_candidates", candidates=[{"path": CORE, "line": 12}, {"path": CORE, "line": 88},
                                            {"path": "src/toylib/nothere.py", "line": 3}]),
        call("submit_verdict", hypotheses=[{"id": "H1", "verdict": "rejected"}, {"id": "H2", "verdict": "accepted"}],
             answer_text="clamp(-1, strict=False) raises ValueError; line 88 decides it.",
             claims=[{"text": "The guard on line 88 raises for negatives",
                      "citations": [{"path": CORE, "line": 88}, {"path": CORE, "line": 12}]}],
             patch={"path": CORE, "line": 88, "new_text": patch_text}),
    ])


def run(flags):
    cfg = load_config([{"multiagent": {"flags": flags}}])
    ws = Workspace("toylib", "toylib", TOYLIB, config=cfg, session_factory=local_factory)
    client = Scripted(script().replies)
    try:
        return MultiAgentSystem(ws, client, cfg).answer("Why does clamp(-1) raise?"), client
    finally:
        ws.close()


def test_e1_hands_off_through_all_five_roles():
    out, client = run({})
    assert out["requests"] == 4 and out["architecture"] == "multiagent"
    assert out["probe_status"] == "reproduced"
    assert out["ranking"][0] == {"path": CORE, "line": 88, "class": "accepted"}
    assert {"path": CORE, "line": 12, "class": "rejected"} in out["ranking"]
    assert all("nothere" not in c for c in out["candidates"]), "lines in files that do not exist are dropped"
    cites = out["claims"][0]["citations"]
    assert cites[0]["causal"] is True and cites[1]["causal"] is False
    assert out["patch_validation"]["validated"] is True
    assert out["flagged_uncertain"] is False and out["mutant_runs"] > 0 and out["probe_runs"] >= 1


def test_e5_uses_graph_active_selection_and_pairs():
    out, client = run({"graph": True, "pairs": True, "active": True})
    exp = out["experiments"]
    assert exp["stop"] and exp["selection"], "information-gain selection logs every choice and why it stopped"
    assert out["ranking"][0]["line"] == 88
    assert "call_graph" in client.seen[0] and "static_slice" in client.seen[0], "E3+ gives the agents graph tools"


def test_probe_status_rules():
    ok = {"report": {"results": [{"status": "pass", "message": ""}, {"status": "pass", "message": ""}]}}
    assert probe_status(ok, "p") == "reproduced"
    lib_raise = {"report": {"results": [{"status": "error", "message": "x", "outcome": {"kind": "raise", "innermost_frame": "p/a.py:3"}}]}}
    assert probe_status(lib_raise, "p") == "not_reproduced"
    assert probe_status({"report": {"results": [{"status": "error", "message": "import failed: x"}]}}, "p") == "broken"
    assert probe_status({"blocked": True, "report": {}}, "p") == "broken"
