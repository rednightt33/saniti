/* The generator's cost probe (scripts/build-screener-registry.mjs, cost_class of report 6.8) counts work, never time:
   its class follows how a kernel's work grows with the length, is the same under a noisy clock to the last executed
   character, and refuses a growth that neither class owns. Kernels: tests/core/cost-doubles.mjs. Plain JavaScript,
   because it spawns the probe's child process (node:child_process), as registry-check.test.mjs. */
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { describe, expect, it } from 'vitest';
import * as G from '../../scripts/build-screener-registry.mjs';
import { DEFAULTS } from './cost-doubles.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url)), APP = path.resolve(HERE, '../..');
const DOUBLES = path.join(HERE, 'cost-doubles.mjs'), NOISY = pathToFileURL(path.join(HERE, 'noisy-clock.mjs')).href;

const group = (key, param, variants = [{}]) => ({ id: key, key, param, value: DEFAULTS[key][param], base: DEFAULTS[key], variants });
/** The probe's child process as build() starts it (--cost-work, the job on stdin), with extra environment. */
function costWork(groups, env = {}) {
  const r = spawnSync(process.execPath, ['--experimental-strip-types', '--no-warnings=ExperimentalWarning', '--import', '../../backtest-worker/loader/register.mjs',
    'scripts/build-screener-registry.mjs', '--cost-work'], { cwd: APP, encoding: 'utf8', input: JSON.stringify({ module: DOUBLES, bars: G.PROBE.cost_bars, groups }), env: { ...process.env, ...env } });
  return { ...r, out: r.status === 0 ? JSON.parse(r.stdout) : null };
}
const classes = out => Object.fromEntries(out.map(g => [`${g.id}.${g.param}#${g.measured.length}`, g.cost_class]));

const GROUPS = [
  group('window_max', 'length'),
  group('window_over_intermediate', 'length'),
  group('window_over_intermediate', 'smooth'),
  group('running_mean', 'length'),
  group('recursive', 'length'),
  group('switchable', 'length', [{}, { method: 'loop' }]),
  group('switchable', 'length'),
];

describe('cost probe: work, not time', () => {
  it('classes a window loop O(N·n), also over an internal intermediate array, and a running or recursive kernel O(N)', () => {
    const r = costWork(GROUPS);
    expect(r.stderr).toBe('');
    expect(r.status).toBe(0);
    expect(classes(r.out)).toEqual({
      'window_max.length#1': 'O(N·n)',
      'window_over_intermediate.length#1': 'O(N·n)',
      'window_over_intermediate.smooth#1': 'O(N)',
      'running_mean.length#1': 'O(N)',
      'recursive.length#1': 'O(N)',
      'switchable.length#2': 'O(N·n)',            // O(N) at the default method, O(N·n) at 'loop': the worst option wins
      'switchable.length#1': 'O(N)',
    });
    for (const g of r.out) for (const m of g.measured) {
      expect(m.lengths).toEqual(G.costLengths(DEFAULTS[g.id][g.param], G.PROBE.cost_bars));
      if (m.cost_class === 'O(N·n)') expect(m.growth).toBeGreaterThanOrEqual(G.PROBE.cost_growth * G.PROBE.cost_margin);
      else expect(m.growth).toBeLessThanOrEqual(G.PROBE.cost_growth / G.PROBE.cost_margin);
    }
  }, 120_000);

  it('measures the same work, to the character, when every clock jumps at random (a noisy clock cannot flip a class)', () => {
    const plain = costWork(GROUPS);
    const log = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'noisy-clock-')), 'pids');
    const noisy = costWork(GROUPS, { NODE_OPTIONS: `${process.env.NODE_OPTIONS ?? ''} --import=${NOISY}`.trim(), NOISY_CLOCK_LOG: log });
    expect(noisy.stderr).toBe('');
    expect(fs.readFileSync(log, 'utf8').trim().split('\n').length).toBeGreaterThanOrEqual(1);   // the clock was in place
    expect(noisy.out).toEqual(plain.out);
    fs.rmSync(path.dirname(log), { recursive: true, force: true });
  }, 120_000);

  it('stops the build, naming the numbers, when the growth is between the classes', () => {
    const r = costWork([group('stepped', 'length')]);
    expect(r.status).not.toBe(0);
    expect(r.stderr).toMatch(/cost probe stepped\.length \{\}: the work grows 1\.\d+ from length 20 to 1000 .* neither at most 1 \(O\(N\)\) nor at least 4 \(O\(N·n\)\)/);
  }, 120_000);
});

describe('cost probe: the decision rule and the work sum', () => {
  it('writes a class only at the documented margin from the boundary', () => {
    expect(G.PROBE).toMatchObject({ cost_growth: 2, cost_margin: 2 });
    expect([32.4, 13.6, 4].map(G.costVerdict)).toEqual(['O(N·n)', 'O(N·n)', 'O(N·n)']);
    expect([-0.09, 0, 1].map(G.costVerdict)).toEqual(['O(N)', 'O(N)', 'O(N)']);
    expect([1.01, 2, 3.99, NaN, Infinity].map(G.costVerdict)).toEqual([null, null, null, null, null]);
  });

  it('uses the default and fifty times it, at most a quarter of the bars', () => {
    expect(G.costLengths(14, 10000)).toEqual([14, 1000]);
    expect(G.costLengths(30, 10000)).toEqual([30, 1500]);
    expect(G.costLengths(55, 10000)).toEqual([55, 2500]);
    expect(G.costLengths(0, 10000)).toEqual([1, 1000]);
  });

  const fn = (ranges, isBlockCoverage = true, functionName = 'k') => ({ functionName, isBlockCoverage, ranges: ranges.map(([startOffset, endOffset, count]) => ({ startOffset, endOffset, count })) });
  const KERNEL = 'file:///kernel.mjs', HARNESS = 'file:///harness.mjs';
  // characters 0-9 and 30-99 run once, 10-14 and 20-29 fifty times, 15-19 two hundred times
  const nested = [[0, 100, 1], [10, 30, 50], [15, 20, 200]], expected = 80 * 1 + 15 * 50 + 5 * 200;

  it('counts each source character once per run of the innermost block that holds it', () => {
    expect(G.executedChars([{ url: KERNEL, functions: [fn(nested)] }])).toBe(expected);
    // V8 leaves out a block whose count equals its parent's, and the order of the blocks does not matter
    expect(G.executedChars([{ url: KERNEL, functions: [fn([[15, 20, 200], [40, 60, 1], ...nested.slice(0, 2)])] }])).toBe(expected);
    // node internals and the harness (the code that calls the meter) are not the measured code
    expect(G.executedChars([{ url: KERNEL, functions: [fn(nested)] }, { url: 'node:internal/x', functions: [fn([[0, 1e6, 1e6]])] },
      { url: HARNESS, functions: [fn([[0, 1e6, 1e6]], false)] }], [HARNESS])).toBe(expected);
  });

  it('stops when measured code ran without block counts or its blocks do not nest', () => {
    expect(() => G.executedChars([{ url: KERNEL, functions: [fn([[0, 100, 3]], false, 'early')] }])).toThrow(/early in file:\/\/\/kernel\.mjs ran without block counts/);
    expect(G.executedChars([{ url: KERNEL, functions: [fn(nested), fn([[0, 100, 0]], false, 'never_ran')] }])).toBe(expected);
    expect(() => G.executedChars([{ url: KERNEL, functions: [fn([[0, 100, 1], [10, 30, 5], [20, 40, 7]])] }])).toThrow(/overlap without nesting/);
  });
});
