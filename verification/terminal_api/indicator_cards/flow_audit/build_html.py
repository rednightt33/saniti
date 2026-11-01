#!/usr/bin/env python3
"""Flow indicator audit page (user 2026-11-01: "1 file HTML saja untuk 39 indikator flow"; "Itu HTML akan menjadi source
bagaimana saya mengaudit indikator-indikator kita"): every Flow indicator's "How it works" card exactly as the Terminal
renders it, with its three parts open (Kalkulator, Grafik, Langkah), on one ticker and its last broker date.

The cards are not rebuilt here: collect_cards.py renders them in the Terminal itself (app/indCard.ts renderCard, the
same explainers whose numbers equal the chart's, tests/calc/explain.test.ts) and saves their HTML; this script adds the
Terminal's own card CSS (styles/terminal.css), a table of contents and the provenance.

  python3 build_html.py <cards.json> <out.html> <commit>
"""
import html
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
CSS = (ROOT / 'apps/edge-bff/terminal/src/styles/terminal.css').read_text()


def card_css():
    """the Terminal's tokens (:root blocks) and every rule of the card (.icd), as the page uses them"""
    roots = re.findall(r':root\{[^}]*\}', CSS)
    rules = [line for line in CSS.splitlines() if line.startswith('.icd') or line.startswith('.icd-')]
    return '\n'.join(roots + rules)


def main(src, out, commit):
    d = json.loads(Path(src).read_text())['cards']
    cards, families = d['cards'], []
    for c in cards:
        if c['family'] not in families:
            families.append(c['family'])
    toc = ''.join(f'<li><b>{html.escape(f)}</b>: ' + ', '.join(f'<a href="#{c["id"]}">{c["id"]} {html.escape(c["name"])}</a>'
                  for c in cards if c['family'] == f) + '</li>' for f in families)
    body = ''.join(f'<section class="aud-card" id="{c["id"]}">{c["html"]}</section>' for c in cards)
    made = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    page = f"""<!doctype html><html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Audit Indikator Flow — {html.escape(d['ticker'])}</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap">
<style>
{card_css()}
html,body{{margin:0;background:var(--bg,#fafafa);color:var(--text,#171717);font:400 13px/1.5 Inter,"Segoe UI",system-ui,sans-serif;font-variant-numeric:tabular-nums}}
main{{max-width:760px;margin:0 auto;padding:24px 16px 64px;display:grid;gap:16px}}
h1{{margin:0;font-size:22px;font-weight:600;letter-spacing:-.01em}}
.aud-meta{{font-size:12.5px;color:var(--text-2);line-height:1.6}}
.aud-meta code{{font-size:12px}}
.aud-toc{{margin:0;padding-left:18px;font-size:12.5px;line-height:1.7}}
.aud-toc a{{color:var(--accent,#0070f3);text-decoration:none}}
.aud-card{{background:var(--surface,#fff);border:1px solid var(--border,#eaeaea);border-radius:12px;padding:16px 18px;scroll-margin-top:12px}}
.aud-sec{{margin:14px 0 2px;padding-top:10px;border-top:1px solid var(--border,#eaeaea);font-size:11px;font-weight:600;letter-spacing:.05em;text-transform:uppercase;color:var(--text-3,#8f8f8f)}}
.aud-out{{font-size:12px;font-weight:500;color:var(--text-3,#8f8f8f)}}
.icd-pane[hidden]{{display:grid}}
.icd-field input[type=range]{{opacity:.7}}
@media print{{.aud-card{{break-inside:avoid}}}}
</style></head><body><main>
<header class="aud-head"><h1>Audit Indikator Flow</h1>
<p class="aud-meta">{len(cards)} indikator Flow Terminal, masing-masing dengan kartu "How it works" persis seperti di Terminal
(Kalkulator, Grafik, Langkah, lalu rumus, parameter dan hal yang perlu diwaspadai).<br>
Saham <b>{html.escape(d['ticker'])}</b>, grafik harian, parameter default Terminal, candle terakhir yang bernilai
(data broker terakhir <b>{html.escape(d['broker'])}</b>; harga sampai {html.escape(d['last'])}).<br>
Angka kartu dihitung oleh kode yang sama dengan chart dan dites sama dengan chart di setiap candle
(<code>apps/edge-bff/terminal/tests/calc/explain.test.ts</code>). Kode: commit <code>{html.escape(commit)}</code>; dibuat {made} dari data dev.</p></header>
<nav><ul class="aud-toc">{toc}</ul></nav>
{body}
</main></body></html>
"""
    Path(out).write_text(page)
    print(f'{out}: {len(cards)} indicators, {len(page):,} bytes')


if __name__ == '__main__':
    main(*sys.argv[1:4])
