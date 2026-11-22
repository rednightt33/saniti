/* Phase 4, the admin page: pure functions (the address's ticket, query strings, dates, sizes, what an audit row changed,
   how a plan value reads), the unit tests' target (tests/model.test.ts). Numbers in en-US digits (the design system's
   rule 7); dates in the viewer's own time, as "Sun 22 Nov 2026, 13:05". */
import type { Account, AuditRow } from './types.ts';

/** the page's views, in the order of its tabs; the Support inbox first (the Telegram summary links a ticket) */
export const VIEWS = ['support', 'overview', 'accounts', 'audit', 'plans', 'settings'] as const;
export type View = typeof VIEWS[number];
export const VIEW_LABEL: Record<View, string> = { support: 'Support', overview: 'Overview', accounts: 'Accounts',
  audit: 'Audit', plans: 'Plans', settings: 'Settings' };

/** ?ticket=<id> of the page's own address (the shell passes the one of /admin?ticket=<id>), or null */
export function ticketOf(search: string): number | null {
  const m = /(?:^\??|&)ticket=(\d{1,15})(?:&|$)/.exec(search || '');
  const n = m ? Number(m[1]) : NaN;
  return Number.isSafeInteger(n) && n > 0 ? n : null;
}

/** a query string of the values that are not empty, in their order; '' when none */
export function queryOf(q: Record<string, string | number | null | undefined>): string {
  const parts = Object.entries(q || {})
    .filter(([, v]) => v !== undefined && v !== null && String(v).trim() !== '')
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v).trim())}`);
  return parts.length ? `?${parts.join('&')}` : '';
}

const WD = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const two = (n: number) => String(n).padStart(2, '0');
const dateOf = (iso: string | null | undefined) => {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
};

/** "Sun 22 Nov 2026, 13:05" (a missing or unreadable time: "—") */
export function when(iso: string | null | undefined): string {
  const d = dateOf(iso);
  return d ? `${WD[d.getDay()]} ${d.getDate()} ${MON[d.getMonth()]} ${d.getFullYear()}, ${two(d.getHours())}:${two(d.getMinutes())}` : '—';
}

/** "Sun 22 Nov 2026" */
export function day(iso: string | null | undefined): string {
  const d = dateOf(iso);
  return d ? `${WD[d.getDay()]} ${d.getDate()} ${MON[d.getMonth()]} ${d.getFullYear()}` : '—';
}

/** "just now", "5 min ago", "3 h ago", "2 days ago"; past a week, the day */
export function ago(iso: string | null | undefined, now = Date.now()): string {
  const d = dateOf(iso);
  if (!d) return '—';
  const s = Math.max(0, Math.round((now - d.getTime()) / 1000));
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  if (s < 7 * 86400) { const n = Math.floor(s / 86400); return `${n} day${n === 1 ? '' : 's'} ago` }
  return day(iso);
}

/** "820 B", "12.4 KB", "1.2 MB" (steps of 1024, as the server's limits) */
export function bytes(n: number | null | undefined): string {
  if (typeof n !== 'number' || !Number.isFinite(n) || n < 0) return '—';
  if (n < 1024) return `${n} B`;
  const units = ['KB', 'MB', 'GB'];
  let v = n / 1024, i = 0;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++ }
  return `${v >= 100 ? Math.round(v) : v.toFixed(1)} ${units[i]}`;
}

/** a whole number with thousands commas: 12,345 */
export function count(n: number | null | undefined): string {
  return typeof n === 'number' && Number.isFinite(n) ? Math.round(n).toLocaleString('en-US') : '—';
}

/** 1 image, 2 images */
export const plural = (n: number, one: string, many = `${one}s`) => `${count(n)} ${n === 1 ? one : many}`;

/** an account's name from its first and last name, or '' */
export const fullName = (a: Pick<Account, 'first_name' | 'last_name'>) => [a.first_name, a.last_name].filter(Boolean).join(' ');

/** a stored value in one short line: true Yes, false No, {"all": true} All, {"ids": [...]} the ids (or None), a list its
    items, any other object its key: value pairs; every value shown as it is, never interpreted beyond these */
export function valueText(v: unknown): string {
  if (v === true) return 'Yes';
  if (v === false) return 'No';
  if (v === null || v === undefined) return '—';
  if (typeof v === 'number') return count(v);
  if (typeof v === 'string') return v;
  if (Array.isArray(v)) return v.length ? v.map(valueText).join(', ') : 'None';
  if (typeof v === 'object') {
    const o = v as Record<string, unknown>, keys = Object.keys(o);
    if (keys.length === 1 && o.all === true) return 'All';
    if (keys.length === 1 && Array.isArray(o.ids)) return o.ids.length ? o.ids.map(valueText).join(', ') : 'None';
    return keys.map(k => `${k}: ${valueText(o[k])}`).join(' · ');
  }
  return String(v);
}

/** what an audit row changed, from its before and after (ids, keys, kinds and status: the audit never holds a person's
    words). With only one of them (a reveal's after, a delete's before) its pairs as they are; with both, each key that
    changed as "key: old → new", one only after as "key: new", one only before as "key: old (gone)" */
export function changeOf(r: Pick<AuditRow, 'before' | 'after'>): string {
  const b = r.before && typeof r.before === 'object' && !Array.isArray(r.before) ? r.before as Record<string, unknown> : null;
  const a = r.after && typeof r.after === 'object' && !Array.isArray(r.after) ? r.after as Record<string, unknown> : null;
  if (!b && !a) return [r.before, r.after].filter(x => x !== null && x !== undefined).map(valueText).join(' → ');
  if (!a || !b) return Object.entries((a || b)!).map(([k, v]) => `${k}: ${valueText(v)}`).join(' · ');
  const keys = [...new Set([...Object.keys(b || {}), ...Object.keys(a || {})])];
  const out: string[] = [];
  for (const k of keys) {
    const inB = !!b && k in b, inA = !!a && k in a;
    if (inB && inA) out.push(JSON.stringify(b![k]) === JSON.stringify(a![k]) ? `${k}: ${valueText(a![k])}` : `${k}: ${valueText(b![k])} → ${valueText(a![k])}`);
    else if (inA) out.push(`${k}: ${valueText(a![k])}`);
    else out.push(`${k}: ${valueText(b![k])} (gone)`);
  }
  return out.join(' · ');
}

/** the actions a list of audit rows names, sorted, for the filter's suggestions (derived from the rows, never a list) */
export const actionsOf = (rows: Pick<AuditRow, 'action'>[]) => [...new Set(rows.map(r => r.action))].sort();

/** the audit file's name: edge-audit-2026-11-22.csv (the viewer's own day) */
export function fileName(now = new Date()): string {
  return `edge-audit-${now.getFullYear()}-${two(now.getMonth() + 1)}-${two(now.getDate())}.csv`;
}

/** a reason the server takes: 1 to 1000 characters once trimmed (app/admin.py reason_of; it checks the rest) */
export const REASON_CHARS = 1000;
export const reasonProblem = (text: string) => !text.trim() ? 'Write why. It is kept in the audit.'
  : text.trim().length > REASON_CHARS ? `Keep it to ${count(REASON_CHARS)} characters.` : '';

/** the 6-digit code as typed (spaces dropped), or '' while it is not six digits */
export const codeOf = (typed: string) => { const c = (typed || '').replace(/\s+/g, ''); return /^\d{6}$/.test(c) ? c : '' };
