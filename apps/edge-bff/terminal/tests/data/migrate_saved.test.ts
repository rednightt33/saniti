/* ERRORS M564: EMA lost its saved style on every load (and every timeframe switch): the migration of the pre-registry
   moving average took today's 'ema' (I02) for the old one. Reproduction (the re-check's ema.mjs): saved
   {"ema":{"on":true,"width":2,"color":"#171717"}} became {"ema":{"on":true}}, the legend read color:undefined. The form
   is now read from the entry's shape (src/data/migrateSaved.ts). */
import { describe, expect, it } from 'vitest';
// @ts-expect-error: the Terminal's tsconfig has no Node types; vitest runs in Node
import { readFileSync } from 'node:fs';
import { isPreRegistryMa, migrateSaved } from '../../src/data/migrateSaved';

const today = { def:'ema', on:true, params:{ length:20, source:'close' },
  style:{ out:{ ema:{ on:true, width:2, color:'#171717', opacity:80, lineStyle:'Dashed' } }, guides:{ on:false, levels:'' }, fill:{ on:false, opacity:10 }, opacity:100, offset:3 }, pid:'0123456789abcdef' };

describe('a saved moving average', () => {
  it('keeps today\'s EMA as saved: its colour, width, line style and offset', () => {
    expect(isPreRegistryMa(today)).toBe(false);
    expect(migrateSaved(today)).toBe(today);
    // an entry of today with a stale top-level colour (an older build's) is still today's form
    const stale = { ...today, style:{ ...today.style, color:'#abcdef' } };
    expect(migrateSaved(stale)).toBe(stale);
    // today's form without a style (a preset, a seeded list) is left alone too: nothing of the old form in it
    expect(migrateSaved({ def:'ema', params:{ length:9 } })).toEqual({ def:'ema', params:{ length:9 } });
    expect(migrateSaved({ def:'sma', style:{ color:'#f00' } })).toEqual({ def:'sma', style:{ color:'#f00' } });   // only the old MA's ids
  });

  it('still moves the pre-registry form to the registry entry of its type', () => {
    expect(migrateSaved({ def:'ma', on:false, params:{ type:'WMA', length:30, source:'High', offset:2 }, style:{ color:'#f23645', width:3 } }))
      .toEqual({ def:'wma', on:false, params:{ length:30, source:'high' }, style:{ out:{ wma:{ color:'#f23645', width:3 } }, offset:2 } });
    expect(migrateSaved({ def:'ema', on:true, params:{ length:50, source:'Close' }, style:{ color:'#0070f3', width:2 } }))
      .toEqual({ def:'ema', on:true, params:{ length:50, source:'close' }, style:{ out:{ ema:{ color:'#0070f3', width:2 } }, offset:0 } });
    // the old form's style without a width: the default width stays (no undefined over it)
    expect(migrateSaved({ def:'ema', params:{ type:'EMA', length:10 }, style:{ color:'#089981' } }))
      .toEqual({ def:'ema', on:undefined, params:{ length:10, source:'close' }, style:{ out:{ ema:{ color:'#089981' } }, offset:0 } });
    expect(migrateSaved({ def:'ma' })).toEqual({ def:'sma', on:undefined, params:{ length:undefined, source:'close' }, style:{ out:{ sma:{} }, offset:0 } });
  });

  it('is the migration the indicator list restores with', () => {
    const src = readFileSync(new URL('../../src/app/indicators.ts', import.meta.url), 'utf8');
    expect(src).toMatch(/const migrate = migrateSaved;/);
    expect(src).not.toMatch(/o\.def !== 'ma' && o\.def !== 'ema'/);
  });
});
