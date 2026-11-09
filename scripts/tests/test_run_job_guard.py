"""ERRORS M322 (user go 2026-11-01): a runner job is finished by the wrapper's marker, not by what the job prints.

The Dockerfiles' wrapper prints JOB_EXIT <exit code> after job.py and keeps the exit code (the runner restarts a failed
job, ON_FAILURE until 2026-11-01, now NEVER); run_job.sh's guard reads the log of the latest container start. No Railway
call is made here."""
import json
import os
import subprocess
from pathlib import Path

import pytest

ONBOARDING = Path(__file__).resolve().parents[1] / 'onboarding'
GUARD = ONBOARDING / 'runner_guard.sh'
CALLERS = [ONBOARDING / 'run_job.sh', ONBOARDING.parents[1] / 'verification/screener/jobs/run_terminal_check.sh']


def is_finished(log: str) -> bool:
    script = f'. "{GUARD}"\nfinished && echo yes || echo no'
    return subprocess.run(['bash', '-c', script], input=log, capture_output=True, text=True, check=True).stdout.strip() == 'yes'


@pytest.mark.parametrize('log, done', [
    ('Starting Container\nOUT {"q": 1}\nJOB_EXIT 0\n', True),                      # a job that never prints JOB_DONE
    ('Starting Container\nOUT {"q": 1}\n', False),                                  # still running
    ('Starting Container\nTraceback (most recent call last):\nJOB_EXIT 1\n', True),   # failed: restart policy NEVER, finished
    ('Starting Container\nJOB_EXIT 1\nStarting Container\nOUT {"q": 1}\n', False),  # a later start (by hand) is running
    ('Starting Container\nJOB_EXIT 1\nStarting Container\nJOB_EXIT 0\n', True),     # the restart succeeded
    ('Starting Container\nMIG APPLY x\nJOB_DONE MIGRATION APPLY\n', True),          # a job from before the wrapper
    ('OTR {"event": "done"}\n', True),                                              # an orc-test-runner suite
    ('OUT 1\nJOB_EXIT 0\n', True),                                                  # no start line: the whole log
    ('Starting Container\nJOB_EXIT 10\n', True),                                    # any exit code ends the job
    ('Starting Container\nTraceback (most recent call last):\n', True),             # a job from before the wrapper that failed
    ('Starting Container\nOUT JOB_EXIT 0 later\n', False),                          # the marker is a whole line's end
    ('Starting Container\nOUT 1\nJOB_EXIT 0\nStarting Container\n', True),          # M341: a fast job's start logged late
    ('OUT 1\nJOB_EXIT 0\nStarting Container\n', True),                               # the same with no earlier start line
    ('Starting Container\nJOB_EXIT 0\nStarting Container\nOUT 1\n', False),         # a real later start is running
    ('Starting Container\nJOB_EXIT 0\nMIG x\nJOB_DONE X\nStarting Container\n', True),  # M415: one second, any order
    ('OUT 1\nJOB_EXIT 0\nOUT 2\nStarting Container\n', True),                       # the same with no earlier start line
    ('Starting Container\nOUT 1\nStarting Container\n', False),                     # no JOB_EXIT: a start, not late
])
def test_guard_reads_the_latest_start(log, done):
    assert is_finished(log) is done


@pytest.mark.parametrize('dockerfile', ['Dockerfile', 'Dockerfile.l2'])
@pytest.mark.parametrize('body, code', [
    ('print("OUT 1")', 0),                       # prints no marker of its own
    ('raise SystemExit(3)', 3),
    ('raise RuntimeError("boom")', 1),
])
def test_wrapper_prints_the_exit_code_and_keeps_it(tmp_path, dockerfile, body, code):
    cmd = next(line for line in (ONBOARDING / dockerfile).read_text().splitlines() if line.startswith('CMD '))
    argv = json.loads(cmd[len('CMD '):])
    (tmp_path / 'job.py').write_text(body + '\n')
    run = subprocess.run(argv, cwd=tmp_path, capture_output=True, text=True)
    assert run.returncode == code
    assert run.stdout.splitlines()[-1] == f'JOB_EXIT {code}'


FAKE_RAILWAY = """#!/bin/bash
# stands in for the Railway CLI: the deployment list and one deployment's log, from the test's environment
case "$1 $2" in
  "deployment list") printf '%s' "$FAKE_LIST" ;;
  logs*) printf '%s' "$FAKE_LOG" ;;
esac
"""


@pytest.mark.parametrize('status, log, free', [
    ('SUCCESS', 'Starting Container\nOUT 1\nJOB_EXIT 0\n', True),
    ('SUCCESS', 'Starting Container\nOUT 1\n', False),
    ('BUILDING', '', False),
    ('CRASHED', 'Starting Container\nJOB_EXIT 1\n', True),
])
def test_runner_free_reads_the_latest_deployment(tmp_path, status, log, free):
    (tmp_path / 'railway').write_text(FAKE_RAILWAY)
    (tmp_path / 'railway').chmod(0o755)
    env = {**os.environ, 'PATH': f'{tmp_path}:{os.environ["PATH"]}',
           'FAKE_LIST': json.dumps([{'id': 'dep-1', 'status': status}]), 'FAKE_LOG': log}
    run = subprocess.run(['bash', '-c', f'. "{GUARD}"; runner_free p e s'], env=env, capture_output=True, text=True)
    assert (run.returncode == 0) is free, run.stdout
    if not free:
        assert run.stdout.startswith('RUNNER_BUSY dep-1')


def test_every_runner_script_uses_the_shared_guard():
    """M322 class: a second copy of the check went stale; every script that starts a runner job sources the one guard."""
    for script in CALLERS:
        text = script.read_text()
        assert 'runner_guard.sh' in text and 'runner_free $P $E $S' in text, script
        assert "grep -q 'JOB_DONE" not in text, script
