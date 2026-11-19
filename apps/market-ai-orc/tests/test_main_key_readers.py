"""EXEC-MU-ACCOUNTS fix round (re-check R1-2; ERRORS M475, M477): the code side of retiring market-ai-orc's main key
from orc-test-runner.

MARKET_AI_ORC_API_KEY may name any owner; MARKET_AI_ORC_TEST_KEY only test owners (golden-*, test-*, someone-else).
orc-test-runner is the project's general job box: it runs apps/orc-test-runner itself and every job that
scripts/onboarding/run_job.sh uploads from scripts/ and verification/. The variable is still on the service
(.railway/railway.ts; verification/edge_multiuser/access_tiers/pending/test_cp0_runner_key.py waits for its deletion
with the user's go). This test holds the precondition of that deletion: no code the runner can run reads the main key,
so deleting it breaks nothing, and a job that starts reading it fails here before it is uploaded.

The readers allowed are derived, not listed by file: the two services that hold the key on Railway and their tests.
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[3]
KEY = 'MARKET_AI_ORC_API_KEY'
# what orc-test-runner runs: its own folder and every job script run_job.sh uploads (any path under these)
RUNNER_CODE = ('apps/orc-test-runner', 'scripts', 'verification')
CODE = {'.py', '.sh', '.mjs', '.js', '.ts', '.mts'}


def readers(top):
    for path in sorted((ROOT / top).rglob('*')):
        if path.suffix not in CODE or 'node_modules' in path.parts or not path.is_file():
            continue
        text = path.read_text(errors='replace')
        if re.search(r'\b' + KEY + r'\b', text):
            yield path.relative_to(ROOT).as_posix()


def test_no_code_the_runner_runs_reads_the_main_orc_key():
    found = [path for top in RUNNER_CODE for path in readers(top)
             # the pending test reads railway.ts for the variable's name, not the environment
             if not path.endswith('pending/test_cp0_runner_key.py')]
    assert found == [], (
        f'{found} name {KEY}: orc-test-runner runs this code, and the main key may name any owner (M475). Use '
        'MARKET_AI_ORC_TEST_KEY with a test owner (golden-*, test-*, someone-else), as apps/orc-test-runner/run.py does')


def test_the_runner_reads_only_the_test_key():
    run = (ROOT / 'apps/orc-test-runner/run.py').read_text()
    assert 'os.environ["MARKET_AI_ORC_TEST_KEY"]' in run
    assert KEY not in run
