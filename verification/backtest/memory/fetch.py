"""The published files of some tickers, and the reference lists, from Railway dev for measure.mjs (ERRORS M463): signed
in as the owner through edge-bff's Terminal proxy (/api/terminal/v1/bundle with packs, as the worker asks; the
reference lists followed to their file), the same way e2e_dev.py signs in (credentials read from Railway into memory,
never printed or saved). Read only. IHSG is always added (a preview and a run read it).

  RAILWAY_TOKEN=dummy EDGE_TEST_CHROMIUM=<chrome> python fetch.py OUT_DIR BBRI,TLKM,...

(the session proxy injects the Railway credential; a dummy value lets it). OUT_DIR gets one folder per ticker
(bundle.json without its URLs, and the files) and ref-brokers.json, ref-tickers.json (decoded)."""
import gzip
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import e2e_dev as e2e  # noqa: E402


def main():
    out, tickers = Path(sys.argv[1]), [t for t in sys.argv[2].split(',') if t]
    if 'IHSG' not in tickers:
        tickers.append('IHSG')
    out.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright
    v = e2e.service_vars('edge-bff')
    base = (v.get('EDGE_PUBLIC_ORIGIN') or ('https://' + v['RAILWAY_PUBLIC_DOMAIN'])).rstrip('/')
    login, password = v.get('EDGE_LOGIN'), v.get('EDGE_INITIAL_PASSWORD')
    del v
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=os.environ.get('EDGE_TEST_CHROMIUM') or None,
                                     proxy={'server': os.environ['HTTPS_PROXY']} if os.environ.get('HTTPS_PROXY') else None)
        ctx = browser.new_context()
        r = ctx.request.post(base + '/api/v1/auth/sign-in', data=json.dumps({'login': login, 'password': password}),
                             headers={'Content-Type': 'application/json', 'Origin': base})
        del password
        if r.status != 200:
            raise SystemExit(f'sign-in failed ({r.status})')
        api = e2e.Api(ctx, base, r.json()['csrf_token'], time.sleep)
        for name in ('brokers', 'tickers'):
            grant = ctx.request.get(f'{base}/api/terminal/v1/reference/{name}').json()
            doc = json.loads(gzip.decompress(ctx.request.get(grant['url']).body()))
            (out / f'ref-{name}.json').write_text(json.dumps(doc))
        for t in tickers:
            code, ans = api.post('/api/terminal/v1/bundle', {'ticker': t, 'datasets': ['price', 'broker', 'events'], 'packs': True})
            if code != 200:
                raise SystemExit(f'{t}: bundle {code}')
            (out / t).mkdir(exist_ok=True)
            size = 0
            for ds, d in (ans.get('datasets') or {}).items():
                for f in d.get('files') or []:
                    body = ctx.request.get(f.pop('url')).body()
                    (out / t / f"{ds}-{f.get('pack') or f.get('year') or 'all'}.gz").write_bytes(body)
                    size += len(body)
            (out / t / 'bundle.json').write_text(json.dumps(ans))
            print(t, size, 'bytes')
        browser.close()


if __name__ == '__main__':
    main()
