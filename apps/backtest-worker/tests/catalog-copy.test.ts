/* EXEC-BACKTEST-REVAMP Stage D (Agent 10, ERRORS M460 item 9): the page's test builds (the smoke stub, the 1:1 fixture)
   cannot import this worker's catalog module (it reads Node files), so they take a copy of its grammar part
   (apps/edge-bff/backtest/tests/grammar-catalog.ts). The copy had drifted (anchored and inventory indicators left out,
   the insider reason missing, FL51 kept). This compares it with the worker's own rule as a session without the admin
   right sees it (edge-bff rights.py leaves the admin entries out), with flow on and off. */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { flowIndicators } from '../src/catalog.ts';
import { NOT_PER_DAY } from '../src/grammar.ts';
import { grammarCatalog } from '../../edge-bff/backtest/tests/grammar-catalog.ts';

test('the page tests\' copy of the catalog\'s grammar part is the worker\'s rule for a session without the admin right', () => {
  for (const flowOn of [true, false]) {
    const copy = grammarCatalog(flowOn);
    assert.deepEqual(copy.flow_indicators, flowIndicators(flowOn).filter(x => x.access !== 'admin'), `flow ${flowOn ? 'on' : 'off'}`);
    assert.deepEqual(copy.grammar_refusals, { ...NOT_PER_DAY });
  }
  assert.ok(grammarCatalog(true).flow_indicators!.length > 30, 'the copy lists the registry\'s indicators');
});
