/* EXEC-TERMINAL-PANELS D1 (user 2026-10-26: "set melalui kalender satu ... opsi lagi adalah kita draw atau bikin range di
   main chart"): one calendar that picks a range (first click = start, second click = end). Only the days in `dates`
   (sessions with broker data) can be picked; the others are dimmed. The footer offers "Select on chart". */

export interface RangeCalendar { from: string; to: string }
export interface CalendarOptions {
  anchor: HTMLElement;
  dates: string[];                       // pickable days, 'YYYY-MM-DD', ascending
  from: string; to: string;              // the current range
  onPick: (from: string, to: string) => void;
  onChart?: () => void;                  // "Select on chart"
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const pad = (n: number) => String(n).padStart(2, '0');
export const ymd = (y: number, m: number, d: number) => `${y}-${pad(m + 1)}-${pad(d)}`;
export const longDay = (t: string) => new Date(t + 'T00:00:00Z')
  .toLocaleDateString('en-GB', { day:'2-digit', month:'short', year:'numeric', timeZone:'UTC' });

/** the weeks (Monday first) of one month: each cell is a 'YYYY-MM-DD' or '' outside the month */
export function monthGrid(y: number, m: number): string[][] {
  const first = (new Date(Date.UTC(y, m, 1)).getUTCDay() + 6) % 7, days = new Date(Date.UTC(y, m + 1, 0)).getUTCDate();
  const cells = [...Array(first).fill(''), ...Array.from({ length:days }, (_, i) => ymd(y, m, i + 1))];
  while (cells.length % 7) cells.push('');
  return Array.from({ length:cells.length / 7 }, (_, w) => cells.slice(w * 7, w * 7 + 7));
}

let open: { pop: HTMLElement; close: () => void } | null = null;

export function closeRangeCalendar() { open?.close() }

export function openRangeCalendar(o: CalendarOptions) {
  closeRangeCalendar();
  if (!o.dates.length) return;
  const have = new Set(o.dates), lo = o.dates[0], hi = o.dates[o.dates.length - 1];
  const loY = +lo.slice(0, 4), hiY = +hi.slice(0, 4);
  let y = +o.to.slice(0, 4), m = +o.to.slice(5, 7) - 1;
  let start: string | null = null, hover: string | null = null;
  const pop = document.createElement('div');
  pop.className = 'rc-pop'; pop.setAttribute('role', 'dialog'); pop.setAttribute('aria-label', 'Choose a period');
  document.body.appendChild(pop);

  const inMonthRange = (yy: number, mm: number) => ymd(yy, mm, 31) >= lo && ymd(yy, mm, 1) <= hi;
  function render() {
    const a = start ? (hover && hover < start ? hover : start) : o.from;
    const b = start ? (hover && hover > start ? hover : start) : o.to;
    const years = Array.from({ length:hiY - loY + 1 }, (_, i) => loY + i);
    pop.innerHTML = `
      <div class="rc-head">
        <button type="button" class="rc-nav" data-nav="-1" aria-label="Previous month" ${inMonthRange(m ? y : y - 1, (m + 11) % 12) ? '' : 'disabled'}>‹</button>
        <strong>${MONTHS[m]} ${y}</strong>
        <button type="button" class="rc-nav" data-nav="1" aria-label="Next month" ${inMonthRange(m === 11 ? y + 1 : y, (m + 1) % 12) ? '' : 'disabled'}>›</button>
      </div>
      <div class="rc-years" role="group" aria-label="Year">${years.map(v => `<button type="button" data-year="${v}" class="${v === y ? 'active' : ''}">${v}</button>`).join('')}</div>
      <div class="rc-grid" role="grid">
        ${['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su'].map(d => `<span class="rc-dow">${d}</span>`).join('')}
        ${monthGrid(y, m).flat().map(t => !t ? '<span></span>'
          : `<button type="button" data-day="${t}" class="rc-day${t >= a && t <= b ? ' in' : ''}${t === a || t === b ? ' edge' : ''}" ${have.has(t) ? '' : 'disabled'}>${+t.slice(8)}</button>`).join('')}
      </div>
      <div class="rc-foot">
        <span class="rc-note">${start ? `From ${longDay(start)} · pick the last day` : o.from === o.to ? longDay(o.from) : `${longDay(o.from)} – ${longDay(o.to)}`}</span>
        ${o.onChart ? '<button type="button" class="rc-chart" data-chart="1">Select on chart</button>' : ''}
      </div>`;
  }
  function place() {
    const r = o.anchor.getBoundingClientRect(), w = pop.offsetWidth, h = pop.offsetHeight;
    pop.style.left = Math.max(8, Math.min(innerWidth - w - 8, r.right - w)) + 'px';
    pop.style.top = (r.bottom + 6 + h > innerHeight - 8 ? Math.max(8, r.top - h - 6) : r.bottom + 6) + 'px';
  }
  pop.addEventListener('click', (e: any) => {
    e.stopPropagation();
    const nav = e.target.closest('[data-nav]'), yr = e.target.closest('[data-year]'), day = e.target.closest('[data-day]');
    if (nav) { m += +nav.dataset.nav; if (m < 0) { m = 11; y-- } if (m > 11) { m = 0; y++ } }
    else if (yr) {
      y = +yr.dataset.year;
      if (ymd(y, m, 31) < lo) m = +lo.slice(5, 7) - 1;                 // stay inside the data
      if (ymd(y, m, 1) > hi) m = +hi.slice(5, 7) - 1;
    } else if (day) {
      const t = day.dataset.day;
      if (!start) start = t;
      else { const [f, g] = t < start ? [t, start] : [start, t]; close(); o.onPick(f, g); return }
    } else if (e.target.closest('[data-chart]')) { close(); o.onChart!(); return }
    else return;
    render(); place();
  });
  pop.addEventListener('pointerover', (e: any) => {
    const day = e.target.closest('[data-day]:not([disabled])');
    if (start && day && day.dataset.day !== hover) { hover = day.dataset.day; render() }
  });
  const outside = (e: Event) => { if (!pop.contains(e.target as Node) && !o.anchor.contains(e.target as Node)) close() };
  const key = (e: KeyboardEvent) => { if (e.key === 'Escape') { close(); o.anchor.focus() } };
  function close() {
    pop.remove(); document.removeEventListener('pointerdown', outside, true); document.removeEventListener('keydown', key);
    removeEventListener('resize', place); if (open?.pop === pop) open = null;
  }
  document.addEventListener('pointerdown', outside, true); document.addEventListener('keydown', key);
  addEventListener('resize', place);
  open = { pop, close };
  render(); place();
  return close;
}
