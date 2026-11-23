/* EXEC-MU-ACCOUNTS "A preview release stage" (the user 2026-11-23: a new indicator on the live site for the admin only,
   "user paid tidak bisa lihat"): the stop and trailing line choices (reg.ts LEVEL_LINES) are built from the page's own
   registry, where the public build keeps a preview entry marked `release: 'preview'` (shared/release-filter.mjs). A
   marked entry is offered only when the account's catalog lists it (SC.by, the Screener catalog edge-bff filters per
   principal); a released entry outside the plan stays, marked not calculated. */
import { afterEach, describe, expect, it } from 'vitest';
import type { BacktestApi } from '../src/api/types.ts';
import { setEnv } from '../src/env.ts';
import { SC } from '../src/grammar.ts';
import { LEVEL_LINES, REG, offered } from '../src/reg.ts';
import { CATALOG } from './smoke/stub.ts';

const overlays = REG.filter(r => r.zone === 'overlay');
const row = overlays[0], other = overlays[1];
const by0 = SC.by;

afterEach(() => { delete row.release; SC.by = by0 });

describe('the line choices and a preview entry', () => {
  it('has two overlay entries to test with', () => { expect(row && other).toBeTruthy() });
  it('leaves a marked entry out until the catalog lists it, and keeps an unmarked one', () => {
    setEnv({ ready:() => false } as unknown as BacktestApi, CATALOG);
    row.release = 'preview';
    SC.by = new Map();
    expect(offered(row)).toBe(false);
    expect(offered(other)).toBe(true);
    const ids = () => new Set(LEVEL_LINES().map(l => l.id));
    expect(ids().has(row.id)).toBe(false);
    expect(ids().has(other.id)).toBe(true);                     // released, not calculated here: still offered
    expect(LEVEL_LINES().find(l => l.id === other.id)?.ready).toBe(false);
    SC.by = new Map([[row.id, { key:row.id } as never]]);       // the admin's catalog lists it
    expect(offered(row)).toBe(true);
    expect(ids().has(row.id)).toBe(true);
  });
});
