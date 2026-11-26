"""EXEC-MU-ACCOUNTS 3e, the example mode (ERRORS M527): the promotion's smoke of the examples as a visitor, in a real
browser, from outside (LIVE_PROMOTION.md, the example mode's row, step (4)). No credentials: a visitor only.

For each data page (the tabs of apps/edge-bff/app/examples.py TABS), it opens /<tab> and checks:
- the shell shows the page's example: the page's app in its frame with ?example=1, under the note naming its date;
- the page read only the example's routes (/api/v1/examples/<tab>/...), never its live routes (/api/v1/<tab>/...);
- a click on the page opens the shell's sign-in box ("Sign in to open <tab>"): for the Market Overview a time control
  (its period buttons), which is locked, while its other controls work; for Sector Analysis (EXEC-SECTOR-ANALYSIS
  decision J) its second internal tab (role=tab) switches without the box, and its first other control asks for it;
- the Watchlist shows the LQ45 list, the prices' and the broker data's date pills.
Prints one OUT line per tab ({tab, note, files, live_reads, box}) and VERDICT OK or VERDICT FAILED with the reasons.

Run: python3 verification/edge_multiuser/live_smoke/example_smoke.py https://app.edgefinance.id [--png <dir>]
     (EDGE_TEST_CHROMIUM names a Chromium where Playwright's own is not installed)
"""
import json
import os
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[3]
TABS = dict(re.findall(r"'(\w+)': '([^']+)'", re.search(
    r'^TABS = \{([^}]*)\}', (ROOT / 'apps' / 'edge-bff' / 'app' / 'examples.py').read_text(), re.M).group(1)))
NAMES = {'overview': 'Overview'}                     # the rail's name where it differs from the example's label


def check(page, origin, tab, label, png):
    name = NAMES.get(tab, label)
    seen = []
    page.on('request', lambda r: seen.append(r.url))
    page.goto(f'{origin}/{tab}', wait_until='domcontentloaded')
    frame_el = page.locator(f'main.example-page[data-example-tab="{tab}"] iframe.terminal-frame')
    frame_el.wait_for(timeout=30000)
    out, fail = {'tab': tab}, []
    if not (frame_el.get_attribute('src') or '').endswith(f'/{tab}-app/?example=1'):
        fail.append('the frame is not the example')
    note = page.locator('.example-bar').inner_text().replace('\xa0', ' ')
    out['note'] = ' '.join(note.split())[:120]
    if 'with the data of' not in note:
        fail.append('no date in the note')
    frame = page.frame_locator('main.example-page iframe.terminal-frame')
    frame.locator('body').wait_for(timeout=30000)
    page.wait_for_timeout(4000)                       # the page draws from its files
    body = frame.locator('body').inner_text().replace('\xa0', ' ')
    if tab == 'watchlist':
        if 'LQ45' not in body or 'Prices to' not in body or 'Broker data to' not in body:
            fail.append('the Watchlist lacks its list or its date pills')
    paths = [u.split('?')[0].replace(origin, '') for u in seen if u.startswith(origin)]
    out['files'] = sorted({p.rsplit('/', 1)[1] for p in paths if p.startswith(f'/api/v1/examples/{tab}/file/')})
    out['live_reads'] = sorted({p for p in paths if p.startswith(f'/api/v1/{tab}/')})
    if not out['files']:
        fail.append('no example file read')
    if out['live_reads']:
        fail.append(f'live routes read: {out["live_reads"]}')
    if tab == 'sector':
        # decision J (the user 2026-11-26: "Dia bisa pilih tab 1, 2, 3, 4, 5"): the page's five tabs switch, no box
        second = frame.locator('[role="tab"]').nth(1)
        second.click()
        page.wait_for_timeout(1500)
        if page.locator('.locked-dialog').count():
            fail.append('an internal tab opened the sign-in box')
            page.keyboard.press('Escape')
        elif second.get_attribute('aria-selected') != 'true':
            fail.append('the second internal tab is not selected after its click')
    clickable = 'button:visible:not([disabled]):not([aria-disabled="true"])'
    target = frame.locator('.seg button[data-v="5D"], .seg button[data-k="5D"], .seg button[data-p="5D"]').first \
        if tab == 'overview' else frame.locator(f'{clickable}:not([role="tab"])').first if tab == 'sector' \
        else frame.locator(clickable).first
    target.click()
    box = page.locator('.locked-dialog')
    try:
        box.wait_for(timeout=10000)
        out['box'] = ' '.join(box.inner_text().split())[:80]
        if f'Sign in to open {name}' not in out['box']:
            fail.append(f'the box says {out["box"]!r}')
    except Exception:  # noqa: BLE001 - reported as a failure of the smoke
        fail.append('no sign-in box after a click')
    if png:
        page.screenshot(path=str(Path(png) / f'example-{tab}.png'))
    out['ok'] = not fail
    print('OUT ' + json.dumps(out), flush=True)
    return [f'{tab}: {f}' for f in fail]


def main():
    origin = sys.argv[1].rstrip('/')
    png = sys.argv[sys.argv.index('--png') + 1] if '--png' in sys.argv else None
    failures = []
    with sync_playwright() as pw:
        # the browser the tests use where Playwright's own is not installed (EDGE_TEST_CHROMIUM, as tests/e2e_people.py)
        browser = pw.chromium.launch(executable_path=os.environ.get('EDGE_TEST_CHROMIUM') or None)
        try:
            for tab, label in TABS.items():
                ctx = browser.new_context(viewport={'width': 1440, 'height': 900}, device_scale_factor=1)
                try:
                    failures += check(ctx.new_page(), origin, tab, label, png)
                except Exception as e:  # noqa: BLE001 - one tab's failure does not hide the others
                    failures.append(f'{tab}: {type(e).__name__}: {str(e).splitlines()[0][:160]}')
                finally:
                    ctx.close()
        finally:
            browser.close()
    print('VERDICT OK' if not failures else f'VERDICT FAILED {failures}', flush=True)
    sys.exit(1 if failures else 0)


if __name__ == '__main__':
    main()
