"""Gate G0: check the environment without ever printing a key's value.

Checks Python, git, Docker, the presence of each key, one tiny live call per
API (to confirm each key works), and the git remote. Prints one line per check.

Usage: python scripts/check_env.py [--no-network]
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import REPO_ROOT, load_config  # noqa: E402
from core.env import key_present, key_report, require_key  # noqa: E402

EXPECTED_REMOTE = "github.com/ameya-purohit/LMA-Final-Project"


def _run(cmd: list[str]) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=60, cwd=REPO_ROOT)
        return p.returncode, (p.stdout + p.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)


def _safe(exc: Exception) -> str:
    """Error text with any key value scrubbed out, truncated."""
    text = f"{type(exc).__name__}: {exc}"
    for name in ("GEMINI_API_KEY", "GROQ_API_KEY", "GITHUB_TOKEN", "MISTRAL_API_KEY"):
        if key_present(name):
            text = text.replace(require_key(name), "<redacted>")
    return text[:300]


def check_gemini(model: str) -> str:
    from google import genai
    client = genai.Client(api_key=require_key("GEMINI_API_KEY"))
    r = client.models.generate_content(model=model, contents="Reply with the single word: ok")
    return f"ok (model {model} replied {r.text.strip()[:20]!r})"


def check_groq(model: str) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=require_key("GROQ_API_KEY"), base_url="https://api.groq.com/openai/v1")
    r = client.chat.completions.create(model=model, max_tokens=200, temperature=0,
                                       messages=[{"role": "user", "content": "Reply with the single word: ok"}])
    return f"ok (model {model} replied {r.choices[0].message.content.strip()[:20]!r})"


def check_mistral() -> str:
    from mistralai import Mistral
    client = Mistral(api_key=require_key("MISTRAL_API_KEY"))
    models = client.models.list()
    return f"ok ({len(models.data)} models visible)"


def check_github() -> str:
    import requests
    r = requests.get("https://api.github.com/rate_limit", timeout=20,
                     headers={"Authorization": f"Bearer {require_key('GITHUB_TOKEN')}"})
    r.raise_for_status()
    core = r.json()["resources"]["core"]
    return f"ok (rate limit {core['remaining']}/{core['limit']})"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-network", action="store_true")
    args = ap.parse_args(argv)
    cfg = load_config()
    results: list[tuple[str, bool, str]] = []

    ok = sys.version_info >= (3, 10)
    results.append(("python", ok, sys.version.split()[0]))
    code, out = _run(["git", "--version"])
    results.append(("git", code == 0, out))
    if shutil.which("docker"):
        code, out = _run(["docker", "info", "--format", "{{.ServerVersion}}"])
        results.append(("docker", code == 0, f"server {out}" if code == 0 else out[:200]))
    else:
        results.append(("docker", False, "docker CLI not found"))
    for name, status in key_report().items():
        optional = name == "MISTRAL_API_KEY"
        results.append((f"key {name}", status == "present" or optional, status + (" (optional)" if optional else "")))
    code, out = _run(["git", "remote", "get-url", "origin"])
    results.append(("git remote", code == 0 and EXPECTED_REMOTE in out, out))

    if not args.no_network:
        checks = [
            ("gemini api", "GEMINI_API_KEY", lambda: check_gemini(cfg["llm"]["main"]["model"])),
            ("groq api", "GROQ_API_KEY", lambda: check_groq(cfg["llm"]["judge"]["model"])),
            ("github api", "GITHUB_TOKEN", check_github),
            ("mistral api", "MISTRAL_API_KEY", check_mistral),
        ]
        for label, key, fn in checks:
            if not key_present(key):
                results.append((label, key == "MISTRAL_API_KEY", "skipped: key missing"))
                continue
            try:
                results.append((label, True, fn()))
            except Exception as exc:  # report, never crash: G0 is a report
                results.append((label, False, _safe(exc)))

    for label, ok, detail in results:
        print(f"[{'OK ' if ok else 'FAIL'}] {label:24s} {detail}")
    return 0 if all(ok for _, ok, _ in results) else 1


if __name__ == "__main__":
    sys.exit(main())
