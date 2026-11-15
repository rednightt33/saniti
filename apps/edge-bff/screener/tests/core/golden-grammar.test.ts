/* EXEC-BACKTEST-REVAMP P0.1: the Screener's results frozen before its condition grammar moves into the Backtest core
   (P1). Every test form the catalog offers (every indicator output form and every pattern, through the page's own
   card -> wire mapping, forms.ts toWire) is bound and run as a whole-series signal (condition.ts conditionSignal) on
   deterministic synthetic tickers, and every preset is screened (screen.ts runScreen). The golden file holds a sha256
   of each 0/1 series and each preset's rows; P1 must leave it byte-identical. Regenerate only for an approved change:
   GOLDEN_UPDATE=1 npx vitest run tests/core/golden-grammar.test.ts. */
import crypto from 'node:crypto';
import fs from 'node:fs';
import { describe, expect, it } from 'vitest';
import type { CatalogResponse, Definition, UniverseRow } from '../../src/core/contract.ts';
import { UNIVERSE_DEFAULTS } from '../../src/core/contract.ts';
import { bindCondition, conditionSignal } from '../../src/core/condition.ts';
import { tickerCalc } from '../../src/core/metrics.ts';
import { runScreen } from '../../src/core/screen.ts';
import { PRESETS } from '../../src/core/catalog.ts';
import { entriesOf } from '../../src/entries.ts';
import { newCard, toWire } from '../../src/forms.ts';
import { fixtureApi } from '../fixture/api.ts';
import { memoryEnv, rowOf, synth } from './helpers.ts';

const FILE = new URL('./golden-grammar.json', import.meta.url).pathname;
const IX = (() => { const t = synth('IHSG', 3, 520, '2024-06-03'); return { ...t, bars: { ...t.bars, V: t.bars.V.map(() => null) } } })();
const E = IX.dates[IX.dates.length - 1];
const TICKERS = [synth('GA01', 701, 520, '2024-06-03'), synth('GA02', 702, 520, '2024-06-03'), synth('GA03', 703, 300, '2025-01-06')];
const rows: UniverseRow[] = TICKERS.map(t => rowOf(t, E, { adv20_idr: 5e9, last: 1000 }));
const sha = (b: Uint8Array) => crypto.createHash('sha256').update(b).digest('hex').slice(0, 24);
const round = (v: unknown) => typeof v === 'number' ? Number(v.toPrecision(12)) : v;

async function compute(): Promise<Record<string, unknown>> {
  const api = fixtureApi(), cat = (await api.catalog(null)) as { status: 200; body: CatalogResponse };
  const entries = entriesOf(cat.body).filter(e => (e.kind === 'indicator' || e.kind === 'pattern') && e.available);
  const env = memoryEnv(TICKERS, IX, rows, E), out: Record<string, unknown> = {};
  for (const e of entries) for (const o of e.opts) {
    if (o.disabled) continue;
    const key = `${e.key}:${o.key}`;
    try {
      const card = newCard(e, [], { opt: o.key }), def = toWire(e, card);
      const b = bindCondition(def, 'golden', env);
      out[key] = TICKERS.map(t => { const calc = tickerCalc(t), s = conditionSignal(b, r => r.full(calc) as ArrayLike<number | null>, t.dates.length);
        return s ? sha(s) : null });
    } catch (err) { out[key] = `refused ${(err as { code?: string }).code ?? (err as Error).message}` }
  }
  const U = { ...UNIVERSE_DEFAULTS, price_min: null, adv20_min_idr: null } as Definition['universe'];
  for (const p of PRESETS.presets) {
    try {
      const r = runScreen({ ...p.definition, universe: U } as Definition, memoryEnv(TICKERS, IX, rows, E));
      out[`preset:${p.id}`] = r.rows.map(x => ({ t: x.ticker, s: x.status, c: (x.cells || []).map(c => [c.status, round(c.value), c.event_date ?? null, c.reason ?? null, c.remark ?? null]) }));
    } catch (err) { out[`preset:${p.id}`] = `refused ${(err as { code?: string }).code ?? (err as Error).message}` }
  }
  return out;
}

describe('golden grammar (EXEC-BACKTEST-REVAMP P0.1)', () => {
  it('every offered test form and every preset gives the frozen result', async () => {
    const got = await compute();
    if (process.env.GOLDEN_UPDATE === '1') fs.writeFileSync(FILE, JSON.stringify(got, null, 1) + '\n');
    const want = JSON.parse(fs.readFileSync(FILE, 'utf8'));
    expect(Object.keys(got).length).toBeGreaterThan(200);
    expect(JSON.parse(JSON.stringify(got))).toEqual(want);
  });
});
