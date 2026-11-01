/* EXEC-IND-CARDS IC4: technical explainers (calc/explain.ts: the interface, the helpers and the rule that the card's
   number is the chart's number). One file per part so they can be written side by side; explainTechIndex.ts joins them. */
import type { TechExplainer } from './explain';
import { dateOf, fmt, intOf, sourceAt, SOURCES } from './explain';

/* I01-I26 (I01 sma is the reference explainer) */
export const TECH_EXPLAIN_A: Record<string, TechExplainer> = {
  /* I01 SMA: SUM(src, n) / n over the last n valid, consecutive values (calc/indicators.ts sma, roll) */
  sma: (B, p, t) => {
    const n = intOf(p.length, 20), s = String(p.source || 'close');
    if (t - n + 1 < 0) return null;
    const xs: number[] = [];
    for (let i = t - n + 1; i <= t; i++) { const v = sourceAt(B, s, i); if (v === null) return null; xs.push(v) }
    const SUM = xs.reduce((x, v) => x + v, 0), combine = (v: Record<string, number>) => v.n ? v.SUM / v.n : null;
    const rows = xs.map((v, k) => [dateOf(B, t - n + 1 + k), fmt.num(v)]);
    const shown = rows.length > 12 ? [...rows.slice(0, 5), ['…', ''], ...rows.slice(-5)] : rows;
    return {
      output:'sma', value:combine({ SUM, n }), expr:'SUM ÷ n', span:{ from:dateOf(B, t - n + 1), to:dateOf(B, t), candles:n },
      terms:[{ key:'SUM', label:`Jumlah ${SOURCES[s] || s} ${n} candle`, value:SUM, unit:'price' }, { key:'n', label:'Panjang (n)', value:n, unit:'count' }], combine,
      steps:[
        { title:`Ambil ${n} candle terakhir`, text:`${dateOf(B, t - n + 1)} sampai ${dateOf(B, t)}, nilai ${SOURCES[s] || s} setiap candle.`,
          table:{ head:['Tanggal', SOURCES[s] || s], rows:shown } },
        { title:'Jumlahkan', text:`SUM = ${fmt.num(SUM)}.` },
        { title:'Bagi dengan n', text:`${fmt.num(SUM)} ÷ ${n} = ${fmt.num(SUM / n)}.` },
      ],
    };
  },
};
