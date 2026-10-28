/* Operator mapping (report TARGET ARCHITECTURE 6.9.1; TEST PLAN 10b.3 "Operator mapping", 10b.10 "Operator
   coverage"): every (key, operator) pair of the prototype's catalogue (verification/screener/evidence/html_ui/
   catalog.json: 53 x_* registry entries, 17 legacy technical, 13 flow, 32 fundamental) maps to one wire test that
   validates, or is refused with its reason (raw cumulative levels; Ichimoku until a registry release; flow until
   Phase 2; fundamentals without data). An unmapped pair fails. A compound operator is one condition, so ANY and AT
   LEAST count it once; the compound ones equal the prototype rules on a fixture: hup, zero, price_ma rising (21 bars)
   vs the line shape's rising (5 bars). */
import { describe, expect, it } from 'vitest';
import catalogText from '../../../../../verification/screener/evidence/html_ui/catalog.json?raw';
import { F } from '../../../terminal/src/calc/indicators.ts';
import { bindCondition } from '../../src/core/condition.ts';
import { ScreenerError } from '../../src/core/errors.ts';
import { INDICATORS } from '../../src/core/registry.ts';
import { tickerCalc } from '../../src/core/metrics.ts';
import { SeriesCache, series, tailLength } from '../../src/core/metrics.ts';
import { validateTest } from '../../src/core/validate.ts';
import { OPTS, WITHIN_MAX, headBars, rowOf, synth, vctx } from './helpers.ts';

const CAT = JSON.parse(catalogText as unknown as string).cat as Record<string, { ops: string[]; g: string }>;
const CTX = vctx(['X']);
const close = { kind: 'price', field: 'close' }, volume = { kind: 'price', field: 'volume' };
const ind = (indicator: string, output: string, params?: Record<string, unknown>) => ({ kind: 'indicator', indicator, output, ...(params ? { params } : {}) });
const tr = (fn: string, of: unknown, args?: Record<string, unknown>) => ({ kind: 'transform', fn, of, ...(args ? { args } : {}) });
const pat = (type: string, params?: Record<string, unknown>) => ({ kind: 'pattern', type, ...(params ? { params } : {}) });
const V = (metric: unknown, op = 'gt', value = 1, value2?: number) => ({ kind: 'value', metric, op, value, ...(value2 !== undefined ? { value2 } : {}) });
const S = (lhs: unknown, op: string, rhs: unknown) => ({ kind: 'state', lhs, op, rhs });
const EV = (lhs: unknown, op: string, rhs: unknown, within = 5) => ({ kind: 'event', within, signal: { lhs, op, rhs } });
const SP = (p: unknown) => ({ kind: 'state', pattern: p });
const EP = (p: unknown, within = 5) => ({ kind: 'event', within, signal: { pattern: p } });
const val = (op: string, metric: unknown) => op === 'between' ? V(metric, 'between', 0, 1) : V(metric, op);
const cross = (op: string) => op === 'xa' ? 'crosses_above' : 'crosses_below';
const UNAVAILABLE = Symbol('refused with its reason');

/** The wire test of one prototype (key, op), report 6.9.1 row by row; UNAVAILABLE where it is refused with a reason. */
function wire(key: string, op: string): unknown {
  if (key.startsWith('x_')) {
    const r = INDICATORS.find(x => x.key === key.slice(2))!, id = r.id, o = r.outputs.map(x => x.key), shape = r.overlay.shape;
    const lineOut = o[0];
    switch (shape) {
      case 'line': return { above: S(close, 'gt', ind(id, lineOut)), below: S(close, 'lt', ind(id, lineOut)), xa: EV(close, 'crosses_above', ind(id, lineOut)), xb: EV(close, 'crosses_below', ind(id, lineOut)),
        rising: S(ind(id, lineOut), 'gt', tr('lag', ind(id, lineOut), { bars: 5 })) }[op] ?? val(op, tr('pct_distance', ind(id, lineOut)));
      case 'band': {
        const [up, mid, lo] = id === 'I43' ? ['upper1', 'vwap', 'lower1'] : ['upper', 'basis', 'lower'];
        const p = id === 'I43' ? { anchor: 'Week' } : undefined;
        return { abu: S(close, 'gt', ind(id, up, p)), bll: S(close, 'lt', ind(id, lo, p)), xau: EV(close, 'crosses_above', ind(id, up, p)), xbl: EV(close, 'crosses_below', ind(id, lo, p)),
          abb: S(close, 'gt', ind(id, mid, p)) }[op] ?? val(op, tr(id === 'I43' ? 'pct_distance' : 'band_position', ind(id, mid, p)));
      }
      case 'dir': return { up: S(ind(id, 'direction'), 'gt', { value: 0 }), flipup: EV(ind(id, 'direction'), 'crosses_above', { value: 0 }), flipdn: EV(ind(id, 'direction'), 'crosses_below', { value: 0 }) }[op]
        ?? val(op, tr('pct_distance', ind(id, o[0])));
      case 'pair': return { xsig: EV(ind(id, o[0]), 'crosses_above', ind(id, o[1])), xsigd: EV(ind(id, o[0]), 'crosses_below', ind(id, o[1])), asig: S(ind(id, o[0]), 'gt', ind(id, o[1])),
        xa: EV(ind(id, o[0]), 'crosses_above', { value: 0 }), xb: EV(ind(id, o[0]), 'crosses_below', { value: 0 }) }[op] ?? val(op, ind(id, o[0]));
      case 'adx': return { plus: S(ind(id, 'plus_di'), 'gt', ind(id, 'minus_di')), dixa: EV(ind(id, 'plus_di'), 'crosses_above', ind(id, 'minus_di')),
        xa: EV(ind(id, 'adx'), 'crosses_above', { value: 25 }), xb: EV(ind(id, 'adx'), 'crosses_below', { value: 25 }) }[op] ?? val(op, ind(id, 'adx'));
      case 'vol': return { vabove: S(volume, 'gt', ind(id, o[0])), vxa: EV(volume, 'crosses_above', ind(id, o[0])) }[op] ?? val(op, ind(id, o[0]));
      case 'cum': {
        const n = ['I50', 'I51'].includes(id) ? 255 : 20;
        return { cabove: S(ind(id, o[0]), 'gt', tr('ma', ind(id, o[0]), { ma: 'EMA', length: n })), cxa: EV(ind(id, o[0]), 'crosses_above', tr('ma', ind(id, o[0]), { ma: 'EMA', length: n })),
          crise: S(ind(id, o[0]), 'gt', tr('lag', ind(id, o[0]), { bars: 20 })) }[op] ?? (op === 'gt' || op === 'lt' ? V(ind(id, o[0]), op) : undefined);
      }
      case 'osc': return { xa: EV(ind(id, o[0]), 'crosses_above', { value: 50 }), xb: EV(ind(id, o[0]), 'crosses_below', { value: 50 }) }[op] ?? val(op, ind(id, o[0]));
    }
    return undefined;
  }
  const sma = (len: number) => ind('I01', 'sma', { length: len });
  const legacy: Record<string, Record<string, unknown>> = {
    price_ma: { above: S(close, 'gt', sma(50)), below: S(close, 'lt', sma(50)), xa: EV(close, 'crosses_above', sma(50)), xb: EV(close, 'crosses_below', sma(50)),
      rising: S(sma(50), 'gt', tr('lag', sma(50), { bars: 21 })), gt: V(tr('pct_distance', sma(50))), lt: V(tr('pct_distance', sma(50)), 'lt'), between: V(tr('pct_distance', sma(50)), 'between', 0, 5) },
    ma_cross: { golden: EV(sma(50), 'crosses_above', sma(200), 20), death: EV(sma(50), 'crosses_below', sma(200), 20), above: S(sma(50), 'gt', sma(200)) },
    rsi: { xa: EV(ind('I13', 'rsi'), 'crosses_above', { value: 30 }), xb: EV(ind('I13', 'rsi'), 'crosses_below', { value: 70 }) },
    stoch: { xa: EV(ind('I15', 'k'), 'crosses_above', { value: 20 }), xb: EV(ind('I15', 'k'), 'crosses_below', { value: 80 }), kxd: EV(ind('I15', 'k'), 'crosses_above', ind('I15', 'd')), kxd_os: EP(pat('stoch_cross_in_zone')) },
    macd: { xsig: EV(ind('I06', 'macd'), 'crosses_above', ind('I06', 'signal')), zero: EV(ind('I06', 'macd'), 'crosses_above', { value: 0 }), bdiv: EP(pat('macd_divergence'), 10),
      hup: S(tr('rising_run', ind('I06', 'histogram')), 'gt', { value: 2 }), gt: V(ind('I06', 'histogram')), lt: V(ind('I06', 'histogram'), 'lt') },
    adx: { xa: EV(ind('I07', 'adx'), 'crosses_above', { value: 25 }), plus: S(ind('I07', 'plus_di'), 'gt', ind('I07', 'minus_di')), dixa: EV(ind('I07', 'plus_di'), 'crosses_above', ind('I07', 'minus_di')) },
    bb: { below: S(close, 'lt', ind('I27', 'lower')), brk: EV(close, 'crosses_above', ind('I27', 'upper')), squeeze: EP(pat('squeeze'), 10) },
    supertrend: { flip: EV(ind('I09', 'direction'), 'crosses_above', { value: 0 }), bull: S(ind('I09', 'direction'), 'gt', { value: 0 }) },
    ichimoku: { above: SP(pat('ichimoku_above')), tk: EP(pat('ichimoku_tk_cross'), 10) },
    breakout: { up: EP(pat('breakout')), dn: EP(pat('breakdown')) },
    volspike: { gt: SP(pat('volspike')), xa: EV(tr('ratio', volume, { by: tr('lag', tr('ma', volume, { ma: 'SMA', length: 20 }), { bars: 1 }) }), 'crosses_above', { value: 2 }) },
    bandar: { acc: V({ kind: 'flow', metric: 'bandar', params: { window: 10, top: 3 } }, 'between', 6, 100), bigacc: V({ kind: 'flow', metric: 'bandar', params: { window: 10 } }, 'between', 10, 100),
      dist: V({ kind: 'flow', metric: 'bandar', params: { window: 10 } }, 'between', -100, -6), bigdist: V({ kind: 'flow', metric: 'bandar', params: { window: 10 } }, 'between', -100, -10) },
    silent: { on: SP(pat('silent')) },
    obv: { rising: S(ind('I40', 'obv'), 'gt', tr('ma', ind('I40', 'obv'), { ma: 'SMA', length: 20 })), high: EP(pat('new_high', { of: 'I40.obv', length: 20 })) },
    mfi: { xa: EV(ind('I47', 'mfi'), 'crosses_above', { value: 20 }), xb: EV(ind('I47', 'mfi'), 'crosses_below', { value: 80 }) },
    cmf: { xa: EV(ind('I45', 'cmf'), 'crosses_above', { value: 0 }) },
    fnet: { xa: EV({ kind: 'flow', metric: 'fnet', params: { window: 20 } }, 'crosses_above', { value: 0 }), xb: EV({ kind: 'flow', metric: 'fnet', params: { window: 20 } }, 'crosses_below', { value: 0 }) },
    broker: { xa: EV({ kind: 'flow', metric: 'broker', params: { window: 5 } }, 'crosses_above', { value: 0 }) },
    freq: { xa: EV({ kind: 'flow', metric: 'freq', params: { window: 20 } }, 'crosses_above', { value: 2.5 }, 3) },
  };
  if (legacy[key]?.[op]) return legacy[key][op];
  const valueMetric: Record<string, unknown> = {
    rsi: ind('I13', 'rsi'), stoch: ind('I15', 'k'), adx: ind('I07', 'adx'), bb: ind('I28', 'percent_b'), atr: ind('I31', 'natr'),
    hi52: tr('pct_distance', tr('rolling_max', { kind: 'price', field: 'high' }, { length: 252 })), lo52: tr('pct_distance', tr('rolling_min', { kind: 'price', field: 'low' }, { length: 252 })),
    ret: ind('I17', 'roc', { length: 20 }), rs: tr('vs_index', close, { window: 63 }), rs_rank: { kind: 'xsection', metric: 'return_rank', params: { window: 252 } },
    volspike: tr('ratio', volume, { by: tr('lag', tr('ma', volume, { ma: 'SMA', length: 20 }), { bars: 1 }) }),
    mfi: ind('I47', 'mfi'), cmf: ind('I45', 'cmf'), adv: { kind: 'universe', attr: 'adv20_idr' },
    bandar: { kind: 'flow', metric: 'bandar', params: { window: 10 } }, topacc: { kind: 'flow', metric: 'topacc', params: { window: 10 } },
    broker: { kind: 'flow', metric: 'broker', params: { window: 5 } }, bavg: { kind: 'flow', metric: 'bavg', params: { window: 10 } },
    fnet: { kind: 'flow', metric: 'fnet', params: { window: 20 } }, fstreak: { kind: 'flow', metric: 'fstreak', params: { window: 60 } },
    fpct: { kind: 'flow', metric: 'fpct', params: { window: 20 } }, freq: { kind: 'flow', metric: 'freq', params: { window: 20 } },
  };
  if (['gt', 'lt', 'between'].includes(op)) {
    if (valueMetric[key]) return val(op, valueMetric[key]);
    if (CAT[key]?.g === 'Fundamental') return val(op, { kind: 'universe', attr: key });
  }
  return undefined;
}

describe('every (key, operator) pair of the prototype maps to a wire test or a stated refusal', () => {
  const pairs = Object.entries(CAT).flatMap(([k, v]) => v.ops.map(op => [k, op] as const));
  it(`covers all ${Object.keys(CAT).length} keys of the prototype catalogue`, () => {
    expect(Object.keys(CAT).length).toBe(115);
    const unmapped: string[] = [], refused: Record<string, string> = {}, mapped: string[] = [];
    for (const [k, op] of pairs) {
      const t = wire(k, op);
      if (t === undefined || t === UNAVAILABLE) { unmapped.push(`${k} ${op}`); continue }
      try { validateTest(t, `t`, CTX); mapped.push(`${k} ${op}`) }
      catch (e) {
        if (!(e instanceof ScreenerError)) throw e;
        refused[`${k} ${op}`] = `${e.code}: ${e.message}`;
      }
    }
    expect(unmapped).toEqual([]);
    // refused only with a stated reason: raw cumulative levels, Ichimoku (P6), flow (Phase 2), fundamentals (no data)
    for (const [pair, why] of Object.entries(refused)) {
      const [k] = pair.split(' ');
      const ok = (CAT[k].g === 'Fundamental' && /^METRIC_UNAVAILABLE/.test(why))
        || (['bandar', 'topacc', 'broker', 'bavg', 'fnet', 'fstreak', 'fpct', 'freq'].includes(k) && /^METRIC_UNAVAILABLE/.test(why))
        || (k === 'ichimoku' && /^METRIC_UNAVAILABLE.*registry release/.test(why))
        || (['x_obv', 'x_pvt', 'x_adl', 'x_nvi', 'x_pvi'].includes(k) && /depends on where its history starts/.test(why));
      expect([pair, ok]).toEqual([pair, true]);
    }
    expect(Object.keys(refused).length).toBe(32 * 3 + 2 + 5 * 2 + 30);  // fundamentals, Ichimoku, raw cumulative gt / lt, the 30 flow pairs
    expect(mapped.length + Object.keys(refused).length).toBe(pairs.length);
  });
});

describe('compound operators equal the prototype rules (one condition each)', () => {
  const t = synth('MAP', 4242, 400);
  const at = (test: unknown, n: number) => {
    const b = bindCondition({ id: 'c', enabled: true, test: validateTest(test, 't', CTX) }, 'c', { ...OPTS, withinMax: WITHIN_MAX });
    const h = headBars(t, n), c = tickerCalc(h), ctx = { versions: { price_data: 'p', screener_engine: 'e' }, tailLength: tailLength(WITHIN_MAX), cache: new SeriesCache(1 << 26) };
    return b.evaluate({ ticker: h.ticker, dates: h.dates, bars: h.bars, at: n - 1, row: rowOf(h, h.dates[n - 1]), ihsgCalendar: h.dates, series: r => series(ctx, c, r), xsection: () => null }).cell.status === 'pass';
  };
  it('hup: the MACD histogram up three sessions running (h[t] > h[t-1] > h[t-2] > h[t-3])', () => {
    const h = F.macd(t.bars, {}).histogram as number[];
    let hits = 0;
    for (let n = 60; n <= 400; n += 3) {
      const i = n - 1, want = h[i] > h[i - 1] && h[i - 1] > h[i - 2] && h[i - 2] > h[i - 3];
      expect([n, at({ kind: 'state', lhs: tr('rising_run', ind('I06', 'histogram')), op: 'gt', rhs: { value: 2 } }, n)]).toEqual([n, want]); hits += +want;
    }
    expect(hits).toBeGreaterThan(0);
  });
  it('zero: MACD crosses above 0 on the bar (prev <= 0, now > 0); price_ma rising reads 21 bars back, the line shape 5', () => {
    const m = F.macd(t.bars, {}).macd as number[], sma = F.sma(t.bars, { length: 50 }).sma as number[];
    for (let n = 80; n <= 400; n += 5) {
      const i = n - 1;
      expect(at(EV(ind('I06', 'macd'), 'crosses_above', { value: 0 }, 1), n)).toBe(m[i - 1] <= 0 && m[i] > 0);
      expect(at(S(ind('I01', 'sma', { length: 50 }), 'gt', tr('lag', ind('I01', 'sma', { length: 50 }), { bars: 21 })), n)).toBe(sma[i] > sma[i - 21]);
      expect(at(S(ind('I01', 'sma', { length: 50 }), 'gt', tr('lag', ind('I01', 'sma', { length: 50 }), { bars: 5 })), n)).toBe(sma[i] > sma[i - 5]);
    }
  });
});
