/* Fixture mode (/terminal-app/?fixture=reference): the reference page's own synthetic data, generated with the same
   seeds and in the same order as 03-terminal-right-panel.html, so the TypeScript page can be compared with it pixel
   for pixel (FRONTEND_ARCHITECTURE.md section 4). Never used for live figures. */
import { BK_BASE, BK_BUMN, BK_FOREIGN, BROKSUM_PROFILE, CATALOG, INSTRUMENTS } from './fixtureConstants';
import type { Bar, BrokerRow, Combo, MarketData, MarketEvent, Point, VolumePoint } from './types';

export function makeRng(seed: number) {
  let t = seed >>> 0;
  return function() {
    t += 0x6D2B79F5;
    let r = Math.imul(t ^ t >>> 15, 1 | t);
    r ^= r + Math.imul(r ^ r >>> 7, 61 | r);
    return ((r ^ r >>> 14) >>> 0) / 4294967296;
  };
}
export const hashSeed = (str: string) => { let h = 2166136261; for(const ch of str) h = Math.imul(h ^ ch.charCodeAt(0), 16777619); return h >>> 0 };

export function fixtureData(stored: string | null): MarketData {
  const SYMBOL = INSTRUMENTS.some(i => i[0] === stored) ? stored as string : 'MAPI';
  const INSTRUMENT = INSTRUMENTS.find(i => i[0] === SYMBOL)!;

  const rng = makeRng(SYMBOL === 'MAPI' ? 7139 : hashSeed(SYMBOL));   // mock data: every ticker gets its own repeatable history
  const dates: string[] = [];
  const DAY = 864e5;
  for (let t = Date.UTC(2021, 0, 4); dates.length < 1280; t += DAY) {
    const d = new Date(t).getUTCDay();
    if (d !== 0 && d !== 6) dates.push(new Date(t).toISOString().slice(0, 10));
  }

  const ohlc: Bar[] = [];
  const lineData: Point[] = [];
  const volume: VolumePoint[] = [];
  let price = SYMBOL === 'MAPI' ? 1450 : INSTRUMENT[3] / 1.83;       // history ends near the ticker's last price
  const shocks: Record<number, number> = { 180: -.08, 350: .07, 620: -.06, 830: .11, 1010: -.075, 1120: .085 };
  for (let i = 0; i < dates.length; i++) {
    const q = i / (dates.length - 1);
    const drift = q < .28 ? .00035 : q < .55 ? .0008 : q < .72 ? -.00015 : .0011;
    const ret = drift + (rng() - .5) * .021 + (shocks[i] || 0);
    const open = price * (1 + (rng() - .5) * .008);
    const close = Math.max(200, open * (1 + ret));
    const high = Math.max(open, close) * (1 + .003 + rng() * .013);
    const low = Math.min(open, close) * (1 - .003 - rng() * .013);
    price = close;
    const round = (n: number) => +n.toFixed(1);
    ohlc.push({ time: dates[i], open: round(open), high: round(high), low: round(low), close: round(close) });
    lineData.push({ time: dates[i], value: round(close) });
    volume.push({
      time: dates[i],
      value: Math.round((4 + rng() * 7 + Math.abs(ret) * 180 + (q > .80 ? (q - .80) * 90 : 0)) * 1000000),
      color: close >= open ? 'rgba(0,150,109,.48)' : 'rgba(235,57,69,.48)'
    });
  }

  const rawSeries: Record<string, Point[]> = {};
  CATALOG.forEach((spec, index) => {
    const localRng = makeRng(9000 + index * 211);
    let value = spec.start;
    rawSeries[spec.id] = lineData.map((point, i) => {
      const mainRet = i === 0 ? 0 : (lineData[i].value / lineData[i - 1].value - 1);
      value = Math.max(8, value * (1 + mainRet * spec.beta + (localRng() - .5) * spec.noise + spec.bias));
      return { time: point.time, value: +value.toFixed(1) };
    });
  });

  return {
    mode: 'fixture', symbol: SYMBOL, instruments: INSTRUMENTS, ohlc, volume, lineData,
    catalog: CATALOG.map(({ id, symbol, name, color }) => ({ id, symbol, name, color })),
    loadCompare: id => Promise.resolve(rawSeries[id]), rawSeries,
    ihsg: rawSeries.ihsg,
    combos: synthesizeCombos(ohlc, volume), flowSource: 'synthetic', flowFrom: 0,
    broker: brokerFixture(),
    loadEvents: () => Promise.resolve(mockEvents(SYMBOL, dates, ohlc)),
    hide: { brokerGauge: false, bandar: false }
  };
}

/* Flow Timeline: daily series seeded from the real 2023-12-18 broker profile (the reference's synthesizeCombos) */
function synthesizeCombos(ohlc: Bar[], volume: VolumePoint[]): Combo[] {
  const N = ohlc.length;
  let sd = 20261022;
  const rnd = () => ((sd = Math.imul(sd,1664525)+1013904223>>>0)/4294967296);
  const combos: Combo[] = BROKSUM_PROFILE.map(([broker,investor,board,buy,sell]) => ({
    broker, investor, board, gross:buy+sell, tilt:(buy-sell)/Math.max(1,buy+sell), net:new Float64Array(N)
  }));
  // The real day has no Cash board — add small synthetic Cash flows for the biggest brokers so the filter is usable.
  const topB = [...new Set(combos.slice().sort((x,y)=>y.gross-x.gross).map(c=>c.broker))].slice(0,6);
  const totalGross = combos.reduce((s,c)=>s+c.gross,0);
  topB.forEach((br,k) => combos.push({broker:br, investor:k%2?'Domestic':'Foreign', board:'Cash', gross:totalGross*.004, tilt:(rnd()-.5)*.6, net:new Float64Array(N)}));
  const share = combos.map(c=>c.gross/totalGross);
  for(let i=0;i<N;i++){
    const bar = ohlc[i], V = volume[i].value*9200, ret = (bar.close-bar.open)/bar.open, tiltDay = Math.tanh(ret*18);
    const raw = new Float64Array(combos.length), w = new Float64Array(combos.length);
    let sumRaw=0, sumW=0;
    combos.forEach((c,j) => {
      const sparse = c.board==='Nego' ? (rnd()<.09 ? 3.2 : 0) : c.board==='Cash' ? (rnd()<.15 ? 1.5 : 0) : 1;
      const regime = Math.cos(i/(120+(j%7)*40)+j);            // slow accumulation / distribution waves
      const k = c.investor==='Foreign' ? 1 : -.6;
      w[j] = V*share[j]*sparse;
      raw[j] = w[j]*3*(.35*c.tilt*regime + .22*k*tiltDay + (rnd()-.5)*.9);
      sumRaw += raw[j]; sumW += w[j];
    });
    // a broker summary always clears: total buy = total sell, so every day's net sums to zero across all participants
    combos.forEach((c,j) => { c.net[i] = sumW ? raw[j]-sumRaw*w[j]/sumW : 0 });
  }
  return combos;
}

/* Broker activity: the last real day (BK_BASE) + 29 synthetic sessions before it */
function brokerFixture(): MarketData['broker'] {
  const BK_DAYS = 30;
  const bkDates = (() => {
    const out: string[] = []; const d = new Date(Date.UTC(2023,11,18));
    while(out.length < BK_DAYS){ if(d.getUTCDay()!==0 && d.getUTCDay()!==6) out.unshift(d.toISOString().slice(0,10)); d.setUTCDate(d.getUTCDate()-1) }
    return out;
  })();
  const hash01 = (s: string) => { let h = 2166136261; for(let i=0;i<s.length;i++){ h ^= s.charCodeAt(i); h = Math.imul(h,16777619) } return ((h>>>0)%100000)/100000 };
  const bkTilt = (b: string) => (hash01('t'+b) - .5) * 1.0;                    // each broker leans buy or sell
  const bkCache = new Map<number, BrokerRow[]>();
  const rows = (d: number): BrokerRow[] => {
    if(d === BK_DAYS-1) return BK_BASE;
    if(bkCache.has(d)) return bkCache.get(d)!;
    const out = BK_BASE.map(r => {
      const k = r[0]+r[1]+r[2]+'|'+d;
      const t = bkTilt(r[0]);
      const fb = Math.max(.1, .35 + 1.3*hash01('b'+k) + t*.6), fs = Math.max(.1, .35 + 1.3*hash01('s'+k) - t*.6);
      return [r[0], r[1], r[2], Math.round(r[3]*fb), Math.round(r[4]*fs), Math.round(r[5]*fb), Math.round(r[6]*fs)] as BrokerRow;
    });
    bkCache.set(d, out); return out;
  };
  const category = (b: string) => BK_FOREIGN.has(b) ? 'F' : BK_BUMN.has(b) ? 'B' : 'L';
  return { dates: bkDates, rows, label: 'BBCA', category };
}

/* Events: mock corporate actions per ticker, repeatable (the reference's mockEvents) */
function mockEvents(SYMBOL: string, dates: string[], ohlc: Bar[]): MarketEvent[] {
  const TYPE_IDS = ['dividend', 'stocksplit', 'reversesplit', 'rightissue', 'bonus', 'rups', 'tenderoffer', 'warrant'];
  const addDays = (d: string, n: number) => new Date(Date.parse(d) + n * 864e5).toISOString().slice(0, 10);
  const idr = (n: number) => 'Rp ' + Math.round(n).toLocaleString('en-US');
  const r = makeRng(hashSeed(SYMBOL) + 4242), n = dates.length, int = (a: number, b: number) => a + Math.floor(r() * (b - a + 1));
  const out: MarketEvent[] = [], at = () => r() < .5 ? int(n - 125, n - 6) : int(12, n - 6);      // about half fall inside the opening view
  const px = (i: number) => ohlc[i].close;
  const make = (type: string, i: number): MarketEvent => {
    const date = dates[i], c = px(i), id = `${SYMBOL}-${type}-${date}`;
    switch(type){
      case 'dividend': { const dps = Math.max(5, Math.round(c * (.008 + r() * .02) / 5) * 5);
        return { id, type, date, title:'Cash dividend', rows:[['Dividend', idr(dps) + ' / share'], ['Yield', (dps / c * 100).toFixed(2) + '%'], ['Cum date', addDays(date, -1)], ['Ex date', date], ['Payment', addDays(date, 14)]] } }
      case 'stocksplit': { const k = int(2, 5); return { id, type, date, title:`Stock split 1:${k}`, rows:[['Ratio', `1 : ${k}`], ['Effective', date], ['Price after', idr(c / k)]] } }
      case 'reversesplit': { const k = int(5, 10); return { id, type, date, title:`Reverse split ${k}:1`, rows:[['Ratio', `${k} : 1`], ['Effective', date], ['Price after', idr(c * k)]] } }
      case 'rightissue': { const k = int(3, 8); return { id, type, date, title:`Rights issue ${k}:1`, rows:[['Ratio', `${k} : 1`], ['Exercise price', idr(c * .72)], ['Cum date', addDays(date, -1)], ['Trading period', `${addDays(date, 4)} – ${addDays(date, 10)}`]] } }
      case 'bonus': { const k = int(5, 20); return { id, type, date, title:`Bonus shares 1:${k}`, rows:[['Ratio', `1 : ${k}`], ['Cum date', addDays(date, -1)], ['Distribution', addDays(date, 12)]] } }
      case 'rups': { const lb = r() < .4; return { id, type, date, title:lb ? 'RUPSLB (extraordinary)' : 'RUPST (annual)', rows:[['Meeting', date], ['Agenda', lb ? 'Capital & board' : 'Annual report'], ['Record date', addDays(date, -8)]] } }
      case 'tenderoffer': return { id, type, date, title:'Tender offer', rows:[['Offer price', idr(c * 1.18)], ['Premium', '+18.0%'], ['Period', `${date} – ${addDays(date, 30)}`]] };
      default: return { id, type:'warrant', date, title:'Warrant series I', rows:[['Exercise price', idr(c * .9)], ['Exercise period', `${date} – ${addDays(date, 180)}`], ['Expiry', addDays(date, 365)]] };
    }
  };
  for(let k = 0; k < 4; k++) out.push(make('dividend', Math.round((k + .3 + r() * .4) * (n - 18) / 4) + 12));
  out.push(make('dividend', int(n - 100, n - 40)));
  TYPE_IDS.slice(1).forEach(t => { const c = t === 'rups' ? 2 : (r() < .75 ? 1 : 0); for(let k = 0; k < c; k++) out.push(make(t, at())) });
  return out.filter(e => e.date >= dates[0]).sort((a, b) => a.date < b.date ? -1 : 1);
}
