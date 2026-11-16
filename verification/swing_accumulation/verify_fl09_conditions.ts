// Hand-made dummy numbers for the four default conditions of FL09, checked against the terminal engine. Run: TERMINAL_SRC=$PWD/src npx vite-node verify_fl09_conditions.ts
const SRC = process.env.TERMINAL_SRC!;
const flow: any = await import(SRC + '/calc/flow.ts');
const PRICE = 1000, VAL = 100 * PRICE;                                // 1 lot = 100 shares = Rp100,000 at Rp1,000
type R = { b: string; bl: number; bf: number; sl: number; sf: number };
function one(rows: R[]) {                                              // one trading day, Regular board
  const d = '2026-01-05', rr = rows.map(r => ({ d, b: r.b, i: 'Domestic', m: 'Regular', bv: r.bl * VAL, sv: r.sl * VAL, bl: r.bl, sl: r.sl, bf: r.bf, sf: r.sf }));
  return { rows: flow.flowRows(rr, 1, () => 0), dates: [d], close: [PRICE], volume: [1e6], insider: [], classification: {} };
}
const P = { scope: 'selected', brokers: ['A', 'B', 'C'], window: 1, boards: ['Regular'], investors: ['Foreign', 'Domestic'] };
const f1 = (x: any) => x === null || x === undefined ? 'kosong' : Number(x).toFixed(2);

// ---- Condition 1: percentile of today's cohort ticket against the 250 days before (baseline ticket rising evenly from 8 to 20 lots per transaction)
const base = Array.from({ length: 250 }, (_, k) => 8 + 12 * k / 249);
console.log('SYARAT 1 (persentil tiket vs 250 hari terakhir; riwayat 8 sampai 20 lot/transaksi, merata)');
for (const v of [40, 19, 18.8, 18, 15]) { const p = flow.percentile([...base, v], 250)[250]; console.log(`  tiket hari ini ${v} lot/transaksi -> persentil ${f1(p)} -> ${p >= 90 ? 'LOLOS' : 'TIDAK'} (ambang 90)`); }

// ---- Condition 2: cohort ticket / market ticket (market includes the cohort), threshold 2.0
console.log('SYARAT 2 (tiket kelompok / tiket rata-rata pasar >= 2,0)');
const c2 = (name: string, cl: number, cf: number, ol: number, of_: number) => {
  const rows: R[] = [{ b: 'A', bl: cl * .5, bf: cf * .5, sl: 0, sf: 1 }, { b: 'B', bl: cl * .3, bf: cf * .3, sl: 0, sf: 1 }, { b: 'C', bl: cl * .2, bf: cf * .2, sl: 0, sf: 1 }, { b: 'D', bl: ol * .55, bf: of_ * .55, sl: 0, sf: 1 }, { b: 'E', bl: ol * .45, bf: of_ * .45, sl: 0, sf: 1 }];
  const mt = (cl + ol) / (cf + of_), ct = cl / cf, r = flow.computeFlow('FL05', one(rows), { ...P, side: 'buy' }).buy[0];
  console.log(`  ${name}: kelompok ${cl} lot / ${cf} transaksi (tiket ${ct.toFixed(1)}); pasar ${cl + ol} lot / ${cf + of_} transaksi (tiket ${mt.toFixed(1)}) -> rasio mesin ${f1(r)} -> ${r >= 2 - 1e-9 ? 'LOLOS' : 'TIDAK'} (ambang 2,0)`);
};
c2('lolos jelas', 30000, 1500, 70000, 18500); c2('tepat di batas', 30000, 1500, 70000, 8500); c2('tidak lolos', 30000, 2000, 70000, 8000);

// ---- Condition 3: cohort buy lots / all buy lots on the board, threshold 5%
console.log('SYARAT 3 (lot beli kelompok / total lot beli papan >= 5%); total lot beli semua broker = 200.000');
for (const [name, cl] of [['lolos', 15000], ['tepat di batas', 10000], ['tidak lolos', 6000]] as [string, number][]) {
  const rows: R[] = [{ b: 'A', bl: cl * .5, bf: 10, sl: 0, sf: 1 }, { b: 'B', bl: cl * .3, bf: 10, sl: 0, sf: 1 }, { b: 'C', bl: cl * .2, bf: 10, sl: 0, sf: 1 }, { b: 'D', bl: (200000 - cl) * .6, bf: 100, sl: 0, sf: 1 }, { b: 'E', bl: (200000 - cl) * .4, bf: 100, sl: 0, sf: 1 }];
  const s = flow.computeFlow('FL07', one(rows), { ...P, denom: 'board', side: 'buy' }).value[0]; console.log(`  ${name}: kelompok membeli ${cl} lot -> porsi mesin ${f1(s)}% -> ${s >= 5 - 1e-9 ? 'LOLOS' : 'TIDAK'} (ambang 5%)`);
}

// ---- Condition 4: cohort net value (buy - sell) / all buy value on the board, must be above 0; all buy value of the board = Rp20 miliar (200.000 lot)
console.log('SYARAT 4 (nilai beli - nilai jual kelompok) / total nilai beli papan > 0; total nilai beli papan = Rp20 miliar');
for (const [name, bl, sl] of [['lolos (beli 30.000 lot, jual 10.000)', 30000, 10000], ['tepat nol (beli = jual)', 30000, 30000], ['tidak lolos (jual lebih besar)', 30000, 35000]] as [string, number, number][]) {
  const rows: R[] = [{ b: 'A', bl: bl * .5, bf: 10, sl: sl * .5, sf: 10 }, { b: 'B', bl: bl * .3, bf: 10, sl: sl * .3, sf: 10 }, { b: 'C', bl: bl * .2, bf: 10, sl: sl * .2, sf: 10 }, { b: 'D', bl: (200000 - bl) * .6, bf: 100, sl: 1000, sf: 1 }, { b: 'E', bl: (200000 - bl) * .4, bf: 100, sl: 1000, sf: 1 }];
  const f = flow.computeFlow('FL11', one(rows), { ...P }).value[0]; const ok = f > 0 && Math.abs(f) > 1e-12; console.log(`  ${name}: net ${((bl - sl) * VAL / 1e9).toFixed(2)} miliar -> arus bersih/turnover ${f1(f)}% -> ${ok ? 'LOLOS' : 'TIDAK'} (harus di atas 0)`);
}
