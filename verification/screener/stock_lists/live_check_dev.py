"""EXEC-SCREENER-STOCK-LISTS live check on dev (user 2026-11-09 "push to dev", "jalankan perbaikan 3 dan 2"): signed in
as the owner through edge-bff (sign-in, client and pacing of verification/screener/live_candles_dev.py; credentials read
from Railway into memory only, never printed), through the public EDGE API only:
  1. GET /api/v1/screener/catalog: stock_lists AVAILABLE, 66 lists (33 INDEX, 33 KONGLO), English definitions;
  2. GET /api/v1/screener/universe: rows carry their indices and groups;
  3. POST /api/v1/screener/run on the wide universe: LQ45 alone, LQ45 + group Astra (both), LQ45 excluding a group, an
     unknown code (refused with a plain message); each answer's tickers compared with the universe rows' memberships.
Writes report.json to OUT; nothing is saved in EDGE. Exit 0 only when every check holds.
Usage: python3 verification/screener/stock_lists/live_check_dev.py OUT"""
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import live_candles_dev as L  # noqa: E402

def main():
    out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
    class A: base_url = None
    base, login, password = L.credentials(A)
    L.SECRETS.update(x for x in (password,) if x)
    edge = L.Edge(base)
    s, _, _, _ = edge.raw('POST', '/api/v1/auth/sign-in', {'login': login, 'password': password}); del password
    if s != 200: raise SystemExit(f'sign-in failed ({s})')
    L.SECRETS.update(c.value for c in edge.jar if c.value)
    s, sess, _ = edge.call('GET', '/api/v1/auth/session'); edge.csrf = (sess or {}).get('csrf_token', '')
    L.SECRETS.update(x for x in (edge.csrf,) if x)
    checks, rep = [], {'checked_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
    def check(name, ok, detail=None): checks.append({'check': name, 'ok': bool(ok), 'detail': detail}); print(('PASS ' if ok else 'FAIL ') + name, '' if ok else json.dumps(detail, default=str)[:300])
    s, cat, ms = edge.call('GET', '/api/v1/screener/catalog')
    b = (cat or {}).get('stock_lists') or {}
    rep['catalog'] = {'status': s, 'ms': ms, 'availability': b.get('availability'), 'reason': b.get('reason'), 'as_of': b.get('as_of'), 'lists': len(b.get('lists') or [])}
    lists = b.get('lists') or []
    check('catalog stock_lists AVAILABLE', s == 200 and b.get('availability') == 'AVAILABLE', rep['catalog'])
    check('66 lists: 33 INDEX and 33 KONGLO', [sum(l['kind'] == k for l in lists) for k in ('INDEX', 'KONGLO')] == [33, 33], len(lists))
    lq = next((l for l in lists if l['code'] == 'LQ45'), {}); astra = next((l for l in lists if l['code'] == 'ASTRA'), {})
    check('definitions in English (LQ45, Astra)', lq.get('definition', '').startswith('45 stocks') and 'Stockbit links to' in astra.get('definition', ''), [lq.get('definition'), astra.get('definition')])
    rep['lists_sample'] = [{k: l[k] for k in ('code', 'kind', 'name', 'tickers')} for l in lists[:3] + [astra]]
    s, uni, ms = edge.call('GET', '/api/v1/screener/universe')
    rows = (uni or {}).get('rows') or []
    check('universe rows carry indices and groups', s == 200 and any(r.get('indices') for r in rows), {'status': s, 'rows': len(rows)})
    mem = {r['ticker']: (set(r.get('indices') or []), set(r.get('groups') or [])) for r in rows}
    check('LQ45 count in the catalog = universe rows in LQ45', lq.get('tickers') == sum('LQ45' in v[0] for v in mem.values()), [lq.get('tickers'), sum('LQ45' in v[0] for v in mem.values())])
    def run(u):
        d = {'universe': {**L.WIDE, **u}, 'conditions': [], 'logic': 'all'}
        return edge.call('POST', '/api/v1/screener/run', {'schema_version': 1, 'definition': d, 'options': {'exhaustive': True}}, pace=0.5)
    cases = [('LQ45', {'indices_in': ['LQ45']}, lambda i, g: 'LQ45' in i),
             ('LQ45 and Astra', {'indices_in': ['LQ45'], 'groups_in': ['ASTRA']}, lambda i, g: 'LQ45' in i and 'ASTRA' in g),
             ('LQ45 without Salim and Djarum', {'indices_in': ['LQ45'], 'groups_out': ['SALIM', 'DJARUM']}, lambda i, g: 'LQ45' in i and not ({'SALIM', 'DJARUM'} & g)),
             ('IDX30 or JII', {'indices_in': ['IDX30', 'JII']}, lambda i, g: bool({'IDX30', 'JII'} & i))]
    rep['runs'] = []
    for name, u, want in cases:
        s, ans, ms = run(u)
        got = sorted(r['ticker'] for r in (ans or {}).get('rows', []) if r.get('status', 'match') == 'match') if s == 200 else None
        exp = sorted(t for t, (i, g) in mem.items() if want(i, g))
        rep['runs'].append({'name': name, 'status': s, 'ms': ms, 'matched': len(got or []), 'expected': len(exp), 'sample': (got or [])[:8]})
        check(f'run {name}: {len(exp)} stocks', s == 200 and got == exp, {'status': s, 'got': (got or [])[:10], 'expected': exp[:10], 'missing': sorted(set(exp) - set(got or []))[:10], 'extra': sorted(set(got or []) - set(exp))[:10]})
    s, ans, ms = run({'indices_in': ['LQ46']})
    msg = json.dumps(ans)[:400] if ans else ''
    rep['refusal'] = {'status': s, 'message': msg}
    check('unknown code LQ46 refused with a plain message', s in (400, 422) and 'LQ46' in msg, rep['refusal'])
    edge.raw('POST', '/api/v1/auth/sign-out', {})
    rep['checks'] = checks; rep['verdict'] = 'PASS' if all(c['ok'] for c in checks) else 'FAIL'
    text = json.dumps(rep, indent=1, default=str)
    for sec in L.SECRETS: text = text.replace(sec, '[redacted]')
    (out / 'report.json').write_text(text)
    print('VERDICT', rep['verdict'], f"{sum(c['ok'] for c in checks)}/{len(checks)}")
    return 0 if rep['verdict'] == 'PASS' else 1

if __name__ == '__main__':
    sys.exit(main())
