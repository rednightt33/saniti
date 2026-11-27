/* The two shared display rules of the 2026-11-27 round (EXEC.md EXEC-DESIGN-SYSTEM): a company name "Pt …" shown as
   "PT …" (UD71, shared/company-name.ts) and the kind of the last input written on <html> for the focus ring (UD75,
   shared/focus-modality.ts). The pages' own use of them: each page's model test, tests/test_company_name.py and
   tests/test_focus_ring.py; the browser check: verification/edge_states/round2_focus_contrast.mjs. */
import { describe, expect, it } from 'vitest';
import { companyName } from '../../shared/company-name.ts';
import { keyModality, trackFocusModality } from '../../shared/focus-modality.ts';
import * as M from '../src/model.ts';
import type { Day, Meta } from '../src/types.ts';

describe('companyName (UD71: "tambah satu aturan tampilan saja")', () => {
  it('shows the three names of IDX_Stock_Universe that start "Pt " as "PT "', () => {
    expect(companyName('Pt Adaro Andalan Indonesia Tbk')).toBe('PT Adaro Andalan Indonesia Tbk');
    expect(companyName('Pt Cipta Sarana Medika Tbk.')).toBe('PT Cipta Sarana Medika Tbk.');
    expect(companyName('Pt Yupi Indo Jelly Gum Tbk')).toBe('PT Yupi Indo Jelly Gum Tbk');
  });
  it('leaves every other name as it is', () => {
    for (const n of ['PT Bank Central Asia Tbk', 'Bank Central Asia Tbk', 'Ptba Tbk', 'Pt', 'pt Kecil Tbk', ' Pt Spasi Tbk', 'Samudera Indonesia', ''])
      expect(companyName(n)).toBe(n);
    expect(companyName(null)).toBeNull();
    expect(companyName(undefined)).toBeUndefined();
  });
  it('the Overview reads every name of its rows through it', () => {
    const meta = { stocks: { ticker: ['AADI', 'BBCA'], name: ['Pt Adaro Andalan Indonesia Tbk', 'PT Bank Central Asia Tbk'], sector: ['Energy', 'Financials'] },
      sectors: [], lists: [] } as unknown as Meta;
    const day = { stocks: { i: [0, 1], close: [1, 2], size: [1, 1], r1d: [0, 0], r5d: [0, 0], r1m: [0, 0], fnet_1d: [0, 0], fnet_5d: [0, 0], fnet_1m: [0, 0], fnet_3m: [0, 0], above_ema50: [1, 1], above_ema200: [1, 1] } } as unknown as Day;
    expect(M.rows(meta, day).map(r => r.name)).toEqual(['PT Adaro Andalan Indonesia Tbk', 'PT Bank Central Asia Tbk']);
  });
});

/** a window with what trackFocusModality uses: the root's dataset and the listeners */
function fakeWindow() {
  const on: Record<string, ((e: any) => void)[]> = {}, dataset: Record<string, string> = {};
  const win = { document: { documentElement: { dataset } }, addEventListener: (t: string, f: any, capture: boolean) => { expect(capture).toBe(true); (on[t] ||= []).push(f) },
    removeEventListener: (t: string, f: any) => { on[t] = (on[t] || []).filter(x => x !== f) } };
  return { win: win as unknown as Window, dataset, fire: (t: string, e: any = {}) => (on[t] || []).forEach(f => f(e)), on };
}
describe('trackFocusModality (UD75: no ring after a mouse or a touch, a grey ring after the keyboard)', () => {
  it('writes the kind of the last input on <html>, in the capture phase', () => {
    const { win, dataset, fire } = fakeWindow();
    trackFocusModality(win);
    expect(dataset.modality).toBeUndefined();                  // before any input the browser's own guess stands
    fire('pointerdown'); expect(dataset.modality).toBe('pointer');
    fire('keydown', { key: 'Tab' }); expect(dataset.modality).toBe('keyboard');
    fire('pointerdown'); expect(dataset.modality).toBe('pointer');
  });
  it('a shortcut with Ctrl, Alt or Meta is not a move of the focus', () => {
    const { win, dataset, fire } = fakeWindow();
    trackFocusModality(win);
    fire('pointerdown');
    for (const m of [{ ctrlKey: true }, { altKey: true }, { metaKey: true }]) { fire('keydown', m); expect(dataset.modality).toBe('pointer') }
    fire('keydown', { shiftKey: true }); expect(dataset.modality).toBe('keyboard');   // Shift+Tab moves the focus back
    expect(keyModality({ ctrlKey: false, altKey: false, metaKey: false })).toBe('keyboard');
    expect(keyModality({ ctrlKey: true, altKey: false, metaKey: false })).toBeNull();
  });
  it('stops when asked', () => {
    const { win, dataset, fire, on } = fakeWindow();
    const stop = trackFocusModality(win);
    stop();
    expect(on.pointerdown).toEqual([]); expect(on.keydown).toEqual([]);
    fire('pointerdown'); expect(dataset.modality).toBeUndefined();
  });
});
