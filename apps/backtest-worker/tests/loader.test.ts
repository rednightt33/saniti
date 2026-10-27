/* The module loader (loader/resolve.mjs, ERRORS M249): the Terminal's sources, written for Vite, import their neighbours
   without an extension; the worker and its tests load them under Node. resolve() alone, then the real processes: the
   image's command (Dockerfile CMD) and every npm script that runs the worker's TypeScript carry the loader, and with it
   (not without) Node loads a module that imports as the Terminal's do, and the Terminal's own data readers. */
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import { test } from 'node:test';
import { resolve } from '../loader/resolve.mjs';

const WORKER_DIR = new URL('..', import.meta.url).pathname;
const IMAGE_CMD: string[] = JSON.parse(fs.readFileSync(new URL('../Dockerfile', import.meta.url), 'utf8').match(/^CMD (\[.*\])$/m)![1]);
const SCRIPTS: Record<string, string> = JSON.parse(fs.readFileSync(new URL('../package.json', import.meta.url), 'utf8')).scripts;
const HOOK = ['--import', './loader/register.mjs'];

const notFound = (code = 'ERR_MODULE_NOT_FOUND') => Object.assign(new Error(`not found (${code})`), { code });
/** a stand-in for Node's own resolution: the specifiers it finds, every other one not found */
const nodeFinds = (...found: string[]) => {
  const asked: string[] = [];
  const next = async (specifier: string) => {
    asked.push(specifier);
    if (found.includes(specifier)) return { url: `file:///x/${specifier}` };
    throw notFound(specifier.endsWith('dir') ? 'ERR_UNSUPPORTED_DIR_IMPORT' : undefined);
  };
  return { asked, next };
};

test('resolve: a relative specifier without an extension that Node cannot find is tried as <specifier>.ts, then <specifier>/index.ts', async () => {
  let n = nodeFinds('./timeframe.ts');
  assert.deepEqual(await resolve('./timeframe', {}, n.next), { url: 'file:///x/./timeframe.ts' });
  assert.deepEqual(n.asked, ['./timeframe', './timeframe.ts']);
  n = nodeFinds('../calc/dir/index.ts');
  assert.deepEqual(await resolve('../calc/dir', {}, n.next), { url: 'file:///x/../calc/dir/index.ts' });
  assert.deepEqual(n.asked, ['../calc/dir', '../calc/dir.ts', '../calc/dir/index.ts']);
});

test('resolve: what Node resolves itself is unchanged, and anything else keeps Node\'s own error', async () => {
  let n = nodeFinds('./timeframe');                                  // Node finds it: asked once, as written
  assert.deepEqual(await resolve('./timeframe', {}, n.next), { url: 'file:///x/./timeframe' });
  assert.deepEqual(n.asked, ['./timeframe']);
  for (const specifier of ['./missing', './x.ts', './indRegistry.json', 'some-package', 'node:fs', '/abs/path']) {
    n = nodeFinds();
    await assert.rejects(resolve(specifier, {}, n.next), (e: Error & { code?: string }) => e.message === `not found (ERR_MODULE_NOT_FOUND)`, specifier);
    // only a relative specifier without an extension is tried again
    assert.deepEqual(n.asked, specifier === './missing' ? ['./missing', './missing.ts', './missing/index.ts'] : [specifier], specifier);
  }
  const other = Object.assign(new Error('syntax'), { code: 'ERR_INVALID_TYPESCRIPT_SYNTAX' });
  await assert.rejects(resolve('./bad', {}, async () => { throw other }), e => e === other);     // not a "not found"
  let calls = 0;
  await assert.rejects(resolve('./b', {}, async () => { calls++; throw calls === 1 ? notFound() : other }), e => e === other);
});

test('every Node entry of the worker carries the loader: the image\'s command and each npm script that runs its TypeScript', () => {
  assert.equal(IMAGE_CMD[0], 'node');
  assert.deepEqual(IMAGE_CMD.slice(1, 4), ['--experimental-strip-types', ...HOOK]);
  const node = Object.entries(SCRIPTS).filter(([, s]) => /^node\b/.test(s));
  assert.ok(node.length >= 4, Object.keys(SCRIPTS).join(' '));      // start, registry, registry:check, test
  for (const [name, script] of node) assert.ok(script.startsWith(`node --experimental-strip-types ${HOOK.join(' ')} `), `${name}: ${script}`);
});

test('with the image\'s flags (not without) Node loads a module that imports as the Terminal\'s do, and the Terminal\'s data readers', () => {
  const flags = IMAGE_CMD.slice(1, -1);                              // the command without its script
  const load = (args: string[], spec: string) => spawnSync(process.execPath, [...args, '--input-type=module', '-e',
    `const m = await import(${JSON.stringify(spec)}); console.log(JSON.stringify(Object.keys(m).sort()))`], { cwd: WORKER_DIR, encoding: 'utf8' });
  const fixture = load(flags, './tests/loader-fixture/a.ts');
  assert.equal(fixture.status, 0, fixture.stderr);
  assert.deepEqual(JSON.parse(fixture.stdout), ['a']);
  const without = load(flags.filter(f => !HOOK.includes(f)), './tests/loader-fixture/a.ts');
  assert.notEqual(without.status, 0);
  assert.match(without.stderr, /ERR_MODULE_NOT_FOUND/);
  const terminal = load(flags, '../edge-bff/terminal/src/data/worker.ts');   // the parity tests' oracle (datafile, flow)
  assert.equal(terminal.status, 0, terminal.stderr);
  assert.ok(JSON.parse(terminal.stdout).includes('priceRows'));
});
