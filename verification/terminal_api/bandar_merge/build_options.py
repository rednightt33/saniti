"""User 2026-11-01: "Kita kirimkan saya 10 opsi dalam satu HTML apabila bandar detector kita gabung ke top brokers".

One review page: ten ways the Bandar detector's summary (Top N choice, verdict, Net, ratio to total buy) could live inside
the Top brokers panel. Every figure is the live Terminal's own (collect_panels.py, Railway dev): the brokers and their
Domestic/Foreign split from Top brokers, ranks 9-10 from Broker summary, and the Top 3/5/10 sums, ratio and verdict from
the Bandar detector. Nothing is computed here except bar widths; ranks 9 and 10 take their Foreign part from the Broker
summary's Foreign list (0 when the broker is not in its top 10 there), which the page says.

Usage: python3 build_options.py panel_data.json OUT.html"""
import html, json, re, sys
from pathlib import Path

UNIT = {'K': 1e3, 'M': 1e6, 'B': 1e9, 'T': 1e12}


def num(s):
    s = s.strip().replace(',', '').replace('−', '-')
    m = re.fullmatch(r'([+-]?\d+(?:\.\d+)?)([KMBT]?)%?', s)
    if not m:
        raise ValueError(s)
    return float(m.group(1)) * UNIT.get(m.group(2), 1)


def split_of(tips):
    """Top brokers tooltips -> {broker: (net, domestic, foreign)}"""
    out = {}
    for t in tips:
        code, text = t.split('|', 1)
        net = re.search(r'net ([+-]?[\d.]+[KMBT]?)', text)
        dom = re.search(r'Domestic ([+-]?[\d.]+[KMBT]?)', text)
        fo = re.search(r'Foreign ([+-]?[\d.]+[KMBT]?)', text)
        out[code] = (num(net.group(1)), num(dom.group(1)) if dom else 0.0, num(fo.group(1)) if fo else 0.0)
    return out


def side(rows, sign, split, foreign_rows):
    fmap = {r[0]: num(r[2]) for r in foreign_rows}
    out = []
    for code, lot, value, avg in rows:
        net = sign * num(value)
        if code in split:
            _, d, f = split[code]
            exact = True
        else:
            f = sign * fmap.get(code, 0.0)
            d, exact = net - f, False
        out.append({'b': code, 'net': net, 'lot': lot, 'avg': avg, 'd': d, 'f': f, 'exact': exact})
    return out


def verdict(text):
    lines = text.split('\n')
    val = lambda key: lines[lines.index(key) + 1]
    v = lines[1]
    return {'v': v, 'cls': 'acc' if 'Acc' in v else 'dist' if 'Dist' in v else 'neu', 'buy': num(val('Buy')),
            'sell': num(val('Sell')), 'net': num(val('Net')), 'ratio': num(val('Ratio to total buy')),
            'fshare': num(val('Foreign share of buyers'))}


def normalise(raw):
    data = {}
    for t, per in raw.items():
        data[t] = {'asof': per['sub'].split('·', 1)[1].strip()}
        for d in ('1', '5', '20'):
            p = per[d]
            split = split_of(p['acc']['rows'])
            bs, fo = p['bs']['All']['tables'], p['bs']['Foreign']['tables']
            data[t][d] = {'range': p['acc']['hint'].split(' · ')[0],
                          'buy': side(bs[0], 1, split, fo[0]), 'sell': side(bs[1], -1, split, fo[1]),
                          'bd': {n: verdict(p['bd'][n]['text']) for n in ('3', '5', '10')}}
    return data


PAGE = r"""<!doctype html>
<html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Top Brokers + Bandar</title>
<style>
:root{--bg:#fafafa;--surface:#fff;--border:#eaeaea;--text:#171717;--text-2:#666;--sel:#f2f2f2;--up:#089981;--down:#f23645;
  --sans:"Geist","Inter","Segoe UI",system-ui,sans-serif;--mono:"Geist Mono",ui-monospace,SFMono-Regular,Menlo,monospace}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:13px/1.45 var(--sans);-webkit-font-smoothing:antialiased}
header.top{position:sticky;top:0;z-index:5;background:rgba(250,250,250,.94);backdrop-filter:blur(6px);border-bottom:1px solid var(--border)}
.wrap{max-width:1180px;margin:0 auto;padding:0 16px}
header.top .wrap{display:flex;flex-wrap:wrap;align-items:center;gap:10px 18px;padding:12px 16px}
h1{font-size:17px;margin:0;letter-spacing:-.01em}
.muted{color:var(--text-2)}
.intro{margin:18px 0 6px;display:grid;gap:10px;grid-template-columns:1fr}
.box{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:12px 14px}
.box h2{font-size:13px;margin:0 0 6px}
.box p{margin:4px 0}
.box code{font-family:var(--mono);font-size:12px;background:var(--sel);padding:1px 4px;border-radius:4px}
.toc{display:flex;flex-wrap:wrap;gap:6px}
.toc a{font-size:12px;color:var(--text);text-decoration:none;border:1px solid var(--border);border-radius:999px;padding:2px 9px;background:var(--surface)}
.toc a:hover{background:var(--sel)}
.opt{display:grid;grid-template-columns:316px 1fr;gap:18px;align-items:start;margin:18px 0;scroll-margin-top:70px}
@media (max-width:760px){.opt{grid-template-columns:1fr}}
.opt .about h3{margin:2px 0 6px;font-size:15px}
.opt .about .n{display:inline-grid;place-items:center;width:22px;height:22px;border-radius:6px;background:var(--text);color:#fff;font-size:12px;margin-right:8px;vertical-align:1px}
.opt .about ul{margin:6px 0;padding-left:18px}
.opt .about li{margin:2px 0}
.pro b{color:var(--up)}.con b{color:var(--down)}
/* the mock panel: the Terminal's right panel section */
.panel{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:10px 12px 12px;width:316px;max-width:100%}
.head{display:flex;align-items:center;gap:8px;margin-bottom:6px}
.head strong{font-size:13px}.head small{margin-left:auto;font-size:11px;color:var(--text-2);white-space:nowrap}
.ctl{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin:0 0 6px}
.seg{display:inline-flex;border:1px solid var(--border);border-radius:6px;padding:2px;gap:2px}
.seg button{height:22px;padding:0 8px;border:0;border-radius:4px;background:none;font:500 11px var(--sans);color:var(--text-2);cursor:pointer}
.seg button.active{background:var(--sel);color:var(--text)}
.seg button:disabled{opacity:.45;cursor:default}
.rp-sel{height:26px;border:1px solid var(--border);border-radius:6px;background:var(--surface);color:var(--text);font:11.5px var(--sans);padding:0 4px}
.tag{display:inline-block;padding:1px 8px;border-radius:999px;font-size:10.5px;font-weight:600;white-space:nowrap}
.tag.acc{background:#e3f5ef;color:#087f5b}.tag.dist{background:#fde8ea;color:#d62839}.tag.neu{background:var(--sel);color:var(--text-2)}
.tag.big.acc{background:#089981;color:#fff}.tag.big.dist{background:#f23645;color:#fff}
.up{color:var(--up)}.down{color:var(--down)}
.num{font-variant-numeric:tabular-nums}
.line{display:flex;justify-content:space-between;align-items:center;font-size:11.5px;padding:2px 0}
.line span:first-child{color:var(--text-2)}
.sub{font-size:11px;color:var(--text-2)}
/* the Top brokers table (as the live panel) */
.pa-head,.pa-row{display:grid;grid-template-columns:minmax(26px,auto) minmax(44px,auto) 1fr 1fr minmax(44px,auto) minmax(26px,auto);align-items:center;column-gap:6px}
.pa-head{padding:0 0 5px;font-size:11px;color:var(--text-2);border-bottom:1px solid var(--border);margin-bottom:3px;white-space:nowrap}
.pa-head .l{grid-column:1/4;display:flex;align-items:center;gap:6px}.pa-head .r{grid-column:4/7;display:flex;align-items:center;justify-content:flex-end;gap:6px}
.pa-head i{width:8px;height:8px;border-radius:2px}.pa-head i.up{background:var(--up)}.pa-head i.down{background:var(--down)}
.pa-row{height:22px;font-size:11.5px;border-radius:4px}
.pa-row .v{font-variant-numeric:tabular-nums;white-space:nowrap}.pa-row .v.up{text-align:right}
.pa-row .b{font-family:var(--mono);font-size:11px;font-weight:600}.pa-row .b:last-child{text-align:right}
.trk{position:relative;height:8px;background:#f0f0f0;border-radius:2px;overflow:hidden}
.fill{position:absolute;top:0;bottom:0;display:flex}
.trk.buy .fill{right:0;flex-direction:row-reverse}.trk.sell .fill{left:0}
.fill i{display:block;height:100%}.trk.buy .fill i{background:var(--up)}.trk.sell .fill i{background:var(--down)}.fill i.f{opacity:.42}
.pa-row.dim{opacity:.38}
.pa-row.inb{background:linear-gradient(90deg,rgba(8,153,129,.08),rgba(8,153,129,0) 55%)}
.pa-row.ins{background:linear-gradient(270deg,rgba(242,54,69,.08),rgba(242,54,69,0) 55%)}
.pa-row.inb.ins{background:linear-gradient(90deg,rgba(8,153,129,.08),transparent 45%,transparent 55%,rgba(242,54,69,.08))}
.cut{border-top:1px dashed #c9c9c9;margin:3px 0}
.leg{display:flex;gap:12px;font-size:11px;color:var(--text-2);margin-top:8px;padding-top:7px;border-top:1px solid var(--border)}
.leg span{display:inline-flex;align-items:center;gap:5px}.leg i{width:14px;height:7px;border-radius:2px;display:inline-block;background:linear-gradient(90deg,var(--up) 50%,var(--down) 50%)}.leg i.f{opacity:.42}
/* option parts */
.strip{display:flex;align-items:center;gap:8px;padding:7px 9px;border:1px solid var(--border);border-radius:6px;margin:0 0 8px;background:var(--bg)}
.strip .grow{flex:1;min-width:0;font-size:11.5px}
.meter{position:relative;height:10px;border-radius:5px;margin:16px 0 4px;background:linear-gradient(90deg,#f23645 0 16.67%,#fbc4c9 16.67% 30%,#ededed 30% 70%,#b9e7da 70% 83.33%,#089981 83.33% 100%)}
.meter .pin{position:absolute;top:-5px;width:2px;height:20px;background:var(--text);border-radius:1px;transform:translateX(-1px)}
.meter .pin b{position:absolute;bottom:22px;left:50%;transform:translateX(-50%);font-size:10.5px;white-space:nowrap;background:var(--text);color:#fff;padding:0 5px;border-radius:4px}
.scale{display:flex;justify-content:space-between;font-size:10px;color:var(--text-2);margin-bottom:8px}
.cards{display:grid;grid-template-columns:1fr auto 1fr;gap:6px;align-items:center;margin:0 0 8px}
.card{border:1px solid var(--border);border-radius:6px;padding:6px 8px}
.card .k{font-size:10.5px;color:var(--text-2)}.card .v{font-size:14px;font-weight:600}
.bars .row{display:grid;grid-template-columns:34px 1fr 54px;gap:6px;align-items:center;font-size:11.5px;margin:3px 0}
.bars .t{height:10px;background:#f0f0f0;border-radius:2px;overflow:hidden}.bars .t i{display:block;height:100%}
.tabs{display:flex;border-bottom:1px solid var(--border);margin:0 0 8px}
.tabs button{border:0;background:none;padding:5px 10px;font:500 12px var(--sans);color:var(--text-2);border-bottom:2px solid transparent;cursor:pointer}
.tabs button.active{color:var(--text);border-bottom-color:var(--text)}
.chips{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin:0 0 8px}
.chip{border:1px solid var(--border);border-radius:6px;padding:5px 6px;background:var(--surface);cursor:pointer;text-align:left;font:inherit}
.chip.on{border-color:var(--text);box-shadow:0 0 0 1px var(--text) inset}
.chip .k{font-size:10.5px;color:var(--text-2)}.chip .r{font-size:11.5px;font-weight:600}
.tug{display:flex;height:16px;border-radius:4px;overflow:hidden;margin:6px 0 3px}
.tug i{display:flex;align-items:center;font-style:normal;font-size:10px;color:#fff;padding:0 5px;white-space:nowrap}
.tot{display:grid;grid-template-columns:1fr auto 1fr;gap:6px;align-items:center;font-size:11.5px;padding:4px 2px;border-top:1px solid var(--border);margin-top:3px}
.tot .r{text-align:right}
.foot{margin:28px 0 40px;font-size:12px}
</style></head>
<body>
<header class="top"><div class="wrap">
  <h1>Top brokers + Bandar detector: 10 opsi</h1>
  <label class="muted">Ticker <select class="rp-sel" id="ticker"></select></label>
  <span class="muted" id="asof"></span>
</div></header>
<main class="wrap">
  <section class="intro">
    <div class="box">
      <h2>Yang digabung</h2>
      <p>Panel <b>Bandar detector</b> dihapus. Isinya pindah ke panel <b>Top brokers</b>: pilihan <b>Top 3 · Top 5 · Top 10</b>,
      <b>vonis</b>, <b>Net</b> dan <b>rasio terhadap total beli</b>. Daftar broker tidak berubah: daftar accumulators di Top brokers
      sama dengan daftar pembeli Bandar detector (keduanya diurutkan menurut beli bersih = nilai beli − nilai jual).</p>
      <p>Rumus vonis (FL24, keputusan user 30 Okt 2026): <code>(beli bersih Top N pembeli − jual bersih Top N penjual) ÷ total nilai beli</code>.
      Rasio ≥ 10%: <span class="tag big acc">Big Acc</span>; ≥ 6%: <span class="tag acc">Acc</span>; −6% sampai 6%: <span class="tag neu">Neutral</span>;
      ≤ −6%: <span class="tag dist">Dist</span>; ≤ −10%: <span class="tag big dist">Big Dist</span>.</p>
      <p class="muted">Semua angka adalah angka Terminal sendiri (Railway dev, data broker sampai tanggal di atas), dibaca dari panel Top brokers,
      Bandar detector, dan Broker summary. Contoh memakai All boards; pilihan papan di contoh tidak aktif. Peringkat 9 dan 10 ditampilkan
      bila memilih Top 10. Bagian asingnya diambil dari daftar Foreign di Broker summary (0 bila broker itu tidak masuk 10 besar asing).
      Ganti ticker di atas, misalnya BBRI 5D untuk Big Acc atau GOTO 1D Top 5 untuk Dist.</p>
    </div>
    <div class="toc" id="toc"></div>
  </section>
  <div id="opts"></div>
  <p class="foot muted">Sumber: verification/terminal_api/bandar_merge/ (collect_panels.py membaca panel live; build_options.py membuat halaman ini).
  Halaman ini usulan tampilan, belum ada yang diubah di Terminal.</p>
</main>
<script>
const DATA = __DATA__;
const TICKERS = Object.keys(DATA);
let T = TICKERS.includes('BBRI') ? 'BBRI' : TICKERS[0];
const U = { K:1e3, M:1e6, B:1e9, T:1e12 };
const fmt = (v, sign = true) => { const a = Math.abs(v), s = v < 0 ? '−' : sign && v > 0 ? '+' : '';
  const [d, u] = a >= 1e12 ? [a / 1e12, 'T'] : a >= 1e9 ? [a / 1e9, 'B'] : a >= 1e6 ? [a / 1e6, 'M'] : [a / 1e3, 'K'];
  return s + (Math.round(d * 10) / 10).toLocaleString('en-US') + u };
const pct = v => (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v).toFixed(2) + '%';
const D = st => DATA[T][st.d], V = st => D(st).bd[st.n];
const tag = v => `<span class="tag ${v.cls}${/Big/.test(v.v) ? ' big' : ''}">${v.v}</span>`;
const seg = (k, st, items) => `<div class="seg" data-k="${k}">${items.map(([v, l, dis]) => `<button data-v="${v}" class="${String(st[k]) === String(v) ? 'active' : ''}"${dis ? ' disabled title="Tidak aktif di contoh"' : ''}>${l}</button>`).join('')}</div>`;
const period = st => seg('d', st, [['1', '1D'], ['5', '5D'], ['20', '20D'], ['c', 'Custom', 1]]);
const topN = (st, short) => seg('n', st, [['3', short ? '3' : 'Top 3'], ['5', short ? '5' : 'Top 5'], ['10', short ? '10' : 'Top 10']]);
const board = '<select class="rp-sel" disabled title="Contoh memakai All boards"><option>All boards</option></select>';
const head = (st, extra = '') => `<div class="head"><strong>Top brokers</strong>${extra}<small>${D(st).range} · net</small></div>`;
const parts = (f, d, side) => { const same = [['d', d], ['f', f]].filter(([, v]) => side === 'buy' ? v > 0 : v < 0), tot = same.reduce((s, [, v]) => s + Math.abs(v), 0);
  return tot ? same.map(([k, v]) => `<i class="${k}" style="width:${(Math.abs(v) / tot * 100).toFixed(1)}%"></i>`).join('') : '' };
/* the paired table of the live panel; `mark`: shade the Top N rows, `cut`: a dashed line after rank N, `dim`: fade the rows past N */
function table(st, o = {}) {
  const x = D(st), n = +st.n, rows = Math.max(o.rows || 8, o.extend ? n : 0);
  const buy = x.buy.slice(0, rows), sell = x.sell.slice(0, rows);
  const mx = Math.max(1, ...buy.map(r => r.net), ...sell.map(r => -r.net));
  const cell = r => r ? `<span class="b" title="${r.b}: Domestic ${fmt(r.d)} · Foreign ${fmt(r.f)}${r.exact ? '' : ' (bagian asing dari Broker summary)'}">${r.b}</span>` : '<span></span>';
  const val = (r, s) => `<span class="v ${s === 'buy' ? 'up' : 'down'}">${r ? fmt(r.net) : ''}</span>`;
  const bar = (r, s) => `<div class="trk ${s}">${r ? `<div class="fill" style="width:${(Math.abs(r.net) / mx * 100).toFixed(1)}%">${parts(r.f, r.d, s)}</div>` : ''}</div>`;
  let out = `<div class="pa-head"><span class="l"><i class="up"></i>Top accumulators</span><span class="r">Top distributors<i class="down"></i></span></div>`;
  for (let k = 0; k < Math.max(buy.length, sell.length); k++) {
    if (o.cut && k === n) out += '<div class="cut"></div>';
    const b = buy[k], s = sell[k], inN = k < n;
    const cls = [o.mark && inN ? 'inb ins' : '', o.dim && !inN ? 'dim' : ''].join(' ');
    out += `<div class="pa-row ${cls}">${cell(b)}${val(b, 'buy')}${bar(b, 'buy')}${bar(s, 'sell')}${val(s, 'sell')}${cell(s)}</div>`;
    if (o.totals && k === n - 1) out += totals(st);
  }
  return out + '<div class="leg"><span><i></i>Domestic</span><span><i class="f"></i>Foreign</span></div>';
}
const totals = st => { const v = V(st);
  return `<div class="tot"><span class="up num">Top ${st.n}: ${fmt(v.buy, false)}</span>${tag(v)}<span class="down num r">${fmt(v.sell, false)}</span></div>
          <div class="line"><span>Net · rasio terhadap total beli</span><span class="num ${v.net >= 0 ? 'up' : 'down'}">${fmt(v.net)} · ${pct(v.ratio)}</span></div><div class="cut"></div>` };
const summary = st => { const v = V(st);
  return `<div class="line"><span>Net Top ${st.n}</span><span class="num ${v.net >= 0 ? 'up' : 'down'}">${fmt(v.net)}</span></div>
          <div class="line"><span>Rasio terhadap total beli</span><span class="num ${v.ratio >= 0 ? 'up' : 'down'}">${pct(v.ratio)}</span></div>` };
const pos = r => Math.max(0, Math.min(100, (r + 15) / 30 * 100));   // -15%..+15% on the meter

const OPTS = [
 { name:'Strip vonis di atas tabel', what:'Satu baris ringkas di atas tabel: pilihan Top N, rasio dan vonis (Net rupiah saat kursor di atas rasio). Baris Top N di tabel diberi warna tipis.',
   pro:['Paling ringkas: tidak menambah tinggi panel berarti', 'Vonis langsung terlihat sebelum daftar'], con:['Net rupiah hanya muncul saat kursor di atas rasio'],
   render:st => `${head(st)}<div class="ctl">${period(st)}${board}</div>
     <div class="strip"><span class="sub">Top</span>${topN(st, true)}<span class="grow num ${V(st).ratio >= 0 ? 'up' : 'down'}" style="white-space:nowrap;text-align:right" title="Net Top ${st.n} ${fmt(V(st).net)}">${pct(V(st).ratio)}</span>${tag(V(st))}</div>${table(st, { mark:1, extend:1 })}` },
 { name:'Vonis di judul panel', what:'Vonis menjadi badge di judul panel (terlihat walau panel dilipat). Top N masuk baris kontrol bersama papan; Net dan rasio di bawah tabel.',
   pro:['Vonis terlihat bahkan saat panel ditutup', 'Tabel tetap paling atas'], con:['Rasio ada di bawah, perlu menggulir'],
   render:st => `${head(st, tag(V(st)))}<div class="ctl">${period(st)}</div><div class="ctl">${topN(st)}${board}</div>${table(st, { extend:1 })}<div style="margin-top:6px">${summary(st)}</div>` },
 { name:'Meter keseimbangan', what:'Satu meter dari −15% sampai +15% dengan zona Big Dist, Dist, Neutral, Acc, Big Acc; jarum di rasio Top N.',
   pro:['Sekali lihat: seberapa jauh dari batas 6% dan 10%', 'Cocok untuk membandingkan Top 3/5/10'], con:['Butuh tinggi tambahan sekitar 40 px', 'Rasio di luar ±15% menempel di ujung'],
   render:st => { const v = V(st); return `${head(st)}<div class="ctl">${period(st)}${board}</div><div class="ctl">${topN(st)}${tag(v)}</div>
     <div class="meter"><span class="pin" style="left:${pos(v.ratio)}%"><b>${pct(v.ratio)}</b></span></div>
     <div class="scale"><span>−15%</span><span>−10</span><span>−6</span><span>0</span><span>6</span><span>10</span><span>+15%</span></div>${table(st, { extend:1 })}` } },
 { name:'Baris total Top N di dalam tabel', what:'Tabel tidak berubah, tetapi sesudah peringkat ke-N ada baris jumlah kedua sisi dengan vonis di tengah, lalu garis putus-putus.',
   pro:['Paling jelas broker mana yang dijumlah', 'Tidak ada elemen baru di atas tabel'], con:['Vonis berpindah posisi saat Top N diganti'],
   render:st => `${head(st)}<div class="ctl">${period(st)}${board}</div><div class="ctl">${topN(st)}</div>${table(st, { totals:1, extend:1 })}` },
 { name:'Dua kartu Beli dan Jual', what:'Dua kartu kecil: jumlah beli bersih Top N dan jumlah jual bersih Top N, vonis di antaranya; rasio di bawahnya.',
   pro:['Angka besar mudah dibaca', 'Menjawab "siapa lebih kuat" secara langsung'], con:['Paling tinggi di antara opsi ringkas'],
   render:st => { const v = V(st); return `${head(st)}<div class="ctl">${period(st)}${board}</div><div class="ctl">${topN(st)}</div>
     <div class="cards"><div class="card"><div class="k">Beli bersih Top ${st.n}</div><div class="v up num">${fmt(v.buy, false)}</div></div>${tag(v)}
     <div class="card" style="text-align:right"><div class="k">Jual bersih Top ${st.n}</div><div class="v down num">${fmt(v.sell, false)}</div></div></div>
     <div class="line" style="margin-bottom:8px"><span>Net ${fmt(v.net)} · rasio terhadap total beli</span><span class="num ${v.ratio >= 0 ? 'up' : 'down'}">${pct(v.ratio)}</span></div>${table(st, { extend:1 })}` } },
 { name:'Batang Buy vs Sell (gaya Bandar sekarang)', what:'Dua batang horizontal Buy dan Sell Top N, seperti Bandar detector sekarang, ditaruh di atas tabel.',
   pro:['Paling mirip panel lama: tidak perlu belajar ulang'], con:['Mengulang informasi yang sudah ada di batang tabel'],
   render:st => { const v = V(st), mx = Math.max(v.buy, v.sell); return `${head(st)}<div class="ctl">${period(st)}${board}</div><div class="ctl">${topN(st)}${tag(v)}</div>
     <div class="bars"><div class="row"><span>Buy</span><div class="t"><i style="width:${v.buy / mx * 100}%;background:var(--up)"></i></div><span class="num up" style="text-align:right">${fmt(v.buy, false)}</span></div>
     <div class="row"><span>Sell</span><div class="t"><i style="width:${v.sell / mx * 100}%;background:var(--down)"></i></div><span class="num down" style="text-align:right">${fmt(v.sell, false)}</span></div></div>
     ${summary(st)}<div style="height:8px"></div>${table(st, { extend:1 })}` } },
 { name:'Dua tab: Daftar | Vonis', what:'Panel punya dua tab. Daftar = tabel Top brokers seperti sekarang. Vonis = isi Bandar detector (batang, Net, rasio, porsi asing).',
   pro:['Panel tetap pendek', 'Isi Bandar lengkap tetap ada'], con:['Vonis tersembunyi di tab kedua'],
   render:st => { const v = V(st), tab = st.tab || 'list'; return `${head(st, tab === 'list' ? tag(v) : '')}<div class="tabs" data-k="tab"><button data-v="list" class="${tab === 'list' ? 'active' : ''}">Daftar</button><button data-v="verdict" class="${tab === 'verdict' ? 'active' : ''}">Vonis</button></div>
     <div class="ctl">${period(st)}${board}</div>${tab === 'list' ? table(st) : `<div class="ctl">${topN(st)}${tag(v)}</div>${summary(st)}
     <div class="line"><span>Beli bersih Top ${st.n}</span><span class="num up">${fmt(v.buy, false)}</span></div><div class="line"><span>Jual bersih Top ${st.n}</span><span class="num down">${fmt(v.sell, false)}</span></div>
     <div class="line"><span>Porsi asing di antara pembeli</span><span class="num">${v.fshare}%</span></div>`}` } },
 { name:'Tiga vonis sekaligus', what:'Tanpa tombol Top N: tiga kotak Top 3, Top 5, Top 10, masing-masing dengan vonis dan rasionya. Klik satu kotak untuk menandai barisnya.',
   pro:['Terlihat apakah sinyal hanya dari 3 broker atau menyebar', 'Satu klik lebih sedikit'], con:['Tiga angka bisa membingungkan pembaca baru'],
   render:st => `${head(st)}<div class="ctl">${period(st)}${board}</div>
     <div class="chips" data-k="n">${['3', '5', '10'].map(n => { const v = D(st).bd[n]; return `<button class="chip${st.n === n ? ' on' : ''}" data-v="${n}"><div class="k">Top ${n}</div>${tag(v)}<div class="r num ${v.ratio >= 0 ? 'up' : 'down'}">${pct(v.ratio)}</div></button>` }).join('')}</div>${table(st, { mark:1, extend:1 })}` },
 { name:'Ringkasan di bawah tabel', what:'Tabel dulu (seperti sekarang), lalu blok vonis di bawahnya dengan Top N, vonis, Net dan rasio. Urutan sama dengan panel lama.',
   pro:['Perubahan paling kecil dari tampilan sekarang'], con:['Vonis tidak terlihat tanpa menggulir'],
   render:st => `${head(st)}<div class="ctl">${period(st)}${board}</div>${table(st, { extend:1, dim:1 })}
     <div style="margin-top:8px;padding-top:8px;border-top:1px solid var(--border)"><div class="ctl">${topN(st)}<span style="margin-left:auto">${tag(V(st))}</span></div>${summary(st)}</div>` },
 { name:'Tarik tambang', what:'Satu batang dibagi dua: porsi beli bersih Top N dan porsi jual bersih Top N dari jumlah keduanya, dengan vonis dan rasio di sampingnya.',
   pro:['Sangat ringkas', 'Sisi yang menang langsung terlihat'], con:['Panjang batang bukan rasio vonis (penyebut berbeda)'],
   render:st => { const v = V(st), b = v.buy / (v.buy + v.sell) * 100; return `${head(st)}<div class="ctl">${period(st)}${board}</div><div class="ctl">${topN(st)}${tag(v)}<span class="sub num" style="margin-left:auto">${pct(v.ratio)}</span></div>
     <div class="tug"><i style="width:${b}%;background:var(--up)">${fmt(v.buy, false)}</i><i style="width:${100 - b}%;background:var(--down);justify-content:flex-end">${fmt(v.sell, false)}</i></div>
     <div class="sub" style="margin-bottom:8px">Net ${fmt(v.net)} · rasio terhadap total beli ${pct(v.ratio)}</div>${table(st, { mark:1, extend:1 })}` } },
];

const states = OPTS.map(() => ({ d:'5', n:'3' }));
function render(i) {
  const el = document.querySelector(`#o${i} .panel`), st = states[i];
  el.innerHTML = OPTS[i].render(st);
  el.querySelectorAll('[data-k]').forEach(g => g.querySelectorAll('[data-v]').forEach(b => b.onclick = () => {
    if (b.disabled) return; st[g.dataset.k] = b.dataset.v; render(i) }));
}
document.getElementById('opts').innerHTML = OPTS.map((o, i) => `<section class="opt" id="o${i}"><div class="panel"></div>
  <div class="about"><h3><span class="n">${i + 1}</span>${o.name}</h3><p>${o.what}</p><ul>${o.pro.map(p => `<li class="pro"><b>+</b> ${p}</li>`).join('')}${o.con.map(p => `<li class="con"><b>−</b> ${p}</li>`).join('')}</ul></div></section>`).join('');
document.getElementById('toc').innerHTML = OPTS.map((o, i) => `<a href="#o${i}">${i + 1}. ${o.name}</a>`).join('');
const sel = document.getElementById('ticker');
sel.innerHTML = TICKERS.map(t => `<option${t === T ? ' selected' : ''}>${t}</option>`).join('');
const all = () => { document.getElementById('asof').textContent = `Data broker sampai ${DATA[T].asof}`; OPTS.forEach((_, i) => render(i)) };
sel.onchange = () => { T = sel.value; all() };
all();
</script>
</body></html>
"""


def main():
    raw = json.loads(Path(sys.argv[1]).read_text())
    data = normalise(raw)
    page = PAGE.replace('__DATA__', json.dumps(data, separators=(',', ':')))
    Path(sys.argv[2]).write_text('\n'.join(line.rstrip() for line in page.split('\n')))
    print('ok', len(data), 'tickers')


if __name__ == '__main__':
    main()
