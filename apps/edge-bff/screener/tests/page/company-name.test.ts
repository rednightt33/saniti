/* UD71 (the user 2026-11-27: "Untuk nama perusahaan PT, tambah satu aturan tampilan saja"): every row the page shows (the
   results table, its CSV, the preview's head and the Copy text) is a Row of src/state.ts, which reads the company name
   through the shared display rule (shared/company-name.ts): a source name "Pt …" shows as "PT …". The preview's ticker
   lookup reads the universe rows the same way (src/preview.ts). */
import { describe, expect, it } from 'vitest';
import { rowOfResult, rowOfUniverse } from '../../src/state.ts';

describe('company names (UD71)', () => {
  it('a universe row and a run row show "Pt …" as "PT …" and keep every other name', () => {
    const u = { ticker: 'AADI', name: 'Pt Adaro Andalan Indonesia Tbk', sector: 'Energy', industry: null, last: 1, chg_1d_pct: 0, adv20_idr: 1,
      remarks: [], stale: false, last_bar: '2026-11-26' } as any;
    expect(rowOfUniverse(u).name).toBe('PT Adaro Andalan Indonesia Tbk');
    expect(rowOfResult({ ...u, status: 'match', met: 1, need: 1, cells: [], last_bar_date: '2026-11-26' }).name).toBe('PT Adaro Andalan Indonesia Tbk');
    expect(rowOfUniverse({ ...u, name: 'Samudera Indonesia' }).name).toBe('Samudera Indonesia');
    expect(rowOfUniverse({ ...u, name: null }).name).toBeNull();
  });
});
