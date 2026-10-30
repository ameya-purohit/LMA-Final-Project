"""End to end on toylib with a scripted LLM: real tools, real probes, real mutation, local backend.

toylib and the sandbox belong to later bundles, so this skips in an earlier
prefix of the push order (import rule, CLAUDE.md §3).
"""

import textwrap
from pathlib import Path

import pytest

from agent.loop import OurAgent
from core.config import load_config
from llm.types import Reply, ToolCall, Usage
from tools.workspace import Workspace

TOYLIB = Path(__file__).resolve().parents[1] / "fixtures" / "toylib"
pytest.importorskip("tools.mutate")
pytest.importorskip("sandbox.session")
if not TOYLIB.exists():
    pytest.skip("toylib is in a later bundle", allow_module_level=True)

CLAIM = textwrap.dedent("""
    import pytest
    from toylib import clamp
    def observe():
        return clamp(-1, strict=False)
    def test_claim():
        with pytest.raises(ValueError):
            clamp(-1, strict=False)
""")
CONTROL = textwrap.dedent("""
    from toylib import clamp
    def observe():
        return clamp(5, strict=False)
    def test_claim():
        assert clamp(5, strict=False) == 5
""")


def call(name, **args):
    return Reply(text="", tool_calls=[ToolCall(id=name, name=name, arguments=args)], usage=Usage(1, 1, 0, 0, 2), provider="gemini", model="fake")


class Scripted:
    def __init__(self, replies):
        self.replies = list(replies)

    def complete(self, messages, tools, **params):
        return self.replies.pop(0)


def local_factory(ws):
    from sandbox.session import LocalBackend
    return LocalBackend(ws.tree, ws.package, trusted=True, config=ws.config)


def test_docs_trap_line_12_rejected_line_88_found():
    """The proposal's example: the draft cites line 12, the check rejects it, line 88 is found."""
    cfg = load_config()
    ws = Workspace("toylib", "toylib", TOYLIB, config=cfg, session_factory=local_factory)
    client = Scripted([
        call("open_file", path="src/toylib/core.py", start=1, end=30),
        call("submit_draft", answer="Strict is on by default, set on line 12.",
             claims=[{"text": "clamp(-1, strict=False) raises ValueError", "source_kind": "doc",
                      "citations": [{"path": "src/toylib/core.py", "line": 12}]}]),
        call("write_probe", probes=[{"claim_id": 1, "code": CLAIM, "controls": [CONTROL]}]),
        call("propose_citation", claim_id=1, path="src/toylib/core.py", line=88),
        call("final_answer", answer_text="clamp(-1, strict=False) raises ValueError, decided at src/toylib/core.py:88."),
    ])
    try:
        out = OurAgent(ws, client, cfg, material_override="(material)").answer("Why?")
    finally:
        ws.close()
    claim = out["claims"][0]
    assert claim["status"] == "confirmed" and "ValueError" in claim["observed_output"]
    assert claim["citations"] == [{"path": "src/toylib/core.py", "line": 88, "causal": True}] and claim["grade"] == "E+C"
    assert out["mutant_runs"] > 0 and out["cpu_seconds"] > 0
    assert any(d["decision"] == "mutation_check" and not d["causal"] for d in out["decisions"]), "line 12 must be rejected"


def test_unsafe_probe_is_blocked_and_counted():
    cfg = load_config()
    ws = Workspace("toylib", "toylib", TOYLIB, config=cfg, session_factory=local_factory)
    unsafe = "import os\ndef observe():\n    return os.system('id')\ndef test_claim():\n    pass\n"
    client = Scripted([
        call("submit_draft", answer="a", claims=[{"text": "t", "citations": []}]),
        call("write_probe", probes=[{"claim_id": 1, "code": unsafe}]),
        call("write_probe", probes=[{"claim_id": 1, "code": unsafe}]),
        call("write_probe", probes=[{"claim_id": 1, "code": unsafe}]),
        call("final_answer", answer_text="unverified"),
    ])
    try:
        out = OurAgent(ws, client, cfg, material_override="(material)").answer("Why?")
    finally:
        ws.close()
    assert out["unsafe_attempts"] == 3 and out["probe_runs"] == 0 and out["flagged_uncertain"]
