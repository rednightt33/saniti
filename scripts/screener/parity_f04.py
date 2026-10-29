"""Feature 04 / Feature 01 parity of the EDGE Screener (EXEC-SCREENER; report DATABASE / FEATURE CHANGES 7.3 "Feature 04
as parity oracle", TEST PLAN 10b.1 and 10b.2). Read-only.

What it proves, for every equity ticker with a bar on the common date:
- snapshot path: the screener core's values (apps/edge-bff/screener/src/core metrics.ts series, the 53 indicators
  pre-warmed at their start parameters as the worker's snapshot does) equal Feature 04's stored registry-default columns
  (sma_20, macd, macd_signal, macd_histogram, rsi_14, bb_upper_20, bb_middle_20, bb_lower_20, atr_14, adx_14) and the
  derived ones (%B, bandwidth, NATR, stddev, PPO line; denominators in NULLIF): relative difference <= 1e-12 and
  identical nulls; each read hits the pre-warmed key (source precomputed, is_default true);
- dynamic path: the configurations Feature 04 stores at non-default parameters (sma_50; ema_12, ema_26, ema_50,
  ema_200) computed for the request through an empty cache (source dynamic, is_default false), same tolerance;
- Feature 01: I35 and I37 (default) and I17 at 5, 20 and 60 sessions (dynamic) equal volume_avg_20d, volume_ratio_20d
  and return_{5,20,60}d_pct within 1e-9 relative; I33 is asserted DIFFERENT from volatility_20d_ann_pct (sample stdev
  of simple returns against F's population stdev of log returns, report 7.3);
- the flat-window tickers (BNBR, BABP, BCAP) are listed on their own;
- self-check: the same comparison with one bar of one ticker perturbed (+1% on O, H, L, C three bars before the date)
  must fail, so a comparison that cannot fail is caught.
The oracle mapping is read from apps/edge-bff/screener/src/core/screener-registry.json indicators[].oracle (generated
from scripts/terminal_indicator_spec.py --json), never typed here.

Data: Feature 04, Feature 01 and the price rows (public."Price_Stock_Indonesia_IDX", final daily, the rows the
publisher packs into the rack with the same filter, decoded by the backtest core's datafile.priceSeries) are read through
the pgweb service (role pgweb, default_transaction_read_only=on), in bounded statements (one date; prices one half-year
per statement), the pattern of verification/terminal_api/pgq.py: the pgweb credentials come from Railway into memory and
a 0600 cache outside the repository and are never printed. --prices FILE reads the price rows from a file of the same
columnar shape instead ({ticker: {d, o, h, l, c, v}}).

Run (repository root): python3 -I scripts/screener/parity_f04.py [--date YYYY-MM-DD] [--prices FILE] [--write]
--write records the result in verification/screener/F04_PARITY.md. Exit status 0 only when every check passes.
Needs node 22 (type stripping) for the screener core. """
import argparse, base64, json, math, os, re, shutil, statistics, subprocess, sys, tempfile, time, urllib.error, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REGISTRY = os.path.join(ROOT, 'apps/edge-bff/screener/src/core/screener-registry.json')
CORE = os.path.join(ROOT, 'scripts/screener/parity_f04_core.mjs')
LOADER = os.path.join(ROOT, 'apps/backtest-worker/loader/register.mjs')
RECORD = os.path.join(ROOT, 'verification/screener/F04_PARITY.md')
F04, F01, PRICE = 'Feature_04_Technical_Indicator', 'Feature_01_Stock_Daily', 'Price_Stock_Indonesia_IDX'
TOL = {F04: 1e-12, F01: 1e-9}
FLAT = ('BNBR', 'BABP', 'BCAP')
SAFE_EXPR = re.compile(r'^[A-Za-z0-9_+\-*/(), .]+$')

# ---- pgweb (verification/terminal_api/pgq.py pattern; secrets stay in memory and the 0600 cache) -------------------
CACHE = os.path.expanduser('~/.pgweb_auth')
def auth():
    if os.path.exists(CACHE):
        return json.load(open(CACHE))
    env = dict(os.environ, RAILWAY_TOKEN=os.environ['RAILWAY_TOKEN'])     # the Railway project token; never committed
    out = subprocess.run(['railway', 'variables', '--service', 'pgweb', '--environment', '4d3e5af2-302b-4a2e-84e2-7d7476d6ff49', '--json'],
                         capture_output=True, text=True, env=env, check=True).stdout
    v = json.loads(out)
    a = {'u': v['PGWEB_AUTH_USER'], 'p': v['PGWEB_AUTH_PASS'], 'd': v['RAILWAY_PUBLIC_DOMAIN']}
    fd = os.open(CACHE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600); os.write(fd, json.dumps(a).encode()); os.close(fd)
    return a
def q(sql):
    a = auth()
    req = urllib.request.Request(f"https://{a['d']}/api/query", data=urllib.parse.urlencode({'query': sql}).encode(), method='POST')
    req.add_header('Authorization', 'Basic ' + base64.b64encode(f"{a['u']}:{a['p']}".encode()).decode())
    req.add_header('User-Agent', 'curl/8.5.0')                            # the proxy refuses Python's default agent
    t = time.time()
    try:
        r = json.loads(urllib.request.urlopen(req, timeout=300).read())
    except urllib.error.HTTPError as e:
        raise SystemExit(f'pgweb answered HTTP {e.code}: {e.read().decode()[:500]}')
    if 'error' in r:
        raise SystemExit(f"pgweb refused the statement: {str(r['error'])[:500]}")
    r['_ms'] = round((time.time() - t) * 1000)
    return [dict(zip(r['columns'], row)) for row in r.get('rows', [])], r['_ms']
def iso(x):
    return x[:10] if isinstance(x, str) else str(x)[:10]

# ---- the oracle -----------------------------------------------------------------------------------------------------
def oracle():
    reg = json.load(open(REGISTRY))
    rows = []
    for ind in reg['indicators']:
        for o in ind['oracle']:
            if 'expr' in o and not SAFE_EXPR.match(o['expr']):
                raise SystemExit(f"{ind['id']}: unexpected characters in the oracle expression {o['expr']!r}")
            rows.append({'id': ind['id'], **o})
    return reg, rows
def label(o):
    return o.get('column') or o['expr']
def rel(x, y):
    m = max(abs(x), abs(y))
    return 0.0 if m == 0 else abs(x - y) / m

def compare(rows, ours, theirs, table):
    """Per oracle row of `table`: n compared, nulls that disagree, max relative difference and its ticker."""
    out = []
    for o, mine in zip(rows, ours):
        if o['table'] != table: continue
        key = f"{o['id']}.{o['output']} {json.dumps(o['params'], separators=(',', ':'))}"
        st = {'oracle': label(o), 'reference': key, 'n': 0, 'null_mismatch': 0, 'max_rel': 0.0, 'worst': None, 'sources': mine['sources'],
              'is_default': mine['is_default'], 'flat': {}}
        col = o.get('column') or f"x_{o['id']}_{o['output']}"
        for t, row in theirs.items():
            if t not in mine['values']: continue
            x, y = mine['values'][t], row.get(col)
            y = None if y is None or (isinstance(y, float) and math.isnan(y)) else float(y)
            if (x is None) != (y is None):
                st['null_mismatch'] += 1; st.setdefault('null_tickers', []).append(t); continue
            if x is None: continue
            st['n'] += 1
            d = rel(x, y)
            if t in FLAT: st['flat'][t] = d
            if d > st['max_rel']: st['max_rel'], st['worst'] = d, t
        st['ok'] = st['n'] > 0 and st['null_mismatch'] == 0 and st['max_rel'] <= TOL[table]
        out.append(st)
    return out

def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--date', help='the common date (default: the latest Feature 04 equity date)')
    ap.add_argument('--prices', help='price rows from this file instead of pgweb')
    ap.add_argument('--write', action='store_true', help=f'record the result in {os.path.relpath(RECORD, ROOT)}')
    args = ap.parse_args()
    reg, rows = oracle()
    started = time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())
    log = []
    if args.date:
        d04 = args.date
    else:
        r, ms = q(f"""SELECT max(trade_date)::text d FROM public."{F04}" WHERE asset_type = 'equity' AND timeframe = 'Daily' AND trade_date >= CURRENT_DATE - 14""")
        d04 = iso(r[0]['d']); log.append(f'latest Feature 04 equity date {d04} ({ms} ms)')
    cols04 = sorted({o['column'] for o in rows if o['table'] == F04 and o.get('column')})
    exprs = [f"{o['expr']} AS \"x_{o['id']}_{o['output']}\"" for o in rows if o['table'] == F04 and o.get('expr')]   # quoted: case kept
    r04, ms = q(f"""SELECT ticker, calculation_version, {', '.join(cols04 + exprs)} FROM public."{F04}"
                    WHERE asset_type = 'equity' AND timeframe = 'Daily' AND trade_date = DATE '{d04}'""")
    f04 = {x['ticker']: x for x in r04}; log.append(f'Feature 04 rows at {d04}: {len(f04)} ({ms} ms)')
    versions04 = sorted({x['calculation_version'] for x in r04})
    r, ms = q(f"""SELECT max(date)::text d FROM public."{F01}" WHERE date BETWEEN DATE '{d04}' - 14 AND DATE '{d04}'""")
    d01 = iso(r[0]['d'])
    cols01 = sorted({o['column'] for o in rows if o['table'] == F01} | {'volatility_20d_ann_pct'})
    r01, ms = q(f"""SELECT ticker, {', '.join(cols01)} FROM public."{F01}" WHERE date = DATE '{d01}'""")
    f01 = {x['ticker']: x for x in r01}; log.append(f'Feature 01 rows at {d01}: {len(f01)} ({ms} ms)')

    work = tempfile.mkdtemp(prefix='parity_f04_')
    price_file = os.path.join(work, 'prices.json')
    if args.prices:
        price_file = args.prices; log.append(f'prices from {args.prices}')
    else:
        per, total, t0 = {}, 0, time.time()
        last = max(d04, d01)
        for y in range(2018, int(last[:4]) + 1):
            for a, b in ((f'{y}-01-01', f'{y}-07-01'), (f'{y}-07-01', f'{y + 1}-01-01')):
                if a > last: continue
                rr, ms = q(f"""SELECT ticker, date::text d, open::float8 o, high::float8 h, low::float8 l, close::float8 c, volume::float8 v
                               FROM public."{PRICE}" WHERE timeframe = 'Daily' AND is_final AND date >= DATE '{a}' AND date < DATE '{b}' AND date <= DATE '{last}'""")
                for x in rr:
                    s = per.setdefault(x['ticker'], {'d': [], 'o': [], 'h': [], 'l': [], 'c': [], 'v': []})
                    for k in 'dohlcv': s[k].append(iso(x[k]) if k == 'd' else x[k])
                total += len(rr)
        for s in per.values():                                                 # oldest first (each statement is unordered)
            order = sorted(range(len(s['d'])), key=s['d'].__getitem__)
            for k in 'dohlcv': s[k] = [s[k][i] for i in order]
        json.dump(per, open(price_file, 'w'), separators=(',', ':'))
        log.append(f'price rows through {last}: {total} of {len(per)} tickers, {round(time.time() - t0, 1)} s (read-only, half-year statements)')
    flat_note = [t for t in FLAT if t in f04]
    perturb_ticker = 'BBCA' if 'BBCA' in f04 else sorted(f04)[0]
    must_differ = [{'id': 'I33', 'output': 'historical_volatility', 'params': {'length': 20, 'source': 'close', 'return_type': 'log', 'annualization_periods': 252},
                    'table': F01, 'column': 'volatility_20d_ann_pct'}]
    job = {'prices': price_file, 'must_differ': must_differ, 'runs': {
        'f04': {'date': d04, 'tickers': sorted(f04)},
        'f01': {'date': d01, 'tickers': sorted(f01)},
        'perturbed': {'date': d04, 'tickers': [perturb_ticker], 'perturb': {'ticker': perturb_ticker, 'bar_offset': 3, 'factor': 1.01}},
    }}
    job_file = os.path.join(work, 'job.json'); json.dump(job, open(job_file, 'w'))
    t0 = time.time()
    p = subprocess.run(['node', '--experimental-strip-types', '--no-warnings=ExperimentalWarning', '--import', LOADER, CORE, job_file],
                       capture_output=True, text=True, cwd=ROOT)
    if p.returncode != 0:
        raise SystemExit(f'the screener core run failed: {p.stderr[-2000:]}')
    core = json.loads(p.stdout); log.append(f'screener core: {round(time.time() - t0, 1)} s')
    shutil.rmtree(work, ignore_errors=True)                                 # the pulled rows are not kept
    runs = core['runs']
    all_rows = rows + must_differ
    res04 = compare(all_rows, runs['f04']['rows'], f04, F04)
    res01 = [s for s in compare(all_rows, runs['f01']['rows'], f01, F01) if s['oracle'] != 'volatility_20d_ann_pct']
    # I33 must differ: the median relative difference is far above the tolerance
    i33 = next(x for x in runs['f01']['rows'] if x['must_differ'])
    diffs = [rel(v, float(f01[t]['volatility_20d_ann_pct'])) for t, v in i33['values'].items() if v is not None and t in f01 and f01[t]['volatility_20d_ann_pct'] is not None]
    i33_ok = len(diffs) > 0 and statistics.median(diffs) > 1e-3
    # source and default flags: registry-default rows hit the snapshot, the others are dynamic
    flags_ok = all((s['is_default'] and s['sources'] == ['precomputed']) or (not s['is_default'] and s['sources'] == ['dynamic']) for s in res04 + res01)
    # self-check: the perturbed ticker must fail
    pert = runs['perturbed']['rows']
    pert_fail = any(not s['ok'] for s in compare(all_rows, pert, {perturb_ticker: f04[perturb_ticker]}, F04) if s['oracle'] in ('sma_20', 'bb_middle_20', 'ema_12'))
    ok = all(s['ok'] for s in res04 + res01) and i33_ok and flags_ok and pert_fail
    summary = {'ok': ok, 'date_f04': d04, 'date_f01': d01, 'f04_rows': len(f04), 'f01_rows': len(f01), 'tickers_f04': runs['f04']['tickers'],
               'tickers_f01': runs['f01']['tickers'], 'feature04_versions': versions04, 'registry_version': core['registry_version'],
               'screener_registry_version': core['screener_registry_version'], 'i33_median_rel': statistics.median(diffs) if diffs else None,
               'i33_n': len(diffs), 'flags_ok': flags_ok, 'perturbed_ticker': perturb_ticker, 'perturbed_fails': pert_fail,
               'prewarm_ms': runs['f04']['prewarm_ms'], 'core_ms': runs['f04']['ms']}
    for s in res04 + res01:
        print(f"{'ok  ' if s['ok'] else 'FAIL'} {s['oracle']:<55} n={s['n']:<4} nulls={s['null_mismatch']:<3} max_rel={s['max_rel']:.3g} ({s['worst']}) {s['sources']} default={s['is_default']}")
    print(json.dumps(summary, indent=1))
    for line in log: print('#', line)
    if args.write:
        write_record(summary, res04, res01, log, started, flat_note)
    sys.exit(0 if ok else 1)

def write_record(s, res04, res01, log, started, flat):
    def table(res, tol):
        lines = ['| Oracle column | Screener reference | Path | n | Null mismatches | Max relative difference (ticker) | Within ' + tol + ' |', '|---|---|---|---|---|---|---|']
        for x in res:
            path = 'snapshot (precomputed, default)' if x['is_default'] else 'dynamic (empty cache, not default)'
            lines.append(f"| `{x['oracle']}` | `{x['reference']}` | {path} | {x['n']} | {x['null_mismatch']} | {x['max_rel']:.3g} ({x['worst'] or '-'}) | {'yes' if x['ok'] else '**no**'} |")
        return '\n'.join(lines)
    flat_rows = ['| Ticker | ' + ' | '.join(f'`{x["oracle"]}`' for x in res04) + ' |', '|---|' + '---|' * len(res04)]
    for t in flat:
        flat_rows.append(f'| {t} | ' + ' | '.join(f"{x['flat'].get(t, float('nan')):.3g}" for x in res04) + ' |')
    text = f"""# Feature 04 parity of the EDGE Screener (pinned record)

Generated by `python3 -I scripts/screener/parity_f04.py --write` (EXEC-SCREENER; report DATABASE / FEATURE CHANGES 7.3,
TEST PLAN 10b.1 and 10b.2). Run {started}. Read-only: Feature 04, Feature 01 and the final daily price rows were read
through pgweb (role pgweb, read-only) in bounded statements; nothing was written. A change to `registry_version` or to
the Feature 04 calculation version below requires a re-run (TEST PLAN 10b.10 "Parity record").

**Result: {'PASS' if s['ok'] else 'FAIL'}.**

| Item | Value |
|---|---|
| Common date (Feature 04) | {s['date_f04']} ({s['f04_rows']} equity rows; {s['tickers_f04']} compared tickers have a bar on it) |
| Feature 01 date | {s['date_f01']} ({s['f01_rows']} rows; {s['tickers_f01']} compared tickers) |
| Feature 04 calculation_version | {', '.join('`' + v + '`' for v in s['feature04_versions'])} |
| registry_version (backtest-registry.json) | `{s['registry_version']}` |
| screener_registry_version | `{s['screener_registry_version']}` |
| Snapshot pre-warm (53 indicators, 76 outputs, at start parameters) | {s['prewarm_ms']} ms for {s['tickers_f04']} tickers on one thread (local, not dev) |
| Sources and default flags | {'every registry-default row hit the pre-warmed snapshot (precomputed, is_default true); every other row was computed for the request (dynamic, is_default false)' if s['flags_ok'] else '**a row reported the wrong source or default flag**'} |
| I33 vs `volatility_20d_ann_pct` (must differ) | median relative difference {s['i33_median_rel']:.3g} over {s['i33_n']} tickers: {'different, as documented' if s['i33_median_rel'] and s['i33_median_rel'] > 1e-3 else '**not different**'} (sample stdev of simple returns vs F's population stdev of log returns) |
| Self-check | {s['perturbed_ticker']} with one bar perturbed (+1% on O, H, L, C three bars before the date): the comparison {'fails, as it must' if s['perturbed_fails'] else '**does not fail**'} |

## Snapshot and dynamic paths vs Feature 04 (relative difference <= 1e-12, identical nulls)

{table(res04, '1e-12')}

## Feature 01 (relative difference <= 1e-9, identical nulls)

{table(res01, '1e-9')}

## Flat-window tickers (relative difference per column)

{chr(10).join(flat_rows) if flat else 'None of BNBR, BABP, BCAP has a Feature 04 row on the date.'}

## How the values were obtained

- Bars: the final daily rows of `Price_Stock_Indonesia_IDX` with the publisher's own filter (`timeframe = 'Daily' AND
  is_final`, from the first price year; `apps/terminal-publisher/publisher.py` PRICE_SQL), the rows it packs into the
  rack, read through pgweb (this script has no terminal-api access to read the rack files themselves).
- Screener side: `scripts/screener/parity_f04_core.mjs` runs the screener core (`apps/edge-bff/screener/src/core/metrics.ts`
  `series`, the backtest core's `Calc` over the Terminal's `F`) on each ticker's bars decoded by `datafile.priceSeries`
  and cut at the date: the 53 indicators are pre-warmed at `registry.ts startParams` into a pinned cache (the worker's
  snapshot), each oracle row is then read with its explicit parameters; rows at non-default parameters are read through
  an empty cache with pre-warm off.
- Oracle side: the oracle rows of `screener-registry.json` (`indicators[].oracle`, generated from
  `scripts/terminal_indicator_spec.py --json`); the derived columns are the registry's SQL expressions, evaluated by
  PostgreSQL on the stored columns.
- Log: {'; '.join(log)}.
"""
    open(RECORD, 'w').write(text)
    print(f'wrote {os.path.relpath(RECORD, ROOT)}')

if __name__ == '__main__':
    main()
