"""Backtest flow conditions: are the broker files the worker reads (terminal-api /bundle with packs, the same path and
identity as the worker) equal to Feature 05 in PostgreSQL, and are their units what the conditions assume (IDR)?
Read-only: terminal-api with the gateway key (read from Railway into memory, never printed), pgweb read-only role.

Usage: RAILWAY_TOKEN=... python flow_data_check.py OUT_DIR [TICKER ...]
Tolerance (derived from source precision, not chosen): file values are float8 copies of the SQL values, summed here
exactly (math.fsum) and in SQL as numeric, so a sum may differ only by the float8 rounding of each term:
|file - sql| <= sum(|x|) * 2**-53 (plus 0 for counts and dates, which must be equal).
"""
import gzip, hashlib, json, math, os, random, sys, time, urllib.request
from collections import defaultdict
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'terminal_api'))
from pgq import q  # noqa: E402

TOK = os.environ['RAILWAY_TOKEN']
PID, EID = '8aef1702-030b-49cb-9df7-5ac2e0a42691', '4d3e5af2-302b-4a2e-84e2-7d7476d6ff49'
F05 = 'public."Feature_05_Foreign_Domestic_Broker_Detail"'
EPS = 2.0 ** -53


def gql(query, variables):
    req = urllib.request.Request('https://backboard.railway.com/graphql/v2', json.dumps({'query': query, 'variables': variables}).encode(),
                                 {'Content-Type': 'application/json', 'Project-Access-Token': TOK, 'User-Agent': 'saniti-readonly/1'})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())['data']


def gateway():
    sid = {e['node']['name']: e['node']['id'] for e in gql('query($id:String!){project(id:$id){services{edges{node{id name}}}}}', {'id': PID})['project']['services']['edges']}['terminal-api']
    v = gql('query($p:String!,$e:String!,$s:String!){variables(projectId:$p,environmentId:$e,serviceId:$s)}', {'p': PID, 'e': EID, 's': sid})['variables']
    return 'https://' + v['RAILWAY_PUBLIC_DOMAIN'], v['TERMINAL_PROXY_KEY']


def Q(sql):
    for _ in range(5):
        r = q(sql)
        if 'error' not in r:
            return r['rows']
        time.sleep(3)
    raise RuntimeError(r['error'][:300])


def fetch(url, data=None, headers=None, tries=4):
    for k in range(tries):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, data, headers or {}), timeout=120).read()
        except urllib.error.HTTPError:
            raise
        except Exception:
            if k == tries - 1:
                raise
            time.sleep(2 ** k)


def columnar(raw, f):
    assert len(raw) == f['bytes'], f'bytes {len(raw)} != {f["bytes"]}'
    assert hashlib.sha256(raw).hexdigest() == f['sha256'], 'sha256 mismatch'
    doc = json.loads(gzip.decompress(raw))
    n = len(doc[doc['columns'][0]])
    return doc, n


def main():
    out = sys.argv[1]; os.makedirs(out, exist_ok=True)
    base, key = gateway()
    hdr = {'Content-Type': 'application/json', 'x-terminal-proxy-key': key, 'User-Agent': 'saniti-backtest-check/1'}
    stocks = [r[0] for r in Q('SELECT "Ticker" FROM public."IDX_Stock_Universe" WHERE "Security Type" = \'stock\' ORDER BY 1')]
    random.seed(20261026)
    tickers = sys.argv[2:] or ['BBCA', 'MAPI', 'GOTO', 'BREN', 'ANTM', 'TLKM'] + random.sample(stocks, 6)
    report = {'tickers': {}, 'tolerance': 'sum(|x|) * 2**-53 per sum; counts and dates exact'}
    for t in tickers:
        t0 = time.time()
        b = json.loads(fetch(base + '/api/terminal/v1/bundle', json.dumps({'ticker': t, 'datasets': ['price', 'broker'], 'packs': True}).encode(), hdr))
        files = {ds: b['datasets'][ds]['files'] for ds in ('price', 'broker')}
        rows, price = [], {}
        for f in files['broker']:
            doc, n = columnar(fetch(f['url']), f)
            rows += [tuple(doc[c][i] for c in ('d', 'b', 'i', 'm', 'bv', 'sv', 'bl', 'sl')) for i in range(n)]
        for f in files['price']:
            doc, n = columnar(fetch(f['url']), f)
            for i in range(n):
                price[doc['d'][i]] = (doc['c'][i], doc['v'][i])
        keys = [r[:4] for r in rows]
        r = {'files': {ds: [{k: f.get(k) for k in ('year', 'pack', 'rows', 'bytes')} for f in fs] for ds, fs in files.items()},
             'data_through': {ds: b['datasets'][ds]['data_through'] for ds in files},
             'sorted_unique': keys == sorted(set(keys)), 'rows_file': len(rows),
             'investors': sorted({x[2] for x in rows}), 'boards': sorted({x[3] for x in rows}), 'download_s': round(time.time() - t0, 1)}
        # per-year aggregates, file side (exact sums of the float8 values) vs SQL numeric sums
        fy = defaultdict(lambda: {'n': 0, 'bv': [], 'sv': [], 'bl': [], 'sl': [], 'fnet': []})
        for d, br, inv, m, bv, sv, bl, sl in rows:
            a = fy[int(d[:4])]; a['n'] += 1; a['bv'].append(bv); a['sv'].append(sv); a['bl'].append(bl); a['sl'].append(sl)
            if inv == 'Foreign':
                a['fnet'] += [bv, -sv]
        sql = {int(y): (int(n), float(bv), float(sv), float(bl), float(sl), float(fn)) for y, n, bv, sv, bl, sl, fn in Q(
            f"SELECT extract(year FROM trade_date)::int, count(*), sum(buy_value::numeric), sum(sell_value::numeric), "
            f"sum(buy_lots::numeric), sum(sell_lots::numeric), "
            f"coalesce(sum(CASE WHEN investor_type = 'Foreign' THEN buy_value::numeric - sell_value::numeric END), 0) "
            f"FROM {F05} WHERE ticker = '{t}' AND trade_date <= '{r['data_through']['broker'] or '1900-01-01'}' GROUP BY 1 ORDER BY 1")}
        years = {}
        for y in sorted(set(fy) | set(sql)):
            a, s = fy.get(y), sql.get(y)
            if not a or not s:
                years[y] = {'ok': False, 'why': 'year only in ' + ('sql' if s else 'file')}; continue
            bad = [] if a['n'] == s[0] else ['count']
            for k, col in ((1, 'bv'), (2, 'sv'), (3, 'bl'), (4, 'sl'), (5, 'fnet')):
                v = a[col]; tol = math.fsum(abs(x) for x in v) * EPS
                if abs(math.fsum(v) - s[k]) > tol:
                    bad.append(f'{col}: file {math.fsum(v)!r} sql {s[k]!r} tol {tol:.3g}')
            years[y] = {'ok': not bad, 'rows': a['n'], **({'bad': bad} if bad else {})}
        r['years'] = years
        # units: per date, sum of buy value over every row vs close x volume; sum of buy lots x 100 vs volume
        day_bv, day_bl = defaultdict(list), defaultdict(list)
        for d, br, inv, m, bv, sv, bl, sl in rows:
            day_bv[d].append(bv); day_bl[d].append(bl)
        ratios = sorted(math.fsum(day_bv[d]) / (price[d][0] * price[d][1]) for d in day_bv if d in price and price[d][1])
        lots = sorted(math.fsum(day_bl[d]) * 100 / price[d][1] for d in day_bl if d in price and price[d][1])
        pick = lambda xs, p: xs[min(len(xs) - 1, int(p * (len(xs) - 1)))] if xs else None
        r['units'] = {'days': len(ratios), 'value_ratio_p05_p50_p95': [pick(ratios, p) for p in (.05, .5, .95)],
                      'lots_ratio_p05_p50_p95': [pick(lots, p) for p in (.05, .5, .95)],
                      'price_days_without_broker_rows': sum(1 for d in price if d not in day_bv and d <= (r['data_through']['broker'] or '')),
                      'broker_days_without_price': sum(1 for d in day_bv if d not in price)}
        r['ok'] = r['sorted_unique'] and all(v['ok'] for v in years.values())
        report['tickers'][t] = r
        print(t, 'ok' if r['ok'] else 'MISMATCH', r['rows_file'], 'rows', r['data_through'], r['units']['value_ratio_p05_p50_p95'], flush=True)
    report['sql_max_trade_date'] = Q(f'SELECT max(trade_date)::text FROM {F05}')[0][0]
    report['all_ok'] = all(v['ok'] for v in report['tickers'].values())
    json.dump(report, open(os.path.join(out, 'flow_data_check.json'), 'w'), indent=1, default=str)
    print('ALL OK' if report['all_ok'] else 'MISMATCHES', 'sql max trade_date', report['sql_max_trade_date'])


if __name__ == '__main__':
    main()
