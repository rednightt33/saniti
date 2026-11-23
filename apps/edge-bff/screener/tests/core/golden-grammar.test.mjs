/* EXEC-BACKTEST-REVAMP P0.1: the Screener's results frozen before the Backtest reads its condition grammar (P1). Every
   test form the catalog offers (every indicator output form, every pattern and every other non-flow metric, through the
   page's own card -> wire mapping, forms.ts toWire) is bound and run as a whole-series signal (condition.ts
   conditionSignal) on deterministic synthetic tickers, and every preset is screened (screen.ts runScreen). The golden
   file holds a sha256 of each 0/1 series and each preset's rows; a later phase must leave it byte-identical.
   Regenerate only for an approved change: GOLDEN_UPDATE=1 npx vitest run tests/core/golden-grammar.test.mjs.
   Plain JavaScript (node:crypto, node:fs): the Screener's typecheck has no Node types. */
import crypto from 'node:crypto';
import fs from 'node:fs';
import { describe, expect, it } from 'vitest';
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
const rows = TICKERS.map(t => rowOf(t, E, { adv20_idr: 5e9, last: 1000 }));
const sha = b => crypto.createHash('sha256').update(b).digest('hex').slice(0, 24);
const round = v => typeof v === 'number' ? Number(v.toPrecision(12)) : v;

async function compute() {
  const api = fixtureApi(), cat = await api.catalog(null);
  // indicators, patterns and the other metrics; flow entries need broker files and fundamentals are not offered yet
  const entries = entriesOf(cat.body).filter(e => e.available && (e.kind === 'indicator' || (e.kind === 'metric' && !e.metric?.flow)));
  const env = memoryEnv(TICKERS, IX, rows, E), out = {};
  for (const e of entries) for (const o of e.opts) {
    if (o.disabled) continue;
    const key = `${e.kind}:${e.key}:${o.key}`;
    try {
      const card = newCard(e, [], { opt: o.key }), def = toWire(e, card);
      const b = bindCondition(def, 'golden', env);
      out[key] = TICKERS.map(t => { const calc = tickerCalc(t), s = conditionSignal(b, r => r.full(calc), t.dates.length); return s ? sha(s) : null });
    } catch (err) { out[key] = `refused ${err?.code ?? err?.message}` }
  }
  const U = { ...UNIVERSE_DEFAULTS, price_min: null, adv20_min_idr: null };
  for (const p of PRESETS.presets) {
    try {
      const r = runScreen({ ...p.definition, universe: U }, memoryEnv(TICKERS, IX, rows, E));
      out[`preset:${p.id}`] = r.rows.map(x => ({ t: x.ticker, s: x.status, c: (x.cells || []).map(c => [c.status, round(c.value), c.event_date ?? null, c.reason ?? null, c.remark ?? null]) }));
    } catch (err) { out[`preset:${p.id}`] = `refused ${err?.code ?? err?.message}` }
  }
  return out;
}

describe('golden grammar (EXEC-BACKTEST-REVAMP P0.1)', () => {
  it('every offered test form and every preset gives the frozen result', async () => {
    const got = await compute();
    if (process.env.GOLDEN_UPDATE === '1') fs.writeFileSync(FILE, JSON.stringify(got, null, 1) + '\n');
    const want = JSON.parse(fs.readFileSync(FILE, 'utf8'));
    const keys = Object.keys(got);
    expect(keys.length).toBeGreaterThan(200);
    expect(keys.filter(k => k.startsWith('metric:')).length).toBeGreaterThan(20);          // the patterns and metrics are in
    // every recorded case gives its frozen result; a case the golden does not hold (a new indicator's offered forms, at
    // its release) is new, not a changed result, and is recorded with GOLDEN_UPDATE=1 in the release's commit (lab dry
    // run 2026-11-23, INDICATOR_BETA_TO_LIVE.md part B)
    const recorded = Object.fromEntries(Object.keys(want).map(k => [k, got[k] ?? null]));
    expect(JSON.parse(JSON.stringify(recorded))).toEqual(want);
  });
});
