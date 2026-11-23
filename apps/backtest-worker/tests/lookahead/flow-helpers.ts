/* EXEC-BACKTEST-REVAMP P3: the Flow indicators a backtest offers, derived from the Screener's generated registry (no
   list kept by hand): its entries computed by the Terminal module (compute 'terminal') with an FL id and no data it
   lacks (requires). Each with its outputs, the option variants one at a time (select and multi options, both booleans;
   a broker list names fixture brokers, among them LATE, whose first row is at session 200, and GONE, whose last is at
   session 350: Stage C2 lens 1 F2), its parameters completed as the backtest completes them (no baseline lowered)
   and the key of an output in computeFlow's answer. */
import { FLOWS as SCREENER_FLOWS, resolveFlowParams, seriesKeyOf } from '../../../edge-bff/screener/src/core/flowmetrics.ts';
import { flowDefaults } from '../../../edge-bff/terminal/src/calc/flow.ts';

const opt = (o: unknown) => Array.isArray(o) ? o[0] : o;
function numbers(q: { kind: string; default?: unknown; min?: number; max?: number }): number[] {
  const d = Number(q.default), lo = q.min ?? (q.kind === 'int' ? 1 : d / 4), hi = Math.min(q.max ?? (Number.isFinite(d) ? d * 10 : 400), 400);
  const vs = [lo, Number.isFinite(d) ? Math.min(hi, d * 3) : hi, hi].filter(v => Number.isFinite(v));
  return [...new Set(vs.map(v => q.kind === 'int' ? Math.round(v) : v))].filter(v => v !== d);
}
export const FLOWS = SCREENER_FLOWS.filter(e => e.compute === 'terminal' && !e.requires && /^FL\d+$/.test(e.id)).map(e => {
  const variants: Record<string, unknown>[] = [{}];
  for (const p of e.params.filter(q => q.condition)) {
    const vs = p.kind === 'select' ? (p.options ?? []).map(opt) : p.kind === 'bool' ? [true, false] : p.kind === 'multi' ? (p.options ?? []).map(o => [opt(o)])
      : p.kind === 'brokers' ? [['AA'], ['AA', 'BK'], ['LATE'], ['AA', 'LATE'], ['GONE']]
      // check of steps 2-3 (2026-11-23, F3): numbers other than the default (minimum, three times the default, maximum,
      // capped at 400 sessions), as the technical part of the gate varies them
      : p.kind === 'int' || p.kind === 'num' ? numbers(p as { kind: string; default?: unknown; min?: number; max?: number }) : [];
    for (const v of vs) variants.push({ [p.key]: v });
    // a broker list is read only where its scope selects it (Stage C F3: the lists were never in use in the gate)
    const scope = p.kind === 'brokers' && p.key.endsWith('brokers') ? e.params.find(q => q.key === `${p.key.slice(0, -'brokers'.length)}scope`) : undefined;
    if (scope && (scope.options ?? []).map(opt).includes('selected')) for (const v of vs) variants.push({ [scope.key]: 'selected', [p.key]: v });
  }
  const normalized = (v: Record<string, unknown>) => resolveFlowParams(e, v, 'f', Number.MAX_SAFE_INTEGER) as Record<string, unknown>;
  return { id: e.id, outputs: e.outputs.map(o => o.key), variants, normalized, defaults: flowDefaults(e.id) as Record<string, unknown>,
    seriesKey: (o: string, v: Record<string, unknown>) => seriesKeyOf(e, o, normalized(v) as never, 'f') };
});
