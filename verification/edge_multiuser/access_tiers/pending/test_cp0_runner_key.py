"""Checker C-P0 (EXEC-MU-ACCOUNTS Phase 0, CONTRACT.md section 7 and 16; ERRORS M475, M477): orc-test-runner still
holds market-ai-orc's main key.

M475's class is "identity accepted from a shared key without a per-caller scope": the test runner held
MARKET_AI_ORC_API_KEY, which may name any owner. The fix gave the runner MARKET_AI_ORC_TEST_KEY (test owners only) and
made run.py read only that key (M477 C1 M4). The main key itself was left on the service "until a runner suite passes
with the test key" (RAILWAY_CHANGELOG.md 2026-11-16 Phase 0, step 4 and "Still open"); no later entry removes it, and
.railway/railway.ts (the live project as code) still lists it. The service is the project's general job box (one-off
jobs with a temporary DATABASE_URL, RAILWAY_CHANGELOG.md), so any code uploaded there can read the main key and name a
real user's owner (u_...) once EDGE_MULTIUSER is on. The open item is recorded only in that changelog line, not in
M475/M477's status nor in CONTRACT.md 8b's "Open before the switch goes on".
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[3]


def service_env(name):
    text = (ROOT / '.railway/railway.ts').read_text()
    block = re.search(r'service\("' + re.escape(name) + r'", \{(.*?)\n  \}\);', text, re.S)
    assert block, f'{name} block not found in .railway/railway.ts'
    env = re.search(r'env: \{([^}]*)\}', block.group(1))
    return set(re.findall(r'([A-Z][A-Z0-9_]+): ', env.group(1))) if env else set()


def test_orc_test_runner_holds_only_the_test_key():
    env = service_env('orc-test-runner')
    assert 'MARKET_AI_ORC_TEST_KEY' in env
    assert 'MARKET_AI_ORC_API_KEY' not in env, (
        'orc-test-runner still holds MARKET_AI_ORC_API_KEY, the key that may name any owner (M475): remove it from '
        'the service after a runner suite has passed with MARKET_AI_ORC_TEST_KEY, then drop it from .railway/railway.ts')
