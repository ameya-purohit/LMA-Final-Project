"""Click through the Streamlit demo with Streamlit's own test harness. Skipped where Streamlit is not installed
(it is an optional dependency, `demo/requirements.txt`), so CI without it is unaffected."""

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

from core.config import REPO_ROOT  # noqa: E402

PAGES = ["1 · The idea", "2 · Live: run it, flip the switch", "3 · Results", "4 · Inside one question",
         "5 · Multi-agent extension"]


def test_every_page_renders_without_an_exception():
    at = AppTest.from_file(str(REPO_ROOT / "demo" / "app.py"), default_timeout=120).run()
    for page in PAGES:
        at.sidebar.radio[0].set_value(page).run()
        assert not at.exception, f"{page}: {[e.value for e in at.exception]}"
        assert at.title, page


def test_live_page_buttons_run_on_toylib():
    at = AppTest.from_file(str(REPO_ROOT / "demo" / "app.py"), default_timeout=120).run()
    at.sidebar.radio[0].set_value(PAGES[1]).run()
    if at.toggle:
        at.toggle[0].set_value(False).run()          # trusted local runner: no Docker needed
    at.button[0].click().run()
    assert not at.exception and any("holds" in s.value for s in at.success)
    at.button[1].click().run()                       # line 88, the planted decider
    assert not at.exception and [m.value for m in at.metric][:3] == ["accept", "accept", "accept"]
