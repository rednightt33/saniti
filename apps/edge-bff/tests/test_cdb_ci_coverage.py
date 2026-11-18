"""C-DB re-check of EXEC-MU-ACCOUNTS Phases 0-3b (2026-11-18): the multi-user tests CI never runs. Failing tests of
verified findings; the fix round makes them pass.

edge-bff deploys only on green checks (checkSuites), and CONTRACT section 13 says every acceptance test runs in CI. Shown
by mutation on 93c9f645: with clearUserState keeping every user key (a sign-out that leaves the account's data, M473)
and static/edge-session.js rebuilt as AGENTS.md says, the edge-bff suite passes, with and without Chromium; only the
Terminal vitest suite fails (12 tests: edge_session.test.ts, c3_phase1_switch_off.test.ts, c4_seed_phase0_mark.test.ts),
and no workflow runs it. A hand edit of static/edge-session.js that keeps its first line passes
tests/test_storage_registry.py; only `node shared/build-shell.mjs --check` fails, and no workflow runs it either.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS = sorted((ROOT / '.github/workflows').glob('*.yml'))


def runs(fragment, directory=None):
    """A workflow step runs a command holding `fragment` (in `directory` when given: its working-directory)."""
    for path in WORKFLOWS:
        text = path.read_text()
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if fragment in line and 'run' in ''.join(lines[max(0, i - 3):i + 1]):
                window = '\n'.join(lines[max(0, i - 6):i + 1])
                if directory is None or directory in window:
                    return True
    return False


def test_ci_runs_the_terminal_vitest_suite_that_holds_the_session_module_tests():
    # apps/edge-bff/terminal/tests/data/edge_session*.test.ts, c1_security_findings, c3_phase1_switch_off,
    # c4_seed_phase0_mark, fixture_bundle (M468, M469, M471, M473, M478): shared/edge-session.ts is tested only there
    assert runs('vitest', 'apps/edge-bff/terminal'), (
        'no workflow runs `npx vitest run` in apps/edge-bff/terminal: the session module (sign-out clearing, change of '
        'user, access.seed, the 403 contract) is tested by no CI job; add the step to a workflow in edge-bff\'s checks')


def test_ci_compares_the_shell_copy_with_its_build():
    assert runs('build-shell.mjs --check'), (
        'no workflow runs `node shared/build-shell.mjs --check`: tests/test_storage_registry.py compares only the '
        'source sha256 in the first line of static/edge-session.js, so an edited body ships unseen (AGENTS.md: a '
        'generated file has a generated_file test that compares it with what the script writes now)')


def test_ci_runs_orc_conversation_ownership_against_postgres():
    # apps/market-ai-orc/tests/test_conversations.py (pytestmark skipif without ORC_TEST_POSTGRES_URL) holds the
    # Phase 0 C2 fix test test_c2_a_client_run_may_name_only_a_conversation_its_owner_holds and the owner isolation
    # test test_another_owner_cannot_continue_or_read_a_conversation (CONTRACT section 13.3)
    text = (ROOT / '.github/workflows/backend-tests.yml').read_text()
    orc = text[text.index('  market-ai-orc:'):text.index('  terminal-api:')]
    assert 'ORC_TEST_POSTGRES_URL' in orc, (
        'backend-tests.yml runs market-ai-orc without ORC_TEST_POSTGRES_URL, so test_conversations.py (the owner '
        'isolation of conversations and the C2 CLIENT-history fix) is skipped in CI')
