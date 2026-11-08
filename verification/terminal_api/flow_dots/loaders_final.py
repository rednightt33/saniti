"""EXEC-FLOW-NEW-3 (user 2026-11-08: "untuk bagian loaders, boleh kirimkan versi static HTML-nya"): a static picture of
the decided Loaders design (option E, resizable edges, broker codes at the cost lines' ends) on the stand-in BBRI data
of loaders_bbri.json (loaders_data.py). Usage: python3 loaders_final.py  -> loaders_final.html (no script)."""
import json
D = json.load(open('loaders_bbri.json'))
LC = ['#8b5a2b', '#65a30d', '#475569']
MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
day = lambda d: f'{int(d[8:])} {MON[int(d[5:7]) - 1]}'
W, H = 1180, 680; L, R, T, B = 70, 90, 30, 40
ohlc = D['ohlc']; n = len(ohlc)
lo = min(r[3] for r in ohlc); hi = max(r[2] for r in ohlc)
for r in D['load'][:3]:
    for c in r['cost']:
        if c: lo = min(lo, c); hi = max(hi, c)
lo -= (hi - lo) * 0.75; hi += (hi - lo) * 0.04        # room under the prices for the box
X = lambda i: L + (i + 0.5) * (W - L - R) / n
Y = lambda v: T + (hi - v) * (H - T - B) / (hi - lo)
svg = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="BBRI price with the loaders cost lines">']
v = int(lo // 100 + 1) * 100
while v < hi:
    y = Y(v); svg.append(f'<line x1="{L}" x2="{W-R}" y1="{y:.1f}" y2="{y:.1f}" class="grid"/><text x="{L-8}" y="{y+4:.1f}" class="ax" text-anchor="end">{v:,}</text>'); v += 100
for i in range(0, n, 10):
    svg.append(f'<text x="{X(i):.1f}" y="{H-14}" class="ax" text-anchor="middle">{day(ohlc[i][0])}</text>')
bw = max(2, (W - L - R) / n * 0.6)
for i, (d, o, h, l, c) in enumerate(ohlc):
    col = 'var(--up)' if c >= o else 'var(--down)'; x = X(i)
    svg.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{Y(h):.1f}" y2="{Y(l):.1f}" stroke="{col}"/>')
    y1, y2 = sorted((Y(o), Y(c))); svg.append(f'<rect x="{x-bw/2:.1f}" y="{y1:.1f}" width="{bw:.1f}" height="{max(1,y2-y1):.1f}" fill="{col}"/>')
ends = []
for j, r in enumerate(D['load'][:3]):
    pts = [(X(i), Y(c)) for i, c in enumerate(r['cost']) if c]
    svg.append('<polyline fill="none" stroke="%s" stroke-width="2" points="%s"/>' % (LC[j], ' '.join(f'{x:.1f},{y:.1f}' for x, y in pts)))
    ends.append([pts[-1][0], pts[-1][1], r['b'], LC[j]])
ends.sort(key=lambda e: e[1])
for k in range(1, len(ends)):                        # the labels stay at least 20 px apart
    if ends[k][1] - ends[k-1][1] < 20: ends[k][1] = ends[k-1][1] + 20
for x, y, b, col in ends:
    svg.append(f'<rect x="{x+6:.1f}" y="{y-10:.1f}" rx="4" width="{16+8*len(b)}" height="20" fill="{col}"/><text x="{x+13:.1f}" y="{y+4:.1f}" class="lbl">{b}</text>')
lc = ohlc[-1][4]; y = Y(lc)
svg.append(f'<line x1="{L}" x2="{W-R}" y1="{y:.1f}" y2="{y:.1f}" stroke="var(--down)" stroke-dasharray="2 3" opacity=".6"/><rect x="2" y="{y-10:.1f}" width="{L-6}" height="20" rx="3" fill="var(--down)"/><text x="{L-8}" y="{y+4:.1f}" class="lbl" text-anchor="end">{lc:,}</text></svg>')
nf = lambda v: ('+' if v > 0 else '−' if v < 0 else '') + (f'{abs(v)/1e6:.1f}M' if abs(v) >= 1e6 else f'{abs(v)/1e3:.1f}K')
pct = lambda v: ('+' if v > 0 else '−' if v < 0 else '') + f'{abs(v):.1f}%'
row = lambda r, cls, col=None: (f'<tr class="{cls}"><td><span class="b" style="--c:{col or "var(--border)"}">{r["b"]}</span></td><td class="{"up" if r["lots"] > 0 else "down"}">{nf(r["lots"])}</td>'
    f'<td>{r["avg"]:,.0f}</td><td class="{"up" if r["dist"] > 0 else "down"}">{pct(r["dist"])}</td><td>{r["buyDays"]}/{r["days"]}</td></tr>')
share = 100 * sum(r['lots'] for r in D['load'][:3]) / D['positive']
box = f'''<div class="box" style="left:{L+14}px;bottom:{B+10}px">
 <div class="hd"><b>Loaders</b><span class="when">{day(D["start"])} – {day(D["end"])}</span><span class="acts"><span class="btn on">In view</span><span class="btn">Select on chart</span></span></div>
 <div class="ctl"><span class="seg"><span class="btn">Loaders</span><span class="btn">Sellers</span><span class="btn on">Both</span></span><span class="seg"><span class="btn on">Top 3</span><span class="btn">Top 5</span><span class="btn">Top 10</span></span></div>
 <table><thead><tr><th>Broker</th><th>Net lot</th><th>Avg buy</th><th>vs price</th><th>Buy days</th></tr></thead><tbody>
 <tr class="grp"><td colspan="5">Top 3 loaders (net buyers)</td></tr>{"".join(row(r, "load", LC[j]) for j, r in enumerate(D["load"][:3]))}
 <tr class="grp"><td colspan="5">Top 3 net sellers</td></tr>{"".join(row(r, "sell") for r in D["sell"][:3])}</tbody></table>
 <p class="foot">Top 3 hold {share:.1f}% of total accumulation</p>
 <span class="edge l"></span><span class="edge r"></span><span class="edge bt"></span><span class="grip"></span></div>'''
legend = " &nbsp;".join(f'<span style="color:{LC[j]}">{r["b"]} {r["cost"][-1]:,.0f}</span>' for j, r in enumerate(D["load"][:3]))
css = open('loaders_final.css').read()
html = f'''<!doctype html><html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Loaders Final Design</title><style>{css}</style></head><body><main>
<h1>Loaders (FL51) · desain akhir</h1>
<p class="lead">Gambar statis dari keputusan 2026-11-08, data BBRI board Regular {day(D["start"])} – {day(D["end"])} 2026 (60 sesi, harga terakhir {D["last"]:,}). Opsi "Cost lines on the price chart" menyala.</p>
<ul><li><b>Opsi E</b>: tab Loaders · Sellers · Both dan Top 3 · 5 · 10, dengan judul kelompok di dalam tabel.</li>
<li><b>Ubah ukuran</b>: tepi kiri, kanan dan bawah (tanda biru) serta sudut kanan bawah bisa ditarik; kotak digeser dari kepalanya; ukuran dan letak diingat.</li>
<li><b>Kode broker di ujung garis</b> harga pokok (warna garisnya), tidak lagi di sumbu Y kiri.</li></ul>
<div class="chart"><span class="leg">Loaders (Regular, from {day(D["start"])} 2026, to {day(D["end"])} 2026) &nbsp;<b>{legend}</b></span>{"".join(svg)}{box}</div>
<div class="notes"><div class="note"><b>Garis harga pokok</b>Harga rata-rata beli berjalan tiap penimbun sejak awal periode; labelnya di ujung kanan garis, ditumpuk agar tidak bertabrakan.</div>
<div class="note"><b>Klik kode broker di kotak</b>Menambah broker itu ke Broker Inventory (panel kanan dan FL52), dapat dibatalkan dengan Ctrl+Z.</div>
<div class="note"><b>Periode</b>"In view" = candle pertama sampai terakhir yang terlihat; "Select on chart" = pilih rentang seperti Alt+B.</div></div>
</main></body></html>'''
open('loaders_final.html', 'w').write(html)
