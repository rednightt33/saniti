/* EXEC-MU-ACCOUNTS re-check of Phase 3b (checker C-P3B, 2026-11-18; user: "Cek juga fase sebelumnya ... Jangan sampai
   fase 3C di bangun dari broken block fase2 sebelumnya"). A failing test of a verified finding; the fix round makes it
   pass.

   F-msg: the worker's 403 CAPABILITY_REQUIRED message carries the internal capability key ("... is not included in your
   plan (screener.indicator:I13) ..."; run.ts checkAllow). edge-bff relays it unchanged (app/allow.py named adds
   details.display_name only), and the Screener page shows the server's message first (shared/edge-session.ts
   accessText, case 'upgrade'), so the person reads the key. ERRORS M481 C1 F3 fixed the same class for
   details.display_name ("an internal key is never shown"); the message path was left out. The fix: the message names
   the item in plain words; the key stays in details.capability only. */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { checkAllow, parseContext } from '../src/run.ts';

const NONE = parseContext({ allow: { indicator: [], flow_indicator: [], candle_pattern: [], screener_metric: [] } }).allow;
const DEF = (test: unknown) => ({ universe: { security_types: ['stock'] }, logic: 'all', conditions: [{ id: 'a', enabled: true, test }] });

test('F-msg: a CAPABILITY_REQUIRED message the person reads names the item, never the internal capability key', () => {
  const tests = [
    { kind: 'value', metric: { kind: 'indicator', indicator: 'I13', params: {}, output: 'rsi' }, op: 'lt', value: 30 },
    { kind: 'value', metric: { kind: 'flow', metric: 'FL24', params: {} }, op: 'gt', value: 0 },
    { kind: 'state', pattern: { kind: 'pattern', type: 'hammer', params: {} } },
    { kind: 'state', pattern: { kind: 'pattern', type: 'breakout', params: {} } },
  ];
  for (const t of tests) {
    let message = '', capability = '';
    try { checkAllow(DEF(t), NONE) } catch (e: any) { message = e.message; capability = String(e.details?.capability) }
    assert.ok(capability.includes(':'), `the refusal keeps details.capability (${capability})`);
    assert.ok(!message.includes(capability) && !/\b(backtest|screener|terminal)\.[a-z_]+:/.test(message),
      `the message shown to the person carries the internal capability key: ${message}`);
  }
});
