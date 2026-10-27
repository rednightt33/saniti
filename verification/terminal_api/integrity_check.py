"""Read-only integrity audit: bucket files vs PostgreSQL (see INTEGRITY.md).

Usage (RAILWAY_TOKEN in the environment; bucket credentials are read from Railway into memory only):
  python integrity_check.py files   WORK   # download every object, check sha/bytes/rows/dates, file-side aggregates
  python integrity_check.py sql     WORK   # per-ticker SQL aggregates (price + broker, by year)
  python integrity_check.py compare WORK   # coverage, aggregates, ordering/types, freshness -> WORK/compare.json
  python integrity_check.py rows    WORK   # row-level sample comparison -> WORK/rows.json
Nothing is written to the bucket or the database.
"""
import gzip, hashlib, json, math, os, subprocess, sys, time, random
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pgq import q  # noqa: E402

PREFIX = 'v1'
Y0, Y1 = 2021, 2026
PRICE_T, BROKER_T = 'public."Price_Stock_Indonesia_IDX"', 'public."Feature_05_Foreign_Domestic_Broker_Detail"'


def bucket():
    import boto3
    from botocore.config import Config
    env = json.loads(subprocess.run(['railway', 'variable', 'list', '-s', 'terminal-publisher', '-e', 'dev', '--json'],
                                    capture_output=True, text=True, check=True).stdout)
    s3 = boto3.client('s3', endpoint_url=env['TERMINAL_BUCKET_ENDPOINT'], region_name=env['TERMINAL_BUCKET_REGION'],
                      aws_access_key_id=env['TERMINAL_BUCKET_ACCESS_KEY_ID'],
                      aws_secret_access_key=env['TERMINAL_BUCKET_SECRET_ACCESS_KEY'],
                      config=Config(s3={'addressing_style': 'virtual'}, signature_version='s3v4',
                                    retries={'max_attempts': 5}, max_pool_connections=32))
    return s3, env['TERMINAL_BUCKET_NAME']


def Q(sql, tries=3):
    for i in range(tries + 4):
        try:
            r = q(sql)
        except Exception as e:  # network reset etc.
            r = {'error': repr(e)}
            time.sleep(5)
        if 'error' not in r:
            return r['rows']
        time.sleep(2)
    raise RuntimeError(r['error'][:300] + ' :: ' + sql[:200])


def universe():
    return Q('SELECT "Ticker","Security Type" FROM public."IDX_Stock_Universe" '
             "WHERE \"Security Type\" IN ('stock','index') ORDER BY 1")


def fsum(xs):
    return math.fsum(x for x in xs if x is not None)


def load(work, name):
    return json.load(open(os.path.join(work, name)))


def save(work, name, obj):
    json.dump(obj, open(os.path.join(work, name), 'w'))


# ---------------------------------------------------------------- files
def file_aggs(dataset, doc):
    if dataset == 'price':
        return {'n': len(doc['d']), 'min': doc['d'][0], 'max': doc['d'][-1], 'o': fsum(doc['o']), 'h': fsum(doc['h']),
                'l': fsum(doc['l']), 'c': fsum(doc['c']), 'v': fsum(doc['v']),
                'vnull': sum(1 for x in doc['v'] if x is None), 'asc': doc['d'] == sorted(doc['d'])}
    keys = list(zip(doc['d'], doc['b'], doc['i'], doc['m']))
    return {'n': len(doc['d']), 'min': doc['d'][0], 'max': doc['d'][-1], 'bv': fsum(doc['bv']), 'sv': fsum(doc['sv']),
            'bl': fsum(doc['bl']), 'sl': fsum(doc['sl']), 'brokers': len(set(doc['b'])),
            'inv': dict(Counter(doc['i'])), 'board': dict(Counter(doc['m'])), 'gap': sorted(map(list, doc['gap'])),
            'asc': doc['d'] == sorted(doc['d']), 'keys_sorted': keys == sorted(keys),
            'dup_keys': len(keys) - len(set(keys)),
            'frac_lots': sum(1 for x in doc['bl'] + doc['sl'] if x is not None and x != int(x))}


def do_files(work):
    os.makedirs(work, exist_ok=True)
    s3, name = bucket()
    t0 = time.time()
    uni = universe()
    out = {'issues': [], 'files': {}, 'manifests': {}}

    def get(key):
        return s3.get_object(Bucket=name, Key=f'{PREFIX}/{key}')['Body'].read()

    def one_manifest(t):
        try:
            return t, json.loads(get(f'manifest/{t}.json'))
        except Exception as e:  # noqa
            return t, repr(e)[:100]
    with ThreadPoolExecutor(24) as ex:
        for t, m in ex.map(one_manifest, [t for t, _ in uni]):
            if isinstance(m, str):
                out['issues'].append(['manifest_missing', t, m])
            else:
                out['manifests'][t] = m
    jobs = []
    for t, m in out['manifests'].items():
        for ds, d in m['datasets'].items():
            for y, f in d['files'].items():
                jobs.append((t, ds, y, f))

    def one(j):
        t, ds, y, f = j
        body = None
        for _ in range(3):
            try:
                body = get(f['key'][len(PREFIX) + 1:])
                break
            except Exception as e:  # noqa
                err = e
        if body is None:
            e = err
            return j, None, [['object_missing', t, ds, y, repr(e)[:100]]]
        errs = []
        sha = hashlib.sha256(body).hexdigest()
        if sha != f['sha256']:
            errs.append(['sha_mismatch', t, ds, y, sha, f['sha256']])
        if len(body) != f['bytes']:
            errs.append(['bytes_mismatch', t, ds, y, len(body), f['bytes']])
        doc = json.loads(gzip.decompress(body))
        if doc.get('ticker') != t or doc.get('dataset') != ds or str(doc.get('year')) != str(y):
            errs.append(['header_mismatch', t, ds, y, [doc.get('ticker'), doc.get('dataset'), doc.get('year')]])
        a = file_aggs(ds, doc)
        for k, mk in (('n', 'rows'), ('min', 'first'), ('max', 'last')):
            if a[k] != f[mk]:
                errs.append(['manifest_vs_file', t, ds, y, mk, a[k], f[mk]])
        return j, a, errs
    with ThreadPoolExecutor(24) as ex:
        for j, a, errs in ex.map(one, jobs):
            out['issues'] += errs
            if a is not None:
                out['files'][f'{j[1]}|{j[0]}|{j[2]}'] = a
    # state.json and refs
    out['state'] = json.loads(get('state.json'))
    out['ref_tickers_rows'] = len(json.loads(gzip.decompress(get('ref/tickers.json.gz')))['ticker'])
    out['seconds'] = round(time.time() - t0, 1)
    out['n_manifests'], out['n_files'] = len(out['manifests']), len(jobs)
    # list all objects to find extras
    keys = []
    pg = s3.get_paginator('list_objects_v2')
    for p in pg.paginate(Bucket=name, Prefix=PREFIX + '/'):
        keys += [o['Key'] for o in p.get('Contents', [])]
    out['bucket_keys'] = keys
    save(work, 'files.json', out)
    print('files done', out['n_manifests'], out['n_files'], len(out['issues']), out['seconds'], 's', len(keys), 'keys')


# ---------------------------------------------------------------- sql
def do_sql(work):
    uni = universe()
    res = {'price': {}, 'broker': {}, 'maxes': {}, 'done': []}
    if os.path.exists(os.path.join(work, 'sql.json')):
        res = load(work, 'sql.json')
        res.setdefault('done', [])
    t0 = time.time()
    res['maxes']['price'] = Q(f"SELECT max(date)::text FROM {PRICE_T} WHERE timeframe='Daily' AND is_final")[0][0]
    res['maxes']['broker'] = Q(f'SELECT max(trade_date)::text FROM {BROKER_T}')[0][0]
    res['universe'] = uni
    for n, (t, typ) in enumerate(uni, 1):
        if t in res['done']:
            continue
        rows = Q(f"""SELECT extract(year FROM date)::int, count(*), min(date)::text, max(date)::text,
          sum(open::float8), sum(high::float8), sum(low::float8), sum(close::float8), sum(volume::float8),
          count(*) FILTER (WHERE volume IS NULL) FROM {PRICE_T}
          WHERE ticker='{t}' AND timeframe='Daily' AND is_final AND date BETWEEN '{Y0}-01-01' AND '{Y1}-12-31' GROUP BY 1""")
        for r in rows:
            res['price'][f'{t}|{r[0]}'] = {'n': r[1], 'min': r[2], 'max': r[3], 'o': r[4], 'h': r[5], 'l': r[6],
                                          'c': r[7], 'v': r[8], 'vnull': r[9]}
        if typ == 'stock':
            rows = Q(f"""SELECT extract(year FROM trade_date)::int, count(*), min(trade_date)::text, max(trade_date)::text,
              sum(buy_value::float8), sum(sell_value::float8), sum(buy_lots::float8), sum(sell_lots::float8),
              count(DISTINCT broker),
              count(*) FILTER (WHERE investor_type='Foreign'), count(*) FILTER (WHERE investor_type='Domestic'),
              count(*) FILTER (WHERE investor_type NOT IN ('Foreign','Domestic') OR investor_type IS NULL),
              count(*) FILTER (WHERE market_board='Regular'), count(*) FILTER (WHERE market_board='Nego'),
              count(*) FILTER (WHERE market_board='Tunai'),
              count(*) FILTER (WHERE market_board NOT IN ('Regular','Nego','Tunai') OR market_board IS NULL),
              count(*) FILTER (WHERE buy_lots <> trunc(buy_lots) OR sell_lots <> trunc(sell_lots))
              FROM {BROKER_T} WHERE ticker='{t}' AND trade_date BETWEEN '{Y0}-01-01' AND '{Y1}-12-31' GROUP BY 1""")
            gaps = Q(f"""SELECT extract(year FROM trade_date)::int, trade_date::text, market_board FROM {BROKER_T}
              WHERE ticker='{t}' AND source_balance_gap AND trade_date BETWEEN '{Y0}-01-01' AND '{Y1}-12-31'
              GROUP BY 1,2,3 ORDER BY 2,3""")
            g = defaultdict(list)
            for y, d, b in gaps:
                g[y].append([d, b])
            for r in rows:
                res['broker'][f'{t}|{r[0]}'] = {
                    'n': r[1], 'min': r[2], 'max': r[3], 'bv': r[4], 'sv': r[5], 'bl': r[6], 'sl': r[7], 'brokers': r[8],
                    'inv': {'Foreign': r[9], 'Domestic': r[10]}, 'inv_other': r[11],
                    'board': {'Regular': r[12], 'Nego': r[13], 'Tunai': r[14]}, 'board_other': r[15],
                    'frac_rows': r[16], 'gap': g.get(r[0], [])}
        res['done'].append(t)
        if n % 50 == 0:
            print('sql', n, len(uni), round(time.time() - t0), 's', flush=True)
            save(work, 'sql.json', res)
    res['seconds'] = round(time.time() - t0, 1)
    save(work, 'sql.json', res)
    print('sql done', res['seconds'])


# ---------------------------------------------------------------- compare
def close(a, b):
    if a is None or b is None:
        return a == b
    if b == 0:
        return abs(a) <= 1e-6
    return abs(a - b) <= 1e-9 * max(abs(a), abs(b))


def do_compare(work):
    F, S = load(work, 'files.json'), load(work, 'sql.json')
    uni = {t: typ for t, typ in S['universe']}
    mism, cov = [], []
    # coverage
    sql_price = {tuple(k.split('|')) for k in S['price']}
    sql_broker = {tuple(k.split('|')) for k in S['broker']}
    file_price = {(k.split('|')[1], k.split('|')[2]) for k in F['files'] if k.startswith('price|')}
    file_broker = {(k.split('|')[1], k.split('|')[2]) for k in F['files'] if k.startswith('broker|')}
    cov += [['price_file_missing', *k] for k in sorted(sql_price - file_price)]
    cov += [['price_file_extra', *k] for k in sorted(file_price - sql_price)]
    cov += [['broker_file_missing', *k] for k in sorted(sql_broker - file_broker)]
    cov += [['broker_file_extra', *k] for k in sorted(file_broker - sql_broker)]
    cov += [['index_has_broker_file', t] for t, y in file_broker if uni.get(t) != 'stock']
    cov += [['manifest_missing', t] for t in uni if t not in F['manifests']]
    cov += [['manifest_not_in_universe', t] for t in F['manifests'] if t not in uni]
    # bucket keys vs manifests
    expected = {f['key'] for m in F['manifests'].values() for d in m['datasets'].values() for f in d['files'].values()}
    expected |= {f'{PREFIX}/manifest/{t}.json' for t in F['manifests']}
    expected |= {p['key'] for m in F['manifests'].values() for p in m.get('packs', {}).values()}
    expected |= {f'{PREFIX}/ref/tickers.json.gz', f'{PREFIX}/ref/brokers.json.gz', f'{PREFIX}/ref/logos.json.gz',
                 f'{PREFIX}/state.json'}
    # EXEC-SCREENER: the cross-sectional files are named by the state.json `xsection` index, not by a manifest
    expected |= {e['key'] for e in (F['state'].get('xsection') or {}).values() if isinstance(e, dict) and e.get('key')}
    # logos are named by ref/logos.json.gz; a data file a newer manifest (or an xsection file a newer index) replaced
    # stays until the publisher's next daily run deletes it (collect_garbage, ERRORS M250), so a few unreferenced keys
    # right after a run are expected
    cov += [['bucket_key_unreferenced', k] for k in sorted(set(F['bucket_keys']) - expected)
            if not k.startswith(f'{PREFIX}/logo/')]
    cov += [['manifest_key_absent_in_bucket', k] for k in sorted(expected - set(F['bucket_keys']))]
    # aggregates
    nrows = {'price': 0, 'broker': 0}
    nfiles = {'price': 0, 'broker': 0}
    for k, a in F['files'].items():
        ds, t, y = k.split('|')
        s = (S['price'] if ds == 'price' else S['broker']).get(f'{t}|{y}')
        if s is None:
            continue
        nfiles[ds] += 1
        nrows[ds] += a['n']
        fields = ['n', 'min', 'max', 'o', 'h', 'l', 'c', 'v', 'vnull'] if ds == 'price' else \
            ['n', 'min', 'max', 'bv', 'sv', 'bl', 'sl', 'brokers']
        for f in fields:
            x, y_ = a[f], s[f]
            if isinstance(x, (int, float)) and not isinstance(x, bool) and f not in ('n', 'vnull', 'brokers'):
                ok = close(x, y_)
            else:
                ok = x == y_
            if not ok and f == 'v' and ds == 'price' and y_ is None and a['vnull'] == a['n'] and x == 0:
                ok = True  # all-NULL volume: SQL sum is NULL, file-side sum of nothing is 0
            if not ok:
                mism.append([ds, t, y, f, x, y_])
        if ds == 'broker':
            for f in ('inv', 'board'):
                if a[f] != {kk: vv for kk, vv in s[f].items() if vv} and a[f] != s[f]:
                    mism.append([ds, t, y, f, a[f], s[f]])
            if a['gap'] != s['gap']:
                mism.append([ds, t, y, 'gap', a['gap'], s['gap']])
            if s['inv_other'] or s['board_other']:
                mism.append([ds, t, y, 'sql_other_values', s['inv_other'], s['board_other']])
            if (a['frac_lots'] > 0) != (s['frac_rows'] > 0):
                mism.append([ds, t, y, 'fractional_lots', a['frac_lots'], s['frac_rows']])
        if not a['asc']:
            mism.append([ds, t, y, 'dates_not_ascending'])
        if ds == 'broker' and (not a['keys_sorted'] or a['dup_keys']):
            mism.append([ds, t, y, 'keys_not_sorted_or_duplicated', a['keys_sorted'], a['dup_keys']])
    # types check inside files
    bad_inv = [k for k, a in F['files'].items() if k.startswith('broker|') and set(a['inv']) - {'Foreign', 'Domestic'}]
    bad_board = [k for k, a in F['files'].items() if k.startswith('broker|') and set(a['board']) - {'Regular', 'Nego', 'Tunai'}]
    frac_files = sum(1 for a in F['files'].values() if a.get('frac_lots', 0) > 0)
    frac_sql = sum(1 for s in S['broker'].values() if s['frac_rows'] > 0)
    # freshness
    fresh = []
    st = F['state']
    if st.get('price_through') != S['maxes']['price']:
        fresh.append(['state.price_through', st.get('price_through'), S['maxes']['price']])
    if st.get('broker_through') != S['maxes']['broker']:
        fresh.append(['state.broker_through', st.get('broker_through'), S['maxes']['broker']])
    if st.get('last_mode') != 'backfill':
        fresh.append(['state.last_mode', st.get('last_mode'), 'backfill'])
    for t, m in F['manifests'].items():
        for ds, d in m['datasets'].items():
            exp = S['maxes'][ds]
            if d.get('data_through') != exp:
                fresh.append(['manifest.data_through', t, ds, d.get('data_through'), exp])
    save(work, 'compare.json', {'coverage': cov, 'mismatches': mism, 'freshness': fresh, 'nrows': nrows,
                                'nfiles': nfiles, 'bad_inv': bad_inv, 'bad_board': bad_board,
                                'frac_files': frac_files, 'frac_sql': frac_sql, 'file_issues': F['issues'],
                                'state': st, 'n_manifests': F['n_manifests'], 'n_files': F['n_files'],
                                'ref_tickers_rows': F['ref_tickers_rows'], 'universe': len(uni)})
    print('coverage', len(cov), 'mismatch', len(mism), 'fresh', len(fresh), 'issues', len(F['issues']), nfiles, nrows,
          'frac files', frac_files, frac_sql)


# ---------------------------------------------------------------- rows
def do_rows(work):
    s3, name = bucket()
    F, S = load(work, 'files.json'), load(work, 'sql.json')
    random.seed(20261025)
    must = ['BBCA', 'GOTO', 'BREN', 'ANTM', 'MAPI']
    bk = defaultdict(list)
    for k in S['broker']:
        t, y = k.split('|')
        bk[t].append(int(y))
    pr = defaultdict(list)
    for k in S['price']:
        t, y = k.split('|')
        pr[t].append(int(y))
    # low liquidity: smallest total broker rows
    tot = sorted(((sum(S['broker'][f'{t}|{y}']['n'] for y in ys), t) for t, ys in bk.items()))
    low = [t for _, t in tot[:6]]
    sample = {'broker': set(), 'price': set()}
    for t in must + low:
        for y in (2021, 2026, random.choice(bk.get(t, [2023]))):
            if f'{t}|{y}' in S['broker']:
                sample['broker'].add((t, y))
    for t in must + ['IHSG'] + low:
        for y in (2021, 2026, random.choice(pr.get(t, [2023]))):
            if f'{t}|{y}' in S['price']:
                sample['price'].add((t, y))
    pool_b = [(t, y) for t, ys in bk.items() for y in ys]
    pool_p = [(t, y) for t, ys in pr.items() for y in ys]
    while len(sample['broker']) < 45:
        sample['broker'].add(random.choice(pool_b))
    while len(sample['price']) < 45:
        sample['price'].add(random.choice(pool_p))
    gap_ty = {tuple([k.split('|')[0], int(k.split('|')[1])]) for k, s in S['broker'].items() if s['gap']}
    sample['broker'] |= gap_ty
    sample['gap_count'] = len(gap_ty)
    res = {'broker': [], 'price': [], 'mismatches': [], 'rows_compared': 0}

    def fetch(ds, t, y):
        key = F['manifests'][t]['datasets'][ds]['files'][str(y)]['key']    # content keys (ERRORS M250): never built
        body = s3.get_object(Bucket=name, Key=key)['Body'].read()
        return json.loads(gzip.decompress(body))
    t0 = time.time()
    for ds in ('price', 'broker'):
        for (t, y) in sorted(sample[ds]):
            doc = fetch(ds, t, y)
            cols = doc['columns']
            frows = list(zip(*[doc[c] for c in cols]))
            if ds == 'price':
                sql = (f"SELECT date::text, open::float8::text, high::float8::text, low::float8::text, close::float8::text, "
                       f"volume::float8::text FROM {PRICE_T} WHERE ticker='{t}' AND timeframe='Daily' AND is_final "
                       f"AND date BETWEEN '{y}-01-01' AND '{y}-12-31' ORDER BY date")
            else:
                sql = (f"SELECT trade_date::text, broker, investor_type, market_board, buy_value::float8::text, "
                       f"sell_value::float8::text, buy_lots::float8::text, sell_lots::float8::text FROM {BROKER_T} "
                       f"WHERE ticker='{t}' AND trade_date BETWEEN '{y}-01-01' AND '{y}-12-31' "
                       f"ORDER BY trade_date, broker, investor_type, market_board")
            srows = Q(sql)
            nb = 0
            if len(srows) != len(frows):
                res['mismatches'].append([ds, t, y, 'row_count', len(frows), len(srows)])
            else:
                nkey = 1 if ds == 'price' else 4
                for i, (fr, sr) in enumerate(zip(frows, srows)):
                    for j, c in enumerate(cols):
                        a, b = fr[j], sr[j]
                        if j >= nkey:
                            b = None if b is None else float(b)
                        if a != b:
                            nb += 1
                            if nb <= 5:
                                res['mismatches'].append([ds, t, y, i, c, a, b])
                res['rows_compared'] += len(srows)
            res[ds].append([t, y, len(srows), nb])
            print(ds, t, y, len(srows), 'bad' if nb else 'ok', round(time.time() - t0), 's', flush=True)
    res['seconds'] = round(time.time() - t0, 1)
    res['gap_ticker_years'] = sorted(map(list, gap_ty))
    save(work, 'rows.json', res)
    print('rows done', res['rows_compared'], len(res['mismatches']))


if __name__ == '__main__':
    {'files': do_files, 'sql': do_sql, 'compare': do_compare, 'rows': do_rows}[sys.argv[1]](sys.argv[2])
