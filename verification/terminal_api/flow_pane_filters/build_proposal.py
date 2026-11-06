"""Proposal (2026-11-06, user: "untuk semua tipe indikator flow, kita mau tambahkan juga [tombol seperti Broker Inventory]
... list down all flow indicators, serta filter yang bisa ditambahkan ... Kalau ada broker scope, maka ada box lain juga bisa
muncul untuk user input N"): which pane-row buttons each Flow indicator gets, derived from its registry parameters, not
listed by hand. Usage: python3 -I build_proposal.py ../../../apps/edge-bff/terminal/src/data/flowRegistry.json out.html"""
import html, json, sys

reg = json.load(open(sys.argv[1]))
HIDDEN = {'FL07', 'FL35', 'FL36'}          # MENU_HIDDEN (indMenu.ts): not offered in the menu
SCOPE = {'all': 'All brokers', 'selected': 'Selected', 'topn': 'Top-N'}
PLACE = {'pane': 'Panel sendiri', 'price': 'Di atas harga', 'marker': 'Tanda di bawah candle'}


def dflt(p):
    d = p.get('default')
    if isinstance(d, list):
        return 'All' if p.get('options') and len(d) == len(p['options']) else ', '.join(d)
    if p['kind'] == 'select':
        o = next((x for x in p.get('options', []) if (x[0] if isinstance(x, list) else x) == d), None)
        return o[1] if isinstance(o, list) else d
    return {'top3_net_buy_20': 'Top 3 net buyers', 'auto_c': '2 net buyers + 1 net seller (layar)'}.get(d, d)


rows = []
for x in reg['indicators']:
    if x['id'] in HIDDEN:
        continue
    P = {p['key']: p for p in x['params'] if p['kind'] != 'fixed'}
    filt, inter, note = [], [], []
    if x['id'] == 'FL46':                   # two sides, each with its own scope, boards and investors
        filt = ['— (tetap di dialog)']
        inter = ['Pembilang dan penyebut masing-masing punya cakupan, papan dan investor: 10 tombol terlalu banyak untuk satu baris']
        note = ['Usul: judul baris sudah menyebut kedua sisi; ubah lewat ⚙']
    else:
        if 'scope' in P:
            mx, t = P.get('brokers', {}).get('max'), P.get('top', {})
            ranks = [o[1] if isinstance(o, list) else o for o in P.get('rank', {}).get('options', [])]
            filt.append(f"<b>Broker</b> ({dflt(P['scope'])})")
            if 'rank' in P:
                filt.append(f"<b>Top N</b> ({dflt(P['top'])}) + <b>Rank by</b> ({dflt(P['rank'])}) — hanya saat Top-N")
            inter.append(f"Broker → pilih <i>All brokers / Selected / Top-N</i>")
            inter.append(f"<i>Top-N</i> → muncul kotak <b>N</b> ({t.get('min', 1)}–{t.get('max', '…')})"
                         + (f" dan menu <b>Rank by</b>: {' / '.join(ranks)}" if ranks else ''))
            inter.append(f"<i>Selected</i> → muncul daftar kode broker (cari{f', maks. {mx}' if mx else ''}); tanpa N dan Rank")
            inter.append('<i>All brokers</i> → tanpa kotak tambahan')
        elif x['id'] == 'FL23':
            filt.append('<b>Brokers</b> (sudah ada)')
            inter.append('Daftar kode (maks. 5); klik kode broker di panel kanan ikut masuk')
        elif 'top' in P:
            filt.append(f"<b>Top N</b> ({dflt(P['top'])})")
            inter.append(f"Kotak <b>N</b> ({P['top'].get('min', 1)}–{P['top'].get('max', '…')}) langsung di baris")
        if 'boards' in P:
            filt.append(f"<b>Board</b> ({dflt(P['boards'])})")
        if 'investors' in P:
            filt.append(f"<b>Investor</b> ({dflt(P['investors'])})")
        if 'side' in P:
            note.append(f"Side ({dflt(P['side'])}) — usul tetap di dialog (sudah tertulis di judul)")
        if 'inst' in P:
            note.append('Daftar Institutional/Retail tetap di dialog')
        if not filt:
            filt = ['—']
            note.append('Tidak memakai broker, papan atau investor')
        if 'boards' in P or 'investors' in P or 'scope' in P:
            inter.append('Clear → garis hilang, panel menulis "Choose at least one …" sampai dipilih lagi')
    if x['place'] != 'pane' and filt[0] not in ('—', '— (tetap di dialog)'):
        inter.append('Garis/tanda di chart harga: tombol muncul saat baris legend di-hover atau disentuh, supaya legend harga tetap bersih')
    rows.append((x['id'], x['name'], x['family'], PLACE.get(x['place'], x['place']), filt, inter, note))

fam = []
for r in rows:
    if r[2] not in fam:
        fam.append(r[2])
cnt = lambda pred: sum(1 for r in rows if pred(r))
body = ''
for f in fam:
    body += f'<tr class="fam"><td colspan="5">{html.escape(f)}</td></tr>'
    for i, nm, _, pl, fl, it, nt in [r for r in rows if r[2] == f]:
        body += (f'<tr><td><b>{html.escape(nm)}</b><small>{i} · {pl}</small></td><td>{"<br>".join(fl)}</td>'
                 f'<td>{"<br>".join(it) or "—"}</td><td>{"<br>".join(nt) or "—"}</td></tr>')
summary = (f'{len(rows)} indikator di menu (FL07, FL35, FL36 disembunyikan). Dengan tombol Broker (cakupan + kotak N): '
           f'{cnt(lambda r: any("<b>Broker</b>" in s for s in r[4]))}; Top N + Rank by saat Top-N: {cnt(lambda r: any("Rank by" in s for s in r[4]))}; kotak Top N tanpa cakupan: {cnt(lambda r: any("Top N" in s for s in r[4]) and not any("<b>Broker</b>" in s for s in r[4]))}; '
           f'Board: {cnt(lambda r: any("Board" in s for s in r[4]))}; Investor: {cnt(lambda r: any("Investor" in s for s in r[4]))}; '
           f'tanpa tombol: {cnt(lambda r: r[4][0].startswith("—"))}.')
out = f'''<!doctype html><html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Flow Pane Filters</title><style>
:root{{--bg:#fafafa;--surface:#fff;--border:#eaeaea;--text:#171717;--text-2:#4d4d4d;--text-3:#8f8f8f;--sel:#f2f2f2}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#0f0f10;--surface:#18181a;--border:#2a2a2d;--text:#ededed;--text-2:#c4c4c4;--text-3:#8a8a8a;--sel:#26262a}}}}
:root[data-theme="dark"]{{--bg:#0f0f10;--surface:#18181a;--border:#2a2a2d;--text:#ededed;--text-2:#c4c4c4;--text-3:#8a8a8a;--sel:#26262a}}
body{{margin:0;background:var(--bg);color:var(--text);font:13px/1.5 Inter,"Segoe UI",system-ui,sans-serif}}
.wrap{{max-width:1180px;margin:0 auto;padding:16px}}h1{{font-size:18px;margin:0 0 6px}}p{{margin:4px 0;color:var(--text-2)}}
.box{{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:12px 14px;margin:12px 0}}
.scroll{{overflow-x:auto}}table{{width:100%;border-collapse:collapse;background:var(--surface);min-width:760px}}
th,td{{text-align:left;vertical-align:top;padding:8px 10px;border-bottom:1px solid var(--border);font-size:12.5px}}
th{{position:sticky;top:0;background:var(--surface);font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--text-3)}}
td small{{display:block;color:var(--text-3);font-size:11px}}tr.fam td{{background:var(--sel);font-weight:600;font-size:12px}}
</style></head><body><div class="wrap"><h1>Tombol filter di baris indikator Flow — usulan final</h1>
<p>{summary}</p>
<div class="box"><b>Aturan (diturunkan dari parameter registry, bukan daftar manual):</b>
<p>• Indikator dengan <b>cakupan broker</b> mendapat tombol <b>Broker</b>: All brokers / Selected / Top-N. <b>Top-N</b>
memunculkan kotak <b>N</b> dan menu <b>Rank by</b> (pilihan dari registry indikator itu); <b>Selected</b> memunculkan daftar
kode broker saja; <b>All brokers</b> tanpa tambahan. Board dan Investor selalu ada. • Indikator dengan Top N tanpa cakupan (Bandar Balance,
Concentration Top-N, FL42) mendapat kotak <b>N</b>. • Papan → tombol <b>Board</b>; jenis investor → tombol <b>Investor</b>
(sama dengan Broker Inventory). • Parameter lain (hari rolling, baseline, satuan, garis acuan, Side) tetap di
dialog ⚙. • Clear di tombol mana pun: garis hilang dan panel menulis "Choose at least one …" (sama dengan butir 3).
• Indikator baru otomatis ikut aturan ini.</p></div>
<div class="scroll"><table><thead><tr><th style="width:24%">Nama indikator</th><th style="width:22%">Filter yang ditambahkan (bawaan)</th>
<th style="width:34%">Interaksi</th><th>Lain-lain</th></tr></thead><tbody>{body}</tbody></table></div>
<p style="margin-top:10px;font-size:11.5px;color:var(--text-3)">Dibuat dari apps/edge-bff/terminal/src/data/flowRegistry.json oleh
verification/terminal_api/flow_pane_filters/build_proposal.py. Belum ada yang diubah di Terminal.</p></div></body></html>'''
open(sys.argv[2], 'w', encoding='utf-8').write(out)
print(summary)
