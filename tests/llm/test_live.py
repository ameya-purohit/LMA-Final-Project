"""Live checks against the real APIs (marker `live`; uses a few requests of free quota)."""

import pytest

from core.env import key_present

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def client():
    if not (key_present("GEMINI_API_KEY") and key_present("GROQ_API_KEY")):
        pytest.skip("API keys not present")
    from scripts.smoke_llm import make_client
    return make_client()[0]


def test_gemini_plain(client):
    from scripts.smoke_llm import plain_call
    assert "gemini" in plain_call(client, "main")


def test_groq_judge_plain(client):
    from scripts.smoke_llm import plain_call
    assert "groq" in plain_call(client, "judge")


def test_gemini_function_round_trip_keeps_thought_signature(client):
    from scripts.smoke_llm import function_round_trip
    assert "turn 2 answered" in function_round_trip(client)
