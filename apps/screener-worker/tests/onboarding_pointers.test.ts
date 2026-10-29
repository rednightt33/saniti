/* SCREENER_ONBOARDING.md's line pointers against the code (docs review 2026-10-29; the rule and the parser are in
   doc-pointers.ts). The document's header stated that no cited file had changed since the commit it was verified at; the
   follow-up edits of the same day moved about thirty cited lines (worker server.ts and catalog.ts, core validate.ts and
   contract.ts, edge-bff screener.py) and nothing failed, and eleven bare `:line` pointers sat after another file's
   pointer, so they named a line of the wrong file. These tests read every pointer out of the document itself and check
   it against the files as they are now; a second test proves each kind of drift fails on a small repository of its own,
   so the cases do not depend on today's code. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { test } from 'node:test';
import { REPO_ROOT } from '../src/version.ts';
import { DOC, pointerProblems, pointersOf, readFrom, repositoryFiles } from './doc-pointers.ts';
import type { Read } from './doc-pointers.ts';

test('every line pointer of SCREENER_ONBOARDING.md names one file, existing lines, and the symbol written next to it on its first line', () => {
  const files = repositoryFiles(), read = readFrom(REPO_ROOT);
  const text = fs.readFileSync(path.join(REPO_ROOT, DOC), 'utf8');
  const found = pointersOf(text, files, read);
  // the parser must keep reading the document's pointers (237 and 140 with a symbol on 2026-10-29)
  assert.ok(found.length >= 200, `only ${found.length} pointers read: the parser lost them`);
  assert.ok(found.filter(p => p.ident).length >= 120, `only ${found.filter(p => p.ident).length} pointers with a symbol read`);
  assert.deepEqual(pointerProblems(text, files, read), []);
});

test('the pointer check fails on each kind of drift (a line that moved under its symbol, a bare pointer after another file, a line past the end, an ambiguous name, a renamed symbol)', () => {
  const files = ['apps/a/src/server.ts', 'apps/b/src/server.ts', 'apps/a/src/pool.ts', 'apps/a/src/data.ts'];
  const code: Record<string, string[]> = {
    'apps/a/src/server.ts': ['// a', 'export function compute() {', '  return 1;', '}', 'const pinned = 1;', ''],
    'apps/b/src/server.ts': ['// b', 'export function other() {}', ''],
    'apps/a/src/pool.ts': ['class Pool {}', 'const lanes = 2;', ''],
    'apps/a/src/data.ts': ['export const decode = 1;', ''],
  };
  const read: Read = f => code[f] ?? null;
  const ok = '## 1 Worker\n\nIt runs (`apps/a/src/server.ts:2-4` `compute`; `pinned`, `:5`) and `pool.ts:2` `lanes`.\n';
  assert.deepEqual(pointerProblems(ok, files, read), []);
  const cases: [string, RegExp][] = [
    // the observed defect: code moved under the pointer; the range still covers the symbol, but no longer starts at it
    ['## 1\n\n(`apps/a/src/server.ts:1-4` `compute`)\n', /`compute` is not on the first cited line of apps\/a\/src\/server\.ts:1-4 \(it is on line 2\)/],
    // the second observed defect: a bare pointer after another file's pointer is in that other file
    ['## 1\n\n`apps/a/src/server.ts` reads (`apps/a/src/data.ts:1` `decode`) its rows (`pinned`, `:5`)\n', /`:5`: apps\/a\/src\/data\.ts has 1 lines, not 5/],
    ['## 1\n\n`apps/a/src/pool.ts:9`\n', /apps\/a\/src\/pool\.ts has 2 lines, not 9/],
    ['## 1\n\n`server.ts:1`\n', /names no single file \(apps\/a\/src\/server\.ts, apps\/b\/src\/server\.ts\)/],
    // a short name the symbol settled until the line moved: the refusal says where the symbol is now
    ['## 1\n\n`server.ts:1` `compute`\n', /names no single file \(.*\): spell the path; `compute` is on apps\/a\/src\/server\.ts:2/],
    ['## 1\n\n(`:4`)\n', /names no single file \(no file in this section before it\)/],
    // a section forgets the files the section before it named
    ['## 1\n\n`apps/b/src/server.ts:2`\n\n## 2\n\n`server.ts:2`\n', /`server\.ts:2`: names no single file/],
    ['## 1\n\n`apps/a/src/server.ts:5` `pinnedSeries`\n', /`pinnedSeries` is not on the first cited line of apps\/a\/src\/server\.ts:5 \(apps\/a\/src\/server\.ts no longer has it\)/],
  ];
  for (const [text, want] of cases) {
    const p = pointerProblems(text, files, read);
    assert.ok(p.some(x => want.test(x)), `${want}: ${p.join('; ') || 'no problem found'}`);
  }
  // a short name is the file its section named last, and the symbol is checked in that file
  assert.deepEqual(pointerProblems('## 1\n\n`apps/b/src/server.ts:2` and `server.ts:2` `other`\n', files, read), []);
  assert.match(pointerProblems('## 1\n\n`apps/b/src/server.ts:2` and `server.ts:2` `compute`\n', files, read).join(), /`compute` is not on the first cited line of apps\/b\/src\/server\.ts:2/);
  // with no file named in the section, the symbol next to it picks the one file whose cited line holds it
  assert.deepEqual(pointerProblems('## 1\n\n`server.ts:2` `compute`\n', files, read), []);
  // a symbol read after one pointer is not also the symbol of the next one
  assert.deepEqual(pointerProblems('## 1\n\n`apps/a/src/pool.ts:2` `lanes`, `apps/a/src/server.ts:5`\n', files, read), []);
  // a code fence is not prose: a span inside it is not a pointer
  assert.deepEqual(pointerProblems('## 1\n\n```\n`apps/a/src/pool.ts:99`\n```\n', files, read), []);
});
