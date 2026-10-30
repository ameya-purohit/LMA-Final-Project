"""The zero-cost ablations: pure formatting, plus a Docker run of A6 on one claim."""

import shutil
import subprocess

import pytest

from analysis import toylib_ablations as T
from core.config import load_config


def test_every_planted_mark_exists():
    for claim in T.CLAIMS:
        for mark in claim["lines"]:
            assert T.mark_line(mark) >= 1
    assert T.mark_line("strict_default") == 12 and T.mark_line("decider") == 88


def test_markdown_counts_agreement():
    a6 = [{"claim": "c", "line": 1, "mark": "m", "ground_truth_causal": True, "any_flip": True, "behavioural": True,
           "specific": False, "specific_constants_only": False}]
    leniency = [{"claim": "c", "n_executed": 4, "share_any_flip": 0.5, "share_behavioural": 0.25, "share_specific": 0.25,
                 "accepted": {"any_flip": [1, 2], "behavioural": [1], "specific": [1]}}]
    md = T.to_markdown(a6, leniency)
    assert "any flip 1, behavioural 1, behavioural + specific 0" in md and "| All | 4 | 50% | 25% | 25% |" in md


@pytest.mark.docker
def test_a6_in_docker():
    cfg = load_config()
    if shutil.which("docker") is None or subprocess.run(["docker", "image", "inspect", cfg["sandbox"]["image"]], capture_output=True).returncode:
        pytest.skip("Docker or image not available")
    from sandbox.session import SandboxSession
    s = SandboxSession(T.TOYLIB, "toylib", config=cfg)
    s.start()
    try:
        rows = T.run_a6(s)
    finally:
        s.cleanup()
    by_mark = {r["mark"]: r for r in rows}
    assert by_mark["decider"]["specific"] and not by_mark["strict_default"]["specific"] and by_mark["strict_default"]["any_flip"]
    assert by_mark["return_result"]["behavioural"] and not by_mark["return_result"]["specific"]
    assert by_mark["compare_no_const"]["specific"] and not by_mark["compare_no_const"]["specific_constants_only"]
