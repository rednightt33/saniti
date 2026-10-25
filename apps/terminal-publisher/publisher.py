"""EXEC-TERMINAL-API: publish display files for the subscriber terminal (verification/terminal_api/DESIGN.md 2.2-2.3).

Reads the market tables through terminal_publisher_login (read-only) and writes gzip JSON files to the private bucket
terminal-display. Browsers download them through presigned URLs issued by terminal-api.

Modes (TERMINAL_PUBLISH_MODE, or the first argument):
  daily         price: every ticker-year whose source stamp changed; broker: the ticker-years of trading dates newer
                than the published data_through. Reference files are refreshed. Run after the price cron.
  backfill      every ticker-year of the window (initial load or a schema change).
  broker-range  TERMINAL_FROM, TERMINAL_TO [, TERMINAL_TICKERS=A,B]: republish broker files after a manual
                refresh_feature_05 of that range (the same arguments).
  verify        compare every published file with SQL (row count, sums, first and last date); prints mismatches.

Objects (all under v1/):
  price/{ticker}/{year}.json.gz    columns d,o,h,l,c,v (v null for an index without volume)
  broker/{ticker}/{year}.json.gz   columns d,b,i,m,bv,sv,bl,sl; gap = [[date, board], ...] (ERRORS M157)
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
UNIVERSE_SQL = ('SELECT "Ticker", "Company Name", "Security Type" FROM public."IDX_Stock_Universe" '
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
        self.first_year, self.last_year = window(today)
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
        m['window'] = {'first_year': self.first_year, 'last_year': self.last_year}
        for dataset, through in data_through.items():
            ds = m['datasets'].setdefault(dataset, {'files': {}})
            ds['data_through'] = through
            ds['files'] = {y: f for y, f in ds['files'].items() if int(y) >= self.first_year}
        m['generated_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
        self.bucket.put(f'manifest/{ticker}.json', json.dumps(m, separators=(',', ':')).encode(), 'application/json')

    # ---- one file --------------------------------------------------------------------------------------------
    def publish(self, dataset, ticker, year, stamp=None):
        lo, hi = f'{year}-01-01', f'{year}-12-31'
        sql_text = PRICE_SQL if dataset == 'price' else BROKER_SQL
        rows = self.conn.execute(sql_text, (ticker, lo, hi)).fetchall()
        files = self.manifest(ticker)['datasets'].setdefault(dataset, {'files': {}})['files']
        if not rows:
            files.pop(str(year), None)
            return None
        doc = price_doc(ticker, year, rows) if dataset == 'price' else broker_doc(ticker, year, rows)
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
        tickers = {'schema_version': SCHEMA_VERSION, 'columns': ['ticker', 'name', 'type'],
                   **columnar(universe, ['ticker', 'name', 'type'])}
        brokers = self.conn.execute('SELECT broker_code, broker_name, broker_type FROM public."IDX_Broker_Profile" '
                                    'ORDER BY 1').fetchall()
        brokers_doc = {'schema_version': SCHEMA_VERSION, 'columns': ['code', 'name', 'type'],
                       'type_means': 'broker domicile (label only; the Foreign figures use investor type)',
                       **columnar(brokers, ['code', 'name', 'type'])}
        for key, doc in (('ref/tickers.json.gz', tickers), ('ref/brokers.json.gz', brokers_doc)):
            body, _ = encode(doc)
            self.bucket.put(key, body, 'application/gzip')

    def data_through(self):
        price = self.conn.execute('SELECT max(date)::text FROM public."Price_Stock_Indonesia_IDX" '
                                  "WHERE timeframe = 'Daily' AND is_final").fetchone()[0]
        broker = self.conn.execute('SELECT max(trade_date)::text FROM '
                                   'public."Feature_05_Foreign_Domestic_Broker_Detail"').fetchone()[0]
        return {'price': price, 'broker': broker}

    # ---- modes -----------------------------------------------------------------------------------------------
    def run(self, mode, start_from=None, end_to=None, only=None):
        started = time.monotonic()
        universe = self.universe()
        kind = {t: typ for t, _, typ in universe}
        through = self.data_through()
        state = self.bucket.get_json('state.json') or {}
        todo = []  # (dataset, ticker, year, stamp)
        years = range(self.first_year, self.last_year + 1)
        if mode == 'backfill':
            todo = [('price', t, y, None) for t in kind for y in years]
            todo += [('broker', t, y, None) for t, typ in kind.items() if typ == 'stock' for y in years]
        elif mode == 'daily':
            todo = self.changed_prices(kind)
            since = state.get('broker_through')
            if since and through['broker'] and through['broker'] > since:
                new = self.conn.execute(
                    'SELECT DISTINCT ticker, extract(year FROM trade_date)::int FROM '
                    'public."Feature_05_Foreign_Domestic_Broker_Detail" WHERE trade_date > %s', (since,)).fetchall()
                todo += [('broker', t, y, None) for t, y in new if kind.get(t) == 'stock' and y >= self.first_year]
        elif mode == 'broker-range':
            tickers = only or [t for t, typ in kind.items() if typ == 'stock']
            lo, hi = int(start_from[:4]), int(end_to[:4])
            todo = [('broker', t, y, None) for t in tickers if kind.get(t) == 'stock'
                    for y in range(max(lo, self.first_year), hi + 1)]
        else:
            raise SystemExit(f'unknown mode {mode}')
        log('plan', mode=mode, files=len(todo), window=[self.first_year, self.last_year], data_through=through)
        touched = set()
        for n, (dataset, ticker, year, stamp) in enumerate(todo, 1):
            self.publish(dataset, ticker, year, stamp)
            touched.add(ticker)
            if n % 500 == 0:
                log('progress', done=n, of=len(todo), written=self.written, mb=round(self.bytes / 1e6, 1))
        for ticker in sorted(touched):
            self.save_manifest(ticker, {'price': through['price'], 'broker': through['broker']} if kind.get(ticker) ==
                               'stock' else {'price': through['price']})
        self.publish_refs(universe)
        broker_through = through['broker'] if mode in ('backfill', 'daily') else state.get('broker_through')
        self.bucket.put('state.json', json.dumps({
            'schema_version': SCHEMA_VERSION, 'price_through': through['price'], 'broker_through': broker_through,
            'window': [self.first_year, self.last_year], 'last_mode': mode,
            'finished_at': dt.datetime.now(dt.timezone.utc).isoformat()}).encode(), 'application/json')
        log('done', mode=mode, files_planned=len(todo), files_written=self.written, mb=round(self.bytes / 1e6, 2),
            tickers=len(touched), seconds=round(time.monotonic() - started, 1))

    def changed_prices(self, kind):
        """Price ticker-years whose source stamp (rows, last date, last ingestion, sum of closes) differs from the
        manifest; a correction of an old candle changes the stamp of its year."""
        out = []
        for ticker, year, count, last, ingested, total in self.conn.execute(
                PRICE_STAMPS_SQL, (f'{self.first_year}-01-01',)).fetchall():
            if ticker not in kind:
                continue
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
    for ticker, _, typ in universe:
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
                if dataset == 'price':
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


def main(argv):
    mode = (argv[1] if len(argv) > 1 else os.environ.get('TERMINAL_PUBLISH_MODE', 'daily')).strip()
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
