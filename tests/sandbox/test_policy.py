import pytest

from sandbox import policy
from tools.probe import run_probe
from llm.trace import Tracer


def rules(code):
    return [v.rule for v in policy.check(code)]


@pytest.mark.parametrize("code,rule", [
    ("import os\nos.system('ls')", "blocked_call"),
    ("import os\nos.popen('ls')", "blocked_call"),
    ("from os import system", "blocked_call"),
    ("import subprocess", "blocked_import"),
    ("from subprocess import run", "blocked_import"),
    ("import socket", "blocked_import"),
    ("eval('1+1')", "dynamic_code"),
    ("exec('x=1')", "dynamic_code"),
    ("__import__('os')", "dynamic_code"),
    ("open('/etc/passwd', 'w')", "write_outside_tmp"),
    ("open('notes.txt', mode='a')", "write_outside_tmp"),
    ("from pathlib import Path\nPath('/work/lib/x').write_text('x')", "write_outside_tmp"),
    ("import os\nos.remove('/work/lib/a.py')", "blocked_call"),
    ("getattr(__builtins__, 'eval')", "introspection_escape"),
    ("().__class__.__base__.__subclasses__()", "introspection_escape"),
    ("import importlib\nimportlib.import_module('os')", "blocked_import"),
])
def test_blocked(code, rule):
    assert rule in rules(code)


@pytest.mark.parametrize("code", [
    "import click\nfrom click.testing import CliRunner\n",
    "open('/tmp/x.txt', 'w').write('ok')",
    "with open('/tmp/a/b.json', 'w') as fh: pass",
    "from pathlib import Path\nPath('/tmp/x').write_text('y')",
    "open('README.rst').read()",
    "x = 'a-b'.replace('-', '_')\nitems = [1, 2]\nitems.remove(1)",
    "import os\nos.path.join('a', 'b')\nos.environ.get('HOME')",
    "import pytest, hypothesis, json, re, datetime, decimal\nvars(object())",
    "def f(:\n  pass",  # syntax errors are the runner's business, not the policy's
])
def test_allowed(code):
    assert policy.check(code) == []


def test_run_probe_blocks_and_logs_without_running():
    class NeverRun:
        def run_probes(self, *a, **k):
            raise AssertionError("a blocked probe must not reach the sandbox")

    tracer = Tracer(None)
    report = run_probe(NeverRun(), "def observe():\n    pass\ndef test_claim():\n    pass\n",
                       ["import os\ndef observe():\n    os.system('id')\ndef test_claim():\n    pass\n"], tracer=tracer)
    assert report.blocked and report.violations[0]["probe"] == "control_1"
    assert tracer.records[0]["event"] == "unsafe_attempt"
    assert tracer.records[0]["violations"][0]["detail"] == "system"
