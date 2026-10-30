# The sandbox: every probe, mutant and repo test runs here, never on the host (CLAUDE.md §2.5).
# At run time the container also gets: --network none, CPU/memory/pid limits, a read-only root
# filesystem with a tmpfs /tmp, and the frozen library mounted read-only (see sandbox/session.py).
FROM python:3.10-slim

# Pinned packages: probe helpers plus the test dependencies of the studied libraries.
COPY test-requirements.txt /opt/runner/test-requirements.txt
RUN pip install --no-cache-dir -r /opt/runner/test-requirements.txt

# Pin the environment so behaviour that depends on it is reproducible (proposal §6.2).
ENV TZ=UTC \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONHASHSEED=0 \
    PYTHONUNBUFFERED=1 \
    HOME=/tmp

# The trusted runner that imports probes and reports outcomes as JSON.
COPY runner.py /opt/runner/runner.py

# Never run as root inside the sandbox.
RUN useradd --create-home --uid 10001 sandbox
USER sandbox
WORKDIR /tmp
