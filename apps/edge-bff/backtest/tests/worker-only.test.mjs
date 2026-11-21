/* EXEC-BACKTEST-REVAMP P0.4 (ERRORS M456): the page computes conditions in the browser with the shared core, and its
   assets are served without a session (app/main.py /backtest-app/). Admin-only series (the point-in-time Flow
   indicators) therefore live in modules only the worker imports (apps/backtest-worker/src/pit). This walks every module
   the page's entry reaches, as Vite resolves relative imports (as written, then .ts, then /index.ts), and refuses any
   under apps/backtest-worker. The built bundle is checked for the same in tests/bundle.test.mjs. */
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { ROOT, reachable } from '../../shared/import-walk.mjs';     // the walk, shared with 3f's public-entry test

const ENTRY = path.join(ROOT, 'apps/edge-bff/backtest/src/main.ts');

describe('worker-only modules stay out of the page (EXEC-BACKTEST-REVAMP P0.4)', () => {
  it('the page entry reaches the shared core but no module of the backtest worker', () => {
    const mods = reachable(ENTRY);
    expect(mods).toContain('apps/edge-bff/backtest/src/core/conditions.ts');
    expect(mods.filter(m => m.startsWith('apps/backtest-worker/'))).toEqual([]);
  });
});
