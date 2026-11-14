"""Prompt files of the multi-agent extension, loaded by name."""

from pathlib import Path

DIR = Path(__file__).resolve().parent


def load(name: str) -> str:
    return (DIR / f"{name}.txt").read_text(encoding="utf-8")
