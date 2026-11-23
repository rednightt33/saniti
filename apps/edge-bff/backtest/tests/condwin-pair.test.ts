// ERRORS M554 (2026-11-23): an output-vs-output choice of the condition window pairs the output with the option's
// `with_output` (the Screener registry's own partner), on every such option of the catalog, never a partner guessed from
// the label (the rule it replaces fell back to the first output not named `direction`: Alpha Volatile's distance would
// have been paired with its decile).
import { describe, expect, it } from 'vitest';
import REG from '../../screener/src/core/screener-registry.json' with { type: 'json' };
import { cwMap } from '../src/cwmap.ts';

type Spec = { form: string; ops: string[]; with_output?: string };
const PAIRED = (REG as { indicators: { id: string; outputs: { key: string; tests: Spec[] }[] }[] }).indicators
  .flatMap(r => r.outputs.flatMap(o => o.tests.filter(t => t.form === 'state_output' || t.form === 'event_output')
    .flatMap(t => t.ops.map(op => ({ id: r.id, output: o.key, op, with_output: t.with_output!, key: `${t.form}|${o.key}|${op}` })))));

describe('the condition window pairs two outputs as the registry does', () => {
  // the page tests run the public build: its registries hold the released indicators only (the lab Alpha Volatile,
  // whose distance is paired with upper_z and lower_z, takes the same rule in the lab build)
  it('the registry has paired options to check (MACD, Stochastic, DMI among them)', () => {
    expect(PAIRED.length).toBeGreaterThan(20);
    expect(PAIRED.map(p => p.id)).toEqual(expect.arrayContaining(['I06', 'I07', 'I14']));
  });
  it('every paired option maps to the output against its with_output', () => {
    for (const p of PAIRED) {
      const m = cwMap(p.id, { key: p.key, with_output: p.with_output });
      expect(m, p.key).not.toBeNull();
      expect(m!.lhs, `${p.id} ${p.key}`).toEqual({ t: 'out', o: p.output });
      expect(m!.rhs, `${p.id} ${p.key}`).toEqual({ t: 'out', o: p.with_output });
    }
  });
  it('the partner is the option\'s, never guessed: a partner the indicator lacks or none at all gives no page card', () => {
    expect(cwMap('I07', { key: 'state_output|plus_di|gt', with_output: 'minus_di' })!.rhs).toEqual({ t: 'out', o: 'minus_di' });
    expect(cwMap('I06', { key: 'state_output|macd|gt' })).toBeNull();
    expect(cwMap('I06', { key: 'state_output|macd|gt', with_output: 'nope' })).toBeNull();
    expect(cwMap('I06', { key: 'state_output|macd|gt', with_output: 'macd' })).toBeNull();
  });
});
