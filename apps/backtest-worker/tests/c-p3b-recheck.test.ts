/* EXEC-MU-ACCOUNTS re-check of Phase 3b (checker C-P3B, 2026-11-18; user: "Cek juga fase sebelumnya ... Jangan sampai
   fase 3C di bangun dari broken block fase2 sebelumnya"). A failing test of a verified finding; the fix round makes it
   pass.

   F-msg: the worker's 403 CAPABILITY_REQUIRED message carries the internal capability key ("... is not included in your
   plan (backtest.indicator:I07) ..."; access.ts requireItem). edge-bff relays it unchanged (app/allow.py named adds
   details.display_name only), and every EDGE page shows the server's message first (shared/edge-session.ts accessText,
   case 'upgrade': `e.message || ...`; backtest/src/api/live.ts failure), so the person reads the key. ERRORS M481 C1 F3
   fixed the same class for details.display_name ("an internal key is never shown", app/errors.py display_name); the
   message path was left out. After the 3b follow-up (CONTRACT 8b) the key named is also one the follow-up's migration
   deletes. The fix: the message names the item (its id and name) and the plan in plain words; the key stays in
   details.capability only (the access.test.ts assertion that the message includes it changes with the fix). */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { allowOf, requireItem } from '../src/access.ts';
import { WorkerError, toApiError } from '../src/errors.ts';

const NONE = allowOf({ indicator: [], flow_indicator: [], candle_pattern: [], screener_metric: [] });

test('F-msg: a CAPABILITY_REQUIRED message the person reads names the item, never the internal capability key', () => {
  const cases: [Parameters<typeof requireItem>[1], string][] = [['indicator', 'I07'], ['flow_indicator', 'FL24'], ['candle_pattern', 'hammer'], ['screener_metric', 'breakout']];
  for (const [kind, id] of cases) {
    let message = '', capability = '';
    try { requireItem(NONE, kind, id, 'entry.conditions[0].x') } catch (e) {
      assert.ok(e instanceof WorkerError);
      const a = toApiError(e);
      message = a.error.message ?? ''; capability = String((a.error.details as { capability?: unknown }).capability);
    }
    assert.ok(capability.includes(':'), `the refusal keeps details.capability (${capability})`);
    assert.ok(message.includes(id), message);
    assert.ok(!message.includes(capability) && !/\b(backtest|screener|terminal)\.[a-z_]+:/.test(message),
      `the message shown to the person carries the internal capability key: ${message}`);
  }
});
