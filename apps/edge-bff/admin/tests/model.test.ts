/* Phase 4, the admin page: its pure functions (src/model.ts). */
import { describe, expect, it } from 'vitest';
import { actionsOf, ago, bytes, changeOf, codeOf, count, day, endOf, fileName, nameOf, plural, queryOf, reasonProblem, ticketOf,
         usageOf, valueText, VIEWS, when } from '../src/model.ts';

describe('the ticket of the address', () => {
  it('reads ?ticket=<id> alone or among other parameters, and nothing else', () => {
    expect(ticketOf('?ticket=12')).toBe(12);
    expect(ticketOf('?x=1&ticket=7')).toBe(7);
    expect(ticketOf('ticket=3')).toBe(3);
    for (const s of ['', '?ticket=', '?ticket=12abc', '?ticket=-1', '?ticket=0', '?tickets=4', '?xticket=5', '?ticket=1e3',
                     '?ticket=1234567890123456'])
      expect(ticketOf(s), s).toBeNull();
  });
});

describe('query strings', () => {
  it('keep the filled values in their order and encode them', () => {
    expect(queryOf({ q: ' a b ', status: '', plan: 'free', before: undefined as unknown as string })).toBe('?q=a%20b&plan=free');
    expect(queryOf({ a: '', b: '  ' })).toBe('');
    expect(queryOf({ since: '2026-11-21T17:00:00.000Z' })).toBe('?since=2026-11-21T17%3A00%3A00.000Z');
  });
});

describe('dates, sizes and counts', () => {
  const at = new Date(2026, 10, 22, 13, 5).toISOString();     // Sun 22 Nov 2026, 13:05 in the viewer's own time
  it('read as the design system writes them', () => {
    expect(when(at)).toBe('Sun 22 Nov 2026, 13:05');
    expect(day(at)).toBe('Sun 22 Nov 2026');
    expect(when(null)).toBe('—');
    expect(when('not a date')).toBe('—');
    const now = new Date(2026, 10, 22, 13, 5).getTime();
    expect(ago(at, now)).toBe('just now');
    expect(ago(new Date(now - 5 * 60e3).toISOString(), now)).toBe('5 min ago');
    expect(ago(new Date(now - 3 * 3600e3).toISOString(), now)).toBe('3 h ago');
    expect(ago(new Date(now - 86400e3).toISOString(), now)).toBe('1 day ago');
    expect(ago(new Date(now - 2 * 86400e3).toISOString(), now)).toBe('2 days ago');
    expect(ago(new Date(2026, 9, 1, 9).toISOString(), now)).toBe('Thu 1 Oct 2026');
    expect(bytes(820)).toBe('820 B');
    expect(bytes(12.4 * 1024)).toBe('12.4 KB');
    expect(bytes(1.25 * 1024 * 1024)).toBe('1.3 MB');
    expect(bytes(500 * 1024 * 1024)).toBe('500 MB');
    expect(bytes(-1)).toBe('—');
    expect(count(12345)).toBe('12,345');
    expect(plural(1, 'image')).toBe('1 image');
    expect(plural(3, 'try', 'tries')).toBe('3 tries');
    expect(fileName(new Date(2026, 10, 2))).toBe('edge-audit-2026-11-02.csv');
  });
});

describe('a stored value and an audit change in one line', () => {
  it('shows the value as it is', () => {
    expect(valueText(true)).toBe('Yes');
    expect(valueText(false)).toBe('No');
    expect(valueText(25)).toBe('25');
    expect(valueText({ all: true })).toBe('All');
    expect(valueText({ ids: ['price', 'rsi'] })).toBe('price, rsi');
    expect(valueText({ ids: [] })).toBe('None');
    expect(valueText({ stages: ['released'] })).toBe('stages: released');
    expect(valueText(null)).toBe('—');
  });
  it('names each key that changed, and what came or went', () => {
    expect(changeOf({ before: { ticket_id: 4, status: 'new' }, after: { ticket_id: 4, status: 'done' } }))
      .toBe('ticket_id: 4 · status: new → done');
    expect(changeOf({ before: null, after: { field: 'phone' } })).toBe('field: phone');
    expect(changeOf({ before: { ticket_id: 9, kind: 'bug', images: 1 }, after: null })).toBe('ticket_id: 9 · kind: bug · images: 1');
    expect(changeOf({ before: { a: 1 }, after: { b: 2 } })).toBe('a: 1 (gone) · b: 2');
    expect(changeOf({ before: null, after: null })).toBe('');
  });
  it('derives the actions to suggest from the rows', () => {
    expect(actionsOf([{ action: 'support.status' }, { action: 'account.reveal' }, { action: 'support.status' }]))
      .toEqual(['account.reveal', 'support.status']);
  });
});

describe('what the person types', () => {
  it('a code is six digits, spaces dropped', () => {
    expect(codeOf('123 456')).toBe('123456');
    expect(codeOf(' 012345 ')).toBe('012345');
    for (const s of ['12345', '1234567', 'abcdef', '12-456', '']) expect(codeOf(s), s).toBe('');
  });
  it('a reason is 1 to 1000 characters once trimmed', () => {
    expect(reasonProblem('  ')).toMatch(/Write why/);
    expect(reasonProblem('x'.repeat(1001))).toMatch(/1,000 characters/);
    expect(reasonProblem('She asked for it')).toBe('');
  });
  it('a plan ends at the last moment of its day, in the viewer\'s own time; empty is no end', () => {
    const end = endOf('2026-12-31');
    expect(end).toBe(new Date(2026, 11, 31, 23, 59, 59).toISOString());
    expect(end?.endsWith('Z')).toBe(true);
    for (const s of ['', '31/12/2026', '2026-12-31T00:00', 'tomorrow']) expect(endOf(s), s).toBeNull();
  });
  it('opens on the Support inbox first', () => {
    expect(VIEWS[0]).toBe('support');
  });
});

describe('the name an account is shown by', () => {
  it('is the username, else the name a registration asked for, else the number; never null', () => {
    expect(nameOf({ user_id: 3, username: 'alice', requested_username: null })).toBe('alice');
    expect(nameOf({ user_id: 4, username: null, requested_username: 'pat' })).toBe('pat (registering)');
    expect(nameOf({ user_id: 5, username: null, requested_username: null })).toBe('account #5');
    expect(nameOf({ user_id: 6, username: null })).toBe('account #6');
  });
});

describe('an account\'s usage counters (the Accounts list, CONTRACT 10)', () => {
  it('total every kind the server sends and name the non-zero ones, singular or plural', () => {
    expect(usageOf({ backtest_jobs: 3, screener_items: 0, support_tickets: 1, watchlist_items: 1200 }))
      .toEqual({ total: 1204, text: '3 backtest jobs · 1 support ticket · 1,200 watchlist items' });
    expect(usageOf({ backtest_jobs: 0 })).toEqual({ total: 0, text: 'Nothing saved yet' });
    expect(usageOf(undefined)).toEqual({ total: 0, text: 'Nothing saved yet' });
    // a kind the page does not know yet is shown by its own name (derived from the server's keys)
    expect(usageOf({ alerts: 2 })).toEqual({ total: 2, text: '2 alerts' });
  });
});
