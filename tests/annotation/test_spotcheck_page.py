"""annotation/spotcheck.html: self-contained; its logic exports verdicts that apply_spotcheck accepts.

The page's pure logic lives in <script id="logic">; these tests run it with node.
The render test opens the real page in headless Chrome with a real member file.
Both skip when the tool is not installed.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from annotation.apply_spotcheck import Verdict
from core.config import REPO_ROOT

PAGE = REPO_ROOT / "annotation" / "spotcheck.html"


def _logic() -> str:
    m = re.search(r'<script id="logic">(.*?)</script>', PAGE.read_text(encoding="utf-8"), re.DOTALL)
    assert m, "the page must keep its pure logic in <script id=\"logic\">"
    return m.group(1)


def _node(js: str) -> str:
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    out = subprocess.run([node, "-e", js], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return out.stdout


def test_page_is_self_contained_and_safe():
    html = PAGE.read_text(encoding="utf-8")
    assert not re.search(r'<(script|link|img)[^>]+(src|href)=["\']https?:', html), "no external files"
    assert "fetch(" not in html and "XMLHttpRequest" not in html, "no network"
    assert ".innerHTML" not in html, "dataset text is shown as text only"
    for field in ("question_text", "fix_pr_url", "source_diff", "observed_before", "gold_evidence", "localStorage"):
        assert field in html


def test_exported_jsonl_is_valid_for_apply_spotcheck():
    rows = [{"qid": "click-1", "member": "sourav", "library": "click"},
            {"qid": "click-2", "member": "sourav", "library": "click"},
            {"qid": "click-3", "member": "sourav", "library": "click"}]
    answers = {"click-1": {"genuine_question": True, "test_captures_behaviour": True, "gold_lines_decide": True},
               "click-2": {"genuine_question": False, "genuine_question_note": " asks for a new feature ",
                           "test_captures_behaviour": True, "gold_lines_decide": True},
               "click-3": {"genuine_question": True}}  # incomplete: not exported
    js = _logic() + f"""
    const L = module.exports;
    const text = {json.dumps("".join(json.dumps(r) + chr(10) for r in rows))};
    const rows = L.parseJsonl(text);
    process.stdout.write(L.toJsonl(rows, {json.dumps(answers)}, "2026-11-07T10:00:00.000Z"));
    """
    lines = [json.loads(line) for line in _node("var module = {exports: {}};" + js).splitlines() if line.strip()]
    verdicts = [Verdict.model_validate(r) for r in lines]
    assert [v.qid for v in verdicts] == ["click-1", "click-2"]
    assert verdicts[0].valid and not verdicts[1].valid
    assert verdicts[1].genuine_question_note == "asks for a new feature"


def test_parse_rejects_mixed_or_foreign_files():
    js = "var module = {exports: {}};" + _logic() + r"""
    const L = module.exports; const out = [];
    for (const t of ['{"qid":"a","member":"x"}\n{"qid":"b","member":"y"}', '{"foo":1}', 'not json', '']) {
      try { L.parseJsonl(t); out.push("ok"); } catch (e) { out.push("error"); }
    }
    process.stdout.write(out.join(","));
    """
    assert _node(js) == "error,error,error,error"


def test_diff_line_classes():
    js = "var module = {exports: {}};" + _logic() + r"""
    const L = module.exports;
    process.stdout.write(["diff --git a/x b/x", "+++ b/x", "@@ -1 +1 @@", "+new", "-old", " same"].map(L.diffLineClass).join(","));
    """
    assert _node(js) == "file,file,hunk,add,del,"


def test_page_renders_a_real_member_file(tmp_path):
    chrome = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")
    member_file = REPO_ROOT / "annotation" / "spotcheck_sourav.jsonl"
    if not chrome or not member_file.exists():
        pytest.skip("needs Chrome and a drawn sample")
    # Load the member file the way the page would after "Open my file…", then dump the DOM.
    page = tmp_path / "page.html"
    data = json.dumps(member_file.read_text(encoding="utf-8"))
    page.write_text(PAGE.read_text(encoding="utf-8").replace(
        "</body>", f"<script>window.__spotcheck.show({data});</script></body>"), encoding="utf-8")
    out = subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-sandbox", f"--user-data-dir={tmp_path / 'profile'}",
                          "--dump-dom", page.as_uri()], capture_output=True, text=True, timeout=60)
    dom = out.stdout
    rows = [json.loads(line) for line in member_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert dom.count('class="card') == len(rows)
    assert all(f'id="card-{r["qid"]}"' in dom for r in rows)
    assert f"sourav: 0 of {len(rows)} answered" in dom
    assert dom.count('type="radio"') == 6 * len(rows)
