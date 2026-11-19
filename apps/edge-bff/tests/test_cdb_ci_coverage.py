"""C-DB re-check of EXEC-MU-ACCOUNTS Phases 0-3b (2026-11-18): the multi-user tests CI never runs. Failing tests of
verified findings; the fix round makes them pass.

edge-bff deploys only on green checks (checkSuites), and CONTRACT section 13 says every acceptance test runs in CI. Shown
by mutation on 93c9f645: with clearUserState keeping every user key (a sign-out that leaves the account's data, M473)
and static/edge-session.js rebuilt as AGENTS.md says, the edge-bff suite passes, with and without Chromium; only the
Terminal vitest suite fails (12 tests: edge_session.test.ts, c3_phase1_switch_off.test.ts, c4_seed_phase0_mark.test.ts),
and no workflow runs it. A hand edit of static/edge-session.js that keeps its first line passes
tests/test_storage_registry.py; only `node shared/build-shell.mjs --check` fails, and no workflow runs it either.

Fix round (records track, 2026-11-19). The refuters of R1-39 and R1-44 noted that the first two checks locked one
instance and one form: the Terminal alone of the page suites no workflow ran (overview, radar and watchlist too), and
a workflow line holding `build-shell.mjs --check`, while AGENTS.md's own form for a generated file is a test marked
generated_file that generated-files.yml runs. The checks below hold the properties instead, derived from the
repository: every package under apps/ with a test script is run by a workflow step in its folder; the shell copy is
compared with its build by a workflow step or by a generated_file test that a workflow runs with the Terminal's
esbuild installed; the edge-bff job installs Playwright with Chromium, so its browser tests (CONTRACT 13.8) run.
"""
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS = sorted((ROOT / '.github/workflows').glob('*.yml'))
TEST_COMMAND = re.compile(r'\bnpm (run )?test\b|\bvitest run\b|\bnode --test\b')


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


def jobs(path):
    """{job name: {'directory': its default working-directory or None, 'text', 'steps': [{'directory', 'text'}]}} of
    a workflow file, read by indentation (the house workflows: jobs at 2 spaces, `steps:` at 4, each step's `- ` at 6
    and its keys at 8; a job's `defaults: run: working-directory:` comes before its steps)."""
    found, job, step, in_jobs = {}, None, None, False
    for line in path.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        if not line.startswith(' '):
            in_jobs = line == 'jobs:'
            continue
        if not in_jobs:
            continue
        if re.fullmatch(r'  [A-Za-z0-9_-]+:', line):
            job, step = found.setdefault(line.strip()[:-1], {'directory': None, 'text': '', 'steps': []}), None
            continue
        if job is None:
            continue
        job['text'] += line + '\n'
        if re.match(r'    \S', line):                      # a key of the job itself (steps:, env:, defaults:, ...)
            step = None
        elif line.startswith('      - ') and re.search(r'^    steps:$', job['text'], re.M):
            step = {'directory': None, 'text': ''}
            job['steps'].append(step)
        directory = re.match(r'\s*(?:- )?working-directory:\s*(\S+)', line)
        if step is not None:
            step['text'] += line + '\n'
            if directory:
                step['directory'] = directory.group(1)
        elif directory:
            job['directory'] = directory.group(1)
    return found


def every_step():
    for path in WORKFLOWS:
        for name, job in jobs(path).items():
            for step in job['steps']:
                yield path.name, name, step['directory'] or job['directory'], step['text']


def tracked(pattern):
    out = subprocess.run(['git', 'ls-files', pattern], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [ROOT / line for line in out.splitlines() if line and 'node_modules' not in line]


def test_ci_runs_the_terminal_vitest_suite_that_holds_the_session_module_tests():
    # apps/edge-bff/terminal/tests/data/edge_session*.test.ts, c1_security_findings, c3_phase1_switch_off,
    # c4_seed_phase0_mark, fixture_bundle (M468, M469, M471, M473, M478): shared/edge-session.ts is tested only there
    assert runs('vitest', 'apps/edge-bff/terminal'), (
        'no workflow runs `npx vitest run` in apps/edge-bff/terminal: the session module (sign-out clearing, change of '
        'user, access.seed, the 403 contract) is tested by no CI job; add the step to a workflow in edge-bff\'s checks')


def test_every_package_with_a_test_script_is_run_by_a_workflow():
    """The general class of R1-39: suites that exist but are wired into no workflow (found from the package files)."""
    packages = []
    for manifest in tracked('apps/*package.json'):
        if 'test' in (json.loads(manifest.read_text()).get('scripts') or {}):
            packages.append(manifest.parent.relative_to(ROOT).as_posix())
    assert 'apps/edge-bff/terminal' in packages and len(packages) >= 8, packages
    steps = list(every_step())
    unrun = [p for p in packages if not any(d == p and TEST_COMMAND.search(text) for _, _, d, text in steps)]
    assert unrun == [], (f'no workflow step runs the tests of {unrun}: add a step with working-directory set to the '
                         'folder and `npm test` (or `npx vitest run`) to a workflow of edge-bff\'s checks '
                         '(backend-tests.yml edge-bff-pages)')


def test_ci_compares_the_shell_copy_with_its_build():
    by_step = runs('build-shell.mjs --check')
    marked = [p for p in tracked('apps/edge-bff/tests/test_*.py')
              if 'generated_file' in (text := p.read_text()) and 'build-shell.mjs' in text and '--check' in text]
    generated = jobs(ROOT / '.github/workflows/generated-files.yml')
    by_marked_test = bool(marked) and any(
        job['directory'] == 'apps/edge-bff' and '-m generated_file' in job['text']
        and any(s['directory'] == 'apps/edge-bff/terminal' and 'npm ci' in s['text'] for s in job['steps'])
        and 'EDGE_TEST_REQUIRE_NODE: "1"' in job['text']
        for job in generated.values())
    assert by_step or by_marked_test, (
        'no workflow runs `node shared/build-shell.mjs --check`: tests/test_storage_registry.py compares only the '
        'source sha256 in the first line of static/edge-session.js, so an edited body ships unseen (AGENTS.md: a '
        'generated file has a generated_file test that compares it with what the script writes now, run by '
        'generated-files.yml with the Terminal page\'s `npm ci` first)')


def test_the_edge_bff_job_runs_its_browser_tests():
    """CONTRACT 13.8 (B on A's browser) and the account-page tests are Playwright tests: without Playwright and
    Chromium in the job they skip (pytest.importorskip), as every one of them did in CI before the fix round."""
    job = jobs(ROOT / '.github/workflows/backend-tests.yml')['edge-bff']
    text = job['text']
    assert 'requirements-dev.txt' in text, 'the edge-bff job installs requirements.txt only: Playwright is in -dev'
    assert 'playwright install' in text and 'chromium' in text, 'the edge-bff job installs no Chromium'
    assert 'EDGE_TEST_CHROMIUM' in text, 'the browser tests read the browser from EDGE_TEST_CHROMIUM'
    assert 'playwright' in (ROOT / 'apps/edge-bff/requirements-dev.txt').read_text()
    # the browser tests that open a built page skip without it (test_c2_e2e_people: the Terminal; the Watchlist page)
    for page in ('terminal', 'watchlist'):
        assert re.search(rf'cd {page} && npm ci && npm run build', text), f'the edge-bff job does not build {page}'


def test_ci_runs_orc_conversation_ownership_against_postgres():
    # apps/market-ai-orc/tests/test_conversations.py (pytestmark skipif without ORC_TEST_POSTGRES_URL) holds the
    # Phase 0 C2 fix test test_c2_a_client_run_may_name_only_a_conversation_its_owner_holds and the owner isolation
    # test test_another_owner_cannot_continue_or_read_a_conversation (CONTRACT section 13.3)
    text = (ROOT / '.github/workflows/backend-tests.yml').read_text()
    orc = text[text.index('  market-ai-orc:'):text.index('  terminal-api:')]
    assert 'ORC_TEST_POSTGRES_URL' in orc, (
        'backend-tests.yml runs market-ai-orc without ORC_TEST_POSTGRES_URL, so test_conversations.py (the owner '
        'isolation of conversations and the C2 CLIENT-history fix) is skipped in CI')
    assert 'image: postgres:16' in orc, 'ORC_TEST_POSTGRES_URL needs a Postgres service in the job'
    # the three test_request_data tests run the SQL Governor's package end to end: its requirements are theirs
    assert '../market-sql-governor/requirements.txt' in (ROOT / 'apps/market-ai-orc/requirements-dev.txt').read_text()
