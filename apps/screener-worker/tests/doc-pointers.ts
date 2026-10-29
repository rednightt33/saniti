/* The line pointers of a document read and checked against the code (docs review 2026-10-29; test:
   onboarding_pointers.test.ts). SCREENER_ONBOARDING.md cites the code as `path:line` plus the symbol (AGENTS.md "Gates
   and evidence": every claim cites file:line), and its header kept, by hand, the claim that no cited file had changed
   since the commit it was verified at. Every pointer is read out of the document itself, never from a list kept here,
   by the rule the document states in its "Pointers" bullet:
     - a pointer is a code span `path:N`, `path:N-M` or a comma list of those, or a bare `:N`;
     - `path` is a repository path; else the file ending in it that the same `#`/`##` section named last; else the only
       repository file ending in it; else, among several, the one whose cited first line holds the symbol next to it;
     - a bare `:N` is in the file the same section named last (any code span naming a repository file);
     - the symbol next to a pointer is the code span right after it (`` `path:N` `name` ``) or, failing that, right
       before it (`` `name` `path:N` ``, `` `name`, `path:N` ``, `` `name` (`path:N` ``), unless that span is already
       the symbol after the pointer before it.
   A pointer must name one file and existing lines, and its symbol must be on the first line of a cited range: a range
   starts where the thing it names starts, so code that moves under a pointer is seen even while the range still covers
   the symbol further down. A refusal names the document line, the pointer and the line the symbol is on now. Spans in
   code fences are not prose and are skipped. */
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { REPO_ROOT } from '../src/version.ts';

export const DOC = 'SCREENER_ONBOARDING.md';
const EXT = '(?:ts|mts|mjs|cjs|js|py|json|sql|md|sh|html|css|toml|txt)';
const FILE = new RegExp(`^((?:[\\w.-]+/)*[\\w.-]+\\.${EXT})(?::(\\d+(?:-\\d*)?(?:, ?\\d+(?:-\\d*)?)*))?$`);
const BARE = /^:(\d+(?:-\d*)?(?:, ?\d+(?:-\d*)?)*)$/;
const IDENT = /^[A-Za-z_][\w.]*(?:\(\))?$/;
// what may separate a pointer from its symbol: white space (one line break at most) after it; before it the same, or a
// comma, an opening parenthesis, or both
const AFTER = /^(?=\s)[ \t]*(?:\n[ \t]*)?$/, BEFORE = /^(?=[\s,(]),?[ \t]*(?:\n[ \t]*)?\(?$/;

export interface Pointer { line: number; span: string; file: string | null; candidates: string[]; ranges: [number, number][]; ident: string | null }
export type Read = (file: string) => string[] | null;

/** Repository files: git's list (tracked and untracked, ignored ones left out), else a walk without dot folders and
    node_modules. */
export function repositoryFiles(root = REPO_ROOT): string[] {
  try {
    return execFileSync('git', ['-C', root, 'ls-files', '--cached', '--others', '--exclude-standard'], { encoding: 'utf8', maxBuffer: 64 << 20 }).split('\n').filter(Boolean);
  } catch {
    const out: string[] = [];
    const walk = (dir: string) => {
      for (const e of fs.readdirSync(path.join(root, dir), { withFileTypes: true })) {
        if (e.name.startsWith('.') || e.name === 'node_modules') continue;
        const rel = dir ? `${dir}/${e.name}` : e.name;
        if (e.isDirectory()) walk(rel); else out.push(rel);
      }
    };
    walk('');
    return out;
  }
}
/** A file's lines, read once. */
export const readFrom = (root: string): Read => {
  const cache = new Map<string, string[] | null>();
  return f => {
    if (!cache.has(f)) { try { cache.set(f, fs.readFileSync(path.join(root, f), 'utf8').split('\n')) } catch { cache.set(f, null) } }
    return cache.get(f) ?? null;
  };
};

const rangesOf = (s: string): [number, number][] => s.split(/, ?/).map(p => { const [a, b] = p.split('-'); return [Number(a), b ? Number(b) : Number(a)] });
const nameOf = (ident: string) => ident.replace(/\(\)$/, '').split('.').pop() as string;
const spell = (ranges: [number, number][]) => ranges.map(([a, b]) => a === b ? `${a}` : `${a}-${b}`).join(', ');
/** The first lines (at most five) that hold the symbol. */
const linesWith = (lines: string[] | null, ident: string) => (lines ?? []).flatMap((l, i) => l.includes(nameOf(ident)) ? [i + 1] : []).slice(0, 5);
/** The symbol is on the first line of a cited range. */
const holds = (lines: string[] | null, ranges: [number, number][], ident: string) =>
  !!lines && ranges.some(([a]) => (lines[a - 1] ?? '').includes(nameOf(ident)));

/** Every pointer of the document, resolved by the document's rule (the file null when it names no single file). */
export function pointersOf(doc: string, files: readonly string[], read: Read): Pointer[] {
  const known = new Set(files), out: Pointer[] = [];
  const ending = (p: string) => files.filter(f => f === p || f.endsWith(`/${p}`));
  // the prose as blocks outside code fences; a block that starts at a `#` or `##` heading starts a section
  const blocks: { start: number; text: string; section: boolean }[] = [{ start: 1, text: '', section: true }];
  let fence = false;
  doc.split('\n').forEach((raw, i) => {
    if (/^\s*```/.test(raw)) { fence = !fence; blocks.push({ start: i + 2, text: '', section: false }); return }
    if (fence) return;
    if (/^#{1,2} /.test(raw)) blocks.push({ start: i + 1, text: '', section: true });
    blocks[blocks.length - 1].text += raw + '\n';
  });
  let named: string[] = [];                                    // files the current section named, the latest last
  for (const b of blocks) {
    if (b.section) named = [];
    const spans = [...b.text.matchAll(/`([^`\n]+)`/g)].map(m => ({ at: m.index as number, end: (m.index as number) + m[0].length, body: m[1] }));
    const isIdent = (x: { body: string }) => IDENT.test(x.body) && !FILE.test(x.body) && !BARE.test(x.body);
    let taken = -1;                                            // the span read as the symbol after the pointer before
    spans.forEach((s, i) => {
      const f = FILE.exec(s.body), bare = BARE.exec(s.body);
      if (!f && !bare) return;
      const next = spans[i + 1], prev = spans[i - 1];
      let ident: string | null = null;
      if (next && AFTER.test(b.text.slice(s.end, next.at)) && isIdent(next)) { ident = next.body; taken = i + 1 }
      else if (prev && taken !== i - 1 && BEFORE.test(b.text.slice(prev.end, s.at)) && isIdent(prev)) ident = prev.body;
      const lines = f ? f[2] : bare?.[1];
      const ranges = lines ? rangesOf(lines) : [];
      let file: string | null = null, candidates: string[] = [];
      if (f) {
        candidates = known.has(f[1]) ? [f[1]] : ending(f[1]);
        if (candidates.length === 1) file = candidates[0];
        else if (candidates.length > 1) {
          file = [...named].reverse().find(n => candidates.includes(n)) ?? null;
          if (!file && ident && ranges.length) { const m = candidates.filter(c => holds(read(c), ranges, ident as string)); if (m.length === 1) file = m[0] }
        }
        if (file) named.push(file);
      } else { file = named.at(-1) ?? null; candidates = file ? [file] : [] }
      if (lines) out.push({ line: b.start + b.text.slice(0, s.at).split('\n').length - 1, span: s.body, file, candidates, ranges, ident });
    });
  }
  return out;
}

/** Every way the document's pointers disagree with the code; [] when they agree. */
export function pointerProblems(doc: string, files: readonly string[], read: Read, name = DOC): string[] {
  const out: string[] = [];
  for (const p of pointersOf(doc, files, read)) {
    const at = `${name}:${p.line} \`${p.span}\``;
    if (!p.file) {
      // several files end in the path and the symbol starts none of their cited lines: say where it is, so a moved line
      // reads as moved rather than as a missing path
      const where = p.ident && p.candidates.length > 1 ? p.candidates.flatMap(c => { const hit = linesWith(read(c), p.ident as string); return hit.length ? [`${c}:${hit.join(', ')}`] : [] }) : [];
      out.push(`${at}: names no single file (${p.candidates.length ? p.candidates.join(', ') : 'no file in this section before it'}): spell the path${where.length ? `; \`${p.ident}\` is on ${where.join('; ')}` : ''}`);
      continue;
    }
    const lines = read(p.file);
    if (!lines) { out.push(`${at}: ${p.file} cannot be read`); continue }
    const n = lines.at(-1) === '' ? lines.length - 1 : lines.length;
    const bad = p.ranges.filter(([a, b]) => !(a >= 1 && b >= a && b <= n));
    if (bad.length) { out.push(`${at}: ${p.file} has ${n} lines, not ${spell(bad)}`); continue }
    if (p.ident && !holds(lines, p.ranges, p.ident)) {
      const now = linesWith(lines, p.ident);
      out.push(`${at}: \`${p.ident}\` is not on the first cited line of ${p.file}:${spell(p.ranges)}${now.length ? ` (it is on line ${now.join(', ')})` : ` (${p.file} no longer has it)`}`);
    }
  }
  return out;
}
