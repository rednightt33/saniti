"""DRYRUN and APPLY job logs of the dev migrations prepared under verification/screener/jobs/: check a log against what
its migration must leave, so the go/no-go after each job is a script's answer, not a reading.

    python3 -I verification/screener/jobs/check_migration_log.py <log> <params.json> <expected sha256 of the file>
    python3 -I verification/screener/jobs/check_migration_log.py --covers <migration file name>
    python3 -I verification/screener/jobs/check_migration_log.py --params-ok <params.json>

Migrations with checks (MIGRATIONS below): 20261028_001_edge_bff_screener.sql (EXEC-SCREENER migration 1) and
20261028_100_terminal_service_accounts.sql (EXEC-MU-RUNTIME step 1). A log of any other file FAILs; --covers exits 0
only for a file with checks (run_migration.sh asks before it starts a job).
The log is the one scripts/onboarding/run_job.sh writes (lines `MIG ...`, `OUT {json}`, `ERR {json}`, `JOB_DONE ...`).
Checks: the job ran the named file with the expected sha256 (DRYRUN: its body ran and was rolled back); every probe
printed once; probes named expect_err_* printed ERR with the text the migration's checks name (a refusal for another
reason, e.g. a missing table, is not the check) and every other probe OUT; the read-back equals the expected state of
that migration. Prints PASS or FAIL lines and `VERDICT PASS n/n` or `VERDICT FAIL n/m`, exits 0 only when every check
passes. No secret is read or printed.

The probes are the reviewed ones (each migration's `probes` and `roles` below), not whatever a params file holds:
- the params name exactly the reviewed probes of the mode, in their order; a probe missing, added or renamed FAILs;
- each probe runs as the role its name gives (`roles`: the first matching prefix; no prefix: the admin connection).
  Right: ["as_api_ready", "terminal_api_login", ...]. Wrong: ["as_api_ready", null, ...] (the admin passes every read);
- each statement is data statements only (SELECT, WITH, INSERT, UPDATE, DELETE, TRUNCATE, VALUES, TABLE; DO only as the
  admin), outside comments, quoted text and $$ bodies, and never set_config: a probe can neither end the DRYRUN's
  transaction nor leave its role. Right: "SELECT count(*) FROM terminal.usage_hour". Wrong: "COMMIT" or
  "SELECT set_config('role', 'postgres', true)" (the first keeps the DRYRUN's writes, ERRORS M230's class).
--params-ok prints `PARAMS_NOT_AS_REVIEWED <probe>: <reason>` per problem and exits 1 (run_migration.sh asks before any
Railway call); after a job, the same reasons FAIL that probe's check. To add or change a probe, change the params and
the migration's `probes` here in one commit."""
import ast
import hashlib
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]

# ---- 20261028_001_edge_bff_screener.sql (EXEC-SCREENER migration 1) ------------------------------------------------
SCREENER = '20261028_001_edge_bff_screener.sql'
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
# the reviewed probes in their order (migration20261028_001_dryrun.params.json); the APPLY runs the first 10 (read-only)
SCREENER_PROBES = ['edge_bff_tables', 'runtime_grants', 'other_grantees_on_new_tables', 'runtime_members',
                   'screener_indexes', 'screener_constraints', 'screener_comments', 'runtime_public_reach',
                   'as_runtime_reads', 'as_runtime_reads_existing', 'as_runtime_insert_screen', 'as_runtime_insert_metric',
                   'as_runtime_replace_revision', 'as_runtime_watch_add', 'as_runtime_watch_add_again',
                   'as_runtime_counts_after_writes', 'as_runtime_delete', 'expect_err_item_id_format', 'expect_err_kind',
                   'expect_err_name_untrimmed', 'expect_err_definition_not_object', 'expect_err_definition_too_large',
                   'expect_err_definition_hash', 'expect_err_duplicate_name', 'expect_err_ticker_format',
                   'expect_err_watchlist_update', 'expect_err_truncate', 'expect_err_public_market_read']
SCREENER_ROLES = (('as_runtime_', 'edge_bff_runtime'), ('expect_err_', 'edge_bff_runtime'))


def check_screener(check, mode, outs, sha):
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


# ---- 20261028_100_terminal_service_accounts.sql (EXEC-MU-RUNTIME step 1, T1) ----------------------------------------
SERVICE_ACCOUNTS = '20261028_100_terminal_service_accounts.sql'
TERMINAL_TABLES = ['access_log', 'admin_log', 'quota', 'quota_override', 'session', 'sign_in_attempt', 'subscriber',
                   'usage_hour']
# terminal_runtime's privileges on every terminal table: arwd on the seven existing ones (read live through pgweb on
# 2026-10-29 before the migration: {postgres=arwdDxtm/postgres,terminal_runtime=arwd/postgres} each), and the same on
# usage_hour as the migration grants it (no TRUNCATE, REFERENCES or TRIGGER)
RUNTIME = 'DELETE,INSERT,SELECT,UPDATE'
MEMBERS = [['terminal_market_reader', 'terminal_api_login'], ['terminal_market_reader', 'terminal_publisher_login'],
           ['terminal_runtime', 'terminal_api_login']]
# rolname, can log in, any of superuser/createrole/createdb/replication/bypassrls, connection limit (live 2026-10-29)
ROLES = [['terminal_api_login', True, False, 20], ['terminal_market_reader', False, False, -1],
         ['terminal_publisher_login', True, False, 4], ['terminal_runtime', False, False, -1]]
KIND_CHECK = "CHECK ((kind = ANY (ARRAY['person'::text, 'service'::text])))"
# the constraints of terminal.subscriber (NOT NULL left out: PostgreSQL 18 lists them, 16 does not), read live
# 2026-10-29, plus the migration's kind check
SUBSCRIBER_CONSTRAINTS = ['subscriber_disabled_reason_check', 'subscriber_display_name_check', 'subscriber_email_check',
                          'subscriber_email_key', 'subscriber_kind_check', 'subscriber_password_hash_check',
                          'subscriber_pkey']
USAGE_COLUMNS = [['subscriber_id', 'bigint', True, None], ['hour_start', 'timestamp with time zone', True, None],
                 ['grants', 'integer', True, '0'], ['files', 'bigint', True, '0'], ['bytes', 'bigint', True, '0']]
USAGE_CONSTRAINTS = [
    ['usage_hour_bytes_check', 'c', 'CHECK ((bytes >= 0))'], ['usage_hour_files_check', 'c', 'CHECK ((files >= 0))'],
    ['usage_hour_grants_check', 'c', 'CHECK ((grants >= 0))'],
    ['usage_hour_pkey', 'p', 'PRIMARY KEY (subscriber_id, hour_start)'],
    ['usage_hour_subscriber_id_fkey', 'f',
     'FOREIGN KEY (subscriber_id) REFERENCES terminal.subscriber(subscriber_id) ON DELETE CASCADE'],
    ['usage_hour_whole_hour', 'c', "CHECK ((hour_start = date_trunc('hour'::text, hour_start, 'UTC'::text)))"]]
USAGE_INDEXES = [['usage_hour_pkey',
                  'CREATE UNIQUE INDEX usage_hour_pkey ON terminal.usage_hour USING btree (subscriber_id, hour_start)']]
# email, display name, kind, active, expires 2100-01-01 UTC, the all-zero verifier (no password), no disabled reason
SERVICES = [['backtest-worker@terminal.local', 'Backtest worker (service account)', 'service', True, True, True, True],
            ['screener-worker@terminal.local', 'Screener worker (service account)', 'service', True, True, True, True]]
# TEMPORARY values (EXEC-MU-RUNTIME D-T6, until Phase 0 measures the services)
CEILINGS = [['service_files_per_hour', 100000, 'files'], ['service_grants_per_hour', 20000, 'grants'],
            ['service_megabytes_per_hour', 100000, 'MB']]
# the people's quotas of 20261025_100, kept
PERSON_QUOTAS = ['failed_sign_ins_per_email', 'failed_sign_ins_per_ip', 'files_per_hour', 'history_per_hour',
                 'megabytes_per_day', 'session_hours', 'sessions_per_subscriber', 'tickers_per_day', 'tickers_per_hour',
                 'url_ttl_seconds']
# role, USAGE on schema terminal, usage_hour SELECT INSERT UPDATE DELETE TRUNCATE REFERENCES TRIGGER, subscriber.kind
PRIVILEGES = [['public'] + [False] * 9,
              ['terminal_api_login', True, True, True, True, True, False, False, False, True],
              ['terminal_market_reader'] + [False] * 9,
              ['terminal_publisher_login'] + [False] * 9,
              ['terminal_runtime', True, True, True, True, True, False, False, False, True]]
SCHEMA_DENIED = 'InsufficientPrivilege: permission denied for schema terminal'
ERR_TEXT_SERVICE_ACCOUNTS = {
    'expect_err_publisher_reads_usage': SCHEMA_DENIED, 'expect_err_publisher_reads_kind': SCHEMA_DENIED,
    'expect_err_market_reader_reads_usage': SCHEMA_DENIED,
    'expect_err_person_on_service_address':
        'UniqueViolation: duplicate key value violates unique constraint "subscriber_email_key"',
    'expect_err_kind_value': '"subscriber_kind_check"',
    'expect_err_kind_null': 'NotNullViolation: null value in column "kind" of relation "subscriber"',
    'expect_err_usage_part_hour': '"usage_hour_whole_hour"',
    'expect_err_usage_negative_grants': '"usage_hour_grants_check"',
    'expect_err_usage_negative_files': '"usage_hour_files_check"',
    'expect_err_usage_negative_bytes': '"usage_hour_bytes_check"',
    'expect_err_usage_duplicate_hour': 'UniqueViolation: duplicate key value violates unique constraint "usage_hour_pkey"',
    'expect_err_usage_unknown_subscriber': '"usage_hour_subscriber_id_fkey"',
    'expect_err_ceiling_zero': '"quota_value_check"',
    'expect_err_ceiling_override_zero': '"quota_override_value_check"',
    'expect_err_usage_truncate': 'InsufficientPrivilege: permission denied for table usage_hour'}
# the reviewed probes in their order (migration20261028_100_dryrun.params.json); the APPLY runs the first 27 (read-only)
SERVICE_PROBES = ['terminal_tables', 'runtime_grants', 'other_grantees', 'schema_acl', 'role_members', 'terminal_roles',
                  'kind_column', 'subscriber_constraints', 'usage_hour_columns', 'usage_hour_constraints',
                  'usage_hour_indexes', 'comments', 'service_rows', 'people_rows', 'ceilings', 'person_quotas',
                  'service_side_rows', 'privileges', 'verify_again', 'as_api_ready', 'as_api_service_accounts',
                  'as_api_people', 'as_api_service_limits', 'as_api_sign_in_lookup', 'expect_err_publisher_reads_usage',
                  'expect_err_publisher_reads_kind', 'expect_err_market_reader_reads_usage', 'as_api_meter_first',
                  'as_api_meter_again', 'as_api_meter_other_service', 'as_api_audit_service', 'as_api_usage_rows',
                  'as_api_prune', 'as_api_session_for_service', 'as_api_session_lookup',
                  'as_api_session_lookup_without_kind', 'as_api_add_person', 'expect_err_person_on_service_address',
                  'expect_err_kind_value', 'expect_err_kind_null', 'expect_err_usage_part_hour',
                  'expect_err_usage_negative_grants', 'expect_err_usage_negative_files', 'expect_err_usage_negative_bytes',
                  'expect_err_usage_duplicate_hour', 'expect_err_usage_unknown_subscriber', 'expect_err_ceiling_zero',
                  'expect_err_ceiling_override_zero', 'expect_err_usage_truncate']
SERVICE_ROLES = (('as_api_', 'terminal_api_login'), ('expect_err_publisher_', 'terminal_publisher_login'),
                 ('expect_err_market_reader_', 'terminal_market_reader'), ('expect_err_', 'terminal_api_login'))


def file_text(name, sha):
    """The migration as committed, only when it is the file the job ran (its sha256): what the probes are compared with."""
    path = ROOT / 'database/migrations' / name
    raw = path.read_bytes() if path.is_file() else b''
    return raw.decode() if raw and hashlib.sha256(raw).hexdigest() == sha else None


def ready_statements():
    """terminal-api's /ready statements (apps/terminal-api/app/store.py READY), read from the code, not copied."""
    path = ROOT / 'apps/terminal-api/app/store.py'
    if not path.is_file():
        return []
    tree = ast.parse(path.read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, 'id', None) == 'READY' for t in node.targets):
            return [ast.literal_eval(e) for e in node.value.elts]
    return []


def check_service_accounts(check, mode, outs, sha, probes):
    check('terminal tables', [r[0] for r in outs.get('terminal_tables', [])] == TERMINAL_TABLES,
          outs.get('terminal_tables'))
    check('terminal_runtime grants exact on every terminal table',
          {r[0]: r[1] for r in outs.get('runtime_grants', [])} == {t: RUNTIME for t in TERMINAL_TABLES},
          outs.get('runtime_grants'))
    check('no PUBLIC or other grantee on any terminal relation', outs.get('other_grantees') == [],
          outs.get('other_grantees'))
    check('schema terminal: USAGE for terminal_runtime only', outs.get('schema_acl') == [['terminal_runtime', 'USAGE']],
          outs.get('schema_acl'))
    check('role memberships unchanged', outs.get('role_members') == MEMBERS, outs.get('role_members'))
    check('terminal roles unchanged (no elevated attribute, connection limits)', outs.get('terminal_roles') == ROLES,
          outs.get('terminal_roles'))
    check('kind: text NOT NULL DEFAULT person', outs.get('kind_column') == [['text', 'NO', "'person'::text"]],
          outs.get('kind_column'))
    cons = outs.get('subscriber_constraints') or []
    check('subscriber constraints: the existing ones and subscriber_kind_check',
          [r[0] for r in cons] == SUBSCRIBER_CONSTRAINTS and ['subscriber_kind_check', 'c', KIND_CHECK] in cons, cons)
    check('usage_hour columns', outs.get('usage_hour_columns') == USAGE_COLUMNS, outs.get('usage_hour_columns'))
    check('usage_hour constraints', outs.get('usage_hour_constraints') == USAGE_CONSTRAINTS,
          outs.get('usage_hour_constraints'))
    check('usage_hour index: its primary key only', outs.get('usage_hour_indexes') == USAGE_INDEXES,
          outs.get('usage_hour_indexes'))
    check('comments on subscriber.kind and usage_hour', outs.get('comments') == [[True, True]], outs.get('comments'))
    check('two service rows: kind service, active, until 2100-01-01, no password, not disabled',
          outs.get('service_rows') == SERVICES, outs.get('service_rows'))
    people = (outs.get('people_rows') or [[None, None, None]])[0]
    check('every other subscriber is a person', people[0] is not None and people[0] == people[1] and people[2] == 0,
          people)
    check('three service ceilings', outs.get('ceilings') == CEILINGS, outs.get('ceilings'))
    check("people's quotas kept", [r[0] for r in outs.get('person_quotas', [])] == PERSON_QUOTAS, outs.get('person_quotas'))
    check('service accounts start without overrides, sessions, audit or usage rows',
          outs.get('service_side_rows') == [[0, 0, 0, 0]], outs.get('service_side_rows'))
    check('privileges per role (schema, usage_hour, subscriber.kind)', outs.get('privileges') == PRIVILEGES,
          outs.get('privileges'))
    text = file_text(SERVICE_ACCOUNTS, sha)
    stated = {p[0]: p[2] for p in probes}
    block = text[text.index('DO $verify$'):text.index('END $verify$;') + len('END $verify$;')] if text else None
    check("the file's own $verify$ block passes again", block is not None and block in stated.get('verify_again', '')
          and outs.get('verify_again') == [['verify passed']],
          'repository file is not the one run' if block is None else outs.get('verify_again'))
    ready = ready_statements()
    check("this build's /ready statements succeed as terminal_api_login (store.py READY)",
          bool(ready) and all(s in stated.get('as_api_ready', '') for s in ready)
          and outs.get('as_api_ready') == [[1] + [0] * (len(ready) - 1)], {'ready': ready, 'out': outs.get('as_api_ready')})
    check('account lookup finds both service accounts', outs.get('as_api_service_accounts') == [
        [r[0], 'service'] for r in SERVICES], outs.get('as_api_service_accounts'))
    found = outs.get('as_api_people') or [[0]]
    check('account lookup still finds the people (kind person)', found[0][0] >= 1 and found[0][0] <= (people[1] or 0),
          {'people': people, 'found': found})
    check('ceilings as terminal-api reads them for a service', outs.get('as_api_service_limits') == [
        r[:2] for r in CEILINGS], outs.get('as_api_service_limits'))
    check('sign-in lookup sees kind service on both (main.py sign_in refuses it)',
          outs.get('as_api_sign_in_lookup') == [[r[0], 'service', True, True] for r in SERVICES],
          outs.get('as_api_sign_in_lookup'))
    if mode == 'DRYRUN':
        check('meter: a first grant, the ON CONFLICT addition, one row per service',
              outs.get('as_api_meter_first') == [[1, 5, 1000000, True]]
              and outs.get('as_api_meter_again') == [[2, 8, 1500000, True]]
              and outs.get('as_api_meter_other_service') == [[1, 1, 100, True]]
              and outs.get('as_api_usage_rows') == [[SERVICES[0][0], 2, 8, 1500000], [SERVICES[1][0], 1, 1, 100]],
              {k: outs.get(k) for k in ('as_api_meter_first', 'as_api_meter_again', 'as_api_meter_other_service',
                                         'as_api_usage_rows')})
        check("a service's audit row and the retention DELETE",
              outs.get('as_api_audit_service') == [['file', 5]] and outs.get('as_api_prune') == [[0]],
              {k: outs.get(k) for k in ('as_api_audit_service', 'as_api_prune')})
        check('a session on a service account is refused by the session lookup, through kind alone',
              outs.get('as_api_session_for_service') == [[1]] and outs.get('as_api_session_lookup') == []
              and outs.get('as_api_session_lookup_without_kind') == [[SERVICES[0][0]]],
              {k: outs.get(k) for k in ('as_api_session_for_service', 'as_api_session_lookup',
                                         'as_api_session_lookup_without_kind')})
        check('the admin route adds a person by default', outs.get('as_api_add_person') == [['person']],
              outs.get('as_api_add_person'))


# file name -> the expected ERR text per expect_err_* probe, the migration's own checks, the reviewed probes per mode
# and the role each probe's name gives (first matching prefix; none: the admin connection)
MIGRATIONS = {
    SCREENER: {'err_text': ERR_TEXT,
               'checks': lambda check, mode, outs, sha, probes: check_screener(check, mode, outs, sha),
               'probes': {'DRYRUN': SCREENER_PROBES, 'APPLY': SCREENER_PROBES[:10]}, 'roles': SCREENER_ROLES},
    SERVICE_ACCOUNTS: {'err_text': ERR_TEXT_SERVICE_ACCOUNTS, 'checks': check_service_accounts,
                       'probes': {'DRYRUN': SERVICE_PROBES, 'APPLY': SERVICE_PROBES[:27]}, 'roles': SERVICE_ROLES},
}
# what a probe statement may be (outside comments, quoted text and $$ bodies): data statements only, so no probe can end
# the DRYRUN's one transaction (a COMMIT there keeps the migration, ERRORS M230's class) or leave its role (SET ROLE,
# RESET, SET SESSION AUTHORIZATION; set_config('role', ...) is refused by name); DO only on the admin connection
PROBE_STATEMENTS = {'SELECT', 'WITH', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'VALUES', 'TABLE'}
SQL_TEXT = re.compile(r"--[^\n]*|/\*.*?\*/|\$((?:[A-Za-z_]\w*)?)\$.*?\$\1\$|'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"", re.S)


def probe_role(spec, name):
    return next((role for prefix, role in spec['roles'] if name.startswith(prefix)), None)


def probe_problem(spec, mode, probe):
    """Why a params probe is not the reviewed one ('' when it is): its name, its role, its statement."""
    if not (isinstance(probe, list) and len(probe) == 3 and all(isinstance(x, str) for x in (probe[0], probe[2]))
            and (probe[1] is None or isinstance(probe[1], str))):
        return 'not a [name, role or null, statement] probe'
    name, role, statement = probe
    if name not in spec['probes'].get(mode, []):
        return f'not a reviewed {mode} probe of this migration'
    want = probe_role(spec, name)
    if role != want:
        return f'runs as {role or "the admin connection"}; its name gives {want or "the admin connection"}'
    if 'set_config' in statement.lower():
        return 'set_config can change the role or the transaction'
    for part in SQL_TEXT.sub(' ', statement).split(';'):
        word = (part.split() or [''])[0].upper()
        if word and word not in PROBE_STATEMENTS and not (word == 'DO' and role is None):
            return f'{word} is not a data statement' + (' (DO only as the admin)' if word == 'DO' else '')
    return ''


def params_problems(params):
    """run_migration.sh's question before any Railway call: are these the reviewed probes of one migration and mode?"""
    named = params.get('migrations')
    spec = MIGRATIONS.get(named[0]) if isinstance(named, list) and len(named) == 1 else None
    mode = params.get('mode')
    if spec is None or mode not in spec['probes']:
        return [f'migrations {named} mode {mode}: one file with checks here ({", ".join(MIGRATIONS)}), DRYRUN or APPLY']
    probes = params.get('probes') if isinstance(params.get('probes'), list) else []
    names = [p[0] if isinstance(p, list) and p else None for p in probes]
    problems = [f'{p[0] if isinstance(p, list) and p else p}: {why}' for p in probes
                if (why := probe_problem(spec, mode, p))]
    want = spec['probes'][mode]
    missing, extra = [n for n in want if n not in names], [n for n in names if n not in want]
    if missing or extra:
        problems.append(f'not the reviewed {mode} probes: missing {missing}, not reviewed {extra}')
    elif names != want:
        problems.append(f'the reviewed {mode} probes in another order or twice (reads first, then writes): {names}')
    return problems


def parse(path):
    mig, parts, errs, done, unreadable, repeated = [], {}, {}, [], [], []
    for raw in open(path, encoding='utf-8', errors='replace'):
        line = raw.strip()
        if line.startswith('MIG '):
            mig.append(line)
        elif line.startswith(('OUT ', 'ERR ')):
            try:
                o = json.loads(line[4:])
                if line.startswith('OUT '):
                    key, rows = (o['q'], int(o['part'])), o['rows']
                    if not isinstance(rows, list):
                        raise TypeError(rows)
                    repeated += [f'{key[0]} part {key[1]}'] if key in parts else []
                    parts[key] = rows
                else:
                    repeated += [f'{o["q"]} ERR'] if o['q'] in errs else []
                    errs[o['q']] = o['error']
            except (ValueError, KeyError, TypeError):
                unreadable.append(line[:120])   # e.g. a line the log service cut; judged below, never skipped
        elif line.startswith('JOB_DONE'):
            done.append(line)
    # a probe's rows in the order of its parts (the job prints them in order; a log service may not keep the order of
    # lines it stamped alike), its parts 0..n-1; a part or an ERR printed twice means two runs or a repeated line
    outs = {}
    for q, part in sorted(parts):
        repeated += [f'{q} part {part} without part {part - 1}'] if part and (q, part - 1) not in parts else []
        outs.setdefault(q, []).extend(parts[(q, part)])
    return mig, outs, errs, done, unreadable, repeated


def main(log, params_path, sha):
    params = json.load(open(params_path))
    mode = params['mode']
    try:
        mig, outs, errs, done, unreadable, repeated = parse(log)
    except FileNotFoundError:
        print(f'FAIL no log at {log}')
        print('VERDICT FAIL')
        return 1
    results = []

    def check(name, ok, detail=''):
        results.append(ok)
        print(('PASS ' if ok else 'FAIL ') + name + (f': {detail}' if detail and not ok else ''))

    named = params['migrations']
    migration = named[0] if len(named) == 1 and named[0] in MIGRATIONS else None
    check('migration list', migration is not None, f'{named}: one file with checks here ({", ".join(MIGRATIONS)})')
    if migration is None:
        print('VERDICT FAIL', f'{sum(results)}/{len(results)}')
        return 1
    spec = MIGRATIONS[migration]
    err_text = spec['err_text']
    check('file and sha256', f'MIG {mode} {migration} sha256={sha}' in mig, mig)
    if mode == 'DRYRUN':
        check('dry-run body ran (then rolled back)', f'MIG DRYRUN_BODY_OK {migration}' in mig, mig)
    check('job finished', done == [f'JOB_DONE MIGRATION {mode}'], done)
    if unreadable:
        check('every OUT and ERR line readable', False, unreadable[:3])
    if repeated:
        check('every probe printed once, its parts in sequence', False, repeated[:3])
    probes = params.get('probes') if isinstance(params.get('probes'), list) else []
    # each probe as reviewed (its name, the role its name gives, data statements only), then its answer; a reviewed
    # probe the params leave out FAILs below, so a shorter params file never gives a shorter PASS
    for probe in probes:
        name = probe[0] if isinstance(probe, list) and probe else str(probe)
        problem = probe_problem(spec, mode, probe)
        if name.startswith('expect_err_'):
            # a refusal without its expected text here is a FAIL, never "any error"
            want = err_text.get(name)
            check(f'{name} refused',
                  not problem and want is not None and name in errs and want in errs[name] and name not in outs,
                  problem or (errs.get(name) or 'printed OUT or nothing' if want
                              else 'no expected error text in this checker'))
        else:
            check(f'{name} answered', not problem and name in outs and name not in errs,
                  problem or errs.get(name) or 'not printed')
    stated = [p[0] for p in probes if isinstance(p, list) and p]
    for name in spec['probes'][mode]:
        if name not in stated:
            check(f'{name} {"refused" if name.startswith("expect_err_") else "answered"}', False,
                  f'a reviewed {mode} probe the params leave out')
    spec['checks'](check, mode, outs, sha, [p for p in probes if isinstance(p, list) and len(p) == 3])
    print('VERDICT', 'PASS' if all(results) else 'FAIL', f'{sum(results)}/{len(results)}')
    return 0 if all(results) else 1


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--covers':
        sys.exit(0 if sys.argv[2] in MIGRATIONS else 1)
    if len(sys.argv) == 3 and sys.argv[1] == '--params-ok':
        try:
            found = params_problems(json.load(open(sys.argv[2])))
        except (OSError, ValueError, AttributeError) as e:
            found = [f'{sys.argv[2]} is not a readable params file ({type(e).__name__})']
        for problem in found:
            print(f'PARAMS_NOT_AS_REVIEWED {problem}'[:600])
        sys.exit(1 if found else 0)
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    sys.exit(main(*sys.argv[1:]))
