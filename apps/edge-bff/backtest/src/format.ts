/* Formatting, colours and small DOM helpers of the reference page (backtest.html app script, the lines before
   section 1). Numbers are shown in Indonesian format: 1.236 · 0,15% · Rp 4,57 M (miliar) · Rp 100,0 jt (juta). */

export const $ = (id: string): any => document.getElementById(id);
export const esc = (s: unknown) => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
export const css = (v: string) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();

/* market colours come from CSS tokens (--up / --dn / --navy) so charts and text always match, in both themes */
export const PAL: Record<string, string> = {};
const hexRgb = (h: string) => { const x = h.replace('#',''); return [0,2,4].map(k=>parseInt(x.slice(k,k+2),16)).join(',') };
export const setPal = () => { PAL.up = css('--up'); PAL.dn = css('--dn'); PAL.navy = css('--navy-c'); PAL.bm = css('--bench'); PAL.upRgb = hexRgb(PAL.up); PAL.dnRgb = hexRgb(PAL.dn); PAL.navyRgb = hexRgb(PAL.navy) };

let toastTimer: ReturnType<typeof setTimeout> | undefined;
/** the reference's toast; line: as wide as its text up to the window (backtest.css .toast.line), for the preview's
    one-line warnings and for every text the page did not write (toastError) */
export const toast = (m: string, line = false) => { const t=$('toast'); t.textContent=m; t.classList.toggle('line', line); t.hidden=false; clearTimeout(toastTimer); toastTimer=setTimeout(()=>t.hidden=true,2200) };
/** a message the page did not write (the server's error, a network failure): any length, so it takes the window's
    width instead of the reference's half (review PG-6). The page's own toasts keep the reference's look. */
export const toastError = (m: string) => toast(m, true);

// Display numbers in Indonesian format: 1.236 · 0,15% · Rp 4,57 M (miliar) · Rp 100,0 jt (juta)
export const nf = (v: number, d=0) => (+v).toLocaleString('id-ID',{minimumFractionDigits:d,maximumFractionDigits:d});
export const pct = (v: number | null | undefined, d=1) => v==null||!isFinite(v) ? '—' : (v>=0?'+':'')+nf(v*100,d)+'%';
export const pctu = (v: number | null | undefined, d=1) => v==null||!isFinite(v) ? '—' : nf(v*100,d)+'%';
export const num = (v: number | null | undefined, d=2) => v==null||!isFinite(v) ? '—' : nf(v,d);
export const rp = (v: number) => { const a=Math.abs(v); const s = a>=1e12?nf(a/1e12,2)+' T':a>=1e9?nf(a/1e9,2)+' M':a>=1e6?nf(a/1e6,1)+' jt':nf(Math.round(a),0); return (v<0?'-':'')+'Rp '+s };
export const MONTHS = ['January','February','March','April','May','June','July','August','September','October','November','December'];
export const fmtD = (iso: string | null | undefined) => { if(!iso) return '—'; const [y,m,d] = iso.split('-'); return d ? `${d} ${MONTHS[+m-1]} ${y}` : `${MONTHS[+m-1]} ${y}` };
// one place decides number grouping for typed amounts (Indonesian: 100.000.000)
export const NUM_LOCALE = 'id-ID';
export const fmtMoney = (v: unknown) => Math.round(+(v as number)||0).toLocaleString(NUM_LOCALE);
export const parseMoney = (t: unknown) => +String(t).replace(/[^\d]/g,'') || 0;
export const CMP_COLORS = ['#b7791f','#7c3aed'];
export const cls = (v: number) => v>=0 ? 'up' : 'down';

/* the condition colours; the reference fixes them once at start (PAL.up of the theme the page opened in) */
export const COLORS: string[] = [];
export const initColors = () => { COLORS.splice(0, COLORS.length, '#0070f3','#7928ca','#f5a623',PAL.up,'#e5484d','#0ea5e9','#a16207','#db2777') };

export const ico = (d: string) => `<svg class="ico" viewBox="0 0 24 24">${d}</svg>`;
export const OPS: Record<string, string> = {gt:'>',lt:'<',ca:'crosses above',cb:'crosses below'};
