"""EXEC-OVERVIEW O7 live check on dev: signed in as the owner through edge-bff (the sign-in and client of
verification/screener/live_candles_dev.py, as the Radar's live check; credentials read from Railway into memory only,
never printed), through the public EDGE API only:
  1. without a session the index answers 401; the session names the Overview (capabilities.overview);
  2. GET /api/v1/overview/index lists meta, series and the 20 day files;
  3. every file read with its sha is gzip JSON whose sha256 equals the index's, cached for good;
  4. the files hold what the database holds: verification/overview/validate_overview.py (independent recalculation,
     read-only pgweb) on three dates (the second, the middle and the newest picker date);
  5. refusals name their cause: an older sha 409 OVERVIEW_FILE_REPLACED, a wrong name 400 OVERVIEW_INVALID_NAME.
Writes the files (decoded) and report.json to OUT; nothing is saved in EDGE. Exit 0 only when every check holds.
Run it at least 90 s after a publication: terminal-api reads state.json at most every 60 s and edge-bff keeps the index
30 s, so an earlier run reads the previous index (2026-11-15: the first two runs, 30 and 50 s after the publication,
saw the 12:04 UTC index; the third, 2 min after, 8/8 PASS). The decoded files go to OUT for the check; keep only
report.json in the repository (the files are market data).
Usage: python3 verification/overview/live_check_dev.py OUT"""
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
sys.path.insert(0, str(ROOT / 'verification/overview'))
import live_candles_dev as L  # noqa: E402
import validate_overview as V  # noqa: E402


def fetch(edge, name, sha=''):
    """(status, raw bytes, headers) of one Overview file as the page reads it (bytes as sent: gzip)."""
    req = urllib.request.Request(f'{edge.base}/api/v1/overview/file/{name}' + (f'?sha={sha}' if sha else ''),
                                 headers={'Origin': edge.base, 'Accept-Encoding': 'gzip'})
    try:
        with edge.opener.open(req, timeout=90) as r:
            return r.status, r.read(), r.headers
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers


def body(raw, headers):
    if headers.get('Content-Encoding') == 'gzip':
        raw = gzip.decompress(raw)
    return json.loads(raw or b'{}')


def main():
    out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)

    class A:
        base_url = None
    base, login, password = L.credentials(A)
    L.SECRETS.update(x for x in (password,) if x)
    anon = urllib.request.Request(f'{base}/api/v1/overview/index', headers={'Origin': base})
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
    check('the session names the Overview', ((sess or {}).get('capabilities') or {}).get('overview') is True,
          (sess or {}).get('capabilities'))
    s, idx, ms = edge.call('GET', '/api/v1/overview/index')
    files = (idx or {}).get('files') or {}
    days = sorted(n for n in files if n.startswith('overview-day-'))
    rep['index'] = {'status': s, 'ms': ms, 'finished_at': (idx or {}).get('finished_at'), 'files': len(files),
                    'days': [days[0], days[-1]] if days else None}
    check('index: meta, series and 20 day files', s == 200 and {'overview-meta', 'overview-series'} <= set(files)
          and len(days) == 20 and len(files) == 22, rep['index'])
    rep['files'] = {}
    for name in sorted(files):
        sha = files[name]['sha256']
        t = time.time()
        st, raw, hd = fetch(edge, name, sha)
        ok = st == 200 and hashlib.sha256(raw).hexdigest() == sha
        rep['files'][name] = {'status': st, 'bytes': len(raw), 'ms': round((time.time() - t) * 1000), 'sha_ok': ok,
                              'cache': hd.get('Cache-Control')}
        if ok:
            (out / f'{name}.json').write_text(json.dumps(json.loads(gzip.decompress(raw))))
        time.sleep(0.2)
    check('every file: its bytes have the index sha256', all(v['sha_ok'] for v in rep['files'].values()),
          {k: v for k, v in rep['files'].items() if not v['sha_ok']})
    check('a file named by its sha is cached for good', all('immutable' in (v['cache'] or '') for v in rep['files'].values()), None)
    meta = json.loads((out / 'overview-meta.json').read_text()) if (out / 'overview-meta.json').exists() else {'dates': []}
    picks = [meta['dates'][1], meta['dates'][len(meta['dates']) // 2], meta['dates'][-1]] if len(meta['dates']) >= 3 else []
    before = len(V.DIFFS)
    if picks:
        V.check_meta(meta)
        series = json.loads((out / 'overview-series.json').read_text())
        for d in picks:
            V.check_day(meta, json.loads((out / f'overview-day-{d}.json').read_text()), series, d)
    rep['validation'] = {'dates': picks, 'comparisons': V.CHECKED[0], 'differences': V.DIFFS[before:][:40],
                         'size_basis': meta.get('size_basis'), 'prices_through': meta.get('prices_through'),
                         'broker_through': meta.get('broker_through')}
    check('the files hold what dev holds (independent recalculation, 3 dates)',
          picks and len(V.DIFFS) == before and V.CHECKED[0] > 1000, rep['validation'])
    st, raw, hd = fetch(edge, 'overview-meta', '0' * 64)
    err = body(raw, hd).get('error') or {}
    check('an older sha: 409 OVERVIEW_FILE_REPLACED', st == 409 and err.get('code') == 'OVERVIEW_FILE_REPLACED', {'status': st, 'error': err})
    st, raw, hd = fetch(edge, 'overview-x')
    err = body(raw, hd).get('error') or {}
    check('a wrong name: 400 OVERVIEW_INVALID_NAME', st == 400 and err.get('code') == 'OVERVIEW_INVALID_NAME', {'status': st, 'error': err})
    edge.raw('POST', '/api/v1/auth/sign-out', {})
    rep['checks'] = checks
    (out / 'report.json').write_text(json.dumps(rep, indent=1, default=str))
    bad = [c for c in checks if not c['ok']]
    print(f'{len(checks) - len(bad)}/{len(checks)} PASS', flush=True)
    return 1 if bad else 0


if __name__ == '__main__':
    raise SystemExit(main())
