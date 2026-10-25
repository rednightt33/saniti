"""PostgreSQL access through terminal_api_login: schema terminal (accounts, sessions, quotas, audit) and read-only
fallback queries on the market tables. Every market query is parameterized and bounded by the caller."""
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


class Store:
    def __init__(self, url):
        self.pool = ConnectionPool(url, min_size=1, max_size=8, open=False,
                                   kwargs={'row_factory': dict_row, 'connect_timeout': 5})

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
        with self.tx() as c:
            c.execute('SELECT 1 FROM terminal.quota LIMIT 1')

    # ---- quotas ----------------------------------------------------------------------------------------------
    @staticmethod
    def lock_subscriber(c, sid):
        c.execute("SELECT pg_advisory_xact_lock(hashtext('terminal.subscriber'), %s::int)", (sid,))

    @staticmethod
    def limits(c, sid):
        rows = c.execute('SELECT q.name, coalesce(o.value, q.value) AS value FROM terminal.quota q '
                         'LEFT JOIN terminal.quota_override o ON o.name = q.name AND o.subscriber_id = %s',
                         (sid,)).fetchall()
        return {r['name']: r['value'] for r in rows}

    @staticmethod
    def usage(c, sid):
        r = c.execute(
            "SELECT count(*) FILTER (WHERE kind = 'file' AND at > now() - interval '1 hour') AS files_hour, "
            "coalesce(array_agg(DISTINCT ticker) FILTER (WHERE ticker <> %s AND at > now() - interval '1 hour'), "
            "'{}') AS tickers_hour, "
            "coalesce(array_agg(DISTINCT ticker) FILTER (WHERE ticker <> %s), '{}') AS tickers_day, "
            'coalesce(sum(bytes), 0)::bigint AS bytes_day, '
            "count(*) FILTER (WHERE kind LIKE 'history%%' AND at > now() - interval '1 hour') AS history_hour "
            "FROM terminal.access_log WHERE subscriber_id = %s AND at > now() - interval '1 day'",
            (REF, REF, sid)).fetchone()
        return Usage(r['files_hour'], frozenset(r['tickers_hour']), frozenset(r['tickers_day']), r['bytes_day'],
                     r['history_hour'])

    @staticmethod
    def log_access(c, sid, kind, ticker, ip, dataset=None, year=None, key=None, bytes_=0):
        c.execute('INSERT INTO terminal.access_log(subscriber_id, kind, ticker, dataset, year, object_key, bytes, ip) '
                  'VALUES (%s, %s, %s, %s, %s, %s, %s, %s)', (sid, kind, ticker, dataset, year, key, bytes_, ip))

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
        return c.execute('SELECT subscriber_id, password_hash, active, expires_at > now() AS current '
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
        return c.execute('SELECT s.subscriber_id, u.email, u.display_name, u.expires_at FROM terminal.session s '
                         'JOIN terminal.subscriber u USING (subscriber_id) WHERE s.token_hash = %s '
                         'AND s.revoked_at IS NULL AND s.expires_at > now() AND u.active AND u.expires_at > now()',
                         (token_hash,)).fetchone()

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
            'SELECT u.subscriber_id, u.email, u.display_name, u.active, u.expires_at, u.disabled_reason, u.created_at, '
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
