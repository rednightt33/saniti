/* EXEC-BACKTEST-REVAMP P0.2 (ERRORS M453): engine_version covers every file that decides a number of a result: the
   shared core and the worker with their subfolders, the Terminal's calculation module, the flow registry and the
   Screener core (P1: it computes the conditions in the Screener's grammar, src/grammar.ts). Checked
   on a scratch tree laid out like the repository, so each source can be changed alone. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { test } from 'node:test';
import { SOURCES, engineVersion, sourceFiles } from '../src/version.ts';

function tree(): string {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'bt-version-'));
  const put = (rel: string, text: string) => { fs.mkdirSync(path.dirname(path.join(root, rel)), { recursive: true }); fs.writeFileSync(path.join(root, rel), text) };
  put('apps/edge-bff/backtest/src/core/engine.ts', 'a');
  put('apps/edge-bff/backtest/src/core/grammar/transforms.ts', 'b');
  put('apps/edge-bff/backtest/src/core/notes.md', 'not a source');
  put('apps/backtest-worker/src/run.ts', 'c');
  put('apps/backtest-worker/src/pit/anchored.ts', 'd');
  put('apps/edge-bff/terminal/src/calc/flow.ts', 'e');
  put('apps/edge-bff/terminal/src/lab/index.ts', 'g');           // 3f TR-2: the lab formulas the worker registers
  put('apps/edge-bff/terminal/src/data/flowRegistry.json', '{}');
  put('apps/edge-bff/screener/src/core/condition.ts', 'f');
  put('apps/edge-bff/screener/src/core/screener-metrics.json', '{}');
  return root;
}

test('the sources are the core, the worker, the Terminal calculation module, the flow registry and the Screener core', () => {
  // changed with 3f TR-2 (2026-11-22, a stated reason): the lab formulas ('@edge-lab', terminal/src/lab) decide a number
  // as the calculation module does, so they are a source too
  assert.deepEqual(SOURCES.map(([e]) => e), ['apps/edge-bff/backtest/src/core', 'apps/backtest-worker/src', 'apps/edge-bff/terminal/src/calc',
    'apps/edge-bff/terminal/src/lab', 'apps/edge-bff/terminal/src/data/flowRegistry.json', 'apps/edge-bff/screener/src/core']);
  const files = sourceFiles();
  for (const f of ['apps/edge-bff/terminal/src/calc/flow.ts', 'apps/edge-bff/terminal/src/calc/indicators.ts', 'apps/edge-bff/terminal/src/data/flowRegistry.json',
    'apps/edge-bff/screener/src/core/condition.ts', 'apps/edge-bff/screener/src/core/screener-metrics.json', 'apps/edge-bff/screener/src/core/screener-registry.json'])
    assert.ok(files.includes(f), f);
});

test('a change in any source, a subfolder included, changes engine_version; a file the patterns leave out does not', () => {
  const root = tree(), v0 = engineVersion(root);
  assert.deepEqual(sourceFiles(root), ['apps/backtest-worker/src/pit/anchored.ts', 'apps/backtest-worker/src/run.ts', 'apps/edge-bff/backtest/src/core/engine.ts',
    'apps/edge-bff/backtest/src/core/grammar/transforms.ts', 'apps/edge-bff/screener/src/core/condition.ts', 'apps/edge-bff/screener/src/core/screener-metrics.json',
    'apps/edge-bff/terminal/src/calc/flow.ts', 'apps/edge-bff/terminal/src/data/flowRegistry.json', 'apps/edge-bff/terminal/src/lab/index.ts']);
  fs.writeFileSync(path.join(root, 'apps/edge-bff/backtest/src/core/notes.md'), 'changed');
  assert.equal(engineVersion(root), v0);
  for (const rel of ['apps/edge-bff/backtest/src/core/grammar/transforms.ts', 'apps/backtest-worker/src/pit/anchored.ts', 'apps/edge-bff/terminal/src/calc/flow.ts',
    'apps/edge-bff/terminal/src/data/flowRegistry.json', 'apps/edge-bff/screener/src/core/condition.ts', 'apps/edge-bff/screener/src/core/screener-metrics.json',
    'apps/edge-bff/terminal/src/lab/index.ts']) {
    const at = path.join(root, rel), before = fs.readFileSync(at, 'utf8'), v = engineVersion(root);
    fs.writeFileSync(at, before + ' ');
    assert.notEqual(engineVersion(root), v, rel);
    fs.writeFileSync(at, before);
    assert.equal(engineVersion(root), v, rel);
  }
  fs.rmSync(root, { recursive: true, force: true });
});
