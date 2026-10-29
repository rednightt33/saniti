/* FIXTURE ONLY (never in the production bundle; tests/bundle checks it): the prototype's synthetic market, kept 1:1
   from screener EDGE layout.html lines 569-710 ("data layer": 94 real IDX tickers with deterministic sample prices,
   volumes, broker nets and a cap-weighted synthetic IHSG over 400 sessions to 2026-10-23), for the page's visual
   check and the Chromium smoke run against the fixture ScreenerApi (report FRONTEND INTEGRATION 9.1). Sample data,
   not market data. The prototype's formulas are not used: the fixture computes indicators with the Terminal's module
   through the Backtest core (tests/fixture/engine.ts), as the worker does. */
/* eslint-disable */
export const N = 400;                                           // daily sessions per ticker
const LAST_DAY = Date.UTC(2026, 9, 23);
export const DAYS: string[] = (() => { const out = []; let t = LAST_DAY; while(out.length < N){ const w = new Date(t).getUTCDay(); if(w && w < 6) out.unshift(new Date(t).toISOString().slice(0, 10)); t -= 864e5 } return out })();
// ticker, name, sector, industry, price, mkt cap (IDR T), sample index flags (L=LQ45 3=IDX30 8=IDX80 S=ISSI), board
export const LISTINGS: any[] = `BBCA|Bank Central Asia|Financials|Banks|9850|1214|L38|Main
BBRI|Bank Rakyat Indonesia|Financials|Banks|5720|867|L38|Main
BMRI|Bank Mandiri|Financials|Banks|6475|604|L38|Main
BBNI|Bank Negara Indonesia|Financials|Banks|4880|182|L38|Main
BRIS|Bank Syariah Indonesia|Financials|Banks|2690|124|L38S|Main
BBTN|Bank Tabungan Negara|Financials|Banks|1350|19|L8|Main
BNGA|Bank CIMB Niaga|Financials|Banks|1720|43|8|Main
BDMN|Bank Danamon|Financials|Banks|2600|25||Main
BJBR|Bank BJB|Financials|Banks|950|10||Main
ARTO|Bank Jago|Financials|Banks|2300|32|L8|Main
SRTG|Saratoga Investama|Financials|Investment Companies|1650|22|8S|Main
ADMF|Adira Dinamika Multi Finance|Financials|Consumer Financing|9800|10||Main
TLKM|Telkom Indonesia|Infrastructures|Telecommunication|3190|316|L38S|Main
ISAT|Indosat Ooredoo Hutchison|Infrastructures|Telecommunication|2400|77|L38S|Main
EXCL|XL Axiata|Infrastructures|Telecommunication|2280|30|L8S|Main
TOWR|Sarana Menara Nusantara|Infrastructures|Telecommunication|700|36|L8S|Main
TBIG|Tower Bersama Infrastructure|Infrastructures|Telecommunication|2000|45|8S|Main
JSMR|Jasa Marga|Infrastructures|Transportation Infrastructure|4530|33|L8S|Main
PGEO|Pertamina Geothermal Energy|Infrastructures|Utilities|1000|41|L8S|Main
BREN|Barito Renewables Energy|Infrastructures|Utilities|7000|936|8S|Main
WIKA|Wijaya Karya|Infrastructures|Heavy Constructions|300|3|S|Main
PTPP|PP (Persero)|Infrastructures|Heavy Constructions|400|2|S|Main
ADHI|Adhi Karya|Infrastructures|Heavy Constructions|300|2|S|Main
ADRO|Alamtri Resources|Energy|Coal|2410|74|L38S|Main
PTBA|Bukit Asam|Energy|Coal|2740|32|L38S|Main
ITMG|Indo Tambangraya Megah|Energy|Coal|26100|29|L38S|Main
HRUM|Harum Energy|Energy|Coal|900|12|8S|Main
INDY|Indika Energy|Energy|Coal|1500|8|8S|Main
BUMI|Bumi Resources|Energy|Coal|140|52|L8|Main
MEDC|Medco Energi|Energy|Oil & Gas|1250|31|L38S|Main
PGAS|Perusahaan Gas Negara|Energy|Oil & Gas|1600|39|L38S|Main
AKRA|AKR Corporindo|Energy|Oil & Gas|1150|23|L38S|Main
ENRG|Energi Mega Persada|Energy|Oil & Gas|250|6|S|Main
ELSA|Elnusa|Energy|Oil & Gas|420|3|S|Main
RAJA|Rukun Raharja|Energy|Oil & Gas|2100|9|S|Main
ANTM|Aneka Tambang|Basic Materials|Metals & Minerals|1540|37|L38S|Main
INCO|Vale Indonesia|Basic Materials|Metals & Minerals|3860|38|L38S|Main
MDKA|Merdeka Copper Gold|Basic Materials|Metals & Minerals|2200|54|L38S|Main
AMMN|Amman Mineral Internasional|Basic Materials|Metals & Minerals|7500|544|L8S|Main
NCKL|Trimegah Bangun Persada|Basic Materials|Metals & Minerals|900|57|L8S|Main
MBMA|Merdeka Battery Materials|Basic Materials|Metals & Minerals|550|59|L8S|Main
TINS|Timah|Basic Materials|Metals & Minerals|1100|8|8S|Main
SMGR|Semen Indonesia|Basic Materials|Construction Materials|3420|23|L8S|Main
INTP|Indocement Tunggal Prakarsa|Basic Materials|Construction Materials|6800|25|L8S|Main
INKP|Indah Kiat Pulp & Paper|Basic Materials|Forestry & Paper|7600|42|L38S|Main
TKIM|Pabrik Kertas Tjiwi Kimia|Basic Materials|Forestry & Paper|6200|19|8S|Main
TPIA|Chandra Asri Pacific|Basic Materials|Chemicals|8000|690|8S|Main
BRPT|Barito Pacific|Basic Materials|Chemicals|950|89|L8S|Main
ESSA|ESSA Industries Indonesia|Basic Materials|Chemicals|800|14|8S|Main
ASII|Astra International|Industrials|Multi-sector Holdings|5225|211|L38S|Main
UNTR|United Tractors|Industrials|Machinery|26450|99|L38S|Main
ARNA|Arwana Citramulia|Industrials|Building Products|700|5|S|Main
AMRT|Sumber Alfaria Trijaya|Consumer Non-Cyclicals|Food & Staples Retailing|2850|118|L38S|Main
ICBP|Indofood CBP Sukses Makmur|Consumer Non-Cyclicals|Food & Beverage|11325|132|L38S|Main
INDF|Indofood Sukses Makmur|Consumer Non-Cyclicals|Food & Beverage|7150|63|L38S|Main
MYOR|Mayora Indah|Consumer Non-Cyclicals|Food & Beverage|2600|58|8S|Main
CPIN|Charoen Pokphand Indonesia|Consumer Non-Cyclicals|Food & Beverage|4800|79|L38S|Main
JPFA|Japfa Comfeed Indonesia|Consumer Non-Cyclicals|Food & Beverage|1800|21|L8S|Main
CMRY|Cisarua Mountain Dairy|Consumer Non-Cyclicals|Food & Beverage|5400|43|8S|Main
ULTJ|Ultrajaya Milk Industry|Consumer Non-Cyclicals|Food & Beverage|1700|20|S|Main
ROTI|Nippon Indosari Corpindo|Consumer Non-Cyclicals|Food & Beverage|1000|6|S|Main
GOOD|Garudafood Putra Putri Jaya|Consumer Non-Cyclicals|Food & Beverage|450|16|S|Main
CLEO|Sariguna Primatirta|Consumer Non-Cyclicals|Food & Beverage|1100|13|S|Main
UNVR|Unilever Indonesia|Consumer Non-Cyclicals|Household Products|1945|74|L38S|Main
SIDO|Industri Jamu Sido Muncul|Consumer Non-Cyclicals|Household Products|600|18|8S|Main
GGRM|Gudang Garam|Consumer Non-Cyclicals|Tobacco|15000|29|8|Main
HMSP|HM Sampoerna|Consumer Non-Cyclicals|Tobacco|700|81|8|Main
AALI|Astra Agro Lestari|Consumer Non-Cyclicals|Agricultural Products|6500|13|S|Main
SIMP|Salim Ivomas Pratama|Consumer Non-Cyclicals|Agricultural Products|450|7|S|Main
MAPI|Mitra Adiperkasa|Consumer Cyclicals|Retailing|1460|24|L8S|Main
MAPA|Map Aktif Adiperkasa|Consumer Cyclicals|Retailing|900|26|8S|Main
ACES|Aspirasi Hidup Indonesia|Consumer Cyclicals|Retailing|800|14|L8S|Main
ERAA|Erajaya Swasembada|Consumer Cyclicals|Retailing|420|7|8S|Main
LPPF|Matahari Department Store|Consumer Cyclicals|Retailing|1700|4||Main
AUTO|Astra Otoparts|Consumer Cyclicals|Automobiles & Components|2300|11|S|Main
SCMA|Surya Citra Media|Consumer Cyclicals|Media & Entertainment|150|11|8S|Main
MNCN|Media Nusantara Citra|Consumer Cyclicals|Media & Entertainment|350|5|8|Main
KLBF|Kalbe Farma|Healthcare|Pharmaceuticals|1530|72|L38S|Main
MIKA|Mitra Keluarga Karyasehat|Healthcare|Healthcare Providers|2780|39|L8S|Main
SILO|Siloam International Hospitals|Healthcare|Healthcare Providers|3000|39|8S|Main
HEAL|Medikaloka Hermina|Healthcare|Healthcare Providers|1500|23|8S|Main
CTRA|Ciputra Development|Properties & Real Estate|Real Estate|1215|23|L8S|Main
BSDE|Bumi Serpong Damai|Properties & Real Estate|Real Estate|1000|21|L8S|Main
PWON|Pakuwon Jati|Properties & Real Estate|Real Estate|400|19|L8S|Main
SMRA|Summarecon Agung|Properties & Real Estate|Real Estate|500|8|8S|Main
DMAS|Puradelta Lestari|Properties & Real Estate|Real Estate|160|8|S|Main
PANI|Pantai Indah Kapuk Dua|Properties & Real Estate|Real Estate|14000|236|8S|Main
GOTO|GoTo Gojek Tokopedia|Technology|Software & IT Services|68|81|L38|Main
BUKA|Bukalapak.com|Technology|Software & IT Services|140|14|8S|Main
EMTK|Elang Mahkota Teknologi|Technology|Software & IT Services|500|30|8S|Main
MTDL|Metrodata Electronics|Technology|Technology Hardware|600|7|S|Development
BIRD|Blue Bird|Transportation & Logistic|Transportation|1900|5|S|Main
ASSA|Adi Sarana Armada|Transportation & Logistic|Logistics & Deliveries|700|3|S|Development
SMDR|Samudera Indonesia|Transportation & Logistic|Transportation|300|5|S|Main`.split('\n').map(l => { const [tk, name, sector, industry, px, cap, flags, board] = l.split('|'); return {tk, name, sector, industry, px:+px, cap:+cap, idx:{LQ45:flags.includes('L'), IDX30:flags.includes('3'), IDX80:flags.includes('8') || flags.includes('L'), ISSI:flags.includes('S')}, board, notation:''} });
export const BROKERS: any[] = [['AK','UBS Sekuritas',1],['BK','J.P. Morgan',1],['ZP','Maybank Sekuritas',1],['KZ','CLSA',1],['RX','Macquarie',1],['DR','RHB Sekuritas',1],['YP','Mirae Asset',0],['CC','Mandiri Sekuritas',0],['PD','Indo Premier',0],['XL','Stockbit Sekuritas',0],['NI','BNI Sekuritas',0],['OD','BRI Danareksa',0],['LG','Trimegah',0],['EP','MNC Sekuritas',0]];

/* ---------- seeded randomness ---------- */
const hashStr = s => { let h = 2166136261; for(const c of s) h = Math.imul(h ^ c.charCodeAt(0), 16777619) >>> 0; return h };
const rng = seed => { let a = hashStr(seed); return () => { a = (a + 0x6D2B79F5) >>> 0; let t = a; t = Math.imul(t ^ t >>> 15, t | 1); t ^= t + Math.imul(t ^ t >>> 7, t | 61); return ((t ^ t >>> 14) >>> 0) / 4294967296 } };
const gaussOf = r => () => { let u = 0, v = 0; while(!u) u = r(); while(!v) v = r(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v) };
const btw = (r, a, b) => a + r() * (b - a);
const tick = p => p < 200 ? 1 : p < 500 ? 2 : p < 2000 ? 5 : p < 5000 ? 10 : 25;
const toTick = p => Math.max(1, Math.round(p / tick(p)) * tick(p));
const factor = seed => { const g = gaussOf(rng(seed)); return Array.from({length:N}, () => g()) };
const MARKET: number[] = factor('mkt'), SECTOR_F: Record<string, number[]> = {};

/* ---------- per-ticker market series ----------
   A hidden "bandar regime" (accumulate / neutral / distribute, 12–40 sessions each) drives a few
   brokers' net buying and nudges price a few sessions later — so flow screens have something real to find. */
function makeTicker(L: any): any {
  const r = rng(L.tk), g = gaussOf(r);
  const vol = L.tk === 'GOTO' || L.tk === 'BUKA' ? .028 : ['Coal','Metals & Minerals','Oil & Gas'].includes(L.industry) ? btw(r, .016, .022) : L.industry === 'Banks' ? btw(r, .009, .013) : L.cap < 10 ? btw(r, .018, .026) : btw(r, .011, .017);
  const beta = btw(r, .6, 1.3); SECTOR_F[L.sector] ??= factor('sec' + L.sector); const S = SECTOR_F[L.sector];
  const regime = new Int8Array(N); for(let i = 0; i < N;){ const len = Math.round(btw(r, 12, 40)), x = r(), st = x < .3 ? 1 : x < .5 ? -1 : 0; for(let k = 0; k < len && i < N; k++, i++) regime[i] = st }
  const noise = MARKET.map((m, i) => beta * m * .006 + S[i] * .004 + g() * vol + (regime[Math.max(0, i - 6)] || 0) * vol * .12);
  const target = Math.log(1 + btw(r, -.35, .7)), drift = (target - noise.reduce((s, x) => s + x, 0)) / N;
  const ret = noise.map(x => Math.exp(x + drift) - 1);
  let p = 100; const raw = ret.map(x => (p *= 1 + x)); const k = L.px / raw[N - 1];
  const c = raw.map((x, i) => i === N - 1 ? L.px : toTick(x * k));
  const o = c.map((x, i) => toTick(i ? c[i - 1] * (1 + g() * vol * .3) : x));
  const h = c.map((x, i) => toTick(Math.max(x, o[i]) * (1 + Math.abs(g()) * vol * .35)));
  const l = c.map((x, i) => toTick(Math.min(x, o[i]) * (1 - Math.abs(g()) * vol * .35)));
  const shares = L.cap * 1e12 / L.px, turn = L.cap > 200 ? btw(r, .0005, .0012) : btw(r, .0008, .0035);
  const v = c.map((x, i) => Math.round(shares * turn * (1 + Math.abs(ret[i]) / vol * .35 + (regime[i] === 1 ? .35 : 0)) * Math.exp(g() * .3) / 100) * 100);
  const val = c.map((x, i) => x * v[i]);
  const ticket = btw(r, 4e6, 25e6), freq = val.map((x, i) => Math.round(x / ticket * Math.exp(g() * .25) * (r() < .02 ? btw(r, 2.5, 5) : 1)));
  const fwd = i => (ret[i + 1] || 0) + (ret[i + 2] || 0) + (ret[i + 3] || 0);
  const foreign = val.map((x, i) => x * (.07 * Math.tanh(fwd(i) / vol) + .04 * Math.tanh(ret[i] / vol) + .05 * regime[i] + g() * .05));
  // broker nets: 2–3 "bandar" brokers per ticker follow the regime, the rest is noise; each day sums to zero
  const bandar = [...BROKERS.keys()].sort(() => r() - .5).slice(0, 2 + (r() < .5 ? 1 : 0));
  const net = BROKERS.map(() => new Float64Array(N));
  for(let i = 0; i < N; i++){ let s = 0; BROKERS.forEach((b, j) => { const x = val[i] * ((bandar.includes(j) ? .09 * regime[i] : 0) + (b[2] ? .25 : .15) * (foreign[i] / (val[i] || 1)) * (b[2] ? 1 : -.4) + g() * .03); net[j][i] = x; s += x }); BROKERS.forEach((_, j) => net[j][i] -= s / BROKERS.length) }
  const tp = c.map((x, i) => (x + h[i] + l[i]) / 3);
  return {...L, c, o, h, l, v, val, freq, foreign, net, tp, ret, regime, shares, bandarIdx:bandar};
}
export const T: Record<string, any> = Object.fromEntries(LISTINGS.map(L => [L.tk, makeTicker(L)]));
export const TICKERS = LISTINGS.map(L => L.tk);
export const IHSG: number[] = (() => { const out = [1]; for(let i = 1; i < N; i++){ let num = 0, den = 0; for(const tk of TICKERS){ const t = T[tk]; num += t.cap * (t.c[i] / t.c[i - 1] - 1); den += t.cap } out.push(out[i - 1] * (1 + num / den)) } return out })();
