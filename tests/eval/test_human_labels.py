"""Gate G3 tooling: the blinded export, the labelling page's logic, and the agreement report (kappa rule)."""

import json
import re
import shutil
import subprocess

import pytest

from core.config import REPO_ROOT
from eval import human_export as H
from eval import kappa as K

PAGE = REPO_ROOT / "eval" / "label.html"


def test_question_sample_is_stratified_seeded_and_order_free():
    pools = {"click": [f"click-{i}" for i in range(86)], "marshmallow": [f"marshmallow-{i}" for i in range(14)]}
    picked = H.sample_questions(pools, 10, 82)
    assert len(picked) == 10 and sum(q.startswith("marshmallow") for q in picked) == 1
    rev = {k: list(reversed(v)) for k, v in pools.items()}
    assert picked == H.sample_questions(rev, 10, 82)
    assert picked != H.sample_questions(pools, 10, 83)


def _answers():
    out = []
    for qid in ("q1", "q2"):
        for system in ("ours", "b2", "a2"):
            out.append({"qid": qid, "system": system, "answer_text": f"{system} says",
                        "claims": [{"text": "c", "citations": [{"path": "a.py", "line": 3}, {"path": "b.py", "line": 9}]}]})
    return out


QUESTIONS = {q: {"question_text": f"why {q}?", "gold_answer": "g", "observed_before": [{"test": "t", "status": "failed", "message": "m"}]}
             for q in ("q1", "q2")}


def test_items_are_blinded_shuffled_and_keyed():
    items, key = H.build_items(_answers(), QUESTIONS, 82, diff_fn=lambda q: "diff", snippet_fn=lambda q, p, l: f"{p}:{l}")
    assert len(items) == 6 and [k["item"] for k in key] == [it["item"] for it in items]
    assert all("system" not in it and "qid" not in it for it in items), "labellers must not see the system or qid"
    assert not any(s in json.dumps(items) for s in ('"ours"', '"b2"', '"a2"'))
    assert [(k["qid"], k["system"]) for k in key] != sorted((k["qid"], k["system"]) for k in key), "shuffled"
    assert items[0]["citations"][1] == {"n": 2, "path": "b.py", "line": 9, "claim": "c", "snippet": "b.py:9"}
    again, key2 = H.build_items(_answers(), QUESTIONS, 82, diff_fn=lambda q: "diff", snippet_fn=lambda q, p, l: "")
    assert key == key2, "seeded"


def _lab(c, *cites):
    return {"correctness": c, "citations": list(cites)}


def test_agreement_consensus_and_kappa_rule():
    a = {"A1": _lab("correct", "causal"), "A2": _lab("partial", "on_topic"), "A3": _lab("incorrect", "irrelevant"),
         "A4": _lab("correct", "causal")}
    b = {"A1": _lab("correct", "causal"), "A2": _lab("correct", "causal"), "A3": _lab("incorrect", "irrelevant"),
         "A4": _lab("correct", "on_topic")}
    judge = {"A1": _lab("correct", "causal"), "A2": _lab("incorrect", "irrelevant"), "A3": _lab("correct", "causal"),
             "A4": _lab("correct", "causal")}
    r = K.agreement({"x": a, "y": b}, judge, 0.6)
    assert r["consensus"]["A2"] == _lab("partial", "on_topic"), "disagreement takes the more conservative label"
    assert r["consensus"]["A4"] == _lab("correct", "on_topic")
    hh = r["kappa"]["answer"]["human_human"]
    assert hh == pytest.approx(round(K.cohens_kappa(["correct", "partial", "incorrect", "correct"],
                                                    ["correct", "correct", "incorrect", "correct"]), 3))
    assert r["kappa"]["answer"]["consensus_judge"] < 0.6 and r["kappa"]["answer"]["use_human_labels"]
    assert r["kappa"]["citation"]["n"] == 4
    md = K.report_md(r)
    assert "human labels" in md and "| answer correctness | 4 |" in md


def test_agreement_needs_two_labellers_and_skips_mismatched_judgements():
    a = {"A1": _lab("correct", "causal")}
    with pytest.raises(ValueError):
        K.agreement({"x": a}, {}, 0.6)
    r = K.agreement({"x": a, "y": a}, {"A1": _lab("correct")}, 0.6)  # judge has a different citation count
    assert r["items_with_judgement"] == 0 and r["kappa"]["answer"]["consensus_judge"] is None
    assert not r["kappa"]["answer"]["use_human_labels"]


def _node(js):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    logic = re.search(r'<script id="logic">(.*?)</script>', PAGE.read_text(encoding="utf-8"), re.DOTALL).group(1)
    out = subprocess.run([node, "-e", "var module = {exports: {}};" + logic + js], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return out.stdout


def test_page_is_self_contained_and_safe():
    html = PAGE.read_text(encoding="utf-8")
    assert not re.search(r'<(script|link|img)[^>]+(src|href)=["\']https?:', html)
    assert "fetch(" not in html and ".innerHTML" not in html


def test_page_export_feeds_the_agreement_report():
    rows = [{"item": "A001", "labeller": "x", "citations": [{"n": 1}, {"n": 2}]},
            {"item": "A002", "labeller": "x", "citations": []},
            {"item": "A003", "labeller": "x", "citations": [{"n": 1}]}]
    answers = {"A001": {"correctness": "partial", "citations": ["causal", "irrelevant"], "note": " ok "},
               "A002": {"correctness": "correct", "citations": []},
               "A003": {"correctness": "correct", "citations": []}}  # citation unlabelled: not exported
    text = "".join(json.dumps(r) + "\n" for r in rows)
    out = _node(f"""const L = module.exports;
      process.stdout.write(L.toJsonl(L.parseJsonl({json.dumps(text)}), {json.dumps(answers)}, "2026-11-10T00:00:00Z"));""")
    recs = [json.loads(l) for l in out.splitlines() if l.strip()]
    assert [r["item"] for r in recs] == ["A001", "A002"]
    assert recs[0]["citations"] == ["causal", "irrelevant"] and recs[0]["note"] == "ok"
    lab = {r["item"]: r for r in recs}
    result = K.agreement({"x": lab, "y": lab}, {}, 0.6)
    assert result["kappa"]["answer"]["human_human"] == 1.0


def test_page_rejects_foreign_files():
    out = _node(r"""const L = module.exports; const r = [];
      for (const t of ['{"item":"A","labeller":"x","citations":[]}\n{"item":"B","labeller":"y","citations":[]}',
                       '{"qid":"click-1","member":"x"}', '']) { try { L.parseJsonl(t); r.push("ok"); } catch (e) { r.push("error"); } }
      process.stdout.write(r.join(","));""")
    assert out == "error,error,error"
