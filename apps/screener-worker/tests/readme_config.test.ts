/* The README's "Configuration" table against src/config.ts (docs review 2026-10-29). The deploy runbook's variable
   step was a list kept by hand beside the code and missed a variable loadConfig requires (SCREENER_CACHE_DIR_BYTES
   with SCREENER_CACHE_DIR, config.ts), so the worker would have refused to start. The README table is a list of the
   same kind, and the runbook takes its values from it. These checks derive what loadConfig reads, requires and accepts
   from loadConfig itself (a recording env, one variable left out at a time), never from a list kept in this file:
   every name it reads has a row and every row is a name it reads; each row cites the config.ts lines that read it and
   the minimum whole() checks; optional/default rows are exactly the ones loadConfig starts without; the proposed
   values pass loadConfig together; the counts the prose states are the counts of the table. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { test } from 'node:test';
import { loadConfig } from '../src/config.ts';
import { REPO_ROOT } from '../src/version.ts';

const README = fs.readFileSync(path.join(REPO_ROOT, 'apps/screener-worker/README.md'), 'utf8');
const CONFIG = fs.readFileSync(path.join(REPO_ROOT, 'apps/screener-worker/src/config.ts'), 'utf8');
const FAKE_SECRET = 'f'.repeat(64);                    // a test value, never a key
const FAKE_ORIGIN = 'https://bucket.example.test';

interface Row { name: string; lines: [number, number] | null; check: string; proposed: string }

/** The rows of the "## Configuration" table whose first cell is a variable name. */
function tableRows(readme: string): { rows: Row[]; section: string } {
  const section = (readme.split('\n## Configuration\n')[1] ?? '').split('\n## ')[0];
  const rows: Row[] = [];
  for (const line of section.split('\n')) {
    const m = /^\| `([A-Z][A-Z0-9_]+)` \| (.*) \| (.*) \| (.*) \|$/.exec(line);
    if (!m) continue;
    const at = /^:(\d+)(?:-(\d+))?/.exec(m[2]);
    rows.push({ name: m[1], lines: at ? [Number(at[1]), Number(at[2] ?? at[1])] : null, check: m[2], proposed: m[4] });
  }
  return { rows, section };
}

/** The value a row proposes, or undefined for a row that is not set. A secret or a value copied from elsewhere has no
    literal in the table: a test value of the kind its check names stands in for it. */
function valueOf(r: Row): string | undefined | null {
  if (/^not set\b/.test(r.proposed)) return undefined;
  const n = /^(\d+)\b/.exec(r.proposed);
  if (n) return n[1];
  const lit = /^`((?:https?:\/\/|\/)[^`\s]+)`/.exec(r.proposed);
  if (lit) return lit[1];
  if (/characters/.test(r.check)) return FAKE_SECRET;
  if (/scheme:\/\//.test(r.check)) return FAKE_ORIGIN;
  return null;
}

type Load = (env: Record<string, string | undefined>) => unknown;

/** Every name the loader reads for this environment (its env lookups recorded), or the error it throws. */
function reads(env: Record<string, string>, load: Load): { names: Set<string>; error: string | null } {
  const names = new Set<string>();
  const seen = new Proxy(env, { get(t, k) { if (typeof k !== 'string') return undefined; names.add(k); return t[k] } });
  try { load(seen); return { names, error: null } } catch (e) { return { names, error: (e as Error).message } }
}

/** Every name the loader reads, also past a variable the table lacks: a name the loader stops on that the table does
    not give is given a stand-in (a number, then a key-length secret, then an origin) and the load repeated. */
const STAND_INS = ['1000000000', FAKE_SECRET, FAKE_ORIGIN];
function allReads(env: Record<string, string>, load: Load): Set<string> {
  const probe = { ...env }, tried = new Map<string, number>();
  for (;;) {
    const r = reads(probe, load);
    const name = r.error ? /^([A-Z][A-Z0-9_]*)\b/.exec(r.error)?.[1] : undefined;
    const k = name && !(name in env) ? (tried.get(name) ?? -1) + 1 : STAND_INS.length;
    if (!r.error || k >= STAND_INS.length) return r.names;
    tried.set(name as string, k); probe[name as string] = STAND_INS[k];
  }
}

/** Every way the table disagrees with config.ts; [] when it agrees. */
function problems(readme: string, load: Load = loadConfig, config = CONFIG): string[] {
  const out: string[] = [];
  const { rows, section } = tableRows(readme);
  if (!rows.length) return ['README has no "Configuration" table with variable rows'];
  const env: Record<string, string> = {};
  for (const r of rows) {
    const v = valueOf(r);
    if (v === null) out.push(`${r.name}: the proposed value "${r.proposed.slice(0, 40)}" is neither a literal nor a kind of test value`);
    else if (v !== undefined) env[r.name] = v;
  }
  const base = reads(env, load);
  if (base.error) out.push(`the proposed values do not pass loadConfig: ${base.error}`);
  const names = allReads(env, load), listed = new Set(rows.map(r => r.name));
  for (const n of names) if (!listed.has(n)) out.push(`${n}: loadConfig reads it, the table has no row`);
  for (const n of listed) if (!names.has(n)) out.push(`${n}: a row, but loadConfig does not read it`);
  // required or not, by leaving each one out of a set that loads (no such analysis when the proposed set fails)
  const optional = new Set<string>();
  if (!base.error) for (const n of base.names) {
    if (!(n in env)) { optional.add(n); continue }        // the proposed set loaded without it
    const e = { ...env }; delete e[n];
    const r = reads(e, load);
    if (!r.error) optional.add(n);
    else if (!r.error.startsWith(`${n} is required`)) out.push(`${n}: left out, loadConfig fails on something else (${r.error})`);
  }
  const src = config.split('\n');
  for (const r of rows) {
    if (!r.lines) { out.push(`${r.name}: the check cell does not start with the config.ts line (":n" or ":a-b")`); continue }
    const [a, b] = r.lines;
    if (!new RegExp(`\\b(?:need|whole|raw)\\('${r.name}'`).test(src.slice(a - 1, b).join('\n')))
      out.push(`${r.name}: config.ts:${a}${b !== a ? `-${b}` : ''} does not read it`);
    const rule = r.check.replace(/^:\d+(?:-\d+)?,?\s*/, '');          // the cell after its line pointer
    const w = new RegExp(`\\bwhole\\('${r.name}', (\\d+)`).exec(config);
    if (w) {
      const stated = /at least (\d+)/.exec(rule)?.[1] ?? /^(\d+)-\d+\b/.exec(rule)?.[1];
      if (stated !== w[1]) out.push(`${r.name}: the table states the minimum ${stated ?? 'nowhere'}, config.ts checks at least ${w[1]}`);
    }
    if (!base.error) {
      const saysOptional = /\boptional\b|\bdefault \d/.test(rule);
      if (saysOptional !== optional.has(r.name)) out.push(`${r.name}: the table says ${saysOptional ? 'optional' : 'required'}, loadConfig ${optional.has(r.name) ? 'starts without it' : 'requires it'}`);
    }
  }
  const total = /reads exactly these (\d+) names/.exec(section);
  if (total && Number(total[1]) !== rows.length) out.push(`the prose says ${total[1]} names, the table has ${rows.length}`);
  const setNames = Object.keys(env), required = setNames.filter(n => !optional.has(n));
  const counts = /(\d+) of the (\d+) set names are required/.exec(section);
  if (!base.error && counts && (Number(counts[1]) !== required.length || Number(counts[2]) !== setNames.length))
    out.push(`the prose says ${counts[1]} of ${counts[2]} set names are required; the table gives ${required.length} of ${setNames.length}`);
  return out;
}

test('the README configuration table is what loadConfig reads, requires and accepts', () => {
  assert.deepEqual(problems(README), []);
});

test('the table check fails on each kind of drift (a row missing, a wrong line, a wrong minimum, values loadConfig refuses, optional wrong, a count wrong)', () => {
  const lineOf = (name: string) => README.split('\n').find(l => l.startsWith(`| \`${name}\` |`)) as string;
  const mutate = (from: string, to: string): string => { assert.ok(README.includes(from), from); const m = README.replace(from, to); assert.notEqual(m, README); return m };
  const cases: [string, RegExp][] = [
    // the runbook's own defect: the directory without its budget (config.ts requires SCREENER_CACHE_DIR_BYTES with it)
    [mutate(lineOf('SCREENER_CACHE_DIR_BYTES') + '\n', ''), /do not pass loadConfig: SCREENER_CACHE_DIR_BYTES is required/],
    [mutate(lineOf('SCREENER_OWNER_CPU_MS') + '\n', ''), /SCREENER_OWNER_CPU_MS: loadConfig reads it, the table has no row/],
    [mutate(lineOf('SCREENER_OWNER_CPU_MS'), lineOf('SCREENER_OWNER_CPU_MS').replace('| :109,', '| :110,')), /SCREENER_OWNER_CPU_MS: config\.ts:110 does not read it/],
    [mutate(lineOf('SCREENER_THREAD_HEAP_MB'), lineOf('SCREENER_THREAD_HEAP_MB').replace('at least 64', 'at least 32')), /SCREENER_THREAD_HEAP_MB: the table states the minimum 32, config\.ts checks at least 64/],
    [mutate(lineOf('SCREENER_OWNER_CPU_MS'), lineOf('SCREENER_OWNER_CPU_MS').replace('| 30000 |', '| 1000 |')), /do not pass loadConfig: SCREENER_OWNER_CPU_MS must be at least SCREENER_MAX_CPU_MS/],
    [mutate(lineOf('SCREENER_CACHE_DIR'), lineOf('SCREENER_CACHE_DIR').replace(':97, optional', ':97')), /SCREENER_CACHE_DIR: the table says required, loadConfig starts without it/],
    [mutate('reads exactly these 30 names', 'reads exactly these 29 names'), /the prose says 29 names, the table has 30/],
    [mutate('28 of the 29 set names are required', '29 of the 29 set names are required'), /the prose says 29 of 29 set names are required; the table gives 28 of 29/],
  ];
  for (const [text, want] of cases) {
    const p = problems(text);
    assert.ok(p.some(x => want.test(x)), `${want}: ${p.join('; ')}`);
  }
  // the runbook's own defect, on the code side: loadConfig gains a required variable the table does not list (the names
  // come from what the loader reads, so no list in this file has to change for the check to see it)
  const gained: Load = env => { const c = loadConfig(env); if (!(env.SCREENER_NEW_LIMIT ?? '').trim()) throw new Error('SCREENER_NEW_LIMIT is required.'); return c };
  const p = problems(README, gained);
  assert.ok(p.some(x => /SCREENER_NEW_LIMIT: loadConfig reads it, the table has no row/.test(x)), p.join('; '));
  assert.ok(p.some(x => /the proposed values do not pass loadConfig: SCREENER_NEW_LIMIT is required/.test(x)), p.join('; '));
});
