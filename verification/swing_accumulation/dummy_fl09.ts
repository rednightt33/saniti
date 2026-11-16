// Dummy data for FL09 Block Money Candidate: 320 ordinary days, then 4 special days. Run: TERMINAL_SRC=$PWD/src npx vite-node dummy_fl09.ts
import fs from 'node:fs';
const SRC = process.env.TERMINAL_SRC!;
const flow: any = await import(SRC + '/calc/flow.ts');
let seed = 12345; const rnd = () => { seed = (seed * 1664525 + 1013904223) % 4294967296; return seed / 4294967296; }; const U = (a: number, b: number) => a + (b - a) * rnd();
const B = ['AA', 'BB', 'CC', 'DD', 'EE', 'FF', 'GG', 'HH', 'II', 'JJ', 'KK', 'LL'], PRICE = 1000, VAL = 100 * PRICE;       // 1 lot = 100 shares
type Row = { d: string; b: string; i: string; m: string; bv: number; sv: number; bl: number; sl: number; bf: number; sf: number };
const dates: string[] = []; const rows: Row[] = [];
const dayStr = (k: number) => { const d = new Date(Date.UTC(2025, 0, 1 + k + 2 * Math.floor(k / 5))); return d.toISOString().slice(0, 10); };
const add = (d: string, b: string, bl: number, bt: number, sl: number, st: number) => rows.push({ d, b, i: 'Domestic', m: 'Regular', bl, sl, bv: bl * VAL, sv: sl * VAL, bf: Math.max(1, Math.round(bt)), sf: Math.max(1, Math.round(st)) });
const NORMAL = 320;
for (let k = 0; k < NORMAL; k++) {            // ordinary day: every broker trades about 3,000-9,000 lots a side with a ticket of 8-14 lots; now and then one broker has a bigger-ticket day
  const d = dayStr(k); dates.push(d); const big = rnd() < 0.3 ? B[Math.floor(rnd() * 12)] : '';
  for (const b of B) { const inst = ['AA', 'BB', 'CC', 'DD'].includes(b), bl = inst ? U(5000, 13000) : U(3000, 8000), sl = inst ? U(3000, 9000) : U(3000, 8000), tb = b === big ? U(20, 40) : inst ? U(8, 14) : U(3, 5), ts = inst ? U(8, 14) : U(3, 5); add(d, b, bl, bl / tb, sl, sl / ts); }
}
type Day = { name: string; cohort: [string, number, number][]; others: [number, number] };   // cohort: broker, buy lots, lots per buy transaction; others: lots per broker, lots per transaction
const SIZE2 = Number(process.env.SIZE2 || 10);
const specials: Day[] = [
  { name: 'HARI 1 (memicu)', cohort: [['AA', 10000, 250], ['BB', 8000, 200], ['CC', 6000, 150]], others: [7000, 4] },
  { name: 'HARI 2 (tiket besar menurut pasar, biasa bagi saham ini)', cohort: [['AA', 10000, SIZE2], ['BB', 8000, SIZE2], ['CC', 6000, SIZE2]], others: [7000, 4] },
  { name: 'HARI 3 (semua broker bertiket besar)', cohort: [['AA', 10000, 250], ['BB', 8000, 200], ['CC', 6000, 150]], others: [7000, 140] },
  { name: 'HARI 4 (porsi kelompok terlalu kecil)', cohort: [['AA', 1000, 250], ['BB', 800, 200], ['CC', 600, 150]], others: [7000, 4] },
];
for (let s = 0; s < specials.length; s++) {
  const d = dayStr(NORMAL + s); dates.push(d); const sp = specials[s], names = new Set(sp.cohort.map(c => c[0]));
  for (const [b, lots, size] of sp.cohort) add(d, b, lots, lots / size, 0, 1);                                // the cohort sells nothing: pure net buyers
  for (const b of B) if (!names.has(b)) add(d, b, sp.others[0], sp.others[0] / sp.others[1], sp.others[0] * U(1.0, 1.03), sp.others[0] / sp.others[1]);   // the others are slight net sellers
}
const N = dates.length, at = new Map(dates.map((d, k) => [d, k]));
const ctx = { rows: flow.flowRows(rows, N, (d: string) => at.get(d) ?? -1), dates, close: dates.map(() => PRICE), volume: dates.map(() => 1e6), insider: [], classification: {} };
const P = { scope: 'topn', top: 3, rank: 'net_buy', window: 1, boards: ['Regular'], investors: ['Foreign', 'Domestic'], baseline: 250 };
const f09 = flow.computeFlow('FL09', ctx, {}).value, f08 = flow.computeFlow('FL08', ctx, { ...P, side: 'buy' }).value, f05 = flow.computeFlow('FL05', ctx, { ...P, side: 'buy' }).buy, f07 = flow.computeFlow('FL07', ctx, { ...P, denom: 'board', side: 'buy' }).value, f11 = flow.computeFlow('FL11', ctx, { ...P }).value;
console.log('defaults FL09:', JSON.stringify(flow.flowDefaults('FL09')));
console.log('hari ordinary terakhir (k=%d): FL09=%s', NORMAL - 1, f09[NORMAL - 1]);
console.log('FL09 pada 320 hari biasa: dipicu', f09.slice(0, NORMAL).filter((v: any) => v === 1).length, 'kali; nol', f09.slice(0, NORMAL).filter((v: any) => v === 0).length, '; kosong', f09.slice(0, NORMAL).filter((v: any) => v === null).length);
const f5 = (x: any) => x === null || x === undefined ? 'kosong' : Number(x).toFixed(1);
for (let s = 0; s < specials.length; s++) {
  const t = NORMAL + s, d = dates[t], R = rows.filter(r => r.d === d), tb = R.reduce((a, r) => a + r.bl, 0), tf = R.reduce((a, r) => a + r.bf, 0), top = [...R].sort((a, b) => (b.bv - b.sv) - (a.bv - a.sv)).slice(0, 3), cl = top.reduce((a, r) => a + r.bl, 0), cf = top.reduce((a, r) => a + r.bf, 0);
  console.log(`${specials[s].name} ${d}: kohort ${top.map(r => r.b).join(',')} | lot beli kohort ${cl.toFixed(0)} dari ${tb.toFixed(0)} | tiket kohort ${(cl / cf).toFixed(0)} lot/transaksi, pasar ${(tb / tf).toFixed(0)} | FL08 persentil ${f5(f08[t])} | FL05 rasio ${f5(f05[t])} | FL07 porsi ${f5(f07[t])}% | FL11 net/turnover ${f5(f11[t])}% | FL09 = ${f09[t]}`);
}
