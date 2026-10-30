import pytest

from core import env


@pytest.fixture(autouse=True)
def no_dotenv(monkeypatch):
    """These tests set keys themselves; never read (or mark as read) the real .env."""
    monkeypatch.setattr(env, "load_env", lambda path=None: None)


def test_key_present_and_require(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "  value  ")
    assert env.key_present("GEMINI_API_KEY")
    assert env.require_key("GEMINI_API_KEY") == "value"
    monkeypatch.setenv("GROQ_API_KEY", "")
    assert not env.key_present("GROQ_API_KEY")
    with pytest.raises(RuntimeError, match="GROQ_API_KEY") as e:
        env.require_key("GROQ_API_KEY")
    assert "value" not in str(e.value)


def test_report_never_contains_values(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "secret-token-123")
    report = env.key_report()
    assert report["GITHUB_TOKEN"] == "present"
    assert "secret-token-123" not in repr(report)
    assert set(report.values()) <= {"present", "missing"}
