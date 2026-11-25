/* Re-check wf_c2fe2424-bf4/terminal:S-6 (both colour boxes offer the colours on the chart): a saved entry that still
   carries an old top-level style.color (from a saved list or a layout) had that colour offered although nothing draws
   it. The boxes now offer only the colours the indicators draw (src/data/drawnColors.ts). */
import { describe, expect, it } from 'vitest';
// @ts-expect-error: the Terminal's tsconfig has no Node types; vitest runs in Node
import { readFileSync } from 'node:fs';
import { drawnColors } from '../../src/data/drawnColors';

const all = { inst:true, part:() => true };
const STATES = ['#089981', '#8b5a2b', '#0070f3', '#d6409f'];
const part = (k: string, kind: string, o: Record<string, unknown> = {}) => ({ o:{ k, ...o }, kind });

describe('the colours an indicator draws', () => {
  it('leaves out an old top-level colour of a registry indicator, and outputs that are off or gone', () => {
    const inst = { def:{ multi:true }, parts:[part('ema', 'line')],
      style:{ color:'#abcdef', out:{ ema:{ on:true, color:'#171717', width:2 }, old_line:{ on:true, color:'#123456' } } } };
    expect(drawnColors(inst, all)).toEqual(['#171717']);                     // not #abcdef (saved list), not #123456 (no such output)
    const off = { ...inst, style:{ ...inst.style, out:{ ema:{ on:false, color:'#171717' } } } };
    expect(drawnColors(off, { inst:true, part:pt => off.style.out[pt.o.k].on })).toEqual([]);
    expect(drawnColors(inst, { inst:false, part:() => true })).toEqual([]);   // hidden by its eye, or folded: nothing drawn
  });

  it('takes the colours each kind of output draws', () => {
    const out = { h:{ on:true, color:'#0a0a0a', color2:'#b00000' }, q:{ on:true, color:'#111111', quad:['#a1', '#a2', '#a3', '#a4'] },
      p:{ on:true, color:'#222222' }, s:{ on:true, color:'#333333', color2:'#444444', states:true }, d:{ on:true, color:'#555555', color2:'#666666' },
      m:{ on:true, color:'#777777', color2:'#888888' } };
    const parts = [part('h', 'hist'), part('q', 'hist', { quad:['#q1', '#q2', '#q3', '#q4'] }), part('p', 'line', { palette:['#p1', '#p2'], paletteFrom:'idx' }),
      part('s', 'hist', { rule:'optional_state' }), part('d', 'dots'), part('m', 'marker')];
    const inst: any = { def:{ multi:true }, parts, style:{ out } };
    expect(drawnColors(inst, all, STATES)).toEqual(['#0a0a0a', '#b00000', '#a1', '#a2', '#a3', '#a4', '#p1', '#p2', ...STATES, '#333333', '#555555', '#777777']);
    inst.disp = { direction:[1, -1] };                                         // dots that follow a direction: both colours
    expect(drawnColors(inst, all, STATES).slice(-3)).toEqual(['#555555', '#666666', '#777777']);
  });

  it('takes a Flow indicator\'s lines per broker, or its one series (and its sell colour as bars)', () => {
    expect(drawnColors({ def:{ lines:true }, style:{ color:'#7928ca', width:2 }, lines:[{ color:'#171717' }, { color:'#f5a623' }] }, all)).toEqual(['#171717', '#f5a623']);
    expect(drawnColors({ def:{}, sType:'hist', style:{ color:'#089981', colorNeg:'#f23645' } }, all)).toEqual(['#089981', '#f23645']);
    expect(drawnColors({ def:{}, sType:'line', style:{ color:'#089981', colorNeg:'#f23645' } }, all)).toEqual(['#089981']);
  });

  it('is what both colour boxes read', () => {
    const src = readFileSync(new URL('../../src/app/indicators.ts', import.meta.url), 'utf8');
    expect(src).toMatch(/ctx\.indicatorColors = \(\) => list\.flatMap\(i => drawnColors\(i, \{ inst:drawn\(i\), part:pt => partShown\(i, pt\) \}, STATE_COLORS\)\);/);
    expect(src).toMatch(/const shown = pt => partShown\(inst, pt\);/);           // drawn by the same rule the colours are read by
    expect(readFileSync(new URL('../../src/app/assets.ts', import.meta.url), 'utf8')).toMatch(/ctx\.indicatorColors\?\.\(\)/);
  });
});
