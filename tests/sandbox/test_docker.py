"""The real Docker sandbox (marker `docker`): outcomes, isolation, limits, shim."""

import shutil
import subprocess

import pytest

from core.config import load_config
from sandbox.session import SandboxSession
from tools.probe import run_probe

pytestmark = pytest.mark.docker
IMAGE = load_config()["sandbox"]["image"]


def _image_available():
    if shutil.which("docker") is None:
        return False
    p = subprocess.run(["docker", "image", "inspect", IMAGE], capture_output=True)
    return p.returncode == 0


@pytest.fixture
def box(fakelib_tree):
    if not _image_available():
        pytest.skip(f"Docker or image {IMAGE} not available (docker build -t {IMAGE} sandbox)")
    s = SandboxSession(fakelib_tree, "fakelib", config={"sandbox": {**load_config()["sandbox"], "probe_timeout_s": 2}})
    s.start()
    yield s
    s.cleanup()


def test_pass_fail_raise(box, probes):
    r = run_probe(box, probes.passing, [probes.failing, probes.raising])
    claim, failing, raising = r.results
    assert claim.status == "pass" and claim.outcome == {"kind": "return", "repr": "8"}
    assert failing.status == "fail"
    assert raising.status == "error" and raising.outcome["type"] == "ValueError"
    assert raising.outcome["innermost_frame"] == "fakelib/__init__.py:10"


def test_container_is_locked_down(box):
    inspect = subprocess.run(["docker", "inspect", "-f",
                              "{{.HostConfig.NetworkMode}} {{.HostConfig.ReadonlyRootfs}} {{.Config.User}}",
                              box.container], capture_output=True, text=True).stdout.split()
    assert inspect[0] == "none" and inspect[1] == "true" and not inspect[2].startswith("0")
    assert box.exec_raw(["id", "-u"]).stdout.strip() != "0"


def test_network_fails_inside_container(box):
    # Bypasses the policy on purpose (trusted test code) to show the container itself has no network.
    code = ("import socket\n"
            "def observe():\n    return socket.create_connection(('1.1.1.1', 53), timeout=3)\n"
            "def test_claim():\n    observe()\n")
    out = box.run_probes([("net", code)])
    outcome = out["results"][0]["outcome"]
    assert outcome["kind"] == "raise" and outcome["type"] in ("OSError", "gaierror", "TimeoutError", "timeout")
    dns = ("import socket\ndef observe():\n    return socket.gethostbyname('github.com')\n"
           "def test_claim():\n    observe()\n")
    assert box.run_probes([("dns", dns)])["results"][0]["outcome"]["kind"] == "raise"


def test_writes_outside_tmp_fail_inside_container(box):
    code = ("def observe():\n    open('/work/lib/hacked.txt', 'w').write('x')\n"
            "def test_claim():\n    observe()\n")
    outcome = box.run_probes([("w", code)])["results"][0]["outcome"]
    assert outcome["kind"] == "raise" and outcome["type"] in ("OSError", "PermissionError")
    tmp = "def observe():\n    open('/tmp/ok.txt', 'w').write('x')\n    return open('/tmp/ok.txt').read()\n" \
          "def test_claim():\n    assert observe() == 'x'\n"
    assert box.run_probes([("t", tmp)])["results"][0]["status"] == "pass"


def test_policy_blocks_before_container(box):
    for bad in ("import os\ndef observe():\n    os.system('id')\ndef test_claim():\n    pass\n",
                "import subprocess\n", "def observe():\n    eval('1')\n", "__import__('os')\n",
                "def observe():\n    open('/work/lib/x', 'w')\n"):
        assert run_probe(box, bad).blocked
    assert box.jobs_run == 0, "blocked probes must never reach the container"


def test_timeout_enforced(box, probes):
    assert run_probe(box, probes.slow).claim.outcome["type"] == "ProbeTimeout"


def test_metadata_shim(box, probes):
    assert run_probe(box, probes.metadata).claim.status == "pass"


def test_environment_pinned(box):
    code = ("import os, sys, time\n"
            "def observe():\n    return (sys.version_info[:2], os.environ.get('TZ'), os.environ.get('LANG'),"
            " os.environ.get('PYTHONHASHSEED'), sys.stdout.isatty())\n"
            "def test_claim():\n    pass\n")
    repr_ = box.run_probes([("env", code)])["results"][0]["outcome"]["repr"]
    assert repr_ == "((3, 10), 'UTC', 'C.UTF-8', '0', False)"


def test_repo_tests_run(box):
    out = box.run_pytest(["tests/test_double.py"])
    assert out["tests"]["tests/test_double.py::test_ok"]["status"] == "passed"
    assert out["tests"]["tests/test_double.py::test_bad"]["status"] == "failed"
    assert box.cpu_seconds > 0
