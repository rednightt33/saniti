"""EXEC-TERMINAL-API: publish display files for the subscriber terminal (verification/terminal_api/DESIGN.md 2.2-2.3).

Reads the market tables through terminal_publisher_login (read-only) and writes gzip JSON files to the private bucket
terminal-display. Browsers download them through presigned URLs issued by terminal-api.

Modes (TERMINAL_PUBLISH_MODE, or the first argument):
  daily         price: every ticker-year whose source stamp changed; broker: the ticker-years of trading dates newer
                than the published data_through. Reference files are refreshed. Run after the price cron. Before it
                writes, the files no manifest or state.json index names any more are deleted (collect_garbage,
                ERRORS M250).
  backfill      every ticker-year of the window (initial load or a schema change).
  broker-range  TERMINAL_FROM, TERMINAL_TO [, TERMINAL_TICKERS=A,B]: republish broker files after a manual
                refresh_feature_05 of that range (the same arguments).
  events        only the event files of tickers whose idx_event_annotation rows changed.
  logos         every ticker's logo (EXEC-TERMINAL-LOGO); `daily` also refreshes them when the index is > 7 days old.
  packs         every ticker's packs (EXEC-TERMINAL-SPEED); the other modes keep the packs of the tickers they touch.
  verify        compare every published file with SQL (row count, sums, first and last date); prints mismatches.
The cross-sectional files (below) are rebuilt by the modes in XSECTION_REBUILT_BY: daily, backfill and packs rebuild
`price` and `actions`, events rebuilds `actions`; every other mode carries the previous index entries forward.

Schedule (T7, user 2026-10-26): TERMINAL_RUN_TIMES_WIB=07:30,19:00 and the service's Railway cronSchedule =
cron_for(those times) ("0,30 0,12 * * *"); a tick that is not a listed time exits at once (should_run). A Railway
service with a cronSchedule does not run when deployed: for a manual run clear the cronSchedule, upload a NEW deployment
(`railway up`; a `railway redeploy` keeps the old deployment's cron and does not run, ERRORS M229) and set the
cronSchedule back after the run.
Price and broker are published from their first stored year (broker: T8, user 2026-10-26).

Objects (all under v1/; <sha> is the sha256 of the object's gzip bytes, ERRORS M250):
  price/{ticker}/{year}.<sha>.json.gz    columns d,o,h,l,c,v (v null for an index without volume)
  broker/{ticker}/{year}.<sha>.json.gz   columns d,b,i,m,bv,sv,bl,sl; gap = [[date, board], ...] (ERRORS M157)
  events/{ticker}/all.<sha>.json.gz      corporate actions and insider transactions of idx_event_annotation, all dates
                                   (one file per ticker, file id "all"); republished when the ticker's rows change
  manifest/{ticker}.json           per dataset: data_through and, per year, key, sha256, bytes, rows, first, last, stamp
  ref/tickers.json.gz, ref/brokers.json.gz, state.json
  logo/{ticker}.png|svg            the ticker's logo: Stockbit's PNG, else TradingView's SVG (scanner `logoid`)
  ref/logos.json.gz                columns ticker, file, sha256, source, fetched_at (tickers without a logo are absent)
  ref/{name}.<sha16>.json.gz       EXEC-MU-RUNTIME T5 (user chose option A, 2026-10-28): the same bytes as each fixed-key
                                   reference file above, under a content key in the xsection form; state.json `refs` =
                                   {name: {key, sha256, bytes, rows}} is their index (index_refs). The fixed keys are
                                   still written, unchanged, for the readers that open them by name
  pack/{ticker}/price.<sha>.json.gz      every price year in one file (the chart's only download)
  pack/{ticker}/broker-archive.<sha>.json.gz   broker rows of every year before the last two (the last two stay yearly)
  xsection/{name}.<sha16>.json.gz  cross-sectional files for the screener-worker (EXEC-SCREENER, P1 a, user
                                   2026-10-28): `price` (every published ticker's final daily rows from its first year,
                                   one columnar file; each ticker's slice equals its price pack) and `actions` (the
                                   corporate actions on their ex dates: share-count changes and cash dividends). <sha16>
                                   is the first 16 hex of the sha256 (the form terminal-api accepts); state.json
                                   `xsection` = {name: {key, sha256, bytes, rows, as_of}} is their manifest
EXEC-TERMINAL-SPEED (user 2026-10-26): a ticker is five objects for the page instead of 21 (ERRORS M240: the bucket's
cost is per object, ~0.8 s each, HTTP/1.1); the packs are listed in manifest `packs` with their sha256.
Data files are written before the manifest that names them, and the xsection and content-keyed reference files before
the state.json that indexes them, so a reader never sees a manifest or an index pointing at a file that is not there
yet. A changed data file, pack, xsection or content-keyed reference file is a new object (its key carries its sha256)
and an object is never written again with other bytes, so the bytes a manifest or index that terminal-api still serves
names stay readable during a run (ERRORS M250, user 2026-10-27; content_key, store). Files written before content keys
keep their fixed key until their bytes change. A daily run deletes, before it writes anything, the data files no
manifest names any more and the xsection and content-keyed reference files their state.json index no longer names,
once no reader can still use them (collect_garbage). Manifests, the fixed-key reference files, logos and state.json
keep fixed keys: readers open them by name and they are never deleted. A failed xsection or content-keyed reference
file keeps its previous index entry, the rest of the run (the Terminal's and the Backtest's files, state.json) goes
on, and the run exits 3. The universe and the changes are derived from the database at run time; no ticker list is
coded.
"""
import datetime as dt
import gzip
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

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
# EXEC-TERMINAL-FRESH (user 2026-10-27): final daily price sessions that have no broker data yet
BEHIND_SQL = ('SELECT count(DISTINCT date) FROM public."Price_Stock_Indonesia_IDX" '
              "WHERE timeframe = 'Daily' AND is_final AND date > %s")
UNIVERSE_SQL = ('SELECT "Ticker", "Company Name", "Security Type", "Sector", "Industry" FROM public."IDX_Stock_Universe" '
                "WHERE \"Security Type\" IN ('stock', 'index') ORDER BY 1")

# ---- EXEC-SCREENER (P1 a, user 2026-10-28): cross-sectional files -------------------------------------------------
# PRICE_SQL without the ticker filter and the ORDER BY: one sequential scan of the final daily rows instead of one
# index walk per ticker; the rows are grouped and ordered here. Bounded by the published years, as the price packs are.
# EXPLAIN (ANALYZE, BUFFERS) on dev 2026-10-28: Seq Scan, 1,331,548 rows, 49,339 buffers, 5.3 s; with ORDER BY ticker,
# date it was 7.4 s and an external merge sort spilled 86 MB to disk (work_mem 4 MB), so the order is set here.
XSECTION_PRICE_SQL = ('SELECT ticker, date::text, open::float8, high::float8, low::float8, close::float8, '
                      'volume::float8 FROM public."Price_Stock_Indonesia_IDX" '
                      "WHERE timeframe = 'Daily' AND is_final AND date BETWEEN %s AND %s")
# verify: the same rows, counted per ticker
XSECTION_PRICE_CHECK_SQL = ('SELECT ticker, count(*), min(date)::text, max(date)::text, sum(close)::float8 '
                            'FROM public."Price_Stock_Indonesia_IDX" '
                            "WHERE timeframe = 'Daily' AND is_final AND date BETWEEN %s AND %s GROUP BY ticker")
# The share-count changes of apps/edge-bff/backtest/src/core/datafile.ts PRICE_ACTION_TYPES (tests keep the two lists
# equal) and cash dividends, on their ex dates (role EX_DATE; annotation_date = ex_date on every such row). The term
# columns come from the payload through idx_event_annotation_terms_map (migration 20261026_002).
PRICE_ACTION_TYPES = ('STOCK_SPLIT', 'REVERSE_SPLIT', 'BONUS_SHARE', 'RIGHT_ISSUE', 'STOCK_DIVIDEND')
ACTION_TYPES = PRICE_ACTION_TYPES + ('DIVIDEND',)
XSECTION_ACTIONS_SQL = ('SELECT ticker, annotation_date::text, event_type, ratio_old::float8, ratio_new::float8, '
                        'amount_per_share::float8, currency, event_key FROM public.idx_event_annotation '
                        "WHERE event_family = 'CORPORATE_ACTION' AND annotation_date_role = 'EX_DATE' "
                        'AND event_type = ANY(%s) AND annotation_date >= %s')
ACTION_COLUMNS = ['t', 'd', 'type', 'ratio_old', 'ratio_new', 'amount_per_share', 'currency']
PRICE_XSECTION_COLUMNS = ['t', 'd', 'o', 'h', 'l', 'c', 'v']
# which modes rebuild which file (report 6.5); every other index entry is carried forward as it is
XSECTION_REBUILT_BY = {'price': ('daily', 'backfill', 'packs'), 'actions': ('daily', 'backfill', 'packs', 'events')}


def indexed_key(family):
    """The key (without v1/) of a file a state.json index names instead of a manifest: `<family>/<name>.<first 16 hex
    of its sha256>.json.gz` (content_key with ticker None), the form terminal-api's xsection_index accepts."""
    return re.compile(rf'{family}/([a-z0-9][a-z0-9_-]{{0,31}})\.([0-9a-f]{{16}})\.json\.gz')


XSECTION_KEY = indexed_key('xsection')
# EXEC-MU-RUNTIME T5: the reference files under content keys; their fixed keys (ref_key) never match: `.json.gz`
# follows the name directly
REF_KEY = indexed_key('ref')
SHA256 = re.compile(r'[0-9a-f]{64}')
# The reference files the publisher writes under fixed keys, the ones terminal-api main.py REF_FILES serves (a test keeps
# the two equal). Each is also stored under its content key and listed in state.json `refs` (index_refs).
REF_NAMES = ('tickers', 'brokers', 'logos')


def ref_key(name):
    """The fixed key of a reference file: `ref/tickers.json.gz`; readers open it by name."""
    return f'ref/{name}.json.gz'


# EXEC-TERMINAL-LOGO (user 2026-10-26): logo sources in order; a ticker none of them has gets a monogram on the page
STOCKBIT_LOGO = 'https://assets.stockbit.com/logos/companies/{ticker}.png'
TRADINGVIEW_SCAN = 'https://scanner.tradingview.com/indonesia/scan'
TRADINGVIEW_LOGO = 'https://s3-symbol-logos.tradingview.com/{logoid}--big.svg'
LOGO_MAX_AGE_DAYS = 7
LOGO_MAX_BYTES = 200_000
# ERRORS M250: how long after the last finished run (state.json) collect_garbage waits before it deletes. It must exceed
# terminal-api's manifest cache check (manifest_cache_seconds, 60 s), the presigned URL lifetime (terminal.quota
# url_ttl_seconds, 120 s) and a download started on such a URL; scheduled runs are about 12 hours apart.
GC_GRACE_SECONDS = 3600
# collect_garbage's bucket listing gives up after this long, and the run publishes without cleaning (listing the dev
# bucket took more than 6 minutes on 2026-10-27; a listing that never ends must not hold the publication).
GC_LIST_SECONDS = 900
# ERRORS M263 (M253 on PR #41's branch): a bucket request the provider cancels or drops (RequestCanceled at 00:32 UTC
# 2026-10-28 and 00:36 UTC 2026-10-27) ended the whole run. Bucket requests that fail this way are asked again after
# 2, 4 and 8 s; botocore's own retries do not count RequestCanceled as transient. Any other error still ends the run.
BUCKET_TRANSIENT_CODES = {'RequestCanceled', 'RequestTimeout', 'RequestTimeoutException', 'InternalError',
                          'ServiceUnavailable', 'SlowDown', 'Throttling', '500', '502', '503', '504'}
BUCKET_RETRY_DELAYS = (2, 4, 8)


def fetch(url, data=None, timeout=30):
    req = urllib.request.Request(url, data=data, headers={'User-Agent': 'Mozilla/5.0 (terminal-publisher)',
                                                          **({'Content-Type': 'application/json'} if data else {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.headers.get('Content-Type', ''), r.read(LOGO_MAX_BYTES + 1)


def logo_image(ticker, logoid, get=fetch):
    """(body, extension, source) of the first source that answers with an image, or None."""
    tries = [('stockbit', STOCKBIT_LOGO.format(ticker=ticker), 'png', b'\x89PNG')]
    if logoid:
        tries.append(('tradingview', TRADINGVIEW_LOGO.format(logoid=logoid), 'svg', b'<svg'))
    for source, url, ext, magic in tries:
        try:
            ctype, body = get(url)
        except (urllib.error.URLError, TimeoutError, OSError):
            continue
        if magic in body[:400] and 0 < len(body) <= LOGO_MAX_BYTES:
            return body, ext, source
    return None


def tradingview_logoids(get=fetch):
    try:
        _, body = get(TRADINGVIEW_SCAN, json.dumps({'columns': ['name', 'logoid'], 'range': [0, 5000]}).encode(), 60)
        return {row['d'][0]: row['d'][1] for row in json.loads(body)['data'] if row['d'][1]}
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError):
        return {}


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


def content_key(family, ticker, name, sha):
    """`price/BBCA/2026.<sha256>.json.gz`: the file's name, then the sha256 of its gzip bytes (ERRORS M250). A family
    without tickers (ticker None: xsection, EXEC-SCREENER; ref, EXEC-MU-RUNTIME T5) is
    `xsection/price.<first 16 hex>.json.gz`, the form terminal-api's xsection_index accepts (indexed_key); its
    state.json index entry carries the whole sha256."""
    if ticker is None:
        return f'{family}/{name}.{sha[:16]}.json.gz'
    return f'{family}/{ticker}/{name}.{sha}.json.gz'


def named_keys(manifest):
    """Every object key (without v1/) a manifest names: its dataset files and its packs."""
    entries = [f for ds in (manifest or {}).get('datasets', {}).values() for f in ds.get('files', {}).values()]
    entries += list((manifest or {}).get('packs', {}).values())
    return {e['key'][len(PREFIX) + 1:] for e in entries if str(e.get('key', '')).startswith(f'{PREFIX}/')}


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


def stream_rows(conn, sql, params, size=10_000):
    """The rows of a large statement, fetched `size` at a time (libpq 17 chunked rows; one by one with an older libpq),
    so the client library never holds the whole result while it is read."""
    with conn.cursor() as cur:
        yield from cur.stream(sql, params, size=size if psycopg.pq.version() >= 170000 else 1)


def price_pack_doc(ticker, rows):
    """pack/{ticker}/price: every published price year of the ticker in one file (EXEC-TERMINAL-SPEED)."""
    return {**price_doc(ticker, None, rows), 'dataset': 'price-pack'}


# ---- cross-sectional files (EXEC-SCREENER) --------------------------------------------------------------------------
def xsection_price_doc(columns, tickers):
    """The `price` xsection file: the columns t,d,o,h,l,c,v of every published ticker, ordered by ticker then date, and
    `tickers`, one entry per ticker in file order. A ticker's slice is its price pack's rows (xsection_slices)."""
    return {'schema_version': SCHEMA_VERSION, 'dataset': 'xsection', 'name': 'price',
            'units': {'o': 'IDR per share (index points for an index)', 'v': 'shares'},
            'means': {'t': 'ticker; rows ordered by ticker (code point order), then date',
                      'v': 'null for an index without volume',
                      'tickers': '[{t, pack_sha256, first, last, rows}] in file order: a ticker\'s slice is the rows of '
                                 'its price pack (manifest packs.price), whose sha256 is pack_sha256'},
            'columns': PRICE_XSECTION_COLUMNS, **columns, 'tickers': tickers}


def xsection_slices(doc):
    """A `price` xsection document -> (ticker, rows) per ticker in file order; rows as PRICE_SQL gives them."""
    at, cols = 0, [doc[c] for c in PRICE_XSECTION_COLUMNS[1:]]
    for entry in doc['tickers']:
        n = entry['rows']
        yield entry['t'], list(zip(*(c[at:at + n] for c in cols)))
        at += n


def xsection_actions_doc(rows):
    """The `actions` xsection file: the corporate actions the screener reads on their ex dates (P4 price breaks; cash
    dividends for Phase 2), from the first published price year on, future ex dates included. Readers apply their own
    rules and windows (the price-break rule's ADJUSTED_HISTORY_BOUNDARY lives in the backtest core, engine.ts)."""
    return {'schema_version': SCHEMA_VERSION, 'dataset': 'xsection', 'name': 'actions',
            'units': {'ratio_old': 'shares', 'ratio_new': 'shares', 'amount_per_share': 'currency per share'},
            'means': {'d': 'ex date (idx_event_annotation annotation_date, role EX_DATE)',
                      'type': 'event_type: DIVIDEND is a cash dividend; ' + ', '.join(PRICE_ACTION_TYPES) +
                              ' change the share count (datafile.ts PRICE_ACTION_TYPES)',
                      'ratio_old': 'shares held before a split or reverse split, or that entitle to ratio_new (bonus, '
                                   'rights)',
                      'ratio_new': 'shares after a split or reverse split, or bonus or rights shares received, for '
                                   'ratio_old',
                      'amount_per_share': 'cash dividend per share in currency; for RIGHT_ISSUE the exercise price',
                      'null': "not in the source; the source's 0 (Stockbit's unknown) is published as null"},
            'columns': ACTION_COLUMNS, **columnar(rows, ACTION_COLUMNS)}


def read_actions(conn, kind, first_year):
    """The rows of the `actions` file in ticker, ex date, type and event key order, and the number of rows whose ticker
    the terminal does not publish (left out, as their event files are)."""
    rows, outside = [], 0
    for t, d, typ, r_old, r_new, amount, currency, event_key in conn.execute(
            XSECTION_ACTIONS_SQL, (list(ACTION_TYPES), f'{first_year}-01-01')).fetchall():
        if t not in kind:
            outside += 1
            continue
        # 0 is the source's "unknown" for a number, as in the events files (_val)
        rows.append((t, d, typ, r_old or None, r_new or None, amount or None, currency, event_key))
    rows.sort(key=lambda r: (r[0], r[1], r[2], r[7]))
    return [r[:7] for r in rows], outside


def _count(v, least):
    return isinstance(v, int) and not isinstance(v, bool) and v >= least


def index_entries(raw, pattern, dropped):
    """The usable entries of a state.json file index: {name: ({key, sha256, bytes, rows}, the raw entry)} whose key is
    the object of that name of the index's family (`pattern`, indexed_key) named by the first 16 hex of its sha256 (64
    lowercase hex), with whole bytes >= 1 and rows >= 0. Anything else is dropped (logged as `dropped`): neither carried
    forward nor protected from collect_garbage."""
    out = {}
    for name, e in (raw.items() if isinstance(raw, dict) else ()):
        key = e.get('key') if isinstance(e, dict) else None
        m = pattern.fullmatch(key[len(PREFIX) + 1:]) if isinstance(key, str) and key.startswith(f'{PREFIX}/') else None
        sha = e.get('sha256') if m else None
        if (m and m.group(1) == name and isinstance(sha, str) and SHA256.fullmatch(sha) and sha[:16] == m.group(2)
                and _count(e.get('bytes'), 1) and _count(e.get('rows'), 0)):
            out[name] = ({'key': key, 'sha256': sha, 'bytes': e['bytes'], 'rows': e['rows']}, e)
        else:
            log(dropped, name=str(name)[:40])
    return out


def xsection_entries(raw):
    """The usable entries of a state.json `xsection` index: {name: {key, sha256, bytes, rows, as_of}} (index_entries,
    plus `as_of`: a string of at most 64 characters, else None). This is exactly what terminal-api's xsection_index
    serves (a test holds the two equal), so the index collect_garbage protects is the one terminal-api serves."""
    out = {}
    for name, (entry, e) in index_entries(raw, XSECTION_KEY, 'xsection_entry_dropped').items():
        as_of = e.get('as_of')
        out[name] = {**entry, 'as_of': as_of if isinstance(as_of, str) and len(as_of) <= 64 else None}
    return out


def ref_entries(raw):
    """EXEC-MU-RUNTIME T5: the usable entries of a state.json `refs` index: {name: {key, sha256, bytes, rows}}
    (index_entries; key `v1/ref/<name>.<16 hex>.json.gz`). A reference file has no data date of its own, so its entry
    has no `as_of`: the publication's `finished_at` dates it."""
    return {name: entry for name, (entry, _) in index_entries(raw, REF_KEY, 'ref_entry_dropped').items()}


# The families whose objects a state.json index names instead of a manifest: family -> (state.json field, key pattern,
# entries reader). collect_garbage treats every one alike (one mechanism).
INDEXED = {'xsection': ('xsection', XSECTION_KEY, xsection_entries), 'ref': ('refs', REF_KEY, ref_entries)}


def transient(error):
    """True for a bucket error that asking again may mend: a canceled, throttled or 5xx answer, or a dropped connection."""
    from botocore.exceptions import ClientError, ConnectionError as BotoConnectionError, ReadTimeoutError
    if isinstance(error, ClientError):
        return str(error.response.get('Error', {}).get('Code')) in BUCKET_TRANSIENT_CODES
    return isinstance(error, (BotoConnectionError, ReadTimeoutError))


def retried(call, sleep=None):
    """call() again after each of BUCKET_RETRY_DELAYS while it fails transiently (ERRORS M263)."""
    for delay in BUCKET_RETRY_DELAYS:
        try:
            return call()
        except Exception as e:  # noqa: BLE001 - classified below; anything else is raised as it is
            if not transient(e):
                raise
            log('bucket_retry', error=type(e).__name__, wait_seconds=delay)
            (sleep or time.sleep)(delay)
    return call()


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
        retried(lambda: self.s3.put_object(
            Bucket=self.name, Key=f'{PREFIX}/{key}', Body=body, ContentType=content_type,
            CacheControl='private, max-age=0' if key.endswith('.json') else 'private, max-age=31536000'))

    def list(self, deadline=None, prefix=''):
        """Every object under v1/{prefix}: {key without v1/: (last modified, bytes)}; TimeoutError past `deadline`
        (time.monotonic())."""
        out, token = {}, None
        while True:
            if deadline is not None and time.monotonic() > deadline:
                raise TimeoutError('bucket listing took too long')
            kw = {'Bucket': self.name, 'Prefix': f'{PREFIX}/{prefix}', **({'ContinuationToken': token} if token else {})}
            page = retried(lambda: self.s3.list_objects_v2(**kw))
            for o in page.get('Contents', []):
                out[o['Key'][len(PREFIX) + 1:]] = (o['LastModified'], o['Size'])
            token = page.get('NextContinuationToken') if page.get('IsTruncated') else None
            if not token:
                return out

    def delete(self, keys):
        """Delete keys (without the prefix), 1000 per request; returns the keys the bucket did not delete."""
        failed = []
        for i in range(0, len(keys), 1000):
            batch = keys[i:i + 1000]
            answer = retried(lambda: self.s3.delete_objects(Bucket=self.name, Delete={
                'Objects': [{'Key': f'{PREFIX}/{k}'} for k in batch], 'Quiet': True}))
            failed += [e['Key'][len(PREFIX) + 1:] for e in answer.get('Errors', [])]
        return failed

    def get_raw(self, key):
        try:
            return retried(lambda: self.s3.get_object(Bucket=self.name, Key=f'{PREFIX}/{key}')['Body'].read())
        except self.s3.exceptions.NoSuchKey:
            return None

    def get_json(self, key):
        body = self.get_raw(key)
        if body is None:
            return None
        return json.loads(gzip.decompress(body) if key.endswith('.gz') else body)


class Publisher:
    def __init__(self, conn, bucket, today=None, get=None, clock=None):
        self.conn, self.bucket = conn, bucket
        self.get = get or fetch                                  # HTTP for the logo sources (tests pass a fake)
        self.clock = clock or (lambda: dt.datetime.now(dt.timezone.utc))   # collect_garbage's grace (tests pass a fake)
        # first_year/last_year: the broker window (TERMINAL_YEARS). Price is small (~2 KB per ticker-year) and is
        # published from its first stored year, so browser indicators start where Feature 04 does (user 2026-10-25).
        self.first_year, self.last_year = window(today)
        self.price_first_year = None
        self.broker_first_year = None
        self.manifests = {}
        self.changed = set()                                      # (dataset, ticker, year) written or removed this run
        self.written = 0
        self.broker_behind = None                          # final price sessions after the broker data (run())
        self.bytes = 0
        self.xsection = {}                                  # the index written into state.json (run())
        self.xsection_failed = []                           # xsection files whose rebuild failed (their entry kept)
        self.ref_written = {}                               # name -> the bytes put under its fixed key this run
        self.refs = {}                                      # the `refs` index written into state.json (index_refs)
        self.refs_failed = []                               # reference files whose content copy failed (entry kept)

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
    def store(self, entry, family, ticker, name, body, sha, present=None, counted=True):
        """Upload a data file, pack, xsection or reference file under its content key unless its manifest entry
        (xsection, ref: its state.json index entry) already names these bytes. -> (key with v1/, uploaded). An object
        is never written with other bytes (ERRORS M250). `present` (xsection, ref: the keys a listing of the bucket
        holds) also puts an object its entry names but the bucket lacks again, with the same bytes, and does not put a
        key the bucket already holds. `counted` False keeps the upload out of files_written (reference files, which
        were never counted there)."""
        named = entry.get('key') if entry.get('sha256') == sha else None
        if named and (present is None or named[len(PREFIX) + 1:] in present):
            return named, False
        key = content_key(family, ticker, name, sha)
        if present is not None and key in present:
            return f'{PREFIX}/{key}', False
        self.bucket.put(key, body, 'application/gzip')
        if counted:
            self.written += 1
            self.bytes += len(body)
        return f'{PREFIX}/{key}', True

    def publish(self, dataset, ticker, year, stamp=None):
        if dataset == 'events':
            rows = event_rows(self.conn.execute(EVENTS_SQL, (ticker,)).fetchall())
        else:
            lo, hi = f'{year}-01-01', f'{year}-12-31'
            rows = self.conn.execute(PRICE_SQL if dataset == 'price' else BROKER_SQL, (ticker, lo, hi)).fetchall()
        files = self.manifest(ticker)['datasets'].setdefault(dataset, {'files': {}})['files']
        if not rows:
            if files.pop(str(year), None):
                self.changed.add((dataset, ticker, year))
            return None
        doc = (price_doc(ticker, year, rows) if dataset == 'price' else broker_doc(ticker, year, rows)
               if dataset == 'broker' else events_doc(ticker, rows))
        body, sha = encode(doc)
        key, uploaded = self.store(files.get(str(year), {}), dataset, ticker, year, body, sha)
        if uploaded:
            self.changed.add((dataset, ticker, year))
        files[str(year)] = {'key': key, 'sha256': sha, 'bytes': len(body), 'rows': len(rows),
                            'first': rows[0][0], 'last': rows[-1][0],
                            'stamp': stamp or f'rows={len(rows)};last={rows[-1][0]}'}
        return rows[-1][0]

    # ---- packs (EXEC-TERMINAL-SPEED) ---------------------------------------------------------------------------
    def put_pack(self, ticker, name, doc, rows, extra=None, encoded=None):
        packs = self.manifest(ticker).setdefault('packs', {})
        if not rows:
            if packs.pop(name, None):
                self.changed.add(('pack', ticker, name))
            return
        body, sha = encoded or encode(doc)
        key, uploaded = self.store(packs.get(name, {}), 'pack', ticker, name, body, sha)
        if uploaded:
            self.changed.add(('pack', ticker, name))
        packs[name] = {'key': key, 'sha256': sha, 'bytes': len(body), 'rows': len(rows),
                       'first': rows[0][0], 'last': rows[-1][0], **(extra or {})}

    def publish_packs(self, ticker, typ, force=False):
        """The price pack (every year) when a price year changed or it is missing; the broker archive (every year before
        the last two) when an archived year changed, it is missing, or the year rolled over."""
        packs = self.manifest(ticker).get('packs', {})
        mine = {(d, y) for d, t, y in self.changed if t == ticker}
        if force or 'price' not in packs or any(d == 'price' for d, _ in mine):
            rows = self.conn.execute(PRICE_SQL, (ticker, f'{self.price_first_year}-01-01', f'{self.last_year}-12-31')).fetchall()
            self.put_pack(ticker, 'price', price_pack_doc(ticker, rows), rows)
        if typ != 'stock':
            return
        hi = self.last_year - 2                                   # the last two years stay yearly files
        span = [self.broker_first_year, hi]
        current = packs.get('broker-archive', {})
        if force or not current or current.get('years') != span or any(d == 'broker' and isinstance(y, int) and y <= hi for d, y in mine):
            rows = self.conn.execute(BROKER_SQL, (ticker, f'{self.broker_first_year}-01-01', f'{hi}-12-31')).fetchall() if hi >= self.broker_first_year else []
            doc = {**broker_doc(ticker, None, rows), 'dataset': 'broker-archive', 'years': span}
            self.put_pack(ticker, 'broker-archive', doc, rows, {'years': span})

    # ---- cross-sectional files (EXEC-SCREENER, P1 a, user 2026-10-28; report 6.5) ------------------------------------
    def xsection_price(self, kind, touched):
        """The `price` file from one statement. Each ticker's slice is encoded as its price pack and compared with the
        manifest's pack sha256: a pack that differs (the table changed after the pack was built this run, or an older
        pack the stamps missed) is republished from the slice, and the ticker's manifest is saved with the others, so
        every slice equals its published pack. -> (document, rows, as_of, log fields)."""
        lo, hi = f'{self.price_first_year}-01-01', f'{self.last_year}-12-31'
        # per ticker one list per column, and one object per distinct date and price (volumes are nearly all distinct):
        # 1.32 M local rows peaked at 355 MB this way, 597 MB as row tuples, with the same bytes. 0 is kept as read.
        by, shared = {}, {}
        one = lambda x: shared.setdefault(x, x) if x else x
        for t, d, o, h, l, c, v in stream_rows(self.conn, XSECTION_PRICE_SQL, (lo, hi)):
            if t not in kind:
                continue
            cols = by.get(t)
            if cols is None:
                cols = by[t] = ([], [], [], [], [], [])
            cols[0].append(one(d)); cols[1].append(one(o)); cols[2].append(one(h))
            cols[3].append(one(l)); cols[4].append(one(c)); cols[5].append(v)
        shared.clear()
        columns = {c: [] for c in PRICE_XSECTION_COLUMNS}
        tickers, repaired = [], []
        for t in sorted(by):
            rows = sorted(zip(*by.pop(t)), key=lambda r: r[0])                     # PRICE_SQL's row order and shape
            body, sha = encode(price_pack_doc(t, rows))
            if self.manifest(t).get('packs', {}).get('price', {}).get('sha256') != sha:
                self.put_pack(t, 'price', None, rows, encoded=(body, sha))
                touched.add(t)
                repaired.append(t)
            columns['t'].extend([t] * len(rows))
            for i, c in enumerate(PRICE_XSECTION_COLUMNS[1:]):
                columns[c].extend([r[i] for r in rows])
            tickers.append({'t': t, 'pack_sha256': sha, 'first': rows[0][0], 'last': rows[-1][0], 'rows': len(rows)})
        as_of = max((e['last'] for e in tickers), default=None)
        return (xsection_price_doc(columns, tickers), len(columns['t']), as_of,
                {'tickers': len(tickers), 'packs_republished': len(repaired), 'republished': repaired[:20]})

    def xsection_actions(self, kind, events_through):
        """The `actions` file; as_of is the newest ingestion_time of idx_event_annotation (the events data_through)."""
        rows, outside = read_actions(self.conn, kind, self.price_first_year)
        return xsection_actions_doc(rows), len(rows), events_through, {'outside_universe': outside}

    def publish_xsection(self, name, kind, through, touched, previous, present):
        """Build one xsection file and store it under its content key (`store`, as every data file and pack: an object
        is never written with other bytes, ERRORS M250). -> its index entry."""
        started = time.monotonic()
        if name == 'price':
            doc, rows, as_of, info = self.xsection_price(kind, touched)
        else:
            doc, rows, as_of, info = self.xsection_actions(kind, through['events'])
        body, sha = encode(doc)
        del doc
        key, uploaded = self.store(previous.get(name, {}), 'xsection', None, name, body, sha, present)
        log('xsection', name=name, key=key, rows=rows, bytes=len(body), uploaded=uploaded, as_of=as_of,
            seconds=round(time.monotonic() - started, 1), **info)
        return {'key': key, 'sha256': sha, 'bytes': len(body), 'rows': rows, 'as_of': as_of}

    def present_keys(self, family, previous):
        """The keys under `<family>/` of an indexed family (xsection, ref; one listing of that prefix, taken after
        collect_garbage), or, when the bucket cannot list them, the keys of the previous index (`store` then trusts the
        index, as it trusts a manifest)."""
        try:
            return set(self.bucket.list(prefix=f'{family}/'))
        except Exception as e:  # noqa: BLE001 - the files are still written and indexed; the class only
            log(f'{family}_list_failed', error=type(e).__name__)
            return {x['key'][len(PREFIX) + 1:] for x in previous.values()}

    # ---- reference files and universe ------------------------------------------------------------------------
    def universe(self):
        return self.conn.execute(UNIVERSE_SQL).fetchall()

    def publish_refs(self, universe):
        # every column after ticker, name and type is a classification the backtest offers as a portfolio filter
        # (backtest CONTRACT.md, decision PF6; user 2026-10-27); readers take columns by name, so one can be added.
        # Values are stored as the table has them: 'Undefined' (no classification) is the readers' to set apart.
        names = ['ticker', 'name', 'type', 'sector', 'industry']
        tickers = {'schema_version': SCHEMA_VERSION, 'columns': names, **columnar(universe, names)}
        brokers = self.conn.execute('SELECT broker_code, broker_name, broker_type FROM public."IDX_Broker_Profile" '
                                    'ORDER BY 1').fetchall()
        brokers_doc = {'schema_version': SCHEMA_VERSION, 'columns': ['code', 'name', 'type'],
                       'type_means': 'broker domicile (label only; the Foreign figures use investor type)',
                       **columnar(brokers, ['code', 'name', 'type'])}
        for name, doc in (('tickers', tickers), ('brokers', brokers_doc)):
            body, _ = encode(doc)
            self.bucket.put(ref_key(name), body, 'application/gzip')
            self.ref_written[name] = body                       # its content-keyed copy: index_refs

    def index_refs(self, previous):
        """EXEC-MU-RUNTIME T5 (user chose option A, 2026-10-28): every reference file of REF_NAMES also under its content
        key `ref/<name>.<first 16 hex of sha256>.json.gz`, the exact bytes of its fixed-key copy: those put this run, or
        the fixed-key object as it stands (the logos, refreshed weekly). Stored through `store` as the xsection files
        are, against one listing of `ref/` taken after collect_garbage (a key the bucket holds is not put again; an
        indexed object it lacks is put again with the same bytes). Called after the fixed-key copies and before
        state.json, which carries the result as `refs`; collect_garbage deletes, in a later daily run, the content-keyed
        reference objects that index no longer names. A reference file that was never published (no logo run yet) has
        no entry; one whose copy fails keeps its previous entry (refs_failed: the run exits 3). -> the `refs` index."""
        present = self.present_keys('ref', previous)
        out, uploaded = {}, []
        for name in REF_NAMES:
            try:
                body = self.ref_written.get(name)
                if body is None:
                    body = self.bucket.get_raw(ref_key(name))
                if body is None:
                    continue
                doc = json.loads(gzip.decompress(body))
                rows = len(doc[doc['columns'][0]])                  # every reference file is columnar
                sha = hashlib.sha256(body).hexdigest()
                key, put = self.store(previous.get(name, {}), 'ref', None, name, body, sha, present, counted=False)
                out[name] = {'key': key, 'sha256': sha, 'bytes': len(body), 'rows': rows}
                if put:
                    uploaded.append(name)
            except Exception as e:  # noqa: BLE001 - the class only; the fixed-key copy stands, the previous entry stays
                self.refs_failed.append(name)
                if name in previous:
                    out[name] = previous[name]
                log('ref_failed', name=name, error=type(e).__name__, kept=previous.get(name, {}).get('key'))
        log('refs', names=sorted(out), uploaded=uploaded, failed=self.refs_failed)
        return out

    def logos_stale(self, now=None):
        index = self.bucket.get_json(ref_key('logos'))
        if not index or not index.get('generated_at'):
            return True
        age = (now or dt.datetime.now(dt.timezone.utc)) - dt.datetime.fromisoformat(index['generated_at'])
        return age > dt.timedelta(days=LOGO_MAX_AGE_DAYS)

    def publish_logos(self, universe):
        """Every ticker's logo; an image is uploaded only when its sha256 changed."""
        get = self.get
        old = self.bucket.get_json(ref_key('logos')) or {}
        known = dict(zip(old.get('ticker', []), zip(old.get('file', []), old.get('sha256', []))))
        logoids = tradingview_logoids(get)
        tickers = [t for t, *_ in universe]
        with ThreadPoolExecutor(8) as ex:
            found = list(ex.map(lambda t: (t, logo_image(t, logoids.get(t), get)), tickers))
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        rows, uploaded, sources = [], 0, {}
        for ticker, hit in found:
            if not hit:
                continue
            body, ext, source = hit
            sha, name = hashlib.sha256(body).hexdigest(), f'{ticker}.{ext}'
            if known.get(ticker) != (name, sha):
                self.bucket.put(f'logo/{name}', body, 'image/png' if ext == 'png' else 'image/svg+xml')
                uploaded += 1
            rows.append((ticker, name, sha, source, now))
            sources[source] = sources.get(source, 0) + 1
        doc = {'schema_version': SCHEMA_VERSION, 'columns': ['ticker', 'file', 'sha256', 'source', 'fetched_at'],
               **columnar(rows, ['ticker', 'file', 'sha256', 'source', 'fetched_at']), 'generated_at': now}
        body, _ = encode(doc)
        self.bucket.put(ref_key('logos'), body, 'application/gzip')
        self.ref_written['logos'] = body                            # its content-keyed copy: index_refs
        log('logos', tickers=len(tickers), with_logo=len(rows), uploaded=uploaded, sources=sources,
            tradingview_logoids=len(logoids), without=[t for t, hit in found if not hit][:40])

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
        kind = {t: typ for t, _, typ, *_ in universe}
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
        elif mode in ('logos', 'packs'):
            todo = []
        elif mode == 'broker-range':
            tickers = only or [t for t, typ in kind.items() if typ == 'stock']
            lo, hi = int(start_from[:4]), int(end_to[:4])
            todo = [('broker', t, y, None) for t in tickers if kind.get(t) == 'stock'
                    for y in range(max(lo, self.broker_first_year), hi + 1)]
        else:
            raise SystemExit(f'unknown mode {mode}')
        log('plan', mode=mode, files=len(todo), window=[self.first_year, self.last_year],
            price_first_year=self.price_first_year, broker_first_year=self.broker_first_year, data_through=through)
        previous = xsection_entries(state.get('xsection'))        # the index terminal-api serves (EXEC-SCREENER)
        previous_refs = ref_entries(state.get('refs'))            # EXEC-MU-RUNTIME T5
        if mode == 'daily':                                       # before the first write of this run (ERRORS M250)
            self.collect_garbage({'xsection': previous, 'ref': previous_refs})
        touched = set()
        for n, (dataset, ticker, year, stamp) in enumerate(todo, 1):
            self.publish(dataset, ticker, year, stamp)
            touched.add(ticker)
            if n % 500 == 0:
                log('progress', done=n, of=len(todo), written=self.written, mb=round(self.bytes / 1e6, 1))
        # packs: every ticker in mode packs (or a ticker without them yet), else the tickers whose files changed
        pack_tickers = list(kind) if mode in ('packs', 'backfill') else sorted({t for _, t, _ in self.changed})
        for n, ticker in enumerate(pack_tickers, 1):
            self.publish_packs(ticker, kind.get(ticker), force=mode == 'backfill')
            touched.add(ticker)
            if n % 200 == 0:
                log('progress', step='packs', done=n, of=len(pack_tickers), written=self.written, mb=round(self.bytes / 1e6, 1))
        # EXEC-SCREENER: the xsection files after the files and packs (a pack the price file finds stale is republished
        # here, so its manifest is saved below) and before state.json, which indexes them. A file whose rebuild fails
        # keeps its previous entry; the Terminal's and the Backtest's publication goes on.
        self.xsection, self.xsection_failed = dict(previous), []
        rebuilt = [name for name, modes in XSECTION_REBUILT_BY.items() if mode in modes]
        # a key the bucket holds is not put again; an indexed object the listing lacks (deleted by hand) is put again,
        # the same bytes. The listing comes after collect_garbage, so it never names an object this run deleted.
        present = self.present_keys('xsection', previous) if rebuilt else None
        for name in rebuilt:
            try:
                self.xsection[name] = self.publish_xsection(name, kind, through, touched, previous, present)
            except Exception as e:  # noqa: BLE001 - the class only: a driver error may carry connection details
                self.xsection_failed.append(name)
                log('xsection_failed', name=name, error=type(e).__name__, kept=self.xsection.get(name, {}).get('key'))
        for ticker in sorted(touched):
            datasets = {'price': through['price']}
            if kind.get(ticker) == 'stock':
                datasets['broker'] = through['broker']
            if self.manifest(ticker)['datasets'].get('events', {}).get('files'):
                datasets['events'] = through['events']
            self.save_manifest(ticker, datasets)
        self.publish_refs(universe)
        if mode == 'logos' or (mode == 'daily' and self.logos_stale()):
            self.publish_logos(universe)
        # EXEC-MU-RUNTIME T5: the reference files' content-keyed copies, after their fixed-key copies and before the
        # state.json that indexes them (every mode: the ticker and broker lists are rewritten by every run)
        self.refs = self.index_refs(previous_refs)
        broker_through = through['broker'] if mode in ('backfill', 'daily') else state.get('broker_through')
        self.broker_behind = self.conn.execute(BEHIND_SQL, (through['broker'],)).fetchone()[0] if through['broker'] else None
        self.bucket.put('state.json', json.dumps({
            'schema_version': SCHEMA_VERSION, 'price_through': through['price'], 'broker_through': broker_through,
            'broker_behind_sessions': self.broker_behind,
            'window': [self.first_year, self.last_year], 'price_first_year': self.price_first_year,
            'broker_first_year': self.broker_first_year, 'last_mode': mode, 'xsection': self.xsection,
            'refs': self.refs, 'finished_at': dt.datetime.now(dt.timezone.utc).isoformat()}).encode(), 'application/json')
        log('done', mode=mode, files_planned=len(todo), files_written=self.written, mb=round(self.bytes / 1e6, 2),
            tickers=len(touched), seconds=round(time.monotonic() - started, 1), broker_behind_sessions=self.broker_behind,
            xsection=sorted(self.xsection), xsection_failed=self.xsection_failed, refs=sorted(self.refs),
            refs_failed=self.refs_failed)

    def collect_garbage(self, indexes=None):
        """ERRORS M250 (user 2026-10-27, option A of 3): delete the data files and packs no manifest names any more, and
        the files of an indexed family (INDEXED: xsection, EXEC-SCREENER; ref, EXEC-MU-RUNTIME T5) their state.json
        index no longer names (that index is their manifest), once no reader can still use them. It runs in a daily run
        before the run writes anything, so the manifests and the indexes it reads are the ones terminal-api serves (its
        cache follows state.json finished_at, bucket.py _fresh). An object is deleted only when all of these hold:
          - its key is <family>/<ticker>/<file>, the family being one that the manifests name (derived from them, so a
            new dataset is covered), and the ticker has a manifest that names at least one file but not this one;
            or its key is an object of an indexed family (its pattern: `xsection/<name>.<16 hex>.json.gz`,
            `ref/<name>.<16 hex>.json.gz`; nothing else under xsection/ or ref/, so the fixed-key reference files never
            match) and that family's state.json index names at least one file but not this one (`indexes`: {family:
            that index as its entries reader keeps it}, read from the bucket's state.json when not given; terminal-api
            presigns only what it names; a state.json without an index of the family, from a publisher before its
            writer or a rollback to one, deletes none of that family);
          - that manifest and the object were written no later than state.json, the last finished run: a manifest
            written after it comes from a run that did not finish, and terminal-api may still serve the one before it;
            an object written after it may belong to such a run;
          - the last finished run ended at least GC_GRACE_SECONDS ago.
        A listing longer than GC_LIST_SECONDS is abandoned and nothing is deleted.
        Manifests, the fixed-key reference files, logos and state.json are never deleted. A failure is logged; the run
        goes on."""
        try:
            started = time.monotonic()
            listing = self.bucket.list(deadline=started + GC_LIST_SECONDS)
            finished = (listing.get('state.json') or (None,))[0]
            if finished is None:
                log('gc_skipped', reason='no finished run (state.json)'); return 0
            age = (self.clock() - finished).total_seconds()
            if age < GC_GRACE_SECONDS:
                log('gc_skipped', reason='the last run finished too recently', seconds=round(age), grace=GC_GRACE_SECONDS)
                return 0
            named, skipped = {}, 0
            for key, (at, _) in listing.items():
                if not (key.startswith('manifest/') and key.endswith('.json')):
                    continue
                ticker = key[len('manifest/'):-len('.json')]
                keys = named_keys(self.manifests.get(ticker) or self.bucket.get_json(key))
                if not keys or at > finished:
                    skipped += 1                                  # unread, empty, or written by a run that did not finish
                    continue
                named[ticker] = keys
            families = {k.split('/', 1)[0] for keys in named.values() for k in keys}
            if indexes is None:
                state = self.bucket.get_json('state.json') or {}
                indexes = {family: read(state.get(field)) for family, (field, _, read) in INDEXED.items()}
            indexed = {family: {e['key'][len(PREFIX) + 1:] for e in (indexes.get(family) or {}).values()}
                       for family in INDEXED}
            doomed, freed, newer = [], 0, 0
            for key, (at, size) in listing.items():
                parts = key.split('/')
                if parts[0] in INDEXED and INDEXED[parts[0]][1].fullmatch(key):
                    if not indexed[parts[0]] or key in indexed[parts[0]]:
                        continue
                elif len(parts) != 3 or parts[0] not in families or parts[1] not in named or key in named[parts[1]]:
                    continue
                if at > finished:
                    newer += 1
                    continue
                doomed.append(key)
                freed += size
            failed = self.bucket.delete(sorted(doomed)) if doomed else []
            log('gc', deleted=len(doomed) - len(failed), not_deleted=len(failed), mb=round(freed / 1e6, 1),
                kept_newer_than_last_run=newer, tickers_skipped=skipped, families=sorted(families),
                xsection_named=len(indexed['xsection']), refs_named=len(indexed['ref']), objects_listed=len(listing),
                last_run_finished=finished,
                seconds=round(time.monotonic() - started, 1))
            return len(doomed) - len(failed)
        except Exception as e:  # noqa: BLE001 - the cleanup never stops a publication; the class only, no detail
            log('gc_failed', error=type(e).__name__)
            return 0

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
    pack_sha = {}                                           # ticker -> its price pack's sha256 (verify_xsection)
    for ticker, _, typ, *_ in universe:
        m = bucket.get_json(f'manifest/{ticker}.json')
        if not m:
            log('verify_missing_manifest', ticker=ticker)
            bad += 1
            continue
        pack_sha[ticker] = m.get('packs', {}).get('price', {}).get('sha256')
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
    x_checked, x_bad = verify_xsection(conn, bucket, {t: typ for t, _, typ, *_ in universe}, pack_sha)
    r_checked, r_bad = verify_refs(bucket)
    checked, bad = checked + x_checked + r_checked, bad + x_bad + r_bad
    log('verify_done', files=checked, mismatches=bad, window=[first_year, last_year])
    return bad


def verify_refs(bucket):
    """EXEC-MU-RUNTIME T5: the files of state.json's `refs` index. Each: present, its bytes and sha256 as indexed, its
    rows as indexed, and byte for byte its fixed-key copy (both are written in the same run, before state.json; a
    verify during a run can see the fixed copy of the next publication). -> (files checked, mismatches)."""
    checked = bad = 0
    for name, e in sorted(ref_entries((bucket.get_json('state.json') or {}).get('refs')).items()):
        body = bucket.get_raw(e['key'][len(PREFIX) + 1:])
        checked += 1
        problems = []
        if body is None or len(body) != e['bytes'] or hashlib.sha256(body).hexdigest() != e['sha256']:
            problems.append('not the indexed bytes')
        else:
            try:
                doc = json.loads(gzip.decompress(body))
                rows = len(doc[doc['columns'][0]])
            except (OSError, ValueError, KeyError, IndexError, TypeError):
                rows = None
            if rows != e['rows']:
                problems.append('rows differ from the index' if rows is not None else 'not a columnar file')
            if bucket.get_raw(ref_key(name)) != body:
                problems.append('differs from the fixed-key copy')
        if problems:
            bad += 1
            log('verify_mismatch', dataset='ref', name=name, key=e['key'], problems=problems)
    return checked, bad


def verify_xsection(conn, bucket, kind, pack_sha):
    """EXEC-SCREENER: the files of state.json's xsection index. Each: present, its bytes and sha256 as indexed, its rows
    as indexed. price: every ticker's slice encodes to its published price pack (manifest `packs`) and has the rows,
    first and last date and sum of closes of SQL, and no published ticker with rows is missing; actions: the rows SQL
    gives now. -> (files checked, mismatches)."""
    state = bucket.get_json('state.json') or {}
    checked = bad = 0
    for name, e in sorted(xsection_entries(state.get('xsection')).items()):
        body = bucket.get_raw(e['key'][len(PREFIX) + 1:])
        checked += 1
        if body is None or len(body) != e['bytes'] or hashlib.sha256(body).hexdigest() != e['sha256']:
            bad += 1
            log('verify_bad_object', dataset='xsection', name=name, key=e['key'])
            continue
        doc = json.loads(gzip.decompress(body))
        problems = [] if len(doc[doc['columns'][0]]) == e['rows'] else ['rows differ from the index']
        if name == 'price':
            lo, hi = f"{state['price_first_year']}-01-01", f"{state['window'][1]}-12-31"
            sql = {t: (n, a, b, s) for t, n, a, b, s in conn.execute(XSECTION_PRICE_CHECK_SQL, (lo, hi)).fetchall()
                   if t in kind}
            seen = set()
            for (t, rows), entry in zip(xsection_slices(doc), doc['tickers']):
                seen.add(t)
                sha = encode(price_pack_doc(t, rows))[1]
                if not (sha == entry['pack_sha256'] == pack_sha.get(t)):
                    problems.append(f'{t}: the slice is not its price pack')
                n, a, b, s = sql.get(t, (0, None, None, 0.0))
                got = (len(rows), rows[0][0] if rows else None, rows[-1][0] if rows else None, sum(r[4] for r in rows))
                if got[:3] != (n, a, b) or abs(got[3] - s) > max(1.0, abs(s) * 1e-9):
                    problems.append(f'{t}: rows {got} but SQL {(n, a, b, s)}')
            problems += [f'{t}: in SQL, not in the file' for t in sorted(set(sql) - seen)]
        elif name == 'actions':
            rows, _ = read_actions(conn, kind, state['price_first_year'])
            if columnar(rows, ACTION_COLUMNS) != {c: doc[c] for c in ACTION_COLUMNS}:
                problems.append('the rows differ from SQL')
        if problems:
            bad += 1
            log('verify_mismatch', dataset='xsection', name=name, problems=problems[:20], count=len(problems))
    return checked, bad


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


def near_time(times, now=None, slack_minutes=20):
    """True when `now` (WIB) is at most slack_minutes after one of the listed WIB times."""
    now = (now or dt.datetime.now(dt.timezone.utc)).astimezone(WIB)
    mins = now.hour * 60 + now.minute
    return any(0 <= (mins - (h * 60 + m)) % 1440 <= slack_minutes for h, m in times)


def notify_broker_behind(run_day):
    """EXEC-TERMINAL-FRESH (user 2026-10-27: "peringatan Telegram kalau broker masih tertinggal setelah putaran 19:00
    WIB"): ask telegram-monitor once per day; it reads the gap from the tables itself and sends only when one exists."""
    url, secret = os.environ.get('TELEGRAM_NOTIFY_URL', '').strip(), os.environ.get('TELEGRAM_NOTIFY_SECRET', '').strip()
    if not url or not secret:
        log('broker_behind_notify_skipped', reason='not_configured'); return
    body = json.dumps({'source_table': 'Terminal_Broker_Freshness', 'execution_id': f'terminal-{run_day}'}).encode()
    for attempt in range(1, 4):
        try:
            req = urllib.request.Request(url, data=body, method='POST',
                                         headers={'Content-Type': 'application/json', 'X-Notify-Secret': secret})
            with urllib.request.urlopen(req, timeout=20) as resp:
                log('broker_behind_notify', status=json.loads(resp.read() or b'{}').get('status'), attempt=attempt); return
        except Exception as e:                                   # the URL and secret are never printed
            log('broker_behind_notify_failed', attempt=attempt, error=type(e).__name__)
            time.sleep(2 ** attempt)


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
        started = dt.datetime.now(dt.timezone.utc)
        pub = Publisher(conn, bucket)
        pub.run(mode, os.environ.get('TERMINAL_FROM'), os.environ.get('TERMINAL_TO'), only)
    # the evening run (TERMINAL_STALE_ALERT_WIB, default 19:00) warns when broker data lags the prices
    if mode == 'daily' and (pub.broker_behind or 0) >= 1 and near_time(run_times(os.environ.get('TERMINAL_STALE_ALERT_WIB', '19:00')), started):
        notify_broker_behind(started.astimezone(WIB).date().isoformat())
    # EXEC-SCREENER: a failed xsection file fails the run visibly once everything else is published (exit 3); so does a
    # reference file whose content-keyed copy failed (EXEC-MU-RUNTIME T5; its fixed-key copy was written)
    return 3 if pub.xsection_failed or pub.refs_failed else 0


if __name__ == '__main__':
    try:
        sys.exit(main(sys.argv))
    except psycopg.Error as e:
        # Driver errors may include connection details; print the class only.
        log('failed', error=type(e).__name__)
        sys.exit(2)
