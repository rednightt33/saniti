"""EXEC-TERMINAL-API: publish display files for the subscriber terminal (verification/terminal_api/DESIGN.md 2.2-2.3).

Reads the market tables through terminal_publisher_login (read-only) and writes gzip JSON files to the private bucket
terminal-display. Browsers download them through presigned URLs issued by terminal-api.

Modes (TERMINAL_PUBLISH_MODE, or the first argument):
  daily         price: every ticker-year whose source stamp changed; broker: the ticker-years of trading dates newer
                than the published data_through. Reference files are refreshed. Run after the price cron.
  backfill      every ticker-year of the window (initial load or a schema change).
  broker-range  TERMINAL_FROM, TERMINAL_TO [, TERMINAL_TICKERS=A,B]: republish broker files after a manual
                refresh_feature_05 of that range (the same arguments).
  events        only the event files of tickers whose idx_event_annotation rows changed.
  verify        compare every published file with SQL (row count, sums, first and last date); prints mismatches.

Schedule (T7, user 2026-10-26): TERMINAL_RUN_TIMES_WIB=07:30,19:00 and the service's Railway cronSchedule =
cron_for(those times) ("0,30 0,12 * * *"); a tick that is not a listed time exits at once (should_run). A Railway
service with a cronSchedule does not run when deployed: for a manual run clear the cronSchedule, upload a NEW deployment
(`railway up`; a `railway redeploy` keeps the old deployment's cron and does not run, ERRORS M229) and set the
cronSchedule back after the run.
Price and broker are published from their first stored year (broker: T8, user 2026-10-26).

Objects (all under v1/):
  price/{ticker}/{year}.json.gz    columns d,o,h,l,c,v (v null for an index without volume)
  broker/{ticker}/{year}.json.gz   columns d,b,i,m,bv,sv,bl,sl; gap = [[date, board], ...] (ERRORS M157)
  events/{ticker}/all.json.gz      corporate actions and insider transactions of idx_event_annotation, all dates
                                   (one file per ticker, file id "all"); republished when the ticker's rows change
  manifest/{ticker}.json           per dataset: data_through and, per year, key, sha256, bytes, rows, first, last, stamp
  ref/tickers.json.gz, ref/brokers.json.gz, state.json
Data files are written before the manifest that names them, so a reader never sees a manifest pointing at a file that
is not there yet. The universe and the changes are derived from the database at run time; no ticker list is coded.
"""
import datetime as dt
import gzip
import hashlib
import json
import os
import sys
import time

import psycopg

SCHEMA_VERSION = 1
PREFIX = 'v1'
PRICE_SQL = ('SELECT date::text, open::float8, high::float8, low::float8, close::float8, volume::float8 '
             'FROM public."Price_Stock_Indonesia_IDX" '
             "WHERE ticker = %s AND timeframe = 'Daily' AND is_final AND date BETWEEN %s AND %s ORDER BY date")
BROKER_SQL = ('SELECT trade_date::text, broker, investor_type, market_board, buy_value::float8, sell_value::float8, '
              'buy_lots::float8, sell_lots::float8, source_balance_gap '
              'FROM public."Feature_05_Foreign_Domestic_Broker_Detail" '
              'WHERE ticker = %s AND trade_date BETWEEN %s AND %s '
              'ORDER BY trade_date, broker, investor_type, market_board')
PRICE_STAMPS_SQL = ('SELECT ticker, extract(year FROM date)::int, count(*), max(date)::text, '
                    "coalesce(max(ingestion_time)::text, ''), sum(close)::text "
                    'FROM public."Price_Stock_Indonesia_IDX" '
                    "WHERE timeframe = 'Daily' AND is_final AND date >= %s GROUP BY 1, 2")
EVENTS_SQL = ('SELECT annotation_date::text, annotation_date_role, event_family, event_type, action, holder_name, '
              'holder_role, broker_code, instrument_code, shares_change::float8, pct_after::float8, '
              'pct_change::float8, pct_quality_flag, price::float8, is_estimated_price, value_idr::float8, data_origin, '
              # corporate-action terms live only in source_payload (ERRORS M223); the closes feed the derived values
              'e.source_payload, cum.close::float8, before.close::float8 '
              'FROM public.idx_event_annotation e '
              'LEFT JOIN LATERAL (SELECT p.close FROM public."Price_Stock_Indonesia_IDX" p WHERE p.ticker = e.ticker '
              # the close ON the cum date: a cum date not traded yet (a future event) has no close and no derived value
              "AND p.timeframe = 'Daily' AND p.is_final AND p.date = (SELECT CASE WHEN v ~ '^\\d{4}-\\d{2}-\\d{2}$' "
              'THEN v::date END FROM (SELECT coalesce(e.source_payload->>\'dividend_cumdate\', '
              "e.source_payload->>'stocksplit_cumdate', e.source_payload->>'rightissue_cumdate') AS v) c) "
              'ORDER BY p.date DESC LIMIT 1) cum ON true '
              "LEFT JOIN LATERAL (SELECT CASE WHEN e.source_payload->>'tender_start' ~ '^\\d{4}-\\d{2}-\\d{2}$' "
              "THEN (e.source_payload->>'tender_start')::date END AS start) s ON true "
              'LEFT JOIN LATERAL (SELECT p.close FROM public."Price_Stock_Indonesia_IDX" p WHERE p.ticker = e.ticker '
              # the last session before the offer start, within 10 days of it (none for an offer far ahead)
              "AND p.timeframe = 'Daily' AND p.is_final AND p.date < s.start AND p.date >= s.start - 10 "
              'ORDER BY p.date DESC LIMIT 1) before ON true '
              'WHERE e.ticker = %s ORDER BY e.annotation_date, e.event_key')
EVENT_COLUMNS = ['d', 'role', 'family', 'type', 'action', 'holder', 'holder_role', 'broker', 'instrument',
                 'shares_change', 'pct_after', 'pct_change', 'pct_flag', 'price', 'price_estimated', 'value', 'origin',
                 'title', 'detail']
# EXEC-TERMINAL-T7-T10 T9: bumping the events format re-stamps every ticker, so the next run republishes all files
EVENTS_FORMAT = 2
EVENT_STAMPS_SQL = ('SELECT ticker, count(*), max(annotation_date)::text, max(ingestion_time)::text '
                    'FROM public.idx_event_annotation GROUP BY ticker')
UNIVERSE_SQL = ('SELECT "Ticker", "Company Name", "Security Type", "Sector" FROM public."IDX_Stock_Universe" '
                "WHERE \"Security Type\" IN ('stock', 'index') ORDER BY 1")


def log(event, **kw):
    print(json.dumps({'event': event, **kw}, default=str), flush=True)


def window(today=None, years=None):
    """First and last calendar year published: the current year and the `years` full years before it."""
    today = today or dt.date.today()
    years = int(years if years is not None else os.environ.get('TERMINAL_YEARS', '5'))
    return today.year - years, today.year


def columnar(rows, names):
    return {n: [r[i] for r in rows] for i, n in enumerate(names)}


def encode(doc):
    raw = json.dumps(doc, separators=(',', ':'), allow_nan=False).encode()
    body = gzip.compress(raw, compresslevel=9, mtime=0)
    return body, hashlib.sha256(body).hexdigest()


def price_doc(ticker, year, rows):
    return {'schema_version': SCHEMA_VERSION, 'dataset': 'price', 'ticker': ticker, 'year': year,
            'units': {'o': 'IDR per share (index points for an index)', 'v': 'shares'},
            'columns': ['d', 'o', 'h', 'l', 'c', 'v'], **columnar(rows, ['d', 'o', 'h', 'l', 'c', 'v'])}


def broker_doc(ticker, year, rows):
    data = [r[:8] for r in rows]
    gaps = sorted({(r[0], r[3]) for r in rows if r[8]})
    return {'schema_version': SCHEMA_VERSION, 'dataset': 'broker', 'ticker': ticker, 'year': year,
            'units': {'bv': 'IDR', 'sv': 'IDR', 'bl': 'lots (100 shares; odd lots as fractions)', 'sl': 'lots'},
            'investor_type': 'source investor identity (Foreign/Domestic), not broker domicile',
            'columns': ['d', 'b', 'i', 'm', 'bv', 'sv', 'bl', 'sl'],
            **columnar(data, ['d', 'b', 'i', 'm', 'bv', 'sv', 'bl', 'sl']), 'gap': [list(g) for g in gaps]}


def _val(payload, key):
    """A payload value, or None when the source leaves it blank; 0 is Stockbit's "unknown" for numbers."""
    v = payload.get(key)
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    if isinstance(v, (int, float)) or (isinstance(v, str) and v.strip().replace('.', '', 1).isdigit()):
        n = float(v)
        return None if n == 0 else n
    return v.strip()


def _period(payload, a, b):
    lo, hi = _val(payload, a), _val(payload, b)
    return f'{lo} – {hi}' if lo and hi else None


def _ratio(payload, old, new):
    o, n = _val(payload, old), _val(payload, new)
    return (o, n) if o and n else (None, None)


def _fmt_ratio(o, n):
    return f'{o:g} : {n:g}' if o and n else None


def _div(a, b):
    return a / b if a is not None and b else None


# T9 (user 2026-10-26): the rows each corporate action shows, from its payload keys; a None value shows "Unavailable".
# kind tells the page how to format: idr, date, text, pct, shares. The three derived rows name their formula.
def corporate_action(etype, payload, close_cum, close_before):
    p = payload or {}
    v = lambda k: _val(p, k)
    if etype == 'DIVIDEND':
        dps = v('dividend_value')
        cur = (v('dividend_currency') or '').replace('CURRENCY_', '')
        rows = [['Dividend', dps if cur in ('', 'IDR') else None, 'idr_per_share'],
                ['Currency', cur or None, 'text'],
                # derived: dividend per share / close on the cum date x 100
                ['Yield (on cum-date close)', None if dps is None or cur not in ('', 'IDR') else
                 (_div(dps, close_cum) * 100 if close_cum else None), 'pct'],
                ['Cum date', v('dividend_cumdate'), 'date'], ['Ex date', v('dividend_exdate'), 'date'],
                ['Record date', v('dividend_recdate'), 'date'], ['Payment', v('dividend_paydate'), 'date']]
        return 'Cash dividend', rows
    if etype in ('STOCK_SPLIT', 'REVERSE_SPLIT'):
        o, n = _ratio(p, 'stocksplit_old', 'stocksplit_new')
        rows = [['Ratio (old : new)', _fmt_ratio(o, n), 'text'],
                ['Cum date', v('stocksplit_cumdate'), 'date'], ['Effective (ex date)', v('stocksplit_exdate'), 'date'],
                ['Record date', v('stocksplit_recdate'), 'date'],
                # derived: close on the cum date x old / new
                ['Price after (from cum-date close)', close_cum * o / n if close_cum and o and n else None, 'idr']]
        name = 'Stock split' if etype == 'STOCK_SPLIT' else 'Reverse split'
        return (f'{name} {_fmt_ratio(o, n)}' if o else name), rows
    if etype == 'RIGHT_ISSUE':
        o, n = _ratio(p, 'rightissue_old', 'rightissue_new')
        rows = [['Ratio (old : new)', _fmt_ratio(o, n), 'text'], ['Exercise price', v('rightissue_price'), 'idr'],
                ['Cum date', v('rightissue_cumdate'), 'date'], ['Ex date', v('rightissue_exdate'), 'date'],
                ['Trading period', _period(p, 'rightissue_trading_start', 'rightissue_trading_end'), 'text']]
        return (f'Rights issue {_fmt_ratio(o, n)}' if o else 'Rights issue'), rows
    if etype == 'BONUS_SHARE':
        o, n = _ratio(p, 'stocksplit_old', 'stocksplit_new')
        rows = [['Ratio (held : bonus)', _fmt_ratio(o, n), 'text'], ['Cum date', v('stocksplit_cumdate'), 'date'],
                ['Ex date', v('stocksplit_exdate'), 'date'], ['Distribution', v('stocksplit_paymentdate'), 'date']]
        return (f'Bonus shares {_fmt_ratio(o, n)}' if o else 'Bonus shares'), rows
    if etype == 'RUPS':
        meeting = v('rups_date')
        rows = [['Meeting', f"{meeting} {v('rups_time') or ''}".strip() if meeting else None, 'text'],
                ['Venue', v('rups_venue'), 'text'], ['Agenda', v('rups_iqp_agenda'), 'text'],
                ['Record date', v('rups_eligible_date'), 'date']]
        kind = (v('rups_iqp_type') or '').upper()
        return ('RUPSLB (extraordinary)' if 'LB' in kind else 'RUPST (annual)' if 'T' in kind else 'RUPS'), rows
    if etype == 'TENDER_OFFER':
        price = v('tender_price')
        rows = [['Offer price', price, 'idr'],
                # derived: offer price / close of the session before the offer start - 1
                ['Premium (vs close before start)', (price / close_before - 1) * 100 if price and close_before else None,
                 'pct'],
                ['Shares sought', v('tender_shares'), 'shares'], ['Share of capital', v('tender_percentage'), 'pct'],
                ['Period', _period(p, 'tender_start', 'tender_end'), 'text'], ['Payment', v('tender_paydate'), 'date']]
        return 'Tender offer', rows
    if etype == 'WARRANT':
        rows = [['Exercise price', v('wrant_exc_price'), 'idr'],
                ['Exercise period', _period(p, 'wrant_exc_from', 'wrant_exc_end'), 'text'],
                ['Trading period', _period(p, 'wrant_trading_from', 'wrant_trading_end'), 'text'],
                ['Expiry', v('wrant_exc_end'), 'date']]
        return 'Warrant', rows
    return None, None


def event_rows(rows):
    """SQL rows -> file rows: the display columns, then title and detail (corporate actions only)."""
    out = []
    for r in rows:
        base, (payload, close_cum, close_before) = list(r[:17]), r[17:20]
        title, detail = (corporate_action(r[3], payload, close_cum, close_before) if r[2] == 'CORPORATE_ACTION'
                         else (None, None))
        out.append(base + [title, detail])
    return out


def events_doc(ticker, rows):
    return {'schema_version': SCHEMA_VERSION, 'dataset': 'events', 'ticker': ticker,
            'units': {'shares_change': 'shares', 'pct_after': 'percent of shares', 'pct_change': 'percentage points',
                      'price': 'IDR per share', 'value': 'IDR'},
            'format': EVENTS_FORMAT,
            'means': {'d': 'annotation date; its meaning is in role (EX_DATE, MEETING_DATE, TRANSACTION_DATE, ...)',
                      'detail': 'corporate actions: [[label, value or null, kind], ...]; null = not in the source '
                                '(shown as Unavailable); kind: idr, idr_per_share, date, text, pct, shares',
                      'pct_flag': 'quality of the insider percentages (OK, ROUNDING, INCONSISTENT, ...)',
                      'origin': 'IDX or KSEI for insider rows'},
            'columns': EVENT_COLUMNS, **columnar(rows, EVENT_COLUMNS)}


class Bucket:
    def __init__(self):
        import boto3
        from botocore.config import Config
        self.name = os.environ['TERMINAL_BUCKET_NAME']
        self.s3 = boto3.client(
            's3', endpoint_url=os.environ['TERMINAL_BUCKET_ENDPOINT'], region_name=os.environ['TERMINAL_BUCKET_REGION'],
            aws_access_key_id=os.environ['TERMINAL_BUCKET_ACCESS_KEY_ID'],
            aws_secret_access_key=os.environ['TERMINAL_BUCKET_SECRET_ACCESS_KEY'],
            config=Config(s3={'addressing_style': 'virtual'}, signature_version='s3v4', retries={'max_attempts': 5}))

    def put(self, key, body, content_type):
        self.s3.put_object(Bucket=self.name, Key=f'{PREFIX}/{key}', Body=body, ContentType=content_type,
                           CacheControl='private, max-age=0' if key.endswith('.json') else 'private, max-age=31536000')

    def get_raw(self, key):
        try:
            return self.s3.get_object(Bucket=self.name, Key=f'{PREFIX}/{key}')['Body'].read()
        except self.s3.exceptions.NoSuchKey:
            return None

    def get_json(self, key):
        body = self.get_raw(key)
        if body is None:
            return None
        return json.loads(gzip.decompress(body) if key.endswith('.gz') else body)


class Publisher:
    def __init__(self, conn, bucket, today=None):
        self.conn, self.bucket = conn, bucket
        # first_year/last_year: the broker window (TERMINAL_YEARS). Price is small (~2 KB per ticker-year) and is
        # published from its first stored year, so browser indicators start where Feature 04 does (user 2026-10-25).
        self.first_year, self.last_year = window(today)
        self.price_first_year = None
        self.broker_first_year = None
        self.manifests = {}
        self.written = 0
        self.bytes = 0

    # ---- manifests -------------------------------------------------------------------------------------------
    def manifest(self, ticker):
        if ticker not in self.manifests:
            m = self.bucket.get_json(f'manifest/{ticker}.json')
            self.manifests[ticker] = m or {'schema_version': SCHEMA_VERSION, 'ticker': ticker, 'datasets': {}}
        return self.manifests[ticker]

    def save_manifest(self, ticker, data_through):
        m = self.manifest(ticker)
        m['window'] = {'first_year': self.first_year, 'last_year': self.last_year,
                       'price_first_year': self.price_first_year, 'broker_first_year': self.broker_first_year}
        for dataset, through in data_through.items():
            ds = m['datasets'].setdefault(dataset, {'files': {}})
            first = self.dataset_first_year(dataset)
            ds['data_through'] = through
            ds['first_year'] = first
            ds['files'] = {y: f for y, f in ds['files'].items() if not y.isdigit() or int(y) >= first}
        m['generated_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
        self.bucket.put(f'manifest/{ticker}.json', json.dumps(m, separators=(',', ':')).encode(), 'application/json')

    # ---- one file --------------------------------------------------------------------------------------------
    def publish(self, dataset, ticker, year, stamp=None):
        if dataset == 'events':
            rows = event_rows(self.conn.execute(EVENTS_SQL, (ticker,)).fetchall())
        else:
            lo, hi = f'{year}-01-01', f'{year}-12-31'
            rows = self.conn.execute(PRICE_SQL if dataset == 'price' else BROKER_SQL, (ticker, lo, hi)).fetchall()
        files = self.manifest(ticker)['datasets'].setdefault(dataset, {'files': {}})['files']
        if not rows:
            files.pop(str(year), None)
            return None
        doc = (price_doc(ticker, year, rows) if dataset == 'price' else broker_doc(ticker, year, rows)
               if dataset == 'broker' else events_doc(ticker, rows))
        body, sha = encode(doc)
        key = f'{dataset}/{ticker}/{year}.json.gz'
        if files.get(str(year), {}).get('sha256') != sha:
            self.bucket.put(key, body, 'application/gzip')
            self.written += 1
            self.bytes += len(body)
        files[str(year)] = {'key': f'{PREFIX}/{key}', 'sha256': sha, 'bytes': len(body), 'rows': len(rows),
                            'first': rows[0][0], 'last': rows[-1][0],
                            'stamp': stamp or f'rows={len(rows)};last={rows[-1][0]}'}
        return rows[-1][0]

    # ---- reference files and universe ------------------------------------------------------------------------
    def universe(self):
        return self.conn.execute(UNIVERSE_SQL).fetchall()

    def publish_refs(self, universe):
        tickers = {'schema_version': SCHEMA_VERSION, 'columns': ['ticker', 'name', 'type', 'sector'],
                   **columnar(universe, ['ticker', 'name', 'type', 'sector'])}
        brokers = self.conn.execute('SELECT broker_code, broker_name, broker_type FROM public."IDX_Broker_Profile" '
                                    'ORDER BY 1').fetchall()
        brokers_doc = {'schema_version': SCHEMA_VERSION, 'columns': ['code', 'name', 'type'],
                       'type_means': 'broker domicile (label only; the Foreign figures use investor type)',
                       **columnar(brokers, ['code', 'name', 'type'])}
        for key, doc in (('ref/tickers.json.gz', tickers), ('ref/brokers.json.gz', brokers_doc)):
            body, _ = encode(doc)
            self.bucket.put(key, body, 'application/gzip')

    def dataset_first_year(self, dataset):
        return {'price': self.price_first_year, 'broker': self.broker_first_year}.get(dataset) or self.first_year

    def resolve_price_first_year(self):
        """Price and broker are published from their first stored year (price: user 2026-10-25; broker: T8, user
        2026-10-26 "data broker feel free untuk dipindahkan ke storage"); derived from the data, no year is coded."""
        first = self.conn.execute('SELECT min(date)::text FROM public."Price_Stock_Indonesia_IDX" '
                                  "WHERE timeframe = 'Daily' AND is_final").fetchone()[0]
        self.price_first_year = min(int(first[:4]), self.first_year) if first else self.first_year
        first = self.conn.execute('SELECT min(trade_date)::text FROM '
                                  'public."Feature_05_Foreign_Domestic_Broker_Detail"').fetchone()[0]
        self.broker_first_year = min(int(first[:4]), self.first_year) if first else self.first_year

    def data_through(self):
        price = self.conn.execute('SELECT max(date)::text FROM public."Price_Stock_Indonesia_IDX" '
                                  "WHERE timeframe = 'Daily' AND is_final").fetchone()[0]
        broker = self.conn.execute('SELECT max(trade_date)::text FROM '
                                   'public."Feature_05_Foreign_Domestic_Broker_Detail"').fetchone()[0]
        events = self.conn.execute('SELECT max(ingestion_time)::text FROM public.idx_event_annotation').fetchone()[0]
        return {'price': price, 'broker': broker, 'events': events}

    # ---- modes -----------------------------------------------------------------------------------------------
    def run(self, mode, start_from=None, end_to=None, only=None):
        started = time.monotonic()
        universe = self.universe()
        kind = {t: typ for t, _, typ, _ in universe}
        through = self.data_through()
        self.resolve_price_first_year()
        state = self.bucket.get_json('state.json') or {}
        todo = []  # (dataset, ticker, year, stamp)
        years = range(self.broker_first_year, self.last_year + 1)
        if mode == 'backfill':
            todo = [('price', t, y, None) for t in kind for y in range(self.price_first_year, self.last_year + 1)]
            todo += [('broker', t, y, None) for t, typ in kind.items() if typ == 'stock' for y in years]
            todo += self.changed_events(kind, force=True)
        elif mode == 'daily':
            todo = self.changed_prices(kind) + self.changed_events(kind)
            since = state.get('broker_through')
            if since and through['broker'] and through['broker'] > since:
                new = self.conn.execute(
                    'SELECT DISTINCT ticker, extract(year FROM trade_date)::int FROM '
                    'public."Feature_05_Foreign_Domestic_Broker_Detail" WHERE trade_date > %s', (since,)).fetchall()
                todo += [('broker', t, y, None) for t, y in new if kind.get(t) == 'stock' and y >= self.broker_first_year]
        elif mode == 'events':
            todo = self.changed_events(kind)
        elif mode == 'broker-range':
            tickers = only or [t for t, typ in kind.items() if typ == 'stock']
            lo, hi = int(start_from[:4]), int(end_to[:4])
            todo = [('broker', t, y, None) for t in tickers if kind.get(t) == 'stock'
                    for y in range(max(lo, self.broker_first_year), hi + 1)]
        else:
            raise SystemExit(f'unknown mode {mode}')
        log('plan', mode=mode, files=len(todo), window=[self.first_year, self.last_year],
            price_first_year=self.price_first_year, broker_first_year=self.broker_first_year, data_through=through)
        touched = set()
        for n, (dataset, ticker, year, stamp) in enumerate(todo, 1):
            self.publish(dataset, ticker, year, stamp)
            touched.add(ticker)
            if n % 500 == 0:
                log('progress', done=n, of=len(todo), written=self.written, mb=round(self.bytes / 1e6, 1))
        for ticker in sorted(touched):
            datasets = {'price': through['price']}
            if kind.get(ticker) == 'stock':
                datasets['broker'] = through['broker']
            if self.manifest(ticker)['datasets'].get('events', {}).get('files'):
                datasets['events'] = through['events']
            self.save_manifest(ticker, datasets)
        self.publish_refs(universe)
        broker_through = through['broker'] if mode in ('backfill', 'daily') else state.get('broker_through')
        self.bucket.put('state.json', json.dumps({
            'schema_version': SCHEMA_VERSION, 'price_through': through['price'], 'broker_through': broker_through,
            'window': [self.first_year, self.last_year], 'price_first_year': self.price_first_year,
            'broker_first_year': self.broker_first_year, 'last_mode': mode,
            'finished_at': dt.datetime.now(dt.timezone.utc).isoformat()}).encode(), 'application/json')
        log('done', mode=mode, files_planned=len(todo), files_written=self.written, mb=round(self.bytes / 1e6, 2),
            tickers=len(touched), seconds=round(time.monotonic() - started, 1))

    def changed_events(self, kind, force=False):
        """Tickers whose event rows changed (count, last date, last ingestion), or every ticker with events."""
        out = []
        for ticker, count, last, ingested in self.conn.execute(EVENT_STAMPS_SQL).fetchall():
            if ticker not in kind:
                continue  # delisted tickers are not served by the terminal
            stamp = f'format={EVENTS_FORMAT};rows={count};last={last};ing={ingested}'
            current = self.manifest(ticker)['datasets'].get('events', {}).get('files', {}).get('all', {})
            if force or current.get('stamp') != stamp:
                out.append(('events', ticker, 'all', stamp))
        log('planning', step='event stamps read', changed=len(out))
        return out

    def changed_prices(self, kind):
        """Price ticker-years whose source stamp (rows, last date, last ingestion, sum of closes) differs from the
        manifest; a correction of an old candle changes the stamp of its year."""
        out, seen = [], set()
        rows = self.conn.execute(PRICE_STAMPS_SQL, (f'{self.price_first_year}-01-01',)).fetchall()
        log('planning', step='price stamps read', ticker_years=len(rows))
        for ticker, year, count, last, ingested, total in rows:
            if ticker not in kind:
                continue
            if ticker not in seen:  # reading each manifest from the bucket is the slow part of planning
                seen.add(ticker)
                if len(seen) % 200 == 0:
                    log('planning', step='manifests read', tickers=len(seen))
            stamp = f'rows={count};last={last};ing={ingested};sum={total}'
            current = self.manifest(ticker)['datasets'].get('price', {}).get('files', {}).get(str(year), {})
            if current.get('stamp') != stamp:
                out.append(('price', ticker, year, stamp))
        return out


def verify(conn, bucket):
    """Every published file against SQL: rows, first/last date and column sums."""
    first_year, last_year = window()
    universe = conn.execute(UNIVERSE_SQL).fetchall()
    checked = bad = 0
    for ticker, _, typ, _ in universe:
        m = bucket.get_json(f'manifest/{ticker}.json')
        if not m:
            log('verify_missing_manifest', ticker=ticker)
            bad += 1
            continue
        for dataset, ds in m['datasets'].items():
            for year, f in ds['files'].items():
                body = bucket.get_raw(f['key'][len(PREFIX) + 1:])
                if body is None or hashlib.sha256(body).hexdigest() != f['sha256']:
                    bad += 1
                    log('verify_bad_object', ticker=ticker, dataset=dataset, year=year)
                    continue
                doc = json.loads(gzip.decompress(body))
                lo, hi = f'{year}-01-01', f'{year}-12-31'
                if dataset == 'events':
                    sql_row = conn.execute(
                        'SELECT count(*), min(annotation_date)::text, max(annotation_date)::text, '
                        'coalesce(sum(value_idr), 0)::float8 FROM public.idx_event_annotation WHERE ticker=%s',
                        (ticker,)).fetchone()
                    got = (len(doc['d']), doc['d'][0], doc['d'][-1], sum(v or 0 for v in doc['value']))
                elif dataset == 'price':
                    sql_row = conn.execute(
                        'SELECT count(*), min(date)::text, max(date)::text, sum(close)::float8 FROM '
                        'public."Price_Stock_Indonesia_IDX" WHERE ticker=%s AND timeframe=\'Daily\' AND is_final '
                        'AND date BETWEEN %s AND %s', (ticker, lo, hi)).fetchone()
                    got = (len(doc['d']), doc['d'][0], doc['d'][-1], sum(doc['c']))
                else:
                    sql_row = conn.execute(
                        'SELECT count(*), min(trade_date)::text, max(trade_date)::text, sum(buy_value)::float8 + '
                        'sum(sell_value)::float8 FROM public."Feature_05_Foreign_Domestic_Broker_Detail" '
                        'WHERE ticker=%s AND trade_date BETWEEN %s AND %s', (ticker, lo, hi)).fetchone()
                    got = (len(doc['d']), doc['d'][0], doc['d'][-1], sum(doc['bv']) + sum(doc['sv']))
                same = got[:3] == tuple(sql_row[:3]) and abs(got[3] - sql_row[3]) <= max(1.0, abs(sql_row[3]) * 1e-9)
                checked += 1
                if not same:
                    bad += 1
                    log('verify_mismatch', ticker=ticker, dataset=dataset, year=year, file=got, sql=sql_row)
    log('verify_done', files=checked, mismatches=bad, window=[first_year, last_year])
    return bad


WIB = dt.timezone(dt.timedelta(hours=7))


def run_times(value):
    """'07:30,19:00' -> [(7, 30), (19, 0)] in WIB."""
    out = []
    for part in (value or '').split(','):
        if part.strip():
            h, m = part.strip().split(':')
            out.append((int(h), int(m)))
    return out


def cron_for(times):
    """The one Railway cronSchedule (UTC) that fires at every listed WIB time: the product of their UTC minutes and
    hours; ticks that are not a listed time are skipped by should_run."""
    utc = [((h - 7) % 24, m) for h, m in times]
    minutes = sorted({m for _, m in utc}); hours = sorted({h for h, _ in utc})
    return f"{','.join(map(str, minutes))} {','.join(map(str, hours))} * * *"


def should_run(times, now=None, slack_minutes=20):
    """T7 (user 2026-10-26: "jadwal publisher ... jam 19.00 dan jam 7.30"): a run near a cron tick that is not a listed
    time exits at once; a run near a listed time, or away from every tick (a deploy or manual run), goes ahead."""
    if not times:
        return True
    now = (now or dt.datetime.now(dt.timezone.utc)).astimezone(WIB)
    mins = now.hour * 60 + now.minute
    near = lambda h, m: 0 <= (mins - (h * 60 + m)) % 1440 <= slack_minutes
    if any(near(h, m) for h, m in times):
        return True
    utc = [((h - 7) % 24, m) for h, m in times]
    ticks = {((uh + 7) % 24, um) for uh in {h for h, _ in utc} for um in {m for _, m in utc}}
    return not any(near(h, m) for h, m in ticks)


def main(argv):
    mode = (argv[1] if len(argv) > 1 else os.environ.get('TERMINAL_PUBLISH_MODE', 'daily')).strip()
    times = run_times(os.environ.get('TERMINAL_RUN_TIMES_WIB'))
    if mode == 'daily' and not should_run(times):
        log('skipped', reason='cron tick is not a listed run time', run_times_wib=os.environ.get('TERMINAL_RUN_TIMES_WIB'),
            cron=cron_for(times))
        return 0
    with psycopg.connect(os.environ['TERMINAL_PUBLISHER_DATABASE_URL'], autocommit=True) as conn:
        bucket = Bucket()
        if mode == 'verify':
            return 1 if verify(conn, bucket) else 0
        only = [t.strip().upper() for t in os.environ.get('TERMINAL_TICKERS', '').split(',') if t.strip()] or None
        Publisher(conn, bucket).run(mode, os.environ.get('TERMINAL_FROM'), os.environ.get('TERMINAL_TO'), only)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main(sys.argv))
    except psycopg.Error as e:
        # Driver errors may include connection details; print the class only.
        log('failed', error=type(e).__name__)
        sys.exit(2)
