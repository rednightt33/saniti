#!/usr/bin/env python3
"""Indicator picker and five indicator-card designs for the user's review (request 2026-10-31: the Terminal's indicator
menu like TradingView's "Indicators, metrics, and strategies", a tooltip, and cards that explain how an indicator works
with an example of how every number is derived; "kasih saya 5 contoh dalam satu HTML buat saya pilih", with the
attached design spec).

Nothing is typed here about which indicators exist: the list comes from the Terminal's registries
(apps/edge-bff/terminal/src/data/indRegistry.json and flowRegistry.json). The worked example is FL24 Bandar Balance · %
on BBCA (fl24_bbca_example.json: real broker rows, equal to the independent oracle). The page uses the user's design
spec (edge-design-spec.css, inlined) and works offline.

  python3 verification/terminal_api/indicator_cards/build_review.py <out.html>
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
TERM = ROOT / 'apps/edge-bff/terminal/src/data'


def catalog():
    out = []
    for r in json.loads((TERM / 'indRegistry.json').read_text()):
        out.append({'id': r['id'], 'name': r['name'], 'group': r['cat'].replace('PriceVolume', 'Price & Volume'),
                    'kind': 'Technical', 'place': 'Overlay' if r.get('zone') == 'overlay' else 'Panel',
                    'unit': r.get('unit') or '', 'tip': r.get('tip') or ''})
    flow = json.loads((TERM / 'flowRegistry.json').read_text())
    for r in flow['indicators']:
        out.append({'id': r['id'], 'name': r['name'], 'group': r['family'], 'kind': 'Flow',
                    'place': 'Overlay' if r.get('place') == 'overlay' else 'Panel', 'unit': r.get('unit') or '',
                    'tip': r.get('tip') or ''})
    return out, flow['families']


def main(out):
    css = (HERE / 'edge-design-spec.css').read_text()
    items, families = catalog()
    tech = []
    for i in items:
        if i['kind'] == 'Technical' and i['group'] not in tech:
            tech.append(i['group'])
    ex = json.loads((HERE / 'fl24_bbca_example.json').read_text())
    html = (HERE / 'review_template.html').read_text()
    html = (html.replace('/*__SPEC_CSS__*/', css)
                .replace('"__ITEMS__"', json.dumps(items, ensure_ascii=False))
                .replace('"__TECH_GROUPS__"', json.dumps(tech))
                .replace('"__FLOW_GROUPS__"', json.dumps(families))
                .replace('"__EXAMPLE__"', json.dumps(ex, ensure_ascii=False)))
    Path(out).write_text(html)
    print(f'{out}: {len(items)} indicators, {len(html):,} bytes')


if __name__ == '__main__':
    main(sys.argv[1])
