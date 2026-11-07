/* Every existing condition of the Backtest core gives the same result as before (EXEC-SCREENER-FLOW-CANDLES P6, user
   decision K2 "A": an approval path for Backtest-core changes, "ditambah tes bahwa hasil kondisi lama tetap sama";
   verification/screener/P6_CANDLES.md section 3).
   On the Terminal parity fixtures (BBCA, CLAY, DEWI, GOTO, IHSG, ISEA, KOCI, UNVR, full stored history) every
   condition the core had before the candle patterns (conditions.ts: indicator conditions over every registry
   indicator, output and operator against a value, the price and a sibling output, at the defaults and one other
   parameter set; every price-action type and operator; the flow conditions fnet, broker and top5 on deterministic
   broker rows) and the portfolio values signals.ts derives (the four ranking scores, the liquidity value) is computed
   with the current core and compared, condition by condition, with conditions-golden.json: the digest of the same
   computation recorded with the core as it was before P6 (`recorded_with` names that core's engine_version, the
   version every Backtest result carries; origin/main 4451a31a had it). A digest covers the 0/1 series (or the values)
   of all eight tickers, or the refusal code where the core refuses the condition on a ticker.
   Record again only for a deliberate change of an existing condition, with its own approval:
     CONDITIONS_GOLDEN=record node --experimental-strip-types --import ./loader/register.mjs --test tests/conditions-unchanged.test.ts
   (from apps/backtest-worker). */
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';
import { DEFAULTS } from '../../edge-bff/terminal/src/calc/indicators.ts';
import { loadFixtures } from '../../edge-bff/terminal/tests/calc/fixtures.mjs';
import { Calc, conditionSeries } from '../../edge-bff/backtest/src/core/conditions.ts';
import type { Condition, Op } from '../../edge-bff/backtest/src/core/conditions.ts';
import type { BrokerRow } from '../../edge-bff/backtest/src/core/datafile.ts';
import { flowData } from '../../edge-bff/backtest/src/core/flow.ts';
import { REGISTRY, ValidationError } from '../../edge-bff/backtest/src/core/registry.ts';
import { RANK_BY, liquidity, rankScores } from '../../edge-bff/backtest/src/core/signals.ts';
import { engineVersion } from '../src/version.ts';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const GOLDEN = path.join(HERE, 'conditions-golden.json');
const sha = (s: string | Uint8Array) => crypto.createHash('sha256').update(s).digest('hex');

const fixtures = loadFixtures().map((f: any) => ({ ticker: f.ticker as string, bars: { T: f.T, O: f.O, H: f.H, L: f.L, C: f.C, V: f.V } }));
/** What the digests were computed on: the fixtures' tickers and the sha256 of their bars. */
const fixtureHash = sha(JSON.stringify(fixtures.map(f => [f.ticker, f.bars.T, f.bars.O, f.bars.H, f.bars.L, f.bars.C, f.bars.V])));

/* ---- deterministic broker rows per ticker (the fixtures carry none), so the flow conditions have values --------- */
function seeded(seed: number) { let s = seed >>> 0; return () => ((s = (Math.imul(s, 1664525) + 1013904223) >>> 0) / 4294967296) }
const BROKERS = ['AK', 'BK', 'CC', 'KZ', 'YP', 'ZP', 'RX', 'DX'];
function brokerRowsOf(ticker: string, dates: readonly string[]): BrokerRow[] {
  const rnd = seeded([...ticker].reduce((h, ch) => Math.imul(h ^ ch.charCodeAt(0), 16777619) >>> 0, 2166136261));
  const rows: BrokerRow[] = [], from = Math.floor(dates.length / 4);             // broker data on the last three quarters
  for (let k = from; k < dates.length; k++) {
    if (rnd() < 0.03) continue;                                                  // a session without any broker row
    for (const b of BROKERS) {
      if (rnd() < 0.4) continue;
      const i = rnd() < 0.45 ? 'Foreign' : 'Domestic', m = rnd() < 0.85 ? 'Regular' : rnd() < 0.5 ? 'Nego' : 'Tunai';
      const bv = Math.round(rnd() * 5e9), sv = Math.round(rnd() * 5e9);
      rows.push({ d: dates[k], b, i, m, bv, sv, bl: Math.round(bv / 1e5), sl: Math.round(sv / 1e5) });
    }
  }
  return rows;
}

/* ---- the cases: every condition the core had before P6 --------------------------------------------------------- */
const OPS: Op[] = ['gt', 'lt', 'crosses_above', 'crosses_below'];
const median = (s: ReadonlyArray<number | null | undefined>) => { const v = s.filter(x => typeof x === 'number' && Number.isFinite(x)).sort((a, b) => (a as number) - (b as number)) as number[]; return v.length ? v[Math.floor(v.length / 2)] : 0 };
interface Case { id: string; make: (c: Calc) => Condition }
function cases(): Case[] {
  const out: Case[] = [];
  for (const r of REGISTRY.indicators) {
    const variants: Record<string, unknown>[] = [{}, Object.fromEntries(r.params.filter(p => p.type === 'integer').map(p => [p.key, (p.default as number) + 1]))];
    variants.forEach((params, v) => {
      for (const o of r.outputs) for (const op of OPS) {
        const sib = r.outputs.find(x => x !== o);
        const base = { kind: 'indicator' as const, indicator: r.id, params, op };
        // the value side is the output's median on the ticker (the page's default threshold, regMedian), so it switches
        out.push({ id: `${r.id}/${v}/${o}/${op}/value`, make: c => ({ ...base, id: 'x', lhs: { type: 'output', output: o }, rhs: { type: 'value', value: median(c.out(r.key, { ...DEFAULTS[r.key], ...params })[o]) } }) });
        out.push({ id: `${r.id}/${v}/${o}/${op}/price`, make: () => ({ ...base, id: 'x', lhs: { type: 'price' }, rhs: { type: 'output', output: o } }) });
        if (sib) out.push({ id: `${r.id}/${v}/${o}/${op}/${sib}`, make: () => ({ ...base, id: 'x', lhs: { type: 'output', output: o }, rhs: { type: 'output', output: sib } }) });
      }
    });
  }
  const pa = (id: string, type: string, extra: Record<string, unknown>) => out.push({ id: `price_action/${id}`, make: () => ({ id: 'x', kind: 'price_action', type, ...extra }) as Condition });
  for (const v of [-0.01, -0.03, -0.07, -0.2]) pa(`dip/${v}`, 'dip', { value: v });
  for (const n of [1, 5, 20, 55, 250]) pa(`breakout/${n}`, 'breakout', { params: { length: n } });
  for (const n of [1, 5, 20, 60]) for (const v of [0, 1, 1.5, 2, 3]) pa(`volspike/${n}/${v}`, 'volspike', { params: { length: n }, value: v });
  for (const op of ['golden_cross', 'fast_above_slow']) for (const [f, s] of [[20, 50], [10, 30], [5, 200], [50, 20]]) pa(`macross/${op}/${f}/${s}`, 'macross', { op, params: { fast_length: f, slow_length: s } });
  pa('macross/default', 'macross', {});
  for (const op of ['bullish_divergence', 'crosses_above_signal', 'histogram_positive']) for (const [f, s, g] of [[12, 26, 9], [8, 21, 5], [5, 35, 5]])
    pa(`macd/${op}/${f}/${s}/${g}`, 'macd', { op, params: { fast_length: f, slow_length: s, signal_length: g } });
  pa('macd/default', 'macd', {});
  const fl = (id: string, cond: Record<string, unknown>) => out.push({ id: `flow/${id}`, make: () => ({ id: 'x', kind: 'flow', ...cond }) as Condition });
  for (const n of [1, 5, 20, 60]) {
    for (const op of ['gt', 'lt']) for (const v of [0, 5e9, -5e9]) fl(`fnet/${n}/${op}/${v}`, { type: 'fnet', op, params: { length: n }, value: v });
    for (const b of ['AK', 'YP', 'NONE']) for (const v of [0, 2e9]) fl(`broker/${b}/${n}/${v}`, { type: 'broker', op: 'gt', params: { length: n, broker: b }, value: v });
    for (const v of [0, 1e10]) fl(`top5/${n}/${v}`, { type: 'top5', op: 'gt', params: { length: n }, value: v });
  }
  return out;
}

/** Every case's digest over the eight tickers (and the signals.ts values), with the current core. */
function digests(): Record<string, string> {
  const all = cases(), parts = new Map<string, string[]>(all.map(k => [k.id, []]));
  const values = new Map<string, string[]>();
  for (const { ticker, bars } of fixtures) {
    const flow = flowData(brokerRowsOf(ticker, bars.T), bars.T);
    const c = new Calc(bars, flow);
    for (const k of all) {
      let part: string;
      try { part = Buffer.from(conditionSeries(c, k.make(c))).toString('base64') }
      catch (e) { if (!(e instanceof ValidationError)) throw e; part = `ERR:${e.code}:${e.field}` }
      parts.get(k.id)!.push(`${ticker}:${part}`);
    }
    const put = (id: string, s: ReadonlyArray<number | null>) => { if (!values.has(id)) values.set(id, []); values.get(id)!.push(`${ticker}:${JSON.stringify(s)}`) };
    for (const by of RANK_BY) {
      try { put(`signals/rank/${by}`, rankScores(c, by, flow)) } catch (e) { if (!(e instanceof ValidationError)) throw e; put(`signals/rank/${by}`, [e.code as unknown as number]) }
    }
    put('signals/liquidity', liquidity(c));
  }
  const out: Record<string, string> = {};
  for (const [id, p] of parts) out[id] = sha(p.join('\n')).slice(0, 16);
  for (const [id, p] of values) out[id] = sha(p.join('\n')).slice(0, 16);
  return out;
}

test('every existing core condition gives the same result as before the candle patterns (golden recorded on the base core)', () => {
  const now = digests();
  if (process.env.CONDITIONS_GOLDEN === 'record') {
    const doc = {
      schema: 1,
      about: 'Digests of every condition the Backtest core had before EXEC-SCREENER-FLOW-CANDLES P6 (and the signals.ts ranking and liquidity values) on the Terminal parity fixtures, recorded with the core whose engine_version is recorded_with; tests/conditions-unchanged.test.ts compares the current core with them (user decision K2 "A", 2026-11-07).',
      recorded_with: engineVersion(),
      fixtures: fixtures.map(f => f.ticker), fixture_sha256: fixtureHash,
      cases: Object.keys(now).length,
      digests: now,
    };
    fs.writeFileSync(GOLDEN, JSON.stringify(doc, null, 1) + '\n');
    console.log(`recorded ${doc.cases} digests with engine_version ${doc.recorded_with} in ${GOLDEN}`);
    return;
  }
  const g = JSON.parse(fs.readFileSync(GOLDEN, 'utf8'));
  assert.equal(g.fixture_sha256, fixtureHash, 'the parity fixtures changed: the golden was recorded on other bars (record again only with the base core)');
  assert.deepEqual(Object.keys(now).sort(), Object.keys(g.digests).sort(), 'the case list changed: a case of an existing condition was added or removed');
  const changed = Object.keys(now).filter(id => now[id] !== g.digests[id]);
  assert.deepEqual(changed, [], `${changed.length} existing conditions give another result than with the core ${g.recorded_with}: ${changed.slice(0, 12).join(', ')}`);
  assert.ok(Object.keys(now).length > 1600, `the golden covers ${Object.keys(now).length} cases`);
});

test('the golden really discriminates: one changed bar changes the digests of the conditions that read it', () => {
  const g = JSON.parse(fs.readFileSync(GOLDEN, 'utf8'));
  const f = fixtures.find(x => x.ticker === 'BBCA')!, n = f.bars.C.length, C = [...f.bars.C];
  C[n - 30] = (C[n - 30] as number) * 1.2;                                        // one close 20% higher
  const c0 = new Calc(f.bars), c1 = new Calc({ ...f.bars, C });
  const cond: Condition = { id: 'x', kind: 'price_action', type: 'breakout', params: { length: 20 } };
  assert.notDeepEqual([...conditionSeries(c0, cond)], [...conditionSeries(c1, cond)]);
  assert.equal(typeof g.recorded_with, 'string');
  assert.match(g.recorded_with, /^[0-9a-f]{16}$/);
});
