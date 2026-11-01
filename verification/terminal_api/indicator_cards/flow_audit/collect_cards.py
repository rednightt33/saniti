"""Flow audit page, step 1 (user 2026-11-01): renders every Flow indicator card in a local Terminal with dev data and saves
their HTML (AUDIT_OUT). Needs a local Terminal build whose main.ts exposes window.__ctx and window.__card = { renderCard,
itemOfDef } (debug build only, never deployed), the edge-bff app root, Playwright Chromium and EDGE_TEST_POSTGRES_URL.
  AUDIT_OUT=cards.json python3 collect_cards.py <app root> <port> <TICKER>; then build_html.py."""
"""EXEC-BROKER-FULL measurement: main-thread JS heap and panel state for one ticker on the D chart, with a given
edge-bff copy (its static/terminal-app). Usage: python measure.py <app root (contains apps/edge-bff)> <port> <TICKER>"""
import json, os, subprocess, sys, threading, time, urllib.error, urllib.request, uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
import psycopg, uvicorn

REPO = Path('/home/user/saniti')
app_root = Path(sys.argv[1]); port = int(sys.argv[2]); ticker = sys.argv[3]
sys.path.insert(0, str(app_root / 'apps/edge-bff'))
from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.security import password_verifier  # noqa: E402
v = json.loads(subprocess.run(['railway', 'variable', 'list', '-s', 'terminal-api', '-e', 'dev', '--json'],
                              capture_output=True, text=True, timeout=60, check=True).stdout)
admin = os.environ['EDGE_TEST_POSTGRES_URL']
name = 'edge_m_' + uuid.uuid4().hex[:8]
p = urlsplit(admin); db = urlunsplit((p.scheme, p.netloc, '/' + name, p.query, p.fragment))
with psycopg.connect(admin, autocommit=True) as c:
    c.execute(f'CREATE DATABASE "{name}"')
try:
  with psycopg.connect(db, autocommit=True) as c:
    for m in ('20261008_002_create_edge_bff.sql', '20261012_008_edge_bff_conversation_hidden.sql', '20261024_002_edge_bff_conversation_branch.sql'):
        c.execute((REPO / 'database/migrations' / m).read_text())
except BaseException:
    with psycopg.connect(admin, autocommit=True) as c:
        c.execute(f'DROP DATABASE "{name}" WITH (FORCE)'); c.execute('DROP ROLE IF EXISTS edge_bff_runtime')
    raise
settings = Settings(database_url=db, orc_url='http://orc.invalid', orc_key='local', owner='local-owner', login='owner',
                    password_verifier=password_verifier('local-live-check'), session_secret='local-live-secret-' * 3,
                    origin=f'http://127.0.0.1:{port}', environment='local', secure_cookie=False, worker_enabled=False,
                    terminal_url='https://' + v['RAILWAY_PUBLIC_DOMAIN'], terminal_proxy_key=v['TERMINAL_PROXY_KEY'])
server = uvicorn.Server(uvicorn.Config(create_app(settings), host='127.0.0.1', port=port, log_level='warning'))
threading.Thread(target=server.run, daemon=True).start()
while not server.started: time.sleep(.05)
from playwright.sync_api import sync_playwright  # noqa: E402
rep = {}
try:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=os.environ.get('EDGE_TEST_CHROMIUM') or None)
        page = browser.new_context(viewport={'width': int(os.environ.get('VW','1600')), 'height': int(os.environ.get('VH','1000'))}).new_page(); errors = []
        cons = []; page.on('console', lambda m: cons.append(m.type + ': ' + m.text[:300]))
        def resp(r):
            if '/bundle' in r.url:
                try: cons.append(f'BUNDLE {r.status} req={r.request.post_data[:200]} body={r.text()[:400]}')
                except Exception as e: cons.append(f'BUNDLE {r.status} ?{e}')
            elif '/api/' in r.url or r.status >= 400: cons.append(f'HTTP {r.status} {r.url[:140]}')
        page.on('response', resp)
        page.on('pageerror', lambda e: errors.append((round(time.time()-T0[0],1), str(e), (getattr(e,'stack','') or '')[:600])))
        T0 = [time.time()]
        def bucket(route):
            for attempt in range(3):
                try:
                    with urllib.request.urlopen(route.request.url, timeout=60) as r:
                        st, body, ct = r.status, r.read(), r.headers.get('content-type', 'application/octet-stream')
                    break
                except urllib.error.HTTPError as e:
                    st, body, ct = e.code, e.read(), 'text/plain'; break
                except Exception:
                    if attempt == 2: raise
            route.fulfill(status=st, body=body, headers={'content-type': ct, 'access-control-allow-origin': f'http://127.0.0.1:{port}'})
        page.route('https://*.t3.storageapi.dev/**', bucket)
        page.request.post(f'http://127.0.0.1:{port}/api/v1/auth/sign-in', headers={'Origin': settings.origin}, data={'login': 'owner', 'password': 'local-live-check'})
        page.goto(f'http://127.0.0.1:{port}/terminal-app/')
        out = {}
        page.evaluate("localStorage.clear(); localStorage.setItem('ml.symbol', TICKER); localStorage.setItem('ml.tf', 'D')".replace('TICKER', repr(ticker)))
        page.goto(f'http://127.0.0.1:{port}/terminal-app/', wait_until='load', timeout=120000)
        page.wait_for_function("() => window.__ctx && window.__ctx.N > 0 && window.__ctx.flowRows && window.__ctx.flowRows.n > 0 && window.__card", timeout=180000)
        page.wait_for_timeout(3000)
        out['cards'] = page.evaluate("""() => { const c = window.__ctx, K = window.__card; c.lastTipIdx = c.N - 1;
          const defs = window.marketLabIndicators.defs.filter(d => d.flow && /^FL\\d\\d$/.test(d.id)).sort((a, b) => a.id < b.id ? -1 : 1);
          const res = [], rows = [];
          for (const d of defs) {
            const item = K.itemOfDef(d), src = c.Ind.cardSource(d.id), host = document.createElement('div');
            document.body.appendChild(host); K.renderCard(host, c, item, src);
            const sel = host.querySelector('[data-out]'), outs = sel ? [...sel.options].map(o => [o.value, o.textContent]) : [[null, null]];
            const parts = [];
            for (const [k, label] of outs) {
              if (k !== null) { const s = host.querySelector('[data-out]'); s.value = k; s.dispatchEvent(new Event('change')) }
              const cl = host.querySelector('.icd').cloneNode(true);
              cl.querySelector('.icd-tabs')?.remove(); cl.querySelectorAll('.icd-nav,[data-reset],.icd-out').forEach(e => e.remove());
              cl.querySelectorAll('[data-pane]').forEach((p, j) => { p.hidden = false; p.insertAdjacentHTML('beforebegin', `<h5 class="aud-sec">${['Kalkulator', 'Grafik', 'Langkah'][j]}</h5>`) });
              cl.querySelectorAll('input').forEach(i => { i.setAttribute('disabled', ''); i.setAttribute('value', i.value) });
              if (k !== null) cl.querySelector('.icd-h h4').insertAdjacentHTML('beforeend', ` <span class="aud-out">output: ${label}</span>`);
              parts.push(cl.outerHTML);
              /* the same card as data, for the Excel (user 2026-11-01: "Excelnya mana?"): the explainer the card shows, and
                 what the card writes (value, filled formula, parameters, cautions), on the same candle */
              const series = d.compute(src.params) || {}, out = k ?? Object.keys(series).find(x => !x.startsWith('_') && Array.isArray(series[x]));
              let t = c.N - 1; while (t >= 0 && !(typeof series[out]?.[t] === 'number' && isFinite(series[out][t]))) t--;
              const e = t >= 0 && d.explain ? d.explain(src.params, t, out) : null, a = Math.max(0, t - 79);
              const txt = sel => [...host.querySelectorAll(sel)].map(x => x.innerText.trim());
              rows.push({ id:d.id, name:d.name, family:item.group, unit:item.unit, output:label ?? out, date:c.dates[t], value:series[out]?.[t] ?? null,
                big:host.querySelector('[data-big]')?.textContent, filled:host.querySelector('[data-expr]')?.textContent,
                expr:e?.expr, span:e?.span || null, terms:(e?.terms || []).map(x => [x.key, x.label, x.value, x.unit]),
                steps:(e?.steps || []).map(st => ({ title:st.title, text:st.text, table:st.table || null })),
                params:[...host.querySelectorAll('[data-pane="2"] .icd-notes table tbody tr')].map(r => [...r.cells].map(x => x.innerText.trim())),
                formula:host.querySelector('.icd-formula')?.innerText.trim(), cautions:txt('[data-pane="2"] .icd-notes ul li'),
                chart:Array.from({ length:t - a + 1 }, (_, j) => [c.dates[a + j], series[out]?.[a + j] ?? null, c.ohlc[a + j]?.close ?? null]) });
            }
            host.remove();
            res.push({ id:d.id, name:d.name, family:item.group, html:parts.join('') });
          }
          return { cards:res, rows, ticker:c.SYMBOL, last:c.dates[c.N - 1], broker:c.dates[c.brokerEnd] };
        }""")
        out['errors'] = errors
        json.dump(out, open(os.environ['AUDIT_OUT'], 'w'), default=str); print('{"saved": true}'); sys.stdout.flush()
        browser.close()
finally:
    server.should_exit = True; time.sleep(.5)
    with psycopg.connect(admin, autocommit=True) as c:
        c.execute(f'DROP DATABASE "{name}" WITH (FORCE)'); c.execute('DROP ROLE IF EXISTS edge_bff_runtime')
print(json.dumps(rep, ensure_ascii=False))
