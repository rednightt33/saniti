/* EXEC-MU-ACCOUNTS "A preview release stage" (the user 2026-11-23): on the live site the admin is served the public
   build, where the alias '@edge-lab' is an empty module (shared/release-filter.mjs labAlias), so an item the public build
   keeps (released, or preview: its entry marked release 'preview') must compute from the public formula files alone. A
   preview indicator whose formula were still in src/lab/ would be listed to the admin on the live site and draw
   nothing. The test runs under the page's own Vite configuration (the release filter, the public alias), so the
   registry is the public build's and src/lab/ is not loaded; tests/calc/flow.test.ts ("registry") does the same for
   every Flow indicator through computeFlow. */
import { describe, expect, it } from 'vitest';
import IND from '../../src/data/indRegistry.json';
import { F } from '../../src/calc/indicators';

const N = 300;
function bars() {
  const T: string[] = [], O: number[] = [], H: number[] = [], L: number[] = [], C: number[] = [], V: number[] = [];
  let p = 1000;
  for (let i = 0; i < N; i++) {
    const d = new Date(Date.UTC(2024, 0, 1 + i));
    p = Math.max(50, p * (1 + Math.sin(i / 7) * 0.01 + ((i * 37) % 11 - 5) / 1000));
    T.push(d.toISOString().slice(0, 10)); O.push(p * 0.995); H.push(p * 1.01); L.push(p * 0.99); C.push(p); V.push(1e5 + (i * 7919) % 5e4);
  }
  return { T, O, H, L, C, V };
}

describe('every indicator the public build keeps computes without the lab module', () => {
  const entries = IND as any[];
  it('the registry is not empty', () => expect(entries.length).toBeGreaterThan(0));
  it.each(entries.map(r => [r.id, r]))('%s', (_, r: any) => {
    expect(typeof F[r.key], `${r.id} (${r.key}${r.release ? `, ${r.release}` : ''}): no public formula; a preview or released item's formula lives in calc/indicators.ts, not src/lab/ (INDICATOR_BETA_TO_LIVE.md part C)`).toBe('function');
    const out = F[r.key](bars() as any) as Record<string, (number | null)[]>;
    for (const o of r.outs) expect(out[o.k], `${r.id}.${o.k}`).toHaveLength(N);
    expect(Object.values(out).some(a => Array.isArray(a) && a.some(v => v !== null && Number.isFinite(v))), `${r.id}: no finite value at its defaults`).toBe(true);
  });
});
