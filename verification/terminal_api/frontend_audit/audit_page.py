"""Front-end audit helper: a signed-in Terminal page on the local edge-bff of audit_server.py.

    from playwright.sync_api import sync_playwright
    import sys; sys.path.insert(0, '/home/user/saniti/verification/terminal_api/frontend_audit')
    from audit_page import open_terminal, switch_ticker
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path='/opt/pw-browsers/chromium')
        page, errors = open_terminal(browser, 'TLKM', (1600, 1000))
        page.evaluate("window.marketLabIndicators.add('FL24')")
        page.screenshot(path='/tmp/.../x.png')

The browser downloads the data files from the private bucket by presigned URLs; the bucket answers CORS only for the
real site, so this routes them through Python (the same bytes). `errors` collects page errors and console errors.
Use only the tickers of the brief (the account has hourly ticker and file quotas).
"""
import json
import urllib.error
import urllib.request

PORT = 18770
ORIGIN = f'http://127.0.0.1:{PORT}'
READY = ("() => document.querySelector('#flowSummary .flow-stat') && (document.getElementById('flowNote').hidden || "
         "!/^Loading/.test(document.getElementById('flowNote').textContent))")


def _bucket(route):
    for attempt in range(3):
        try:
            with urllib.request.urlopen(route.request.url, timeout=60) as r:
                status, body, ctype = r.status, r.read(), r.headers.get('content-type', 'application/octet-stream')
            break
        except urllib.error.HTTPError as e:
            status, body, ctype = e.code, e.read(), 'text/plain'; break
        except Exception:
            if attempt == 2:
                raise
    route.fulfill(status=status, body=body, headers={'content-type': ctype, 'access-control-allow-origin': ORIGIN})


def open_terminal(browser, ticker='TLKM', viewport=(1600, 1000), tf='D', panels_open=True, wait_full_history=True,
                  color_scheme='light'):
    """A new browser context signed in, the Terminal on `ticker` and timeframe `tf` (D, W, M), side panels open."""
    ctx = browser.new_context(viewport={'width': viewport[0], 'height': viewport[1]}, color_scheme=color_scheme)
    page = ctx.new_page()
    errors = []
    page.on('pageerror', lambda e: errors.append('pageerror: ' + str(e) + ' | ' + (e.stack or '')[:400]))
    page.on('console', lambda m: errors.append('console: ' + m.text) if m.type == 'error' else None)
    page.route('https://*.t3.storageapi.dev/**', _bucket)
    page.request.post(f'{ORIGIN}/api/v1/auth/sign-in', headers={'Origin': ORIGIN},
                      data={'login': 'owner', 'password': 'local-live-check'})
    page.goto(f'{ORIGIN}/terminal-app/')
    keep = '0' if panels_open else '1'
    page.evaluate(f"""() => {{ localStorage.setItem('ml.symbol', {json.dumps(ticker)}); localStorage.setItem('ml.tf', {json.dumps(tf)});
      for (const k of ['ml.broker.collapsed', 'ml.stats.collapsed', 'ml.flow.collapsed']) localStorage.setItem(k, '{keep}') }}""")
    page.goto(f'{ORIGIN}/terminal-app/', wait_until='load', timeout=120000)
    _wait(page, wait_full_history)
    return page, errors


def switch_ticker(page, ticker, wait_full_history=True):
    """Open another ticker in the same page (a reload, as the symbol search does)."""
    page.evaluate(f"localStorage.setItem('ml.symbol', {json.dumps(ticker)})")
    page.reload(wait_until='load')
    _wait(page, wait_full_history)


def _wait(page, full):
    page.wait_for_function(READY, timeout=180000)
    if full:   # the whole broker history (the Flow indicators recompute when it arrives)
        page.wait_for_function("() => window.__flowAll === true || document.getElementById('flowNote').hidden", timeout=240000)
    page.wait_for_timeout(1500)
