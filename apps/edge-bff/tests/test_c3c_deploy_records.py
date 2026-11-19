"""C3C-DEPLOY check of EXEC-MU-ACCOUNTS Phase 3c with the re-check's fix round (2026-11-19, `git diff bf273f52
dec1cfef`): failing tests of verified findings of the lens "migrations, deploy order and records".

1. A test the records cite as the lock of a fix runs in no workflow. ERRORS M490 (re-check R1-17, blocks-switch-on: the
   Screener's cached paint showed the last result after the plan lost the Screener) names
   `screener/tests/smoke/c_p1s_plan_refused_cache.mjs` as its test, and it is the only test of the "a refused catalog
   drops the pointer and the rows" half of the fix (`screener/tests/page/page.test.ts` holds the `cacheId` half). No
   workflow step runs it: the Screener page has no smoke script in its package.json, backtest-page-smoke.yml runs only
   the Backtest page's `npm run smoke`, and tests/test_cdb_ci_coverage.py (R1-39's property test) looks only at
   packages' `test` scripts. M502's own lesson: "a suite wired into no workflow is not a test".
2. ERRORS M503 says CONTRACT section 17 "holds the rollback floors (..., 3d, the guest build)", but the table has no
   row for the guest build (the floor is written only in verification/edge_multiuser/fix_round/guest.md "Deploy order
   and rollback floors": while guests are on anywhere, terminal-api is never rolled back below the guest build).
3. Each unapplied migration ends with "Rollback (a new forward migration with this body ...)". The block of
   20261119_050 holds a sentence in place of SQL ("(CREATE OR REPLACE edge_bff.capability_value_check with the body of
   20261117_003)"), so the block cannot be run as written, and its SQL lines alone leave the replaced
   capability_value_check reading the dropped columns: probe on a database with every migration applied, then the
   block's statements, then `INSERT INTO edge_bff.plan_capabilities ... ('free', 'terminal.layouts_max', '3')` ->
   ERROR column "value_min" does not exist (PL/pgSQL function edge_bff.capability_value_check() line 10): after such
   a rollback no plan value or override can be written.
4. The 3b follow-up gates the legacy `broker` and `top5` cards and `rank_by` 'fnet' in the backtest-worker only; the
   deployed worker gates none of them (probe on bf273f52's src: legacyItemKind('broker') and ('top5') are null, no
   RANK_ITEM; on dec1cfef both 'flow_indicator' and RANK_ITEM.fnet the item fnet). Section 17 sets no floor for it, so a
   backtest-worker rollback while the switch is on anywhere fails open.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ERRORS = (ROOT / 'ERRORS_AND_SOLUTIONS.md').read_text()
CONTRACT = (ROOT / 'verification/edge_multiuser/access_tiers/CONTRACT.md').read_text()
WORKFLOWS = sorted((ROOT / '.github/workflows').glob('*.yml'))


def recheck_entries():
    """The ERRORS entries of the re-check and its fix round (M483 to M503)."""
    start, end = ERRORS.index('\n### M503 '), ERRORS.index('\n### M482 ')
    return ERRORS[start:end]


def node_tests_cited():
    """Every Node test script (.mjs under a tests/ folder) the re-check's entries name, resolved to its file."""
    found = set()
    for cited in re.findall(r'`([^` ]+/tests/[^` ]+\.mjs)`', recheck_entries()):
        hits = [p for p in (ROOT / 'apps').rglob(Path(cited).name)
                if 'node_modules' not in p.parts and p.as_posix().endswith(cited)]
        assert len(hits) == 1, f'{cited}: cited in ERRORS M483-M503 but found {len(hits)} times under apps/'
        found.add(hits[0])
    return found


def runs_in_a_workflow(path):
    """A workflow step names the script, or runs an npm script of its package whose command names it."""
    package = next(p for p in path.parents if (p / 'package.json').is_file())
    scripts = json.loads((package / 'package.json').read_text()).get('scripts') or {}
    relative = path.relative_to(package).as_posix()
    via = {name for name, command in scripts.items() if relative in command or path.name in command}
    folder = package.relative_to(ROOT).as_posix()
    for workflow in WORKFLOWS:
        text = workflow.read_text()
        if path.name in text:
            return True
        if folder in text and any(re.search(rf'npm run {re.escape(name)}\b', text) for name in via):
            return True
    return False


def test_every_node_test_the_recheck_records_cite_runs_in_a_workflow():
    cited = node_tests_cited()
    assert cited, 'the re-check entries cite no Node test script any more: update this check'
    unrun = sorted(p.relative_to(ROOT).as_posix() for p in cited if not runs_in_a_workflow(p))
    assert unrun == [], (
        f'ERRORS M483-M503 cite {unrun} as the test of a fix, but no workflow step runs it (no step names it, and no '
        'npm script of its package that names it is run by a workflow): the fix it locks can regress with every check '
        'green. Fix: add a workflow step (in a workflow of edge-bff\'s checks) that builds the page\'s smoke bundle and '
        'runs it, e.g. in apps/edge-bff/screener `npx vite build --mode smoke && node tests/smoke/'
        'c_p1s_plan_refused_cache.mjs`, or name a test that a workflow runs')


def test_the_rollback_floors_of_section_17_hold_the_guest_build_m503_says_they_hold():
    claim = re.search(r'section 17 holds the rollback\s+floors \(([^)]*)\)', recheck_entries())
    assert claim and 'the guest build' in claim.group(1), 'M503 no longer says section 17 holds the guest floor'
    start = CONTRACT.index('- **Rollback floors** (R2-6)')
    table = CONTRACT[start:CONTRACT.index('\n## 18.', start)]
    rows = [line for line in table.splitlines() if line.startswith('| ') and not line.startswith('| After this step')
            and not line.startswith('|---')]
    assert any(re.search(r'guest|x-terminal-client|20261119_170', row, re.I) for row in rows), (
        'ERRORS M503 says CONTRACT section 17 holds the rollback floor of the guest build, but its table has no such '
        'row: a terminal-api rolled back below the guest build while EDGE_GUESTS is on (verification/edge_multiuser/'
        'fix_round/guest.md "Deploy order and rollback floors") is not listed where a rollback is read from. Fix: add '
        'the row (after: terminal-api and edge-bff of the guest build with guests on; floor: terminal-api at or above '
        'that build; order: edge-bff-live guests off first), or correct M503')


def test_the_rollback_floors_hold_the_backtest_workers_floor_of_the_broker_data_gates():
    """The 3b follow-up gates the Backtest's broker-data built-ins in the worker only (apps/backtest-worker/src/
    validate.ts legacyItemKind: the legacy `broker` and `top5` cards by LEGACY group 'flow'; checkRequest:
    `portfolio.rank_by` 'fnet' by signals.ts RANK_ITEM). The deployed worker (3b, `3e27dd56`) gates none of them, so
    a switch-on site (edge-bff-live) paired with a backtest-worker rolled back below the follow-up runs them for a plan
    without the Flow items: it fails open. Section 17's floors name only the 3b builds for the workers (the floor that
    makes them read `allow`), not this one."""
    start = CONTRACT.index('- **Rollback floors** (R2-6)')
    table = CONTRACT[start:CONTRACT.index('\n## 18.', start)]
    assert re.search(r'broker|top5|rank_by|fnet', table), (
        'CONTRACT section 17 "Rollback floors" has no floor for the backtest-worker build of the 3b follow-up: while '
        'EDGE_MULTIUSER is on anywhere, a backtest-worker below it (the deployed 3e27dd56) runs the legacy broker and '
        'top5 cards and rank_by fnet for a plan that lacks the Flow items (fails open, validate.ts legacyItemKind and '
        'checkRequest RANK_ITEM are new in this build). Fix: add the row (after: the 3b follow-up workers; floor: '
        'backtest-worker at or above that build while the switch is on anywhere; order: edge-bff-live off, or its '
        'principals on plans holding the Flow items, before such a rollback)')


MIGRATIONS = ROOT / 'database/migrations'


def unapplied():
    """The migrations of EXEC-MU-ACCOUNTS Phase 3c and the fix round not yet in APPLIED.sha256 (20261118_*, 20261119_*)."""
    applied = {line.split()[1] for line in (MIGRATIONS / 'APPLIED.sha256').read_text().splitlines()
               if line.strip() and not line.startswith('#')}
    return [p for p in sorted(MIGRATIONS.glob('2026111[89]_*.sql')) if p.name not in applied]


def rollback_block(path):
    """The commented block after the file's COMMIT, from '-- BEGIN;' to '-- COMMIT;', as the SQL it holds."""
    lines = path.read_text().splitlines()
    tail = lines[max(i for i, line in enumerate(lines) if line.strip() == 'COMMIT;') + 1:]
    start = next(i for i, line in enumerate(tail) if line.strip() == '-- BEGIN;')
    end = next(i for i, line in enumerate(tail) if line.strip() == '-- COMMIT;')
    return [line[3:] if line.startswith('-- ') else line[2:] for line in tail[start:end + 1]]


def test_every_unapplied_edge_bff_migrations_rollback_block_runs_as_written(database):
    """On the suite's database (conftest: every edge_bff migration applied), each edge_bff block, newest first, in one
    transaction that is rolled back (DDL is transactional; nothing is kept). Then a plan value is written, as an
    operator or the Phase 4 admin would after the rollback. The terminal blocks (20261118_100, 20261119_170) need the
    terminal schema, which this database does not hold (they ran as written on the checker's cluster)."""
    import psycopg
    blocks = [p for p in reversed(unapplied()) if 'edge_bff' in p.name]
    assert len(blocks) >= 13, [p.name for p in blocks]
    failed = []
    with psycopg.connect(database) as c:
        for path in blocks:
            body = '\n'.join(line for line in rollback_block(path) if line.strip() not in ('BEGIN;', 'COMMIT;'))
            c.execute('SAVEPOINT block')
            try:
                c.execute(body)
                c.execute('RELEASE SAVEPOINT block')
            except psycopg.Error as e:
                c.execute('ROLLBACK TO SAVEPOINT block')
                failed.append(f'{path.name}: {type(e).__name__}: {str(e).splitlines()[0][:160]}')
        try:
            c.execute("INSERT INTO edge_bff.plan_capabilities(plan_key, capability_key, value) "
                      "VALUES ('free', 'terminal.layouts_max', '3')")
        except psycopg.Error as e:
            failed.append(f'a plan value written after the rollbacks: {type(e).__name__}: {str(e).splitlines()[0][:160]}')
        c.rollback()
    assert failed == [], (
        f'rollback blocks that do not run as written: {failed}. Each file says its rollback is "a new forward migration '
        'with this body". The block of 20261119_050 holds the sentence "(CREATE OR REPLACE edge_bff.capability_value_check '
        'with the body of 20261117_003)" where SQL belongs, and its statements alone leave capability_value_check '
        'reading the dropped value_min, value_max and item_pattern, so every plan or override write fails afterwards. '
        'Fix: write the CREATE OR REPLACE FUNCTION edge_bff.capability_value_check() body of 20261117_003 into the '
        'block, before the DROP FUNCTION and DROP COLUMN lines')
