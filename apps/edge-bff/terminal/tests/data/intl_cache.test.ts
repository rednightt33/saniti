// EXEC-TERMINAL-LAG-2 U4 (user 2026-11-22: "U1 + U2 + U4 go"): one Intl formatter per locale and options, made once
// (src/data/intlCache.ts). The text must stay what toLocaleString / toLocaleDateString gave, and no formatting path may go
// back to making a formatter per call (the class behind ERRORS M538's longDay and the price axis's priceText).
import { describe, expect, it } from 'vitest';
import { dateFormat, numberFormat } from '../../src/data/intlCache';

const RAW = import.meta.glob('../../src/**/*.ts', { query: '?raw', import: 'default', eager: true }) as Record<string, string>;
const SOURCES = Object.entries(RAW).map(([path, text]) => ({ path: path.replace('../../src/', ''), text }));

/** the argument texts of every call of `name(` in the sources (balanced parentheses, strings skipped) */
function callArgs(name: string): string[] {
  const out: string[] = [];
  for (const { path, text } of SOURCES) {
    if (path.endsWith('intlCache.ts')) continue;
    const re = new RegExp(`\\b${name}\\(`, 'g'); let m: RegExpExecArray | null;
    while ((m = re.exec(text))) {
      let i = m.index + m[0].length, d = 1, q = '';
      const start = i;
      for (; i < text.length && d; i++) {
        const c = text[i];
        if (q) { if (c === q && text[i - 1] !== '\\') q = ''; continue }
        if (c === '\'' || c === '"' || c === '`') q = c; else if (c === '(') d++; else if (c === ')') d--;
      }
      out.push(text.slice(start, i - 1));
    }
  }
  return out;
}
/** the arguments that are plain literals (a call whose options use a variable, as `minimumFractionDigits:d`, is skipped) */
const literal = (args: string): unknown[] | null => { try { return new Function(`return [${args}]`)() } catch { return null } };

const DATES = ['2026-09-01', '2026-11-22', '2025-12-31', '2026-01-02', '2024-02-29'].map(d => new Date(d + 'T00:00:00Z'));
const NUMBERS = [0, -0.5, 1.005, 7123.456, -48210.4, 1234567.891, 0.0042, 1e12, -3.2e9, 99.995];

describe('the cached formatters give the text of toLocale*', () => {
  it('every literal date format in src/ formats as toLocaleDateString', () => {
    const sets = callArgs('dateFormat').map(literal).filter((a): a is unknown[] => !!a);
    expect(sets.length).toBeGreaterThanOrEqual(10);          // the scan found the Terminal's date formats
    for (const [loc, opts] of sets as [string, Intl.DateTimeFormatOptions][])
      for (const d of DATES) expect(dateFormat(loc, opts).format(d)).toBe(d.toLocaleDateString(loc, opts));
  });
  it('every literal number format in src/ formats as toLocaleString', () => {
    const sets = callArgs('numberFormat').map(literal).filter((a): a is unknown[] => !!a);
    expect(sets.length).toBeGreaterThanOrEqual(3);
    for (const [loc, opts] of sets as [string, Intl.NumberFormatOptions][])
      for (const v of NUMBERS) expect(numberFormat(loc, opts).format(v)).toBe(v.toLocaleString(loc, opts));
  });
  it('a date format without a day, month or year part gets the defaults of toLocaleDateString', () => {
    const d = DATES[1];
    expect(dateFormat('en-GB', { timeZone: 'UTC' }).format(d)).toBe(d.toLocaleDateString('en-GB', { timeZone: 'UTC' }));
    expect(dateFormat('en-US').format(d)).toBe(d.toLocaleDateString('en-US'));
  });
  it('the price decimals of the axis (variable options) format as before', () => {
    for (const dp of [0, 2, 3]) for (const v of NUMBERS)
      expect(numberFormat('en-US', { minimumFractionDigits: dp, maximumFractionDigits: dp }).format(v))
        .toBe(v.toLocaleString('en-US', { minimumFractionDigits: dp, maximumFractionDigits: dp }));
  });
  it('one formatter per locale and options, made once', () => {
    expect(numberFormat('en-US', { maximumFractionDigits: 1 })).toBe(numberFormat('en-US', { maximumFractionDigits: 1 }));
    expect(dateFormat('en-GB', { month: 'short' })).toBe(dateFormat('en-GB', { month: 'short' }));
    expect(numberFormat('en-US', { maximumFractionDigits: 1 })).not.toBe(numberFormat('en-US', { maximumFractionDigits: 2 }));
  });
});

describe('no formatting path makes a formatter per call', () => {
  it('src/ has no toLocale*() call and no Intl formatter made inside a function', () => {
    const bad: string[] = [];
    for (const { path, text } of SOURCES) {
      if (path.endsWith('intlCache.ts')) continue;
      text.split('\n').forEach((line, i) => {
        if (/\.toLocale(Date|Time)?String\(/.test(line)) bad.push(`${path}:${i + 1} toLocale*(): use numberFormat/dateFormat`);
        // a module-level constant is made once; any other `new Intl.` runs per call
        if (/new Intl\.\w+\(/.test(line) && !/^(export )?const \w+ = new Intl\.\w+\(/.test(line)) bad.push(`${path}:${i + 1} new Intl inside a function: use numberFormat/dateFormat`);
      });
    }
    expect(bad).toEqual([]);
  });
});
