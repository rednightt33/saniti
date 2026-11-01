"""ERRORS M332 (user 2026-11-01, US10Y screenshot): a bond's chart draws only the indicators it has the data for; the
saved Flow and volume indicators are kept for the next stock.

Read-only check on Railway dev, signed in as the owner (credentials read from edge-bff's Railway variables into memory,
never printed). The page's indicator list is seeded in the browser's own storage with five entries: Bandar Balance
(FL24, broker data), SMA and RSI (closes), On-Balance Volume (closes and volume) and Net Buy Flow (broker data), and the
base volume histogram is left on. Then
  1. US10Y: the legend shows SMA and RSI only, no Volume row, no "Loading broker data"; the other three are parked and
     the saved list still holds all five in their order; the Indicators menu offers no Flow, volume or volume indicator;
  2. BBCA (the next ticker, as the page's search does: store and reload): all five are drawn again, the volume too.
LOCAL_BUILD=1 serves /terminal-app/ from the local build (apps/edge-bff/static/terminal-app) on the live data, so the
fix is checked before it is deployed. Writes OUT/report.json and a screenshot per step.

Usage: python3 bond_indicators_live_check.py OUT"""
import json, mimetypes, os, subprocess, sys
from pathlib import Path
from playwright.sync_api import sync_playwright

out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
v = json.loads(subprocess.run(['railway', 'variable', 'list', '-s', 'edge-bff', '-e', 'dev', '--json'],
                              capture_output=True, text=True, timeout=60, check=True).stdout)
base = 'https://' + v['RAILWAY_PUBLIC_DOMAIN']
login, password = v.get('EDGE_LOGIN'), v.get('EDGE_INITIAL_PASSWORD')
del v
BUILD = Path(__file__).resolve().parents[2] / 'apps/edge-bff/static/terminal-app'
SAVED = [{'def': 'FL24'}, {'def': 'sma'}, {'def': 'obv'}, {'def': 'rsi'}, {'def': 'netflow'}]

STATE = """() => {
  const I = window.marketLabIndicators, row = document.getElementById('indRow');
  const legend = [...document.querySelectorAll('.ind-row, .ind-legend-row, [data-uid]')].map(e => e.textContent.trim()).filter(Boolean);
  return { drawn: I.list().map(i => i.def), parked: I.parked ? I.parked() : null,
           saved: JSON.parse(localStorage.getItem('ml.ind.v1') || '[]').map(o => o.def),
           volumeRow: row ? getComputedStyle(row).display !== 'none' : null,
           loadingText: document.body.innerText.includes('Loading broker data'),
           flowReadout: (() => { const t = document.getElementById('flowTip'); return !!t && !t.hidden && t.textContent.trim() !== '' })(),
           noVolumeText: document.body.innerText.includes('No volume for this ticker'),
           legendText: (row && row.parentElement ? row.parentElement.innerText : '').slice(0, 600) };
}"""
MENU = """() => {
  document.getElementById('indBtn').click();
  const rows = [...document.querySelectorAll('.im-row[data-id]')].map(r => r.dataset.id);
  document.getElementById('indBtn').click();
  return rows;
}"""

report = {'local_build': os.environ.get('LOCAL_BUILD') == '1'}
with sync_playwright() as pw:
    proxy = os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy')
    browser = pw.chromium.launch(executable_path=os.environ.get('EDGE_TEST_CHROMIUM') or None,
                                 **({'proxy': {'server': proxy}} if proxy else {}))
    ctx = browser.new_context(viewport={'width': 1600, 'height': 1000})
    r = ctx.request.post(base + '/api/v1/auth/sign-in', data=json.dumps({'login': login, 'password': password}),
                         headers={'Content-Type': 'application/json', 'Origin': base})
    if r.status != 200:
        raise SystemExit(f'sign-in failed ({r.status})')
    if report['local_build']:
        def serve(route):
            path = route.request.url.split('/terminal-app/', 1)[1].split('?', 1)[0] or 'index.html'
            f = BUILD / path
            if not f.is_file():
                return route.continue_()
            route.fulfill(status=200, body=f.read_bytes(), content_type=mimetypes.guess_type(f.name)[0] or 'application/octet-stream')
        ctx.route('**/terminal-app/**', serve)
    page = ctx.new_page()
    page.goto(base + '/favicon.svg')
    page.evaluate("""s => { localStorage.setItem('ml.ind.v1', JSON.stringify(s)); localStorage.setItem('ml.symbol', 'US10Y');
                            localStorage.setItem('ml.vol.removed', '0'); localStorage.setItem('ml.vol.on', '1'); localStorage.setItem('ml.tf', 'D') }""", SAVED)

    def step(name, symbol):
        page.evaluate("s => localStorage.setItem('ml.symbol', s)", symbol)
        page.goto(base + '/terminal-app/')
        page.wait_for_function("() => window.marketLabIndicators && document.querySelector('#chart canvas')", timeout=60000)
        page.wait_for_timeout(4000)                                  # the broker files of a stock
        box = page.locator('#chart').bounding_box()                  # the crosshair writes the legend's readouts
        page.mouse.move(box['x'] + box['width'] * 0.6, box['y'] + box['height'] * 0.4)
        page.wait_for_timeout(300)
        s = page.evaluate(STATE)
        s['menu'] = page.evaluate(MENU)
        s['menu_has_flow'] = any(i.startswith('FL') for i in s['menu'])
        s['menu_has_vol'] = 'VOL' in s['menu']
        s['menu_count'] = len(s['menu'])
        del s['menu']
        page.screenshot(path=str(out / f'{name}.png'))
        report[name] = s

    step('bond_US10Y', 'US10Y')
    step('stock_BBCA', 'BBCA')
    browser.close()

b, s = report['bond_US10Y'], report['stock_BBCA']
report['checks'] = {
    'bond draws SMA and RSI only': sorted(b['drawn']) == ['rsi', 'sma'],
    'bond parks FL24, OBV, Net Buy Flow': sorted(b['parked'] or []) == ['FL24', 'netflow', 'obv'],
    'saved list keeps all five in order': b['saved'] == [o['def'] for o in SAVED],
    'bond has no Volume row': b['volumeRow'] is False,
    'bond shows no "Loading broker data"': not b['loadingText'],
    'bond has no Flow readout (Net, Cumulative)': b['flowReadout'] is False,
    'bond menu: no Flow, no volume': not b['menu_has_flow'] and not b['menu_has_vol'],
    'stock draws all five again': sorted(s['drawn']) == sorted(o['def'] for o in SAVED),
    'stock has the Volume row': s['volumeRow'] is True,
    'stock menu: Flow and volume offered': s['menu_has_flow'] and s['menu_has_vol'],
}
(out / 'report.json').write_text(json.dumps(report, indent=1))
print(json.dumps(report['checks'], indent=1))
print('ALL PASS' if all(report['checks'].values()) else 'FAILED')
