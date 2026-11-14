"""EXEC-RADAR R9 live check on dev (user 2026-11-14 "2 OK": merge to main and deploy): signed in as the owner through
edge-bff (the sign-in and client of verification/screener/live_candles_dev.py; credentials read from Railway into memory
only, never printed), through the public EDGE API only:
  1. the session names the Radar (capabilities.radar);
  2. GET /api/v1/radar/index lists the 31 files (meta, days, 20 boards, 9 filters);
  3. every file read with its sha is gzip JSON whose sha256 equals the index's; radar-meta, radar-days and the newest
     board hold what the database holds (the dates, the hit counts and the board rows of the newest date, read through
     pgweb, read-only);
  4. refusals name their cause: an older sha 409 RADAR_FILE_REPLACED, a wrong name 400 RADAR_INVALID_NAME;
  5. without a session the index answers 401.
Writes report.json to OUT; nothing is saved in EDGE. Exit 0 only when every check holds.
Usage: python3 verification/radar/live_check_dev.py OUT"""
import gzip
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'verification/screener'))
sys.path.insert(0, str(ROOT / 'verification/terminal_api'))
import live_candles_dev as L  # noqa: E402
import pgq  # noqa: E402

FILTERS = ('s1', 's2', 's3', 's6', 's6d_ratio', 's6d_rank', 's6d_both', 's7', 's8')


def fetch(edge, name, sha=''):
    """(status, raw bytes, headers) of one Radar file as the page reads it (bytes as sent: gzip)."""
    req = urllib.request.Request(f'{edge.base}/api/v1/radar/file/{name}' + (f'?sha={sha}' if sha else ''),
                                 headers={'Origin': edge.base, 'Accept-Encoding': 'gzip'})
    try:
        with edge.opener.open(req, timeout=90) as r:
            return r.status, r.read(), r.headers
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers


def body(raw, headers):
    """A JSON answer as sent (a refusal is gzip when the client accepts it)."""
    if headers.get('Content-Encoding') == 'gzip':
        raw = gzip.decompress(raw)
    return json.loads(raw or b'{}')


def main():
    out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)

    class A:
        base_url = None
    base, login, password = L.credentials(A)
    L.SECRETS.update(x for x in (password,) if x)
    anon = urllib.request.Request(f'{base}/api/v1/radar/index', headers={'Origin': base})
    try:
        anon_status = urllib.request.urlopen(anon, timeout=30).status
    except urllib.error.HTTPError as e:
        anon_status = e.code
    edge = L.Edge(base)
    s, _, _, _ = edge.raw('POST', '/api/v1/auth/sign-in', {'login': login, 'password': password}); del password
    if s != 200:
        raise SystemExit(f'sign-in failed ({s})')
    L.SECRETS.update(c.value for c in edge.jar if c.value)
    s, sess, _ = edge.call('GET', '/api/v1/auth/session'); edge.csrf = (sess or {}).get('csrf_token', '')
    L.SECRETS.update(x for x in (edge.csrf,) if x)
    checks, rep = [], {'checked_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'base': base}

    def check(name, ok, detail=None):
        checks.append({'check': name, 'ok': bool(ok), 'detail': detail})
        print(('PASS ' if ok else 'FAIL ') + name, '' if ok else json.dumps(detail, default=str)[:400], flush=True)

    check('no session: the index answers 401', anon_status == 401, anon_status)
    check('the session names the Radar', ((sess or {}).get('capabilities') or {}).get('radar') is True,
          (sess or {}).get('capabilities'))
    s, idx, ms = edge.call('GET', '/api/v1/radar/index')
    files = (idx or {}).get('files') or {}
    boards = sorted(n for n in files if n.startswith('radar-board-'))
    rep['index'] = {'status': s, 'ms': ms, 'finished_at': (idx or {}).get('finished_at'), 'files': len(files),
                    'boards': [boards[0], boards[-1]] if boards else None}
    want = {'radar-meta', 'radar-days', *(f'radar-f-{f}' for f in FILTERS)}
    check('index: 31 files (meta, days, 20 boards, 9 filters)',
          s == 200 and len(files) == 31 and want <= set(files) and len(boards) == 20, rep['index'])
    docs, rep['files'] = {}, {}
    for name in sorted(files):
        sha = files[name]['sha256']
        t = time.time()
        st, raw, hd = fetch(edge, name, sha)
        ok = st == 200 and hashlib.sha256(raw).hexdigest() == sha
        rep['files'][name] = {'status': st, 'bytes': len(raw), 'ms': round((time.time() - t) * 1000),
                              'sha_ok': ok, 'cache': hd.get('Cache-Control')}
        if ok:
            docs[name] = json.loads(gzip.decompress(raw))
        time.sleep(0.2)
    check('every file: its bytes have the index sha256', all(v['sha_ok'] for v in rep['files'].values()),
          {k: v for k, v in rep['files'].items() if not v['sha_ok']})
    check('a file named by its sha is cached for good',
          all('immutable' in (v['cache'] or '') for v in rep['files'].values()), None)
    days, meta = docs.get('radar-days') or {}, docs.get('radar-meta') or {}
    newest = (days.get('dates') or [None])[-1]
    # the dates are the gate rows' (one per result date); ERRORS M434: the first four have no result rows
    db = pgq.q('SELECT count(*), max(trade_date)::text FROM public."Feature_07_Radar_Gate"')['rows'][0]
    rep['days'] = {'dates': len(days.get('dates') or []), 'newest': newest, 'db_dates': db[0], 'db_newest': db[1],
                   'boards': len(days.get('boards') or []), 'broker_through': days.get('broker_through'),
                   'prices_through': days.get('prices_through')}
    check('radar-days: the dates of the database', rep['days']['dates'] == db[0] and newest == db[1], rep['days'])
    hits = pgq.q("SELECT filter_id, level, gate, count(*) FROM public.\"Feature_07_Radar_Result\" WHERE status = 'hit' "
                 f"AND trade_date = '{newest}' GROUP BY 1, 2, 3")['rows']
    pos = (days.get('dates') or []).index(newest) if newest else -1
    counts = days.get('counts') or {}
    diff = [(f, lv, g, n, (counts.get(f) or {}).get(f'{lv}/{g}', [None] * (pos + 1))[pos]) for f, lv, g, n in hits
            if (counts.get(f) or {}).get(f'{lv}/{g}', [None] * (pos + 1))[pos] != n]
    rep['hits_newest'] = {'groups': len(hits), 'differences': diff[:10],
                          'standard': sorted([f, g, n] for f, lv, g, n in hits if lv == 'standard')}
    check(f'radar-days: the hit counts of {newest} equal the database', hits and not diff, rep['hits_newest'])
    board = docs.get(f'radar-board-{newest}') or {}
    db_rows = pgq.q(f'SELECT count(*) FROM public."Feature_07_Radar_Result" WHERE trade_date = \'{newest}\'')['rows'][0][0]
    rep['board_newest'] = {'rows': len((board.get('rows') or {}).get('filter') or []), 'db_rows': db_rows,
                           'stocks': len((board.get('stocks') or {}).get('ticker') or [])}
    check(f'radar-board-{newest}: every result row of the date', rep['board_newest']['rows'] == db_rows, rep['board_newest'])
    s6d = [r for r in meta.get('rules') or [] if str(r.get('filter', '')).startswith('S6D') and r.get('cond') == 'D']
    rep['s6d_rules'] = s6d
    check('radar-meta: S6-delta thresholds 12/20/35 and 40/65/90 (user 1A)',
          sorted({(r['filter'], r['level'], r['threshold'], r.get('threshold2')) for r in s6d}) == sorted(
              {(f, lv, {'S6D_RANK': rk}.get(f, rt), {'S6D_BOTH': rk}.get(f))
               for f in ('S6D_RATIO', 'S6D_RANK', 'S6D_BOTH')
               for lv, rt, rk in (('loose', 12, 40), ('standard', 20, 65), ('strict', 35, 90))}), s6d)
    st, raw, hd = fetch(edge, 'radar-meta', '0' * 64)
    err = body(raw, hd).get('error') or {}
    check('an older sha: 409 RADAR_FILE_REPLACED with the current sha', st == 409 and err.get('code') == 'RADAR_FILE_REPLACED',
          {'status': st, 'error': err})
    st, raw, hd = fetch(edge, 'radar-x')
    err = body(raw, hd).get('error') or {}
    check('a wrong name: 400 RADAR_INVALID_NAME naming the valid names', st == 400 and err.get('code') == 'RADAR_INVALID_NAME',
          {'status': st, 'error': err})
    edge.raw('POST', '/api/v1/auth/sign-out', {})
    rep['checks'] = checks
    (out / 'report.json').write_text(json.dumps(rep, indent=1, default=str))
    bad = [c for c in checks if not c['ok']]
    print(f'{len(checks) - len(bad)}/{len(checks)} PASS', flush=True)
    return 1 if bad else 0


if __name__ == '__main__':
    raise SystemExit(main())
