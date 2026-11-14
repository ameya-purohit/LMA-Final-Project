#!/usr/bin/env bash
# Unattended run of the exploratory extension (PREREGISTRATION.md, "Exploratory extension").
# Waits for any extension job already running, checks E5 on 2 dev questions, then runs E1-E6 on the 47 test
# questions, the judge and the tables. Every step is resumable: re-running this script skips finished work.
# On a daily-quota stop (exit code 3) it waits an hour and tries again, up to 12 times.
# Usage: bash scripts/run_extension.sh      (log: results/ext_pipeline.log)
set -u
cd "$(dirname "$0")/.."
source .venv/bin/activate
export PYTHONPATH="$PWD"
LOG=results/ext_pipeline.log
TEST=(--split test --allow-test --run-id ext --qids-file data/ext_qids.txt)

say() { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }

wait_for() {  # wait until no process matches the pattern
  while pgrep -f "$1" > /dev/null; do sleep 30; done
}

with_quota_retry() {  # run a command; on exit 3 (daily quota) wait an hour and retry
  local tries=0 code
  while true; do
    "$@"; code=$?
    [ "$code" -ne 3 ] && return "$code"
    tries=$((tries + 1))
    [ "$tries" -ge 12 ] && return 3
    say "quota stop in: $* ; retrying in 1 hour ($tries/12)"
    sleep 3600
  done
}

run_system() {  # run one system twice: the second pass retries any question that failed
  local sys=$1
  for pass in 1 2; do
    with_quota_retry python -m eval.run --system "$sys" "${TEST[@]}" >> "results/ext_$sys.log" 2>&1
    local code=$?
    say "$sys pass $pass exit $code: $(tail -1 "results/ext_$sys.log")"
    [ "$code" -eq 3 ] && return 3
  done
}

say "start"
wait_for "analysis.retrieval_study"
wait_for "eval.run --system e1 --split test"
say "retrieval study and E1 first pass finished"

# Check the graph and hybrid parts on real code before spending test runs on them.
with_quota_retry python -m eval.run --system e5 --split dev --limit 2 --run-id ext_dev >> results/ext_dev_e5.log 2>&1
if grep -q "FAILED" results/ext_dev_e5.log || ! grep -q "2 of 2 done" results/ext_dev_e5.log; then
  say "E5 dev check FAILED; stopping before the test runs. See results/ext_dev_e5.log"
  exit 1
fi
say "E5 dev check passed: $(tail -1 results/ext_dev_e5.log)"

# One system at a time: each E2+ process loads the embedding and reranking models (~1 GB), and two at once ran
# this 6 GB laptop out of memory (2026-11-12 02:47). E4-E6 reuse earlier systems' cached agent calls.
for sys in e1 e2 e3 e4 e5 e6; do run_system "$sys"; done
say "all systems finished"

for sys in e1 e2 e3 e4 e5 e6; do
  with_quota_retry python -m eval.judge --run-id ext --split test --system "$sys" >> results/ext_judge.log 2>&1
  say "judge $sys exit $?: $(tail -1 results/ext_judge.log)"
done

python -m analysis.retrieval_study --split test > /dev/null 2>&1
python -m analysis.extension --run-id ext >> "$LOG" 2>&1
say "DONE: results/summary/extension.md and results/summary/retrieval_study.md"
