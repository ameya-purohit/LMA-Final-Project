"""Load API keys from `.env` and check that they are present, never what they are.

Why a helper: several components need keys, and the rule "never print, log or
commit key values" (CLAUDE.md §0.2) is easiest to keep if exactly one place
reads them and every report says only "present" or "missing".
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from core.config import REPO_ROOT

REQUIRED_KEYS = ("GEMINI_API_KEY", "GROQ_API_KEY", "GITHUB_TOKEN")
OPTIONAL_KEYS = ("MISTRAL_API_KEY",)

_loaded = False


def load_env(path: str | Path | None = None) -> None:
    """Load `.env` once. Existing environment variables win over the file."""
    global _loaded
    if _loaded and path is None:
        return
    load_dotenv(Path(path) if path else REPO_ROOT / ".env", override=False)
    _loaded = True


def key_present(name: str) -> bool:
    load_env()
    return bool(os.environ.get(name, "").strip())


def require_key(name: str) -> str:
    """Return a key's value for an SDK client; raise if missing.

    The error names the key, never a value.
    """
    load_env()
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is not set; add it to .env (see .env.example)")
    return value


def key_report() -> dict[str, str]:
    """{key_name: "present" | "missing"} for required and optional keys."""
    return {k: ("present" if key_present(k) else "missing") for k in REQUIRED_KEYS + OPTIONAL_KEYS}
