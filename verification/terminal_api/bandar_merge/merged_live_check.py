"""EXEC-BANDAR-MERGE and EXEC-INV-SYNC (user 2026-11-01), read-only check on Railway dev (owner sign-in; credentials read
from edge-bff's Railway variables into memory, never printed). LOCAL_BUILD=1 serves /terminal-app/ from the local build on
the live data (before a deploy).
  1. the Bandar detector section is hidden; Top brokers carries Top 3/5/10, the ratio and the verdict;
  2. its figures equal the old Bandar detector's for the same ticker and period (EXPECTED: read from the old panel on
     2026-11-01, panel_data_2026-10-27.json: BBRI 5D, all boards);
  3. a broker picked in Broker summary joins the Broker Inventory indicator (FL23), whose lines carry their broker code.
Usage: python3 merged_live_check.py OUT"""
import json, mimetypes, os, subprocess, sys
from pathlib import Path
from playwright.sync_api import sync_playwright

out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
v = json.loads(subprocess.run(['railway', 'variable', 'list', '-s', 'edge-bff', '-e', 'dev', '--json'], capture_output=True, text=True, check=True).stdout)
base = 'https://' + v['RAILWAY_PUBLIC_DOMAIN']; login, pw = v.get('EDGE_LOGIN'), v.get('EDGE_INITIAL_PASSWORD'); del v
BUILD = Path(__file__).resolve().parents[3] / 'apps/edge-bff/static/terminal-app'
old = json.loads((Path(__file__).parent / 'panel_data_2026-10-27.json').read_text())['BBRI']['5']['bd']
EXPECTED = {n: (old[n]['text'].split('\n')[1], old[n]['text'].split('\n')[old[n]['text'].split('\n').index('Ratio to total buy') + 1].replace('-', '−')) for n in ('3', '5', '10')}
rep = {}
with sync_playwright() as p:
    proxy = os.environ.get('HTTPS_PROXY')
    b = p.chromium.launch(executable_path=os.environ.get('EDGE_TEST_CHROMIUM') or None, **({'proxy': {'server': proxy}} if proxy else {}))
    ctx = b.new_context(viewport={'width': 1600, 'height': 1000})
    assert ctx.request.post(base + '/api/v1/auth/sign-in', data=json.dumps({'login': login, 'password': pw}), headers={'Content-Type': 'application/json', 'Origin': base}).status == 200
    if os.environ.get('LOCAL_BUILD') == '1':
        def serve(route):
            path = route.request.url.split('/terminal-app/', 1)[1].split('?', 1)[0] or 'index.html'; f = BUILD / path
            if not f.is_file(): return route.continue_()
            route.fulfill(status=200, body=f.read_bytes(), content_type=mimetypes.guess_type(f.name)[0] or 'application/octet-stream')
        ctx.route('**/terminal-app/**', serve)
    pg = ctx.new_page(); pg.goto(base + '/favicon.svg')
    pg.evaluate("""() => { localStorage.clear(); localStorage.setItem('ml.symbol', 'BBRI'); localStorage.setItem('ml.broker.collapsed', '0');
                           localStorage.setItem('ml.tf', 'D'); localStorage.setItem('ml.ind.v1', JSON.stringify([{ def:'FL23' }])) }""")
    pg.goto(base + '/terminal-app/')
    pg.wait_for_function("() => window.__flowAll === true", timeout=90000); pg.wait_for_timeout(1500)
    rep['bandar_hidden'] = pg.evaluate("() => document.querySelector('.st[data-sec=\"bd\"]').hidden")
    pg.evaluate("() => document.querySelector('#accRange .seg button[data-n=\"5\"]').click()"); pg.wait_for_timeout(300)
    rep['top'] = {}
    for n in ('3', '5', '10'):
        pg.evaluate(f"() => document.querySelector('#accTop button[data-n=\"{n}\"]').click()"); pg.wait_for_timeout(300)
        rep['top'][n] = pg.evaluate("() => ({ verdict: document.querySelector('.acc-bal .tag').textContent, ratio: document.querySelector('.acc-bal .acc-ratio').textContent,"
                                    " tug: document.querySelector('.acc-tug').innerText.replace(/\\n/g, ' | '), net: document.querySelector('.acc-net').textContent,"
                                    " shaded: document.querySelectorAll('#accBody .pa-row.in-top').length, hint: document.getElementById('accHint').textContent })")
    pg.evaluate("() => document.querySelector('#accTop button[data-n=\"3\"]').click()"); pg.wait_for_timeout(300)
    pg.locator('.st[data-sec="acc"]').screenshot(path=str(out / 'top_brokers.png'))
    before = pg.evaluate("() => marketLabIndicators.list().find(i => i.def === 'FL23').params.brokers")
    shown = before if isinstance(before, list) else pg.evaluate("() => Object.keys(marketLabIndicators.values('2000-01-01')[0].outputs)")
    pick = pg.evaluate("s => [...document.querySelectorAll('#bsBody tr[data-b]')].map(r => r.dataset.b).find(c => !s.includes(c))", shown)
    pg.evaluate("c => document.querySelector(`#bsBody tr[data-b=\"${c}\"]`).click()", pick); pg.wait_for_timeout(800)
    after = pg.evaluate("() => marketLabIndicators.list().find(i => i.def === 'FL23').params.brokers")
    rep['inv'] = {'before': before, 'shown_before': shown, 'picked': pick, 'after': after,
                  'outputs': pg.evaluate("() => Object.keys(marketLabIndicators.values('2000-01-01')[0].outputs)")}
    pg.screenshot(path=str(out / 'chart.png'))
    b.close()
rep['expected_old_bandar'] = EXPECTED
rep['checks'] = {
    'Bandar detector hidden': rep['bandar_hidden'] is True,
    'Top 3/5/10 equal the old Bandar detector': all(rep['top'][n]['verdict'] == EXPECTED[n][0] and rep['top'][n]['ratio'] == EXPECTED[n][1] for n in EXPECTED),
    'Top N rows shaded': all(rep['top'][n]['shaded'] == int(n) for n in ('3', '5', '10')),
    'picked broker joins Broker Inventory': rep['inv']['picked'] in (rep['inv']['after'] or []) and rep['inv']['picked'] in rep['inv']['outputs'],
}
(out / 'report.json').write_text(json.dumps(rep, indent=1))
print(json.dumps(rep, indent=1))
print('ALL PASS' if all(rep['checks'].values()) else 'FAILED')
