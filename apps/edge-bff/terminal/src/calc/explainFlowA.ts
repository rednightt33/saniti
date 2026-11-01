/* EXEC-IND-CARDS IC3: Flow explainers (calc/explain.ts: the interface, the helpers and the rule that the card's number
   is the chart's number). One file per part so they can be written side by side; explainFlowIndex.ts joins them. */
import type { BrokerSums, FlowExplainer } from './explain';
import { againstLevels, brokerRow, filterOf, filterText, flowWindow, fmt, intOf, levelsOf, spanOf, topBy, windowSums } from './explain';

/* ---- Flow explainers (FL ids of flowRegistry.json) ---- */
/* FL01-FL19 (FL24 is the reference explainer, kept here) */
export const FLOW_EXPLAIN_A: Record<string, FlowExplainer> = {
  /* FL24 Bandar Balance · %: 100 (NB + NS) / TBV(filter) (calc/flow.ts balancePct, bandar) */
  FL24: (c, p, t) => {
    const R = c.rows, W = intOf(p.window, 10), N = intOf(p.top, 3), a = flowWindow(R, t, W);
    if (a === null) return null;
    const { brokers, total } = windowSums(R, a, t, filterOf(p, 'boards'), filterOf(p, 'investors'));
    const net = (s: BrokerSums) => s.bv - s.sv;
    const buyers = topBy(brokers, N, net), sellers = topBy(brokers, N, s => -net(s));
    const NB = buyers.reduce((x, s) => x + net(s), 0), NS = sellers.reduce((x, s) => x + net(s), 0), TBV = total.bv;
    const combine = (v: Record<string, number>) => v.TBV ? 100 * (v.NB + v.NS) / v.TBV : null;
    const value = combine({ NB, NS, TBV }), lv = levelsOf(p);
    return {
      output:'value', value, expr:'100 × (NB + NS) ÷ TBV', span:spanOf(c, a, t),
      terms:[{ key:'NB', label:`Net beli ${N} pembeli terbesar`, value:NB, unit:'idr' },
             { key:'NS', label:`Net jual ${N} penjual terbesar`, value:NS, unit:'idr' },
             { key:'TBV', label:'Total nilai beli semua broker', value:TBV, unit:'idr' }], combine,
      steps:[
        { title:`Ambil ${W} candle`, text:`${c.dates[a]} sampai ${c.dates[t]}, ${filterText(p)}.` },
        { title:'Hitung net setiap broker', text:`Net = nilai beli − nilai jual selama jendela. Ambil ${N} net beli terbesar (NB) dan ${N} net jual terbesar (NS).`,
          table:{ head:['Broker', 'Beli', 'Jual', 'Net'],
            rows:[...buyers.map(brokerRow), ['NB', '', '', fmt.idr(NB)], ...sellers.map(brokerRow), ['NS', '', '', fmt.idr(NS)]] } },
        { title:'Bandingkan dengan seluruh transaksi', text:`Total nilai beli semua broker (TBV) dalam jendela: ${fmt.idr(TBV)}.` },
        { title:'Hitung nilainya', text:`100 × (${fmt.idr(NB)} + ${fmt.idr(NS)}) ÷ ${fmt.idr(TBV)} = ${fmt.pct(value)}.` },
        ...(value !== null && lv.length ? [{ title:'Baca hasilnya', text:`${fmt.pct(value)} berada ${againstLevels(value, lv)}.` }] : []),
      ],
    };
  },
};
