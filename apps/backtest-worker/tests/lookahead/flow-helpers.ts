/* EXEC-BACKTEST-REVAMP P3: the Flow indicators a backtest offers, derived from the Screener's generated registry (no
   list kept by hand): its entries computed by the Terminal module (compute 'terminal') with an FL id and no data it
   lacks (requires). Each with its outputs, the option variants one at a time (select and multi options, both booleans;
   a broker list names one fixture broker), its parameters completed as the backtest completes them (no baseline lowered)
   and the key of an output in computeFlow's answer. */
import { FLOWS as SCREENER_FLOWS, resolveFlowParams, seriesKeyOf } from '../../../edge-bff/screener/src/core/flowmetrics.ts';
import { flowDefaults } from '../../../edge-bff/terminal/src/calc/flow.ts';

const opt = (o: unknown) => Array.isArray(o) ? o[0] : o;
export const FLOWS = SCREENER_FLOWS.filter(e => e.compute === 'terminal' && !e.requires && /^FL\d+$/.test(e.id)).map(e => {
  const variants: Record<string, unknown>[] = [{}];
  for (const p of e.params.filter(q => q.condition)) {
    const vs = p.kind === 'select' ? (p.options ?? []).map(opt) : p.kind === 'bool' ? [true, false] : p.kind === 'multi' ? (p.options ?? []).map(o => [opt(o)])
      : p.kind === 'brokers' ? [['AA'], ['AA', 'BK']] : [];
    for (const v of vs) variants.push({ [p.key]: v });
  }
  const normalized = (v: Record<string, unknown>) => resolveFlowParams(e, v, 'f', Number.MAX_SAFE_INTEGER) as Record<string, unknown>;
  return { id: e.id, outputs: e.outputs.map(o => o.key), variants, normalized, defaults: flowDefaults(e.id) as Record<string, unknown>,
    seriesKey: (o: string, v: Record<string, unknown>) => seriesKeyOf(e, o, normalized(v) as never, 'f') };
});
