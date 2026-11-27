/* Phase 4, the admin page's look check (npm run build:fixture -> dist-fixture/): the real page on made-up accounts and
   tickets held in memory, without edge-bff. The code step takes 123456. Never part of dist/ (tests/bundle.test.mjs). */
import '../../../shared/focus-modality.ts';   // UD75: the focus ring follows the last input (no ring after a mouse or a touch)
import '../../src/styles/admin.css';
import { AdminError } from '../../src/api.ts';
import { start } from '../../src/app.ts';
import { ticketOf } from '../../src/model.ts';
import type { AdminApi, Ticket, TicketRow } from '../../src/types.ts';

const at = (hoursAgo: number) => new Date(Date.now() - hoursAgo * 3600e3).toISOString();
const PIXEL = 'data:image/svg+xml;utf8,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="320" height="200"><rect width="320" height="200" fill="#e8eaed"/><path d="M20 160l80-70 60 50 50-40 90 60" fill="none" stroke="#888" stroke-width="6"/></svg>');
let stepped = false;
const tickets: Ticket[] = [1, 2, 3].map(n => ({
  ticket_id: 40 + n, created_at: at(n * 5), site: 'beta', kind: n === 1 ? 'bug' : 'question',
  kind_label: n === 1 ? 'Bug / Something not working' : 'Question',
  subject: n === 1 ? 'The chart does not load after I switch to the weekly view' : `A question about plan limits ${n}`,
  body: 'I open the Terminal, choose a stock and switch the chart to weekly.\nThe chart stays empty.\n\nWhat should I do?',
  details: { page: '/terminal', viewport: '1440x900', timezone: 'Asia/Jakarta', language: 'en-US', browser: 'Chrome 153' },
  status: 'new', done_at: null, done_by: null, images: n === 1 ? 1 : 0, images_purged_at: null, images_due: null,
  files: n === 1 ? [{ position: 1, filename: 'screen.png', content_type: 'image/png', bytes: 182044 }] : [],
  telegram_sent_at: n === 2 ? null : at(n * 5), telegram_attempts: n === 2 ? 2 : 1,
  sender: { user_id: 7 + n, username: `member${n}`, email: `m***@fixture.example` } }));
const row = (t: Ticket): TicketRow => ({ ticket_id: t.ticket_id, created_at: t.created_at, site: t.site, kind: t.kind,
  kind_label: t.kind_label, subject: t.subject, images: t.images, status: t.status, done_at: t.done_at,
  telegram_sent_at: t.telegram_sent_at, images_purged_at: t.images_purged_at, username: t.sender.username, plan: 'free' });
const find = (id: number) => { const t = tickets.find(x => x.ticket_id === id); if (!t) throw new AdminError('NOT_FOUND', 'Not found.', 404); return t };

const fixture: AdminApi = {
  async stepState() { return { needed: !stepped, enrolled: true, available: true } },
  async stepUp(code) {
    if (code !== '123456') throw new AdminError('MFA_CODE_INVALID', 'That code is not right. Enter the current code from your authenticator app.', 400, ['code']);
    stepped = true;
  },
  async overview() {
    return { accounts: { by_status: { active: 12, pending: 2, disabled: 1 }, active_by_plan: { free: 9, paid: 3 }, test_accounts: 2 },
      sessions_live: 5, support: { new: tickets.filter(t => t.status === 'new').length, done: tickets.filter(t => t.status === 'done').length,
      unsent: 1, images_bytes: 182044 }, emails: { waiting: 0, failed_7d: 1 }, site: 'beta', commit: 'abc1234def00', support_storage_mb: 500 };
  },
  async users() {
    return { users: Array.from({ length: 6 }, (_, i) => ({ user_id: 20 - i, username: `member${i + 1}`, first_name: 'Member', last_name: `${i + 1}`,
      email: `m***@fixture.example`, phone: i % 2 ? '+62••••••••890' : null, role: 'user', status: i === 5 ? 'disabled' : 'active',
      test_account: i === 0, plan: i % 3 ? 'free' : 'paid', plan_ends: null, created_at: at(200 + i), last_sign_in_at: i === 4 ? null : at(i + 1) })), next: null };
  },
  async user(id) {
    return { account: { user_id: id, username: 'member1', first_name: 'Member', last_name: 'One', email: 'm***@fixture.example',
      phone: '+62••••••••890', role: 'user', status: 'active', test_account: true, plan: 'free', plan_ends: null, created_at: at(300),
      last_sign_in_at: at(2) }, email_verified_at: at(299), mfa: 'none',
      subscriptions: [], overrides: [], sessions: { live: 1, last_seen: at(1) },
      usage: { backtest_jobs: 3, screener_items: 2, watchlist_items: 10, terminal_layouts: 1, terminal_drawings: 0, support_tickets: 1 },
      audit: [{ audit_id: 3, at: at(30), action: 'account.test_mark', actor_user_id: 1, actor: 'owner', before: null, after: { test_account: true }, reason: 'Registration test window' }],
      holds_admin: false,
      actions: { status: { open: true, why: null }, plan: { open: true, why: null }, sessions: { open: true, why: null },
                 resend_code: { open: false, why: 'A code is sent from here only to an account still registering.' } } };
  },
  async reveal(_id, field) { return { field, value: field === 'email' ? 'member.one@fixture.example' : '+6281234567890' } },
  async setAccountStatus(_id, status) { return { status, changed: true, sessions_revoked: status === 'disabled' ? 1 : 0 } },
  async givePlan(_id, plan, expires_at) { return { plan, expires_at } },
  async endSessions() { return { revoked: 1 } },
  async sendCode() { return { sent: true } },
  async audit() {
    return { audit: [
      { audit_id: 5, at: at(1), action: 'support.status', actor_user_id: 1, actor: 'owner', target_user_id: 8, target: 'member1',
        before: { ticket_id: 41, status: 'new' }, after: { ticket_id: 41, status: 'done' }, reason: null },
      { audit_id: 4, at: at(4), action: 'account.reveal', actor_user_id: 1, actor: 'owner', target_user_id: 9, target: 'member2',
        before: null, after: { field: 'phone' }, reason: 'Asked for a call back about a payment' }], next: null };
  },
  async auditFile() { return new Blob(['audit_id,at\r\n'], { type: 'text/csv' }) },
  async plans() {
    return { plans: [{ plan_key: 'free', display_name: 'Free', is_default: true, for_guests: false, gives_admin: false },
                     { plan_key: 'paid', display_name: 'Paid', is_default: false, for_guests: false, gives_admin: false },
                     { plan_key: 'guest', display_name: 'Visitor', is_default: false, for_guests: true, gives_admin: false }],
      capabilities: [{ capability_key: 'terminal.view', kind: 'flag', unit: null, display_name: 'Terminal', means: null, value_min: null, value_max: null, item_pattern: null },
                     { capability_key: 'support.send', kind: 'flag', unit: null, display_name: 'Contact support', means: null, value_min: null, value_max: null, item_pattern: null },
                     { capability_key: 'backtest.runs_per_day', kind: 'limit', unit: 'runs', display_name: 'Backtest runs per day', means: null, value_min: 0, value_max: 1000, item_pattern: null }],
      values: [{ plan_key: 'free', capability_key: 'terminal.view', value: true, version: 1, updated_at: at(500) },
               { plan_key: 'paid', capability_key: 'terminal.view', value: true, version: 1, updated_at: at(500) },
               { plan_key: 'guest', capability_key: 'terminal.view', value: true, version: 1, updated_at: at(500) },
               { plan_key: 'free', capability_key: 'support.send', value: true, version: 1, updated_at: at(500) },
               { plan_key: 'paid', capability_key: 'support.send', value: true, version: 1, updated_at: at(500) },
               { plan_key: 'free', capability_key: 'backtest.runs_per_day', value: 5, version: 1, updated_at: at(500) },
               { plan_key: 'paid', capability_key: 'backtest.runs_per_day', value: 100, version: 1, updated_at: at(500) }] };
  },
  async settings() {
    return { settings: { site: 'beta', multiuser: false, environment: 'dev', email_mode: 'resend', support_per_hour: 5,
      support_per_day: 20, support_storage_mb: 500, session_seconds: 86400 }, telegram_summary: true };
  },
  async tickets(q) {
    const all = tickets.filter(t => q.status === 'all' || t.status === q.status).map(row);
    return { tickets: all, next: null };
  },
  async ticket(id) { return find(id) },
  imageUrl: () => PIXEL,
  async setStatus(id, status) {
    const t = find(id);
    t.status = status; t.done_at = status === 'done' ? new Date().toISOString() : null; t.done_by = status === 'done' ? 'owner' : null;
    t.images_due = status === 'done' && t.images ? new Date(Date.now() + 90 * 86400e3).toISOString() : null;
    return t;
  },
  async telegram(id) { const t = find(id); t.telegram_sent_at = new Date().toISOString(); return { sent: true } },
  async deleteTicket(id) { tickets.splice(tickets.indexOf(find(id)), 1) },
};

const dark = new URLSearchParams(location.search).get('theme') === 'dark';
document.documentElement.dataset.theme = dark ? 'dark' : 'light';
document.documentElement.classList.toggle('dark', dark);
void start(fixture, document.getElementById('page') as HTMLElement, { ticket: ticketOf(location.search) }).boot();
