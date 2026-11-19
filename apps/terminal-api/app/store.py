"""PostgreSQL access through terminal_api_login: schema terminal (accounts, sessions, quotas, audit) and read-only
fallback queries on the market tables. Every market query is parameterized and bounded by the caller."""
import hashlib
import math
from contextlib import contextmanager

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .quota import REF, Usage

PRICE_HISTORY = ('SELECT date::text, open::float8, high::float8, low::float8, close::float8, volume::float8 '
                 'FROM public."Price_Stock_Indonesia_IDX" '
                 "WHERE ticker = %s AND timeframe = 'Daily' AND is_final AND date BETWEEN %s AND %s ORDER BY date")
BROKER_HISTORY = ('SELECT trade_date::text, broker, investor_type, market_board, buy_value::float8, '
                  'sell_value::float8, buy_lots::float8, sell_lots::float8, source_balance_gap '
                  'FROM public."Feature_05_Foreign_Domestic_Broker_Detail" '
                  'WHERE ticker = %s AND trade_date BETWEEN %s AND %s '
                  'AND (%s::text[] IS NULL OR broker = ANY(%s::text[])) '
                  'AND (%s::text IS NULL OR investor_type = %s) AND (%s::text IS NULL OR market_board = %s) '
                  'ORDER BY trade_date, broker, investor_type, market_board')


ACCOUNT = 'subscriber_id, email, display_name, expires_at, kind'
# Store.frees_in: when a refused quota's rolling window has let enough use go. The amount column and the rows each quota
# counts are the ones Store.usage sums (keep the two together); the oldest rows leave first, and the row whose leaving
# makes the cumulative amount reach the excess names the time. Tickers: a new ticker fits once one ticker's newest read
# has left the window.
# Track guest (main.py meter): a visitor of the guest plan is counted on its own rows of the guest owner,
# `client_key = %s` beside the subscriber (CLIENT, filled in only for such a call; the index access_log_client_at,
# migration 20261119_170)
CLIENT = ' AND client_key = %s'
_LEAVES = ('SELECT extract(epoch FROM at + interval {w} - now()) AS wait FROM (SELECT at, sum({amount}) OVER '
           '(ORDER BY at, access_id ROWS UNBOUNDED PRECEDING) AS gone FROM terminal.access_log WHERE subscriber_id = %s'
           '{client} AND at > now() - interval {w}{rows}) t WHERE gone >= %s ORDER BY at LIMIT 1')
_TICKER_LEAVES = ('SELECT extract(epoch FROM min(newest) + interval {w} - now()) AS wait FROM (SELECT max(at) AS newest '
                  'FROM terminal.access_log WHERE ticker <> %s AND subscriber_id = %s{client} '
                  'AND at > now() - interval {w} GROUP BY ticker) t')
FREES = {
    'files_per_hour': _LEAVES.format(w="'1 hour'", amount='file_count', rows=" AND kind = 'file'", client='{client}'),
    'history_per_hour': _LEAVES.format(w="'1 hour'", amount='1', rows=" AND kind LIKE 'history%%'", client='{client}'),
    'megabytes_per_day': _LEAVES.format(w="'1 day'", amount='bytes', rows='', client='{client}'),
    'tickers_per_hour': _TICKER_LEAVES.format(w="'1 hour'", client='{client}'),
    'tickers_per_day': _TICKER_LEAVES.format(w="'1 day'", client='{client}'),
}
# What the migrations after the terminal schema (20261025_100) added and this build reads, without reading a row: a
# missing column, table or privilege fails the statement. 20261026_100: access_log.file_count; 20261028_100
# (EXEC-MU-RUNTIME T1): subscriber.kind and usage_hour. 20261118_100 (EXEC-MU-ACCOUNTS Phase 3c):
# subscriber.edge_owner_key and access_log.version. 20261119_170 (track guest): access_log.client_key.
READY = ('SELECT 1 FROM terminal.quota LIMIT 1',
         'SELECT file_count FROM terminal.access_log LIMIT 0',
         'SELECT kind FROM terminal.subscriber LIMIT 0',
         'SELECT hour_start, grants, files, bytes FROM terminal.usage_hour LIMIT 0',
         'SELECT edge_owner_key FROM terminal.subscriber LIMIT 0',
         'SELECT version FROM terminal.access_log LIMIT 0',
         'SELECT client_key FROM terminal.access_log LIMIT 0')
# EXEC-MU-ACCOUNTS Phase 3c: an EDGE owner's row (kind 'owner', migration 20261118_100). terminal.subscriber needs an
# email, a display name, a verifier and an end: a synthetic address no mail reaches (under the reserved .local name of
# the service accounts, config.py SERVICE_DOMAIN) derived from the owner key, the all-zero verifier no password derives
# (an owner never signs in: sign-in and session_subscriber take kind 'person' only) and the service rows' end.
OWNER_DOMAIN = 'edge-owner.terminal.local'
NO_PASSWORD = 'scrypt$' + '0' * 32 + '$' + '0' * 64
OWNER_EXPIRES = '2100-01-01T00:00:00Z'


def owner_email(owner_key):
    """u_0123... -> owner-<first 32 hex of its sha256>@edge-owner.terminal.local: lower case, as the email check
    requires (an owner key may hold capitals, ':' or '@')."""
    return f'owner-{hashlib.sha256(owner_key.encode()).hexdigest()[:32]}@{OWNER_DOMAIN}'


class Store:
    def __init__(self, url, max_size=8):
        """max_size: TERMINAL_POOL_MAX (config.py; EXEC-MU-RUNTIME T9), connections per process."""
        # check: a connection the server dropped (a Postgres restart, ERRORS M414) is replaced before it is handed out,
        # as edge-bff does since M246; without it the first request after a restart fails and /ready answers 503
        self.pool = ConnectionPool(url, min_size=1, max_size=max_size, open=False,
                                   kwargs={'row_factory': dict_row, 'connect_timeout': 5},
                                   check=ConnectionPool.check_connection)

    def open(self):
        self.pool.open(wait=True, timeout=30)

    def close(self):
        self.pool.close()

    @contextmanager
    def tx(self):
        with self.pool.connection() as c:
            with c.transaction():
                yield c

    def ready(self):
        """/ready, the Railway healthcheck (EXEC-MU-RUNTIME T9): the database answers and holds what this build reads
        (READY), so a deployment started before its migration never becomes ready and Railway keeps the previous
        deployment serving instead of switching to one whose every account read would fail."""
        with self.tx() as c:
            for statement in READY:
                c.execute(statement)

    # ---- quotas ----------------------------------------------------------------------------------------------
    @staticmethod
    def lock_subscriber(c, sid, client=None):
        """The account's lock for a grant; track guest: a visitor's own lock under the guest owner (one key per visitor,
        so the visitors of the one guest row do not wait for each other; two that share a hash only wait longer)."""
        if client is not None:
            c.execute("SELECT pg_advisory_xact_lock(hashtext('terminal.client:' || %s), %s::int)", (client, sid))
            return
        c.execute("SELECT pg_advisory_xact_lock(hashtext('terminal.subscriber'), %s::int)", (sid,))

    @staticmethod
    def limits(c, sid):
        rows = c.execute('SELECT q.name, coalesce(o.value, q.value) AS value FROM terminal.quota q '
                         'LEFT JOIN terminal.quota_override o ON o.name = q.name AND o.subscriber_id = %s',
                         (sid,)).fetchall()
        return {r['name']: r['value'] for r in rows}

    @staticmethod
    def usage(c, sid, client=None):
        """The rolling usage of the account; track guest: of one visitor of the guest owner (`client`)."""
        r = c.execute(
            "SELECT coalesce(sum(file_count) FILTER (WHERE kind = 'file' AND at > now() - interval '1 hour'), 0) AS files_hour, "
            "coalesce(array_agg(DISTINCT ticker) FILTER (WHERE ticker <> %s AND at > now() - interval '1 hour'), "
            "'{}') AS tickers_hour, "
            "coalesce(array_agg(DISTINCT ticker) FILTER (WHERE ticker <> %s), '{}') AS tickers_day, "
            'coalesce(sum(bytes), 0)::bigint AS bytes_day, '
            "count(*) FILTER (WHERE kind LIKE 'history%%' AND at > now() - interval '1 hour') AS history_hour "
            "FROM terminal.access_log WHERE subscriber_id = %s" + (CLIENT if client is not None else '')
            + " AND at > now() - interval '1 day'",
            (REF, REF, sid) + ((client,) if client is not None else ())).fetchone()
        return Usage(r['files_hour'], frozenset(r['tickers_hour']), frozenset(r['tickers_day']), r['bytes_day'],
                     r['history_hour'])

    @staticmethod
    def frees_in(c, sid, refusal, client=None):
        """EXEC-MU-ACCOUNTS re-check R1-1/R1-26: whole seconds until the rolling window of a refused quota has let
        enough of the account's use go for the refused request to fit (quota.Refusal.excess), read only when a request
        is refused (FREES, on the index subscriber_id, at). None when the window's rows never free enough (the request
        alone is larger than the limit): the caller then names the window's length."""
        sql = FREES.get(refusal.quota)
        if sql is None:
            return None
        sql = sql.format(client=CLIENT if client is not None else '')
        mine = (sid,) + ((client,) if client is not None else ())
        row = c.execute(sql, (REF,) + mine if refusal.quota.startswith('tickers') else mine + (refusal.excess,)).fetchone()
        return None if row is None or row['wait'] is None else max(1, math.ceil(row['wait']))

    @staticmethod
    def meter(c, sid, files, bytes_):
        """EXEC-MU-RUNTIME T1: a service account's grant added to its clock hour (UTC) in terminal.usage_hour, and the
        hour's totals after it (hour_start, grants, files, bytes). The row lock of the UPSERT orders concurrent grants
        of one service, so every grant sees the totals that include it; a refused grant rolls its addition back with
        its transaction."""
        return c.execute(
            'INSERT INTO terminal.usage_hour AS u (subscriber_id, hour_start, grants, files, bytes) '
            "VALUES (%s, date_trunc('hour', now(), 'UTC'), 1, %s, %s) "
            'ON CONFLICT (subscriber_id, hour_start) DO UPDATE SET grants = u.grants + 1, files = u.files + EXCLUDED.files, '
            'bytes = u.bytes + EXCLUDED.bytes RETURNING hour_start, grants, files, bytes', (sid, files, bytes_)).fetchone()

    @staticmethod
    def log_access(c, sid, kind, ticker, ip, dataset=None, year=None, key=None, bytes_=0, keys=None, version=None,
                   client=None):
        """One row; `keys` (EXEC-TERMINAL-SPEED): every file a /bundle grants, counted in file_count. `version`
        (EXEC-MU-ACCOUNTS Phase 3c): the entitlements version of x-terminal-capabilities, null without the header.
        `client` (track guest): the visitor key of a guest's call, null otherwise."""
        c.execute('INSERT INTO terminal.access_log(subscriber_id, kind, ticker, dataset, year, object_key, bytes, ip, '
                  'file_count, object_keys, version, client_key) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
                  (sid, kind, ticker, dataset, year, key or (keys[0] if keys else None), bytes_, ip,
                   len(keys) if keys else 1, keys, version, client))

    @staticmethod
    def prune(c, days):
        """Audit rows older than `days` (user 2026-10-26: 90); quotas look back one day at most. The service accounts'
        hourly counters (EXEC-MU-RUNTIME T1) are kept as long as the audit rows they summarize."""
        c.execute('DELETE FROM terminal.usage_hour WHERE hour_start < now() - make_interval(days => %s)', (days,))
        return c.execute('DELETE FROM terminal.access_log WHERE at < now() - make_interval(days => %s)', (days,)).rowcount

    # ---- accounts and sessions -------------------------------------------------------------------------------
    @staticmethod
    def failed_sign_ins(c, email, ip):
        r = c.execute("SELECT count(*) FILTER (WHERE email = %s) AS by_email, "
                      "count(*) FILTER (WHERE ip IS NOT DISTINCT FROM %s::inet) AS by_ip "
                      "FROM terminal.sign_in_attempt WHERE NOT ok AND at > now() - interval '15 minutes' "
                      'AND (email = %s OR ip IS NOT DISTINCT FROM %s::inet)', (email, ip, email, ip)).fetchone()
        return r['by_email'], r['by_ip']

    @staticmethod
    def record_sign_in(c, email, ip, ok):
        c.execute('INSERT INTO terminal.sign_in_attempt(email, ip, ok) VALUES (%s, %s, %s)', (email, ip, ok))

    @staticmethod
    def subscriber_by_email(c, email):
        return c.execute('SELECT subscriber_id, password_hash, active, expires_at > now() AS current, kind '
                         'FROM terminal.subscriber WHERE email = %s', (email,)).fetchone()

    @staticmethod
    def open_session(c, sid, token_hash, ip, hours, max_sessions):
        active = c.execute('SELECT token_hash FROM terminal.session WHERE subscriber_id = %s AND revoked_at IS NULL '
                           'AND expires_at > now() ORDER BY created_at DESC', (sid,)).fetchall()
        for old in active[max_sessions - 1:]:
            c.execute('UPDATE terminal.session SET revoked_at = now() WHERE token_hash = %s', (old['token_hash'],))
        c.execute("INSERT INTO terminal.session(token_hash, subscriber_id, expires_at, ip) "
                  "VALUES (%s, %s, now() + %s * interval '1 hour', %s)", (token_hash, sid, hours, ip))

    @staticmethod
    def session_subscriber(c, token_hash):
        """The active person behind a sign-in (a service account never signs in: main.py sign_in)."""
        return c.execute('SELECT s.subscriber_id, u.email, u.display_name, u.expires_at, u.kind FROM terminal.session s '
                         'JOIN terminal.subscriber u USING (subscriber_id) WHERE s.token_hash = %s '
                         "AND s.revoked_at IS NULL AND s.expires_at > now() AND u.active AND u.expires_at > now() "
                         "AND u.kind = 'person'", (token_hash,)).fetchone()

    @staticmethod
    def account(c, email, kind):
        """The active, unexpired account of a key: the gateway's TERMINAL_PROXY_SUBSCRIBER (kind 'person') or a
        service account (kind 'service', EXEC-MU-RUNTIME T1). One row by the unique email index (subscriber_email_key)."""
        return c.execute(f'SELECT {ACCOUNT} FROM terminal.subscriber '
                         'WHERE email = %s AND kind = %s AND active AND expires_at > now()', (email, kind)).fetchone()

    @staticmethod
    def gateway_state(c, email):
        """Re-check R1-4: the gateway's account row as it is (active, seconds until expires_at), or None when absent."""
        return c.execute("SELECT active, extract(epoch FROM expires_at - now())::float8 AS seconds_left "
                         "FROM terminal.subscriber WHERE email = %s AND kind = 'person'", (email,)).fetchone()

    @staticmethod
    def owner_account(c, owner_key):
        """EXEC-MU-ACCOUNTS Phase 3c: the usable row of an EDGE owner (kind 'owner'), made on first use. Race-safe: two
        first calls of one owner both INSERT ... ON CONFLICT DO NOTHING (every unique index is an arbiter:
        edge_owner_key and the email derived from it), and the one that inserted nothing reads the row the other
        made. None when the row is inactive or expired (the administrator turned the owner off)."""
        select = (f'SELECT {ACCOUNT}, active AND expires_at > now() AS usable FROM terminal.subscriber '
                  "WHERE edge_owner_key = %s AND kind = 'owner'")
        row = c.execute(select, (owner_key,)).fetchone()
        if row is None:
            c.execute('INSERT INTO terminal.subscriber(email, display_name, password_hash, expires_at, kind, '
                      "edge_owner_key) VALUES (%s, %s, %s, %s, 'owner', %s) ON CONFLICT DO NOTHING",
                      (owner_email(owner_key), f'EDGE owner {owner_key}'[:120], NO_PASSWORD, OWNER_EXPIRES, owner_key))
            row = c.execute(select, (owner_key,)).fetchone()
        if row is None or not row['usable']:
            return None
        return {k: row[k] for k in ('subscriber_id', 'email', 'display_name', 'expires_at', 'kind')}

    @staticmethod
    def revoke_session(c, token_hash):
        c.execute('UPDATE terminal.session SET revoked_at = now() WHERE token_hash = %s AND revoked_at IS NULL',
                  (token_hash,))

    @staticmethod
    def set_password(c, sid, verifier, keep_token_hash=None):
        c.execute('UPDATE terminal.subscriber SET password_hash = %s, updated_at = now() WHERE subscriber_id = %s',
                  (verifier, sid))
        c.execute('UPDATE terminal.session SET revoked_at = now() WHERE subscriber_id = %s AND revoked_at IS NULL '
                  'AND token_hash IS DISTINCT FROM %s', (sid, keep_token_hash))

    @staticmethod
    def password_hash(c, sid):
        return c.execute('SELECT password_hash FROM terminal.subscriber WHERE subscriber_id = %s',
                         (sid,)).fetchone()['password_hash']

    # ---- admin -----------------------------------------------------------------------------------------------
    @staticmethod
    def add_subscriber(c, email, name, verifier, expires_at):
        return c.execute('INSERT INTO terminal.subscriber(email, display_name, password_hash, expires_at) '
                         'VALUES (%s, %s, %s, %s) RETURNING subscriber_id', (email, name, verifier,
                                                                            expires_at)).fetchone()['subscriber_id']

    @staticmethod
    def list_subscribers(c):
        return c.execute(
            'SELECT u.subscriber_id, u.email, u.display_name, u.kind, u.edge_owner_key, u.active, u.expires_at, u.disabled_reason, u.created_at, '
            '(SELECT max(at) FROM terminal.access_log a WHERE a.subscriber_id = u.subscriber_id) AS last_access, '
            "(SELECT coalesce(sum(bytes), 0) FROM terminal.access_log a WHERE a.subscriber_id = u.subscriber_id "
            "AND at > now() - interval '1 day') AS bytes_day "
            'FROM terminal.subscriber u ORDER BY u.subscriber_id').fetchall()

    @staticmethod
    def update_subscriber(c, sid, fields):
        allowed = {'display_name', 'active', 'expires_at', 'disabled_reason', 'password_hash'}
        cols = [k for k in fields if k in allowed]
        if not cols:
            return False
        sets = ', '.join(f'{k} = %s' for k in cols)
        r = c.execute(f'UPDATE terminal.subscriber SET {sets}, updated_at = now() WHERE subscriber_id = %s '
                      'RETURNING subscriber_id', [fields[k] for k in cols] + [sid]).fetchone()
        if r and (fields.get('active') is False or 'password_hash' in fields):
            c.execute('UPDATE terminal.session SET revoked_at = now() WHERE subscriber_id = %s AND revoked_at IS NULL',
                      (sid,))
        return bool(r)

    @staticmethod
    def admin_log(c, action, sid, detail, ip):
        from psycopg.types.json import Jsonb
        c.execute('INSERT INTO terminal.admin_log(action, subscriber_id, detail, ip) VALUES (%s, %s, %s, %s)',
                  (action, sid, Jsonb(detail), ip))

    # ---- market fallback -------------------------------------------------------------------------------------
    @staticmethod
    def price_history(c, ticker, lo, hi):
        return c.execute(PRICE_HISTORY, (ticker, lo, hi)).fetchall()

    @staticmethod
    def broker_history(c, ticker, lo, hi, brokers, investor_type, market_board):
        return c.execute(BROKER_HISTORY, (ticker, lo, hi, brokers, brokers, investor_type, investor_type,
                                          market_board, market_board)).fetchall()
