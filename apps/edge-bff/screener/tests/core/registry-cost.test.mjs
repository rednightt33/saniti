/* The generator's cost probe (scripts/build-screener-registry.mjs, cost_class of report 6.8) counts work, never time:
   its class follows how a kernel's work grows with the length, is the same under a noisy clock to the last executed
   character, runs only below V8's optimizing compiler, refuses a growth that neither class owns and lengths that cannot
   tell the classes apart, and stops when the measured code was compiled before its meter started. Kernels:
   tests/core/cost-doubles.mjs. Plain JavaScript, because it spawns the probe's child process (node:child_process), as
   registry-check.test.mjs. */
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
/** The probe's child process as build() starts it (G.costChildArgs(): --cost-work, the job on stdin), with extra
    environment, or with other node arguments. */
function costWork(groups, env = {}, args = G.costChildArgs()) {
  const r = spawnSync(process.execPath, args, { cwd: APP, encoding: 'utf8', input: JSON.stringify({ module: DOUBLES, bars: G.PROBE.cost_bars, groups }), env: { ...process.env, ...env } });
  return { ...r, out: r.status === 0 ? JSON.parse(r.stdout) : null };
}
const classes = out => Object.fromEntries(out.map(g => [`${g.id}.${g.param}#${g.measured.length}`, g.cost_class]));

const GROUPS = [
  group('window_max', 'length'),
  group('window_reduce', 'length'),
  group('window_over_intermediate', 'length'),
  group('window_over_intermediate', 'smooth'),
  group('running_mean', 'length'),
  group('recursive', 'length'),
  group('switchable', 'length', [{}, { method: 'loop' }]),
  group('switchable', 'length'),
];

describe('cost probe: work, not time', () => {
  it('classes a window loop O(N·n), also over an internal intermediate array or through reduce, and a running or recursive kernel O(N)', () => {
    const r = costWork(GROUPS);
    expect(r.stderr).toBe('');
    expect(r.status).toBe(0);
    expect(classes(r.out)).toEqual({
      'window_max.length#1': 'O(N·n)',
      'window_reduce.length#1': 'O(N·n)',          // a built-in that calls back into JavaScript (reduce) is counted
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
  }, 600_000);

  it('measures the same work, to the character, when every clock jumps at random (a noisy clock cannot flip a class)', () => {
    const plain = costWork(GROUPS), dir = fs.mkdtempSync(path.join(os.tmpdir(), 'noisy-clock-')), log = path.join(dir, 'pids');
    try {
      const noisy = costWork(GROUPS, { NODE_OPTIONS: `${process.env.NODE_OPTIONS ?? ''} --import=${NOISY}`.trim(), NOISY_CLOCK_LOG: log });
      expect(noisy.stderr).toBe('');
      expect(fs.readFileSync(log, 'utf8').trim().split('\n').length).toBeGreaterThanOrEqual(1);   // the clock was in place
      expect(noisy.out).toEqual(plain.out);
    } finally {
      fs.rmSync(dir, { recursive: true, force: true });
    }
  }, 600_000);

  it('runs only below the optimizing compiler, whose block counts depend on when it takes over', () => {
    const r = costWork([group('running_mean', 'length')], {}, G.costChildArgs().filter(a => a !== G.COST_TIER_FLAG));
    expect(r.status).not.toBe(0);
    expect(r.stderr).toContain(`cost probe: the child must run with ${G.COST_TIER_FLAG}`);
  }, 600_000);

  it('stops the build, naming the numbers, when the growth is between the classes', () => {
    const r = costWork([group('stepped', 'length')]);
    expect(r.status).not.toBe(0);
    expect(r.stderr).toMatch(/cost probe stepped\.length \{\}: the work grows 1\.\d+ from length 20 to 1000 .* neither at most 1 \(O\(N\)\) nor at least 4 \(O\(N·n\)\)/);
    expect(r.stderr).toContain('read the kernel\'s loops, or raise PROBE.cost_long_length before building');
  }, 600_000);

  it('refuses lengths too close to tell the classes apart: a window loop at a large default would come out O(N)', () => {
    // at 1500 the second length is 2500 (a quarter of the bars): the window loop grows 0.47, inside the O(N) bound
    const r = costWork([group('wide_window', 'length')]);
    expect(r.status).not.toBe(0);
    expect(r.stderr).toMatch(/cost probe wide_window\.length \{\}: at lengths 1500 and 2500 on 10000 bars even a kernel that is all window loop grows only 0\.47\d, less than 4 \(O\(N·n\)\), so the probe cannot tell O\(N·n\) from O\(N\) at this default: raise PROBE\.cost_bars/);
  }, 600_000);

  it('stops when the measured code was compiled before the meter started (V8 gives it no block counts)', () => {
    // the module loaded before the generator (NODE_OPTIONS --import): its import-time call compiles windowMax (and nul)
    // early, so V8 reports them by function only
    const r = costWork([group('window_max', 'length')], { NODE_OPTIONS: `${process.env.NODE_OPTIONS ?? ''} --import=${pathToFileURL(DOUBLES).href}`.trim() });
    expect(r.status).not.toBe(0);
    expect(r.stderr).toMatch(/^cost probe: (windowMax|nul) in file:\S*cost-doubles\.mjs ran without block counts \(compiled before the work meter started\)/);
  }, 600_000);
});

describe('cost probe: the decision rule and the work sum', () => {
  it('writes a class only at the documented margin from the boundary', () => {
    expect(G.PROBE).toMatchObject({ cost_growth: 2, cost_margin: 2 });
    expect([32.4, 13.6, 4].map(G.costVerdict)).toEqual(['O(N·n)', 'O(N·n)', 'O(N·n)']);
    expect([-0.09, 0, 1].map(G.costVerdict)).toEqual(['O(N)', 'O(N)', 'O(N)']);
    expect([1.01, 2, 3.99, NaN, Infinity].map(G.costVerdict)).toEqual([null, null, null, null, null]);
  });

  it('bounds the growth of an O(N·n) parameter by a kernel that is all window loop', () => {
    expect(G.windowGrowth([14, 1000], 10000)).toBeCloseTo(1000 * 9001 / (14 * 9987) - 1, 12);
    expect(G.windowGrowth([55, 2500], 10000)).toBeGreaterThan(30);               // the largest default of the 53 (I52)
    expect(G.windowGrowth(G.costLengths(1500, 10000), 10000)).toBeLessThan(G.PROBE.cost_growth / G.PROBE.cost_margin);
    expect(G.windowGrowth(G.costLengths(3000, 10000), 10000)).toBeLessThan(0);   // the second length below the first
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
