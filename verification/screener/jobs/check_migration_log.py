"""EXEC-SCREENER migration 1 (20261028_001_edge_bff_screener.sql): check a DRYRUN or APPLY job log against what the
migration must leave, so the go/no-go after each job is a script's answer, not a reading.

    python3 -I verification/screener/jobs/check_migration_log.py <log> <params.json> <expected sha256 of the file>

The log is the one scripts/onboarding/run_job.sh writes (lines `MIG ...`, `OUT {json}`, `ERR {json}`, `JOB_DONE ...`).
Checks: the job ran the named file with the expected sha256 (DRYRUN: its body ran and was rolled back); every probe
printed; probes named expect_err_* printed ERR and every other probe OUT; the read-back equals the expected state
below (tables, exact grants, membership, no PUBLIC or other grantee, the runtime role still reads no public relation).
Prints PASS or FAIL lines and exits 0 only when every check passes. No secret is read or printed."""
import json
import sys

MIGRATION = '20261028_001_edge_bff_screener.sql'
TABLES = ['backtest_jobs', 'backtest_results', 'backtest_trials', 'conversation_ui', 'jobs', 'screener_items',
          'sessions', 'watchlist_items']
# edge_bff_runtime's privileges per table after the migration: the two new tables as the migration grants them, every
# existing table unchanged (read live through pgweb on 2026-10-28 before the migration)
GRANTS = {'backtest_jobs': 'INSERT,SELECT,UPDATE', 'backtest_results': 'DELETE,INSERT,SELECT',
          'backtest_trials': 'INSERT,SELECT,UPDATE', 'conversation_ui': 'DELETE,INSERT,SELECT,UPDATE',
          'jobs': 'DELETE,INSERT,SELECT,UPDATE', 'sessions': 'DELETE,INSERT,SELECT,UPDATE',
          'screener_items': 'DELETE,INSERT,SELECT,UPDATE', 'watchlist_items': 'DELETE,INSERT,SELECT'}
INDEXES = {('screener_items', 'screener_items_owner_kind_name'), ('screener_items', 'screener_items_owner_kind_updated'),
           ('screener_items', 'screener_items_pkey'), ('watchlist_items', 'watchlist_items_pkey')}
# the error a refusal must carry (a refusal for another reason, e.g. a missing table, is not the check)
# (constraint names as PostgreSQL derives them for the migration's unnamed CHECKs; seen in the local rehearsal)
ERR_TEXT = {'expect_err_item_id_format': '"screener_items_item_id_check"', 'expect_err_kind': '"screener_items_kind_check"',
            'expect_err_name_untrimmed': '"screener_items_name_check"',
            'expect_err_definition_not_object': '"screener_items_definition_check"',
            'expect_err_definition_too_large': '"screener_items_definition_size"',
            'expect_err_definition_hash': '"screener_items_definition_hash_check"',
            'expect_err_duplicate_name': '"screener_items_owner_kind_name"',
            'expect_err_ticker_format': '"watchlist_items_ticker_check"',
            'expect_err_watchlist_update': 'InsufficientPrivilege: permission denied for table watchlist_items',
            'expect_err_truncate': 'InsufficientPrivilege: permission denied for table screener_items',
            'expect_err_public_market_read': 'InsufficientPrivilege: permission denied for table Price_Stock_Indonesia_IDX'}


def parse(path):
    mig, outs, errs, done = [], {}, {}, []
    for raw in open(path, encoding='utf-8', errors='replace'):
        line = raw.strip()
        if line.startswith('MIG '):
            mig.append(line)
        elif line.startswith('OUT '):
            o = json.loads(line[4:])
            outs.setdefault(o['q'], []).extend(o['rows'])
        elif line.startswith('ERR '):
            o = json.loads(line[4:])
            errs[o['q']] = o['error']
        elif line.startswith('JOB_DONE'):
            done.append(line)
    return mig, outs, errs, done


def main(log, params_path, sha):
    params = json.load(open(params_path))
    mode = params['mode']
    try:
        mig, outs, errs, done = parse(log)
    except FileNotFoundError:
        print(f'FAIL no log at {log}')
        print('VERDICT FAIL')
        return 1
    results = []

    def check(name, ok, detail=''):
        results.append(ok)
        print(('PASS ' if ok else 'FAIL ') + name + (f': {detail}' if detail and not ok else ''))

    check('migration list', params['migrations'] == [MIGRATION], params['migrations'])
    check('file and sha256', f'MIG {mode} {MIGRATION} sha256={sha}' in mig, mig)
    if mode == 'DRYRUN':
        check('dry-run body ran (then rolled back)', f'MIG DRYRUN_BODY_OK {MIGRATION}' in mig, mig)
    check('job finished', done == [f'JOB_DONE MIGRATION {mode}'], done)
    names = [p[0] for p in params['probes']]
    for name in names:
        if name.startswith('expect_err_'):
            want = ERR_TEXT.get(name, '')
            check(f'{name} refused', name in errs and want in errs[name] and name not in outs,
                  errs.get(name) or 'printed OUT or nothing')
        else:
            check(f'{name} answered', name in outs and name not in errs, errs.get(name) or 'not printed')
    check('edge_bff tables', [r[0] for r in outs.get('edge_bff_tables', [])] == TABLES, outs.get('edge_bff_tables'))
    check('edge_bff_runtime grants exact', {r[0]: r[1] for r in outs.get('runtime_grants', [])} == GRANTS,
          outs.get('runtime_grants'))
    check('no PUBLIC or other grantee on the new tables', outs.get('other_grantees_on_new_tables') == [],
          outs.get('other_grantees_on_new_tables'))
    check('runtime members', outs.get('runtime_members') == [['edge_bff_login']], outs.get('runtime_members'))
    check('indexes', {(r[0], r[1]) for r in outs.get('screener_indexes', [])} == INDEXES, outs.get('screener_indexes'))
    check('comments present', bool(outs.get('screener_comments')) and all(r[2] is True for r in outs['screener_comments']),
          outs.get('screener_comments'))
    reach = outs.get('runtime_public_reach') or [[None, None]]
    check('runtime reads no public relation', reach[0][0] == 0 and (reach[0][1] or 0) > 0, reach)
    check('new tables empty, readable by the runtime role', outs.get('as_runtime_reads') == [[0, 0]],
          outs.get('as_runtime_reads'))
    if mode == 'DRYRUN':
        check('writes the app needs', outs.get('as_runtime_replace_revision') == [[2]]
              and outs.get('as_runtime_watch_add') == [['BBCA']] and outs.get('as_runtime_watch_add_again') == []
              and outs.get('as_runtime_counts_after_writes') == [[2, 1]] and outs.get('as_runtime_delete') == [[1, 1]],
              {k: outs.get(k) for k in ('as_runtime_replace_revision', 'as_runtime_watch_add', 'as_runtime_watch_add_again',
                                         'as_runtime_counts_after_writes', 'as_runtime_delete')})
    print('VERDICT', 'PASS' if all(results) else 'FAIL', f'{sum(results)}/{len(results)}')
    return 0 if all(results) else 1


if __name__ == '__main__':
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    sys.exit(main(*sys.argv[1:]))
