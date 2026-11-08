/* EXEC-SCREENER-V21 (ERRORS M355 lesson: "test fixtures must carry the wire's real fields"): the fixture's run answer
   carries the Cell.unit and ConditionSummary.unit the REAL screener core writes (src/core/screen.ts runScreen over
   tests/core/helpers.ts memoryEnv) for every condition the fixture offers (its presets and the extra columns'
   auxiliary conditions). The fixture computes with the core itself (tests/fixture/engine.ts, QA5 unit B item 4); this
   keeps it so. The fixture and smoke builds, and the Chromium checks on them, meet production's coarse units
   ('dimensionless' for a percent distance, ROC or ATR %), and the page's formatting from the catalog (entries.ts
   formatOfOpt, format.ts fmtValue) is the path they exercise. */
import { beforeAll, describe, expect, it } from 'vitest';
import type { CatalogResponse, Definition, RunResponse, UniverseRow } from '../../src/core/contract.ts';
import { UNIVERSE_DEFAULTS } from '../../src/core/contract.ts';
import { runScreen } from '../../src/core/screen.ts';
import { validateDefinition } from '../../src/core/validate.ts';
import { entriesOf } from '../../src/entries.ts';
import { canonical, ctx, rowOfUniverse } from '../../src/state.ts';
import { availableColumns, nextAuxDefinition, setColumns } from '../../src/extra-columns.ts';
import { fixtureApi } from '../fixture/api.ts';
import { memoryEnv, rowOf, synth, vctx } from '../core/helpers.ts';

const IX = (() => { const t = synth('IHSG', 3, 520, '2024-06-03'); return { ...t, bars: { ...t.bars, V: t.bars.V.map(() => null) } } })();
const E = IX.dates[IX.dates.length - 1];
const TICKERS = Array.from({ length: 12 }, (_, k) => synth(`U${String(k).padStart(2, '0')}`, 300 + k, 520, '2024-06-03'));
const rows: UniverseRow[] = TICKERS.map(t => rowOf(t, E, { adv20_idr: 5e9, last: 1000 }));
const CTX = vctx(TICKERS.map(t => t.ticker));
const U = { ...UNIVERSE_DEFAULTS, price_min: null, adv20_min_idr: null, traded_on_eval_date: false, exclude_price_breaks: false } as Definition['universe'];
/** the fixture market's universe for the same definitions (every stock, so every condition has cells) */
const FX_U = { ...U, include_unclassified: true } as Definition['universe'];

let catalog: CatalogResponse;
const fx = fixtureApi();
beforeAll(async () => {
  const c = await fx.catalog(null); if (c.status !== 200) throw new Error('fixture catalog');
  catalog = c.body;
  ctx.catalog = catalog; ctx.entries = entriesOf(catalog); ctx.byKey = new Map(ctx.entries.map(e => [e.key, e]));
});

/** the core's units per condition id of a definition (its summary, and the set over every cell), or null when the
    core refuses it here */
function coreUnits(def: Definition): Map<string, { summary: string | null; cells: Set<string | null> }> | null {
  let norm;
  try { norm = validateDefinition({ ...def, universe: U }, CTX) } catch { return null }
  const r = runScreen(norm, memoryEnv(TICKERS, IX, rows, E));
  const out = new Map<string, { summary: string | null; cells: Set<string | null> }>();
  for (const s of r.conditions) out.set(s.id, { summary: s.unit ?? null, cells: new Set() });
  for (const row of r.rows) for (const c of row.cells) out.get(c.id)?.cells.add(c.unit ?? null);
  return out;
}

describe('the fixture answers with the core\'s Cell.unit', () => {
  it('for every condition of every fixture preset and of the extra columns: equal to the real core, on every cell and summary', async () => {
    const defs: [string, Definition][] = catalog.presets.map(p => [`preset ${p.id}`, p.definition]);
    // the extra columns' auxiliary definition, every offered column at once (chunked by max_conditions)
    const tableDef: Definition = { universe: U, conditions: [], logic: 'all' };
    ctx.R = { rows: rows.map(rowOfUniverse), run: null, defHash: canonical(tableDef), def: tableDef, eligible: rows.length, listed: rows.length, staleHidden: 0, breakHidden: 0 };
    ctx.running = false; ctx.api = { run: () => new Promise(() => {}) } as any;
    const ids = availableColumns().filter(c => !c.unavailable).map(c => c.id);
    for (let i = 0; i < ids.length; i += 10) { setColumns(ids.slice(i, i + 10)); const aux = nextAuxDefinition(); if (aux) defs.push([`extra columns ${i}`, aux]) }
    setColumns([]);
    let compared = 0, dimensionless = 0;
    const diffs: string[] = [];
    for (const [where, def] of defs) {
      const core = coreUnits(def); if (!core) continue;
      // the fixture's answer on its own market (its universe: the units do not depend on the stocks); a definition
      // whose leg the fixture's publication lacks (a fundamental) is refused there, as by the worker
      let got: RunResponse;
      try { got = (await fx.run({ schema_version: 1, definition: { ...def, universe: FX_U }, options: { exhaustive: true, explain: false } } as never)).body } catch { continue }
      for (const s of got.conditions) {
        const want = core.get(s.id); if (!want) continue;
        expect(want.cells.size, `${where} ${s.id}: the core writes one cell unit per condition`).toBeLessThanOrEqual(1);
        if ((s.unit ?? null) !== want.summary) diffs.push(`${where} ${s.id}: summary fixture ${s.unit}, core ${want.summary}`);
        const cells = new Set(got.rows.flatMap(r => r.cells.filter(c => c.id === s.id).map(c => { expect('unit' in c, `${where} ${s.id}: a cell without its unit`).toBe(true); return c.unit ?? null })));
        for (const u of cells) { if (want.cells.size && !want.cells.has(u)) diffs.push(`${where} ${s.id}: cell fixture ${u}, core ${[...want.cells]}`); if (u === 'dimensionless') dimensionless++ }
        compared++;
      }
    }
    expect(diffs).toEqual([]);
    expect(compared).toBeGreaterThan(20);
    expect(dimensionless, 'the M355 path (a percent arriving as dimensionless) is exercised').toBeGreaterThan(0);
  });
});
