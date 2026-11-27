/* UD71 (the user 2026-11-27: "Untuk nama perusahaan PT, tambah satu aturan tampilan saja"): the page's stock rows (the
   drill-down tables, the market map's tiles, the popovers, the search) read the company name through the shared display
   rule (shared/company-name.ts), so a source name "Pt …" shows as "PT …". */
import { describe, expect, it } from 'vitest';
import * as M from '../src/model.ts';
// @ts-ignore: a plain module of the tests
import { makeFiles } from './fixture/make.mjs';

describe('company names (UD71)', () => {
  it('a name the source writes "Pt …" shows as "PT …"; the others as they are', () => {
    const F = makeFiles(), meta = structuredClone(F.files['sector-meta']);
    const day = F.files[`sector-day-${meta.dates.at(-1)}`], src: string[] = meta.stocks.name;
    meta.stocks.name = src.map((n, i) => (i === 0 ? 'Pt Cipta Sarana Medika Tbk.' : n));
    const rows = M.makeData(meta, F.files['sector-series'], day).rows, at = (i: number) => rows.find(r => r.i === i)!;
    expect(at(0).n).toBe('PT Cipta Sarana Medika Tbk.');
    expect(rows.filter(r => r.i !== 0).every(r => r.n === src[r.i])).toBe(true);
  });
});
