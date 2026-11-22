/* Phase 4, the admin page of the beta (CONTRACT.md 10; app/admin.py; the user, 2026-11-22: "1A, 2B, 3A").
   - First the code step (1A): the 6-digit code of the authenticator the admin uses on the live site, once per session;
     the screen says so when that authenticator is not set up yet or the site cannot check it.
   - Then six views, the Support inbox first (the Telegram summary links /admin?ticket=<id>): a ticket in full with its
     images, marked done (its images are deleted 90 days later, 2B) or new, its Telegram summary again, deleted by hand
     with a reason; the overview; the accounts (address and phone masked, a reveal asks why and is audited); the audit and
     its file; the plans (read-only); the settings that are no secret.
   Every text a person wrote (a subject, a description, a name) is set as text, never as markup. A refusal shows the
   server's words, each field's reason under that field. */
import { AdminError } from './api.ts';
import { actionsOf as auditActions, ago, bytes, changeOf, codeOf, count, day, endOf, fileName, fullName, plural, reasonProblem,
         REASON_CHARS, valueText, VIEW_LABEL, VIEWS, when, type View } from './model.ts';
import type { Account, AccountDetail, AdminApi, AuditRow, Overview, Plans, StepState, Ticket, TicketRow } from './types.ts';

type Child = Node | string | number | null | undefined | false;
type Attrs = Record<string, unknown>;

/** an element: attributes as they are (class, aria-*, data-*, on<event> handlers), children as nodes or text */
function h<K extends keyof HTMLElementTagNameMap>(tag: K, attrs: Attrs = {}, ...children: Child[]): HTMLElementTagNameMap[K] {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === undefined || v === null || v === false) continue;
    if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2).toLowerCase(), v as EventListener);
    else if (k === 'class') el.className = String(v);
    else if (v === true) el.setAttribute(k, '');
    else el.setAttribute(k, String(v));
  }
  for (const c of children) if (c !== null && c !== undefined && c !== false) el.append(c instanceof Node ? c : String(c));
  return el;
}
function icon(name: string, small = true) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('class', small ? 'ic ic-sm' : 'ic');
  svg.setAttribute('aria-hidden', 'true');
  const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
  use.setAttribute('href', `#i-${name}`);
  svg.append(use);
  return svg;
}
/** an element's children replaced by these, leaving out what is not there (null, undefined, false) */
function put(el: Element, ...children: Child[]) {
  el.replaceChildren(...children.filter(c => c !== null && c !== undefined && c !== false).map(c => c instanceof Node ? c : String(c)));
}
const kv = (label: string, ...value: Child[]) => h('div', { class: 'kv' }, h('span', {}, label), h('b', {}, ...value));
/** a table in its scroll box; each header cell takes its column's alignment and phone rule from the first row's cell
    (l: left, num: right, hide-sm: hidden on a phone), so a header always sits over its values */
function table(head: string[], rows: HTMLTableRowElement[], cls = '') {
  const first = rows[0] ? [...rows[0].cells] : [];
  const ths = head.map((t, i) => h('th', { class: (first[i]?.className || '').split(/\s+/).filter(c => ['l', 'num', 'hide-sm'].includes(c)).join(' ') || null }, t));
  return h('div', { class: 'tbl-wrap' }, h('table', { class: `tbl ${cls}` }, h('thead', {}, h('tr', {}, ...ths)), h('tbody', {}, ...rows)));
}

export function start(api: AdminApi, root: HTMLElement, opts: { ticket: number | null }) {
  const state = {
    step: null as StepState | null,
    overview: null as Overview | null,
    view: 'support' as View,
    ticket: opts.ticket as number | null,           // the ticket open in the Support view, or null: the list
    account: null as number | null,                 // the account open in the Accounts view, or null: the list
    support: 'new' as 'new' | 'done' | 'all',
    accounts: { q: '', status: '', plan: '' },
    audit: { action: '', since: '', until: '' },
    plans: null as Plans | null,
  };
  const toastEl = document.getElementById('toast');
  let toastTimer = 0;
  function toast(text: string) {
    if (!toastEl) return;
    toastEl.textContent = text;
    toastEl.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => { toastEl.hidden = true }, 7000);
  }

  /** a refusal anywhere: the session ended or the step is needed again (another session renewed it, a deploy), the
      screen that says so; any other, the server's words where the action was */
  function failed(e: unknown, where?: HTMLElement) {
    const err = e instanceof AdminError ? e : new AdminError('FAILED', 'EDGE could not do this. Try again in a minute.', 0);
    if (err.code === 'MFA_REQUIRED' && err.details.step_up === true) { state.step = { needed: true, enrolled: true, available: true }; render(); return }
    if (where) { put(where, notice(err.message)); return }
    toast(err.message);
  }
  const notice = (text: string, retry?: () => void) => h('div', { class: 'empty', role: 'alert' }, h('strong', {}, text),
    retry ? h('div', { class: 'row center' }, h('button', { class: 'btn sm', type: 'button', onclick: retry }, icon('refresh'), 'Try again')) : null);
  const loading = () => h('p', { class: 'muted loading' }, 'Loading…');

  // ---- the frame of the page ------------------------------------------------------------------------------------------
  const header = () => h('header', { class: 'head' },
    h('div', {}, h('h1', {}, 'Admin'), h('p', {}, 'Support messages, accounts and the audit of EDGE. On the beta only.')),
    h('div', { class: 'actions' }, state.overview ? h('span', { class: 'pill' }, h('span', { class: 'dot' }),
      `Site ${state.overview.site}${state.overview.commit ? ` · build ${state.overview.commit.slice(0, 7)}` : ''}`) : null));

  function tabs() {
    const list = h('div', { class: 'tabs', role: 'tablist', 'aria-label': 'Admin views' });
    for (const v of VIEWS) {
      const n = v === 'support' ? state.overview?.support.new ?? 0 : 0;
      const b = h('button', { type: 'button', role: 'tab', id: `tab-${v}`, 'aria-controls': 'view', 'aria-selected': String(state.view === v),
        tabindex: state.view === v ? '0' : '-1', class: state.view === v ? 'on' : '',
        // the tab already shown leads back to its list (a ticket or an account open in it closes)
        onclick: () => { if (state.view === v) { if (v === 'support') state.ticket = null; if (v === 'accounts') state.account = null }
                         state.view = v; render(); (document.getElementById(`tab-${v}`) as HTMLElement | null)?.focus() } },
        VIEW_LABEL[v], n ? h('span', { class: 'cnt', 'aria-label': `${n} new` }, count(n)) : null);
      list.append(b);
    }
    // arrows move between the tabs (the tablist pattern)
    list.addEventListener('keydown', e => {
      if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
      const i = VIEWS.indexOf(state.view) + (e.key === 'ArrowRight' ? 1 : -1);
      state.view = VIEWS[(i + VIEWS.length) % VIEWS.length];
      render();
      (document.getElementById(`tab-${state.view}`) as HTMLElement | null)?.focus();
      e.preventDefault();
    });
    return list;
  }

  function render() {
    root.removeAttribute('aria-busy');
    if (!state.step || state.step.needed) { put(root, header(), stepScreen()); return }
    const view = h('section', { id: 'view', role: 'tabpanel', 'aria-labelledby': `tab-${state.view}`, class: 'view' }, loading());
    put(root, header(), tabs(), view);
    const fill = { support: supportView, overview: overviewView, accounts: accountsView, audit: auditView, plans: plansView,
                   settings: settingsView }[state.view];
    void fill(view);
  }

  async function refreshOverview() {
    try { state.overview = await api.overview() } catch { /* the counts stay as they were */ }
    const tab = document.getElementById('tab-support');
    if (tab) {
      tab.querySelector('.cnt')?.remove();
      const n = state.overview?.support.new ?? 0;
      if (n) tab.append(h('span', { class: 'cnt', 'aria-label': `${n} new` }, count(n)));
    }
  }

  // ---- the code step (1A) ---------------------------------------------------------------------------------------------
  function stepScreen() {
    const s = state.step;
    const card = h('section', { class: 'card step', 'aria-labelledby': 'step-title' });
    const body = h('div', { class: 'card-b' });
    card.append(body);
    body.append(h('div', { class: 'step-mark' }, icon('shield', false)));
    if (s && !s.available) {
      body.append(h('h2', { id: 'step-title' }, 'The authenticator cannot be checked here yet'),
        h('p', {}, 'This site is not connected to the live site\'s authenticator. Ask the operator to connect it, then open the admin page again.'));
      return card;
    }
    if (s && !s.enrolled) {
      body.append(h('h2', { id: 'step-title' }, 'Set up your authenticator on the live site first'),
        h('p', {}, 'Sign in on the live site: EDGE asks you to set up an authenticator app there. Then come back here and enter its code.'));
      return card;
    }
    const input = h('input', { class: 'inp code', id: 'code', name: 'code', inputmode: 'numeric', autocomplete: 'one-time-code',
      maxlength: '7', 'aria-describedby': 'code-hint code-error', spellcheck: 'false' }) as HTMLInputElement;
    const error = h('small', { class: 'ferr', id: 'code-error', 'aria-live': 'polite' });
    const submit = h('button', { class: 'btn primary', type: 'submit' }, 'Open the admin page') as HTMLButtonElement;
    const form = h('form', { class: 'step-form', novalidate: true },
      h('label', { class: 'field' }, h('span', {}, 'Authenticator code'), input),
      h('small', { class: 'hint', id: 'code-hint' }, 'The 6-digit code from the authenticator app you use on the live site.'),
      error, submit);
    input.addEventListener('input', () => { error.textContent = ''; input.removeAttribute('aria-invalid') });
    form.addEventListener('submit', async e => {
      e.preventDefault();
      const code = codeOf(input.value);
      if (!code) { error.textContent = 'Enter the 6 digits of the code.'; input.setAttribute('aria-invalid', 'true'); input.focus(); return }
      submit.disabled = true; submit.textContent = 'Checking…';
      try {
        await api.stepUp(code);
        state.step = { needed: false, enrolled: true, available: true };
        await refreshOverview();
        render();
      } catch (err) {
        const ae = err instanceof AdminError ? err : null;
        error.textContent = ae ? ae.message : 'The code could not be checked. Try again in a minute.';
        input.setAttribute('aria-invalid', 'true');
        submit.disabled = false; submit.textContent = 'Open the admin page';
        input.select();
      }
    });
    body.append(h('h2', { id: 'step-title' }, 'Enter your authenticator code'),
      h('p', {}, 'The admin page asks for it once per session, before it shows any account or message.'), form);
    if (matchMedia('(hover:hover)').matches) requestAnimationFrame(() => input.focus());
    return card;
  }

  // ---- dialogs ----------------------------------------------------------------------------------------------------------
  /** a dialog that asks why (the reason is kept in the audit) and runs `act` with it, after any fields of its own
      (`extras`: a plan, an end); it stays open on a refusal and shows each of the server's reasons under its field (one
      for no field above the buttons). Resolves true once `act` succeeded, false when closed. */
  type Extra = { name: string; label: string; control: HTMLElement; hint?: string };
  function askReason(o: { title: string; lead: string; label: string; confirm: string; danger?: boolean; extras?: Extra[];
                          act: (reason: string) => Promise<void> }): Promise<boolean> {
    return new Promise(resolve => {
      const back = document.activeElement as HTMLElement | null;
      const text = h('textarea', { class: 'inp', id: 'reason', rows: '3', maxlength: String(REASON_CHARS + 50), 'aria-describedby': 'reason-error' }) as HTMLTextAreaElement;
      const error = h('small', { class: 'ferr', id: 'reason-error', 'aria-live': 'polite' });
      const general = h('p', { class: 'ferr', role: 'alert' });
      const errors: Record<string, HTMLElement> = { reason: error };
      const fields = (o.extras || []).map(x => {
        x.control.id = x.control.id || `field-${x.name}`;
        x.control.setAttribute('aria-describedby', `${x.name}-error`);
        errors[x.name] = h('small', { class: 'ferr', id: `${x.name}-error`, 'aria-live': 'polite' });
        x.control.addEventListener('input', () => { errors[x.name].textContent = ''; general.textContent = '' });
        return h('div', { class: 'extra' }, h('label', { class: 'field' }, h('span', {}, x.label), x.control),
          x.hint ? h('small', { class: 'hint' }, x.hint) : null, errors[x.name]);
      });
      const ok = h('button', { class: `btn ${o.danger ? 'danger' : 'primary'}`, type: 'submit' }, o.confirm) as HTMLButtonElement;
      const cancel = h('button', { class: 'btn', type: 'button' }, 'Cancel');
      const dialog = h('form', { class: 'dialog', role: 'dialog', 'aria-modal': 'true', 'aria-labelledby': 'dialog-title', novalidate: true },
        h('div', { class: 'dialog-head' }, h('strong', { id: 'dialog-title' }, o.title), h('span', { class: 'note' }, o.lead)),
        h('div', { class: 'dialog-body' }, ...fields, h('label', { class: 'field' }, h('span', {}, o.label), text), error, general),
        h('div', { class: 'dialog-foot' }, cancel, ok));
      const backdrop = h('div', { class: 'backdrop' }, dialog);
      const close = (done: boolean) => { backdrop.remove(); document.removeEventListener('keydown', keys, true); back?.focus(); resolve(done) };
      const keys = (e: KeyboardEvent) => {
        if (e.key === 'Escape') { e.preventDefault(); close(false); return }
        if (e.key !== 'Tab') return;
        const items = [...dialog.querySelectorAll<HTMLElement>('select,input,textarea,button')].filter(x => !(x as HTMLButtonElement).disabled);
        const first = items[0], last = items[items.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus() }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
      };
      cancel.addEventListener('click', () => close(false));
      backdrop.addEventListener('mousedown', e => { if (e.target === backdrop) close(false) });
      text.addEventListener('input', () => { error.textContent = ''; general.textContent = ''; text.removeAttribute('aria-invalid') });
      dialog.addEventListener('submit', async e => {
        e.preventDefault();
        const problem = reasonProblem(text.value);
        if (problem) { error.textContent = problem; text.setAttribute('aria-invalid', 'true'); text.focus(); return }
        ok.disabled = true; cancel.disabled = true;
        try { await o.act(text.value.trim()); close(true) }
        catch (err) {
          const ae = err instanceof AdminError ? err : null;
          const reasons = Object.entries(ae?.reasons || {});
          for (const [field, why] of reasons) (errors[field] || general).textContent = why;
          if (!reasons.length) general.textContent = ae ? ae.message : 'EDGE could not do this. Try again in a minute.';
          if (ae?.reasons.reason) text.setAttribute('aria-invalid', 'true');
          ok.disabled = false; cancel.disabled = false;
        }
      });
      document.addEventListener('keydown', keys, true);
      document.body.append(backdrop);
      requestAnimationFrame(() => (o.extras?.[0]?.control ?? text).focus());
    });
  }

  // ---- Support ------------------------------------------------------------------------------------------------------------
  async function supportView(view: HTMLElement) {
    if (state.ticket !== null) return ticketView(view, state.ticket);
    const filter = h('div', { class: 'seg', role: 'group', 'aria-label': 'Which tickets' },
      ...(['new', 'done', 'all'] as const).map(s => h('button', { type: 'button', class: state.support === s ? 'on' : '', 'aria-pressed': String(state.support === s),
        onclick: () => { state.support = s; render() } }, { new: 'New', done: 'Done', all: 'All' }[s])));
    const bar = h('div', { class: 'bar' }, filter, h('span', { class: 'grow' }),
      h('button', { class: 'iconbtn', type: 'button', 'aria-label': 'Reload the tickets', title: 'Reload', onclick: () => { void refreshOverview(); render() } }, icon('refresh', false)));
    const body = h('div', { class: 'card' }, loading());
    put(view, bar, body);
    const rows: TicketRow[] = [];
    const more = async (before = '') => {
      const page = await api.tickets({ status: state.support, before, limit: '50' });
      rows.push(...page.tickets);
      if (!rows.length) {
        put(body, h('div', { class: 'empty' }, h('strong', {}, state.support === 'new' ? 'No new support messages' : 'No tickets here'),
          state.support === 'new' ? 'A message sent from the mailbox in EDGE\'s menu shows here, on Telegram and in your email.' : 'Choose another filter above.'));
        return;
      }
      const all = state.support === 'all';
      const trs = rows.map(t => {
        const open = () => { state.ticket = t.ticket_id; render() };
        const tr = h('tr', { class: t.status === 'new' ? 'unread' : '', onclick: open },
          h('td', { class: 'num l' }, `#${t.ticket_id}`),
          h('td', { class: 'l nowrap', title: when(t.created_at) }, ago(t.created_at)),
          h('td', { class: 'l hide-sm' }, t.kind_label),
          h('td', { class: 'l subject' }, h('button', { type: 'button', class: 'linklike', onclick: (e: Event) => { e.stopPropagation(); open() } }, t.subject)),
          h('td', { class: 'l' }, t.username),
          h('td', { class: 'num hide-sm' }, t.images ? (t.images_purged_at ? 'deleted' : count(t.images)) : '—'),
          h('td', { class: 'l hide-sm' }, t.telegram_sent_at ? 'sent' : h('span', { class: 'warn-text' }, 'not sent')),
          all ? h('td', { class: 'l' }, h('span', { class: `pill ${t.status === 'new' ? 'info' : ''}` }, t.status === 'new' ? 'New' : 'Done')) : null);
        return tr as HTMLTableRowElement;
      });
      const head = ['#', 'Received', 'Type', 'Subject', 'From', 'Images', 'Telegram', ...(all ? ['Status'] : [])];
      const t = table(head, trs, 'tickets');
      put(body, t, page.next ? h('div', { class: 'card-f' }, h('button', { class: 'btn sm', type: 'button',
        onclick: (e: Event) => { (e.currentTarget as HTMLButtonElement).disabled = true; void more(String(page.next)).catch(err => failed(err)) } }, 'Show older tickets')) : null);
    };
    try { await more() } catch (e) { failed(e, body) }
  }

  async function ticketView(view: HTMLElement, id: number) {
    const back = h('button', { class: 'btn ghost sm back', type: 'button', onclick: () => { state.ticket = null; render() } }, icon('back'), 'All tickets');
    const holder = h('div', {}, loading());
    put(view, h('div', { class: 'bar' }, back), holder);
    let t: Ticket;
    try { t = await api.ticket(id) }
    catch (e) {
      if (e instanceof AdminError && e.status === 404) { put(holder, notice(`Ticket #${id} is not here: it was deleted, or the link is wrong.`)); return }
      return failed(e, holder);
    }
    put(holder, ticketCard(t));
  }

  function ticketCard(t: Ticket): HTMLElement {
    const status = h('span', { class: `pill ${t.status === 'new' ? 'info' : 'pos'}` }, t.status === 'new' ? 'New' : 'Done');
    const facts = h('div', { class: 'facts' },
      kv('From', t.sender.username, t.sender.email ? h('span', { class: 'muted' }, ` · ${t.sender.email}`) : null),
      kv('Received', when(t.created_at)),
      kv('Site', t.site),
      kv('Telegram', t.telegram_sent_at ? `sent ${when(t.telegram_sent_at)}` : `not sent yet${t.telegram_attempts ? ` (${plural(t.telegram_attempts, 'try', 'tries')})` : ''}`),
      t.status === 'done' ? kv('Done', `${when(t.done_at)}${t.done_by ? ` by ${t.done_by}` : ''}`) : null);
    const images = h('div', { class: 'images' });
    if (t.images_purged_at) images.append(h('p', { class: 'muted' }, `${plural(t.images, 'image')} deleted on ${day(t.images_purged_at)}, 90 days after the ticket was done.`));
    else if (!t.files.length) images.append(h('p', { class: 'muted' }, 'No images.'));
    else for (const f of t.files) {
      const url = api.imageUrl(t.ticket_id, f.position);
      images.append(h('figure', {}, h('a', { href: url, target: '_blank', rel: 'noopener', title: `Open ${f.filename} in a new tab` },
        h('img', { src: url, alt: f.filename, loading: 'lazy' })), h('figcaption', {}, f.filename, h('span', { class: 'muted' }, ` · ${bytes(f.bytes)}`))));
    }
    if (t.images_due) images.append(h('p', { class: 'muted small' }, `These images are deleted on ${day(t.images_due)}, 90 days after the ticket was marked done.`));
    const details = h('div', { class: 'facts' }, ...Object.entries(t.details || {}).map(([k, v]) => kv(k.replace(/_/g, ' '), valueText(v))));
    const actions = h('div', { class: 'card-f actions' });
    const mark = h('button', { class: t.status === 'new' ? 'btn primary' : 'btn', type: 'button' }, icon('check'), t.status === 'new' ? 'Mark done' : 'Mark as new');
    mark.addEventListener('click', async () => {
      mark.setAttribute('disabled', '');
      try {
        const next = await api.setStatus(t.ticket_id, t.status === 'new' ? 'done' : 'new');
        toast(next.status === 'done' ? `Ticket #${next.ticket_id} marked done.${next.images_due ? ` Its images are deleted on ${day(next.images_due)}.` : ''}` : `Ticket #${next.ticket_id} is new again.`);
        void refreshOverview();
        card.replaceWith(ticketCard(next));
      } catch (e) { mark.removeAttribute('disabled'); failed(e) }
    });
    actions.append(mark);
    if (!t.telegram_sent_at) {
      const again = h('button', { class: 'btn', type: 'button' }, icon('send'), 'Send to Telegram again');
      again.addEventListener('click', async () => {
        again.setAttribute('disabled', '');
        try {
          const r = await api.telegram(t.ticket_id);
          toast(r.sent ? 'The summary was sent to Telegram.' : 'Telegram did not take the summary. Try again later.');
          if (r.sent) card.replaceWith(ticketCard(await api.ticket(t.ticket_id)));
          else again.removeAttribute('disabled');
        } catch (e) { again.removeAttribute('disabled'); failed(e) }
      });
      actions.append(again);
    }
    const del = h('button', { class: 'btn danger', type: 'button' }, icon('trash'), 'Delete ticket');
    del.addEventListener('click', async () => {
      const done = await askReason({ title: `Delete ticket #${t.ticket_id}?`, danger: true, label: 'Why delete it',
        lead: `“${t.subject}” and its ${plural(t.images, 'image')} are deleted now. The audit keeps the ticket's number, type and your reason, never the message.`,
        confirm: 'Delete ticket', act: reason => api.deleteTicket(t.ticket_id, reason) });
      if (!done) return;
      toast(`Ticket #${t.ticket_id} deleted.`);
      state.ticket = null; void refreshOverview(); render();
    });
    actions.append(h('span', { class: 'grow' }), del);
    const card = h('article', { class: 'card ticket', 'aria-labelledby': 'ticket-subject' },
      h('div', { class: 'card-h' }, h('div', { class: 'ttl' }, h('h2', { id: 'ticket-subject' }, t.subject),
        h('span', { class: 'ttl-s' }, `Ticket #${t.ticket_id} · ${t.kind_label}`)), status),
      h('div', { class: 'card-b' }, facts,
        h('h3', {}, 'Description'), h('p', { class: 'message' }, t.body),
        h('h3', {}, 'Images'), images,
        h('h3', {}, 'Technical details'), details,
        h('p', { class: 'muted small' }, 'Answer from this ticket\'s email in your mailbox: its Reply-To is the sender\'s address.')),
      actions);
    return card;
  }

  // ---- Overview -----------------------------------------------------------------------------------------------------------
  async function overviewView(view: HTMLElement) {
    try { state.overview = await api.overview() } catch (e) { return failed(e, view) }
    const o = state.overview!;
    const tile = (label: string, value: string, sub = '') => h('div', { class: 'card ktile' }, h('div', { class: 'lb' }, h('span', {}, label)),
      h('div', {}, h('div', { class: 'v' }, value), sub ? h('div', { class: 's' }, sub) : null));
    const st = o.accounts.by_status;
    const total = Object.values(st).reduce((a, b) => a + b, 0);
    put(view,
      h('div', { class: 'kpis' },
        tile('Accounts', count(total), `${count(st.active ?? 0)} active · ${count(st.pending ?? 0)} pending · ${count(st.disabled ?? 0)} disabled`),
        tile('Test accounts', count(o.accounts.test_accounts), 'marked for a test window'),
        tile('Live sessions', count(o.sessions_live), 'signed in now, every site'),
        tile('Support, new', count(o.support.new), `${count(o.support.done)} done · ${count(o.support.unsent)} not on Telegram yet`),
        tile('Images stored', bytes(o.support.images_bytes), `of ${count(o.support_storage_mb)} MB`),
        tile('Emails waiting', count(o.emails.waiting), `${count(o.emails.failed_7d)} failed in 7 days`)),
      h('div', { class: 'card' }, h('div', { class: 'card-h' }, h('h3', {}, 'Active accounts by plan')),
        h('div', { class: 'card-b' }, ...(Object.keys(o.accounts.active_by_plan).length
          ? Object.entries(o.accounts.active_by_plan).sort().map(([plan, n]) => kv(plan, count(n)))
          : [h('p', { class: 'muted' }, 'No active account yet.')]))));
  }

  // ---- Accounts -----------------------------------------------------------------------------------------------------------
  async function accountsView(view: HTMLElement) {
    if (state.account !== null) return accountView(view, state.account);
    const f = state.accounts;
    const q = h('input', { class: 'inp', type: 'search', id: 'q', value: f.q, placeholder: 'Username, name or full email', 'aria-describedby': 'q-error' }) as HTMLInputElement;
    const status = h('select', { class: 'sel', id: 'status' }, h('option', { value: '' }, 'All'),
      ...Object.keys(state.overview?.accounts.by_status ?? {}).sort().map(s => h('option', { value: s, selected: f.status === s }, s))) as HTMLSelectElement;
    const plan = h('select', { class: 'sel', id: 'plan' }, h('option', { value: '' }, 'All')) as HTMLSelectElement;
    const qError = h('small', { class: 'ferr', id: 'q-error', 'aria-live': 'polite' });
    const form = h('form', { class: 'filters', role: 'search' },
      h('label', { class: 'field grow' }, h('span', {}, 'Search'), q),
      h('label', { class: 'field' }, h('span', {}, 'Status'), status),
      h('label', { class: 'field' }, h('span', {}, 'Plan'), plan),
      h('button', { class: 'btn', type: 'submit' }, icon('search'), 'Search'));
    const body = h('div', { class: 'card' }, loading());
    put(view, form, qError, body);
    form.addEventListener('submit', e => { e.preventDefault(); state.accounts = { q: q.value.trim(), status: status.value, plan: plan.value }; render() });
    void (state.plans ? Promise.resolve(state.plans) : api.plans()).then(p => {
      state.plans = p;
      for (const x of p.plans) plan.append(h('option', { value: x.plan_key, selected: f.plan === x.plan_key }, x.display_name));
    }, () => { /* the filter keeps All */ });
    const rows: Account[] = [];
    const more = async (before = '') => {
      const page = await api.users({ q: f.q, status: f.status, plan: f.plan, before, limit: '50' });
      rows.push(...page.users);
      if (!rows.length) { put(body, h('div', { class: 'empty' }, h('strong', {}, 'No account matches'), 'Search by any part of a username or name, or by a whole email address.')); return }
      const trs = rows.map(a => {
        const open = () => { state.account = a.user_id; render() };
        return h('tr', { onclick: open },
          h('td', { class: 'num l' }, a.user_id),
          h('td', { class: 'l' }, h('button', { type: 'button', class: 'linklike', onclick: (e: Event) => { e.stopPropagation(); open() } }, a.username)),
          h('td', { class: 'l hide-sm' }, fullName(a) || '—'),
          h('td', { class: 'l hide-sm' }, a.email ?? '—'),
          h('td', { class: 'l' }, a.plan ?? '—'),
          h('td', { class: 'l' }, h('span', { class: `pill ${a.status === 'active' ? 'pos' : a.status === 'disabled' ? 'neg' : 'warn'}` }, a.status),
            a.test_account ? h('span', { class: 'pill' }, 'test') : null),
          h('td', { class: 'l hide-sm nowrap', title: when(a.last_sign_in_at) }, a.last_sign_in_at ? ago(a.last_sign_in_at) : 'never')) as HTMLTableRowElement;
      });
      const t = table(['#', 'Username', 'Name', 'Email', 'Plan', 'Status', 'Last sign-in'], trs, 'accounts');
      put(body, t, page.next ? h('div', { class: 'card-f' }, h('button', { class: 'btn sm', type: 'button',
        onclick: (e: Event) => { (e.currentTarget as HTMLButtonElement).disabled = true; void more(String(page.next)).catch(err => failed(err)) } }, 'Show more accounts')) : null);
    };
    try { await more() }
    catch (e) {
      if (e instanceof AdminError && e.reasons.q) { qError.textContent = e.reasons.q; put(body, ); return }
      failed(e, body);
    }
  }

  async function accountView(view: HTMLElement, id: number) {
    const back = h('button', { class: 'btn ghost sm back', type: 'button', onclick: () => { state.account = null; render() } }, icon('back'), 'All accounts');
    const holder = h('div', {}, loading());
    put(view, h('div', { class: 'bar' }, back), holder);
    let d: AccountDetail;
    try { d = await api.user(id) }
    catch (e) {
      if (e instanceof AdminError && e.status === 404) { put(holder, notice(`Account #${id} is not here.`)); return }
      return failed(e, holder);
    }
    const a = d.account;
    const shown = (field: 'email' | 'phone', masked: string | null) => {
      const value = h('span', {}, masked ?? '—');
      if (!masked) return value;
      const show = h('button', { class: 'btn ghost sm', type: 'button' }, icon('eye'), 'Show');
      show.addEventListener('click', async () => {
        let full: string | null = null;
        const done = await askReason({ title: `Show the ${field === 'email' ? 'email address' : 'phone number'} of ${a.username}?`,
          lead: 'It is shown in full here and the audit records who saw it, when and why.', label: 'Why you need it',
          confirm: 'Show', act: async reason => { full = (await api.reveal(a.user_id, field, reason)).value } });
        if (!done) return;
        value.textContent = full ?? '—';
        show.remove();
        toast('Shown in full and recorded in the audit.');
      });
      return h('span', { class: 'reveal' }, value, show);
    };
    const subs = d.subscriptions.map(s => h('tr', {}, h('td', { class: 'l' }, s.plan_key), h('td', { class: 'l' }, s.status),
      h('td', { class: 'l nowrap' }, day(s.starts_at)), h('td', { class: 'l nowrap' }, s.expires_at ? day(s.expires_at) : 'no end'),
      h('td', { class: 'l hide-sm' }, s.provider ?? '—')) as HTMLTableRowElement);
    const overrides = d.overrides.map(o => h('tr', {}, h('td', { class: 'l' }, o.capability_key), h('td', { class: 'l' }, valueText(o.value)),
      h('td', { class: 'l' }, o.reason ?? '—'), h('td', { class: 'l nowrap' }, o.expires_at ? day(o.expires_at) : 'no end')) as HTMLTableRowElement);
    put(holder, h('article', { class: 'card account', 'aria-labelledby': 'account-name' },
      h('div', { class: 'card-h' }, h('div', { class: 'ttl' }, h('h2', { id: 'account-name' }, a.username),
        h('span', { class: 'ttl-s' }, `Account #${a.user_id}${fullName(a) ? ` · ${fullName(a)}` : ''} · ${a.role}`)),
        h('span', { class: `pill ${a.status === 'active' ? 'pos' : a.status === 'disabled' ? 'neg' : 'warn'}` }, a.status)),
      h('div', { class: 'card-b' },
        h('div', { class: 'facts' },
          kv('Email', shown('email', a.email)), kv('Phone', shown('phone', a.phone)),
          kv('Plan', a.plan ?? '—', a.plan_ends ? h('span', { class: 'muted' }, ` · ends ${day(a.plan_ends)}`) : null),
          kv('Email verified', d.email_verified_at ? day(d.email_verified_at) : 'not yet'),
          kv('Authenticator', { confirmed: 'set up', pending: 'being set up', none: 'none' }[d.mfa] ?? d.mfa),
          kv('Test account', a.test_account ? 'yes' : 'no'),
          kv('Created', when(a.created_at)), kv('Last sign-in', a.last_sign_in_at ? when(a.last_sign_in_at) : 'never'),
          kv('Live sessions', count(d.sessions.live), d.sessions.last_seen ? h('span', { class: 'muted' }, ` · last seen ${ago(d.sessions.last_seen)}`) : null)),
        h('h3', {}, 'Actions'), actionsOf(d, () => accountView(view, id)),
        h('h3', {}, 'Plan history'), subs.length ? table(['Plan', 'Status', 'From', 'Until', 'Provider'], subs) : h('p', { class: 'muted' }, 'On the default plan; no plan was given to it.'),
        h('h3', {}, 'Overrides'), overrides.length ? table(['Capability', 'Value', 'Reason', 'Until'], overrides) : h('p', { class: 'muted' }, 'None.'),
        h('h3', {}, 'Usage'), h('div', { class: 'facts' }, ...Object.entries(d.usage).map(([k, n]) => kv(k.replace(/_/g, ' '), count(n)))),
        h('h3', {}, 'Audit about this account'), d.audit.length ? auditTable(d.audit, false) : h('p', { class: 'muted' }, 'Nothing recorded yet.'))));
  }

  /** slice 5: what may be done to the account, as its answer says (actions: open, or why not); each asks why, then
      shows the account again */
  function actionsOf(d: AccountDetail, again: () => Promise<void>) {
    const a = d.account, name = a.username;
    const done = (text: string) => { toast(text); void again() };
    const box = h('div', { class: 'acts' });
    const add = (open: { open: boolean; why: string | null }, button: HTMLElement | null, quietWhenClosed = false) => {
      if (open.open && button) box.append(button);
      else if (!open.open && open.why && !quietWhenClosed) box.append(h('p', { class: 'muted why' }, open.why));
    };
    const disabled = a.status === 'disabled';
    const status = h('button', { class: `btn ${disabled ? '' : 'danger'}`, type: 'button' }, disabled ? 'Enable account' : 'Disable account');
    status.addEventListener('click', async () => {
      const ok = await askReason(disabled
        ? { title: `Enable ${name}?`, lead: 'It can sign in again with its own password.', label: 'Why', confirm: 'Enable account',
            act: async reason => { await api.setAccountStatus(a.user_id, 'active', reason) } }
        : { title: `Disable ${name}?`, lead: 'It is signed out everywhere at once and cannot sign in until it is enabled again.',
            label: 'Why', confirm: 'Disable account', danger: true,
            act: async reason => { await api.setAccountStatus(a.user_id, 'disabled', reason) } });
      if (ok) done(disabled ? `${name} can sign in again.` : `${name} is disabled and signed out everywhere.`);
    });
    add(d.actions.status, status);
    const plan = h('button', { class: 'btn', type: 'button' }, 'Change plan');
    plan.addEventListener('click', async () => {
      let choices: Plans;
      try { choices = state.plans ?? (state.plans = await api.plans()) } catch (e) { failed(e); return }
      const select = h('select', { class: 'sel' }, ...choices.plans.filter(p => !p.for_guests && !p.gives_admin)
        .map(p => h('option', { value: p.plan_key, selected: p.plan_key === a.plan }, p.display_name))) as HTMLSelectElement;
      const ends = h('input', { class: 'inp', type: 'date' }) as HTMLInputElement;
      const ok = await askReason({ title: `Change the plan of ${name}`, label: 'Why',
        lead: 'The new plan starts now and the one it has ends. To extend, choose the same plan and a later end.',
        extras: [{ name: 'plan_key', label: 'Plan', control: select },
                 { name: 'expires_at', label: 'Ends', control: ends, hint: 'The last day of the plan; empty for no end.' }],
        confirm: 'Change plan', act: async reason => { await api.givePlan(a.user_id, select.value, endOf(ends.value), reason) } });
      if (ok) done(`The plan of ${name} changed.`);
    });
    add(d.actions.plan, plan);
    const out = h('button', { class: 'btn', type: 'button' }, 'Sign out everywhere');
    out.addEventListener('click', async () => {
      let ended = 0;
      const ok = await askReason({ title: `Sign ${name} out everywhere?`, label: 'Why', confirm: 'Sign out everywhere',
        lead: 'Every session on every site ends now; its password stays.',
        act: async reason => { ended = (await api.endSessions(a.user_id, reason)).revoked } });
      if (ok) done(`${plural(ended, 'session')} of ${name} ended.`);
    });
    add(d.actions.sessions, out, a.status === 'pending');
    const code = h('button', { class: 'btn', type: 'button' }, 'Resend code');
    code.addEventListener('click', async () => {
      const ok = await askReason({ title: `Send ${name} a new code?`, label: 'Why', confirm: 'Send code',
        lead: 'It works only in the browser where the registration began; a registration gets at most 3 emails a day.',
        act: async reason => { await api.sendCode(a.user_id, reason) } });
      if (ok) done(`A new code was sent to ${name}.`);
    });
    add(d.actions.resend_code, code, a.status !== 'pending');
    if (!box.childNodes.length) box.append(h('p', { class: 'muted why' }, 'Nothing can be done to this account here.'));
    return box;
  }

  // ---- Audit --------------------------------------------------------------------------------------------------------------
  function auditTable(rows: AuditRow[], about = true) {
    const trs = rows.map(r => h('tr', {}, h('td', { class: 'l nowrap', title: when(r.at) }, when(r.at)), h('td', { class: 'l' }, h('code', {}, r.action)),
      h('td', { class: 'l' }, r.actor ?? (r.actor_user_id ? `#${r.actor_user_id}` : '—')),
      about ? h('td', { class: 'l' }, r.target ?? (r.target_user_id ? `#${r.target_user_id}` : '—')) : null,
      h('td', { class: 'l change' }, changeOf(r) || '—'), h('td', { class: 'l reason' }, r.reason ?? '—')) as HTMLTableRowElement);
    return table(['When', 'Action', 'By', ...(about ? ['About'] : []), 'Change', 'Reason'], trs, 'audit');
  }

  /** the viewer's local day as the moment it starts (a date field's value), or '' */
  const startOf = (date: string, plusDays = 0) => {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(date || '');
    return m ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]) + plusDays).toISOString() : '';
  };

  async function auditView(view: HTMLElement) {
    const f = state.audit;
    const list = h('datalist', { id: 'actions' });
    const action = h('input', { class: 'inp', id: 'action', list: 'actions', value: f.action, placeholder: 'All actions', autocomplete: 'off' }) as HTMLInputElement;
    const since = h('input', { class: 'inp', id: 'since', type: 'date', value: f.since, 'aria-describedby': 'since-error' }) as HTMLInputElement;
    const until = h('input', { class: 'inp', id: 'until', type: 'date', value: f.until }) as HTMLInputElement;
    const err = h('small', { class: 'ferr', id: 'since-error', 'aria-live': 'polite' });
    const file = h('button', { class: 'btn', type: 'button' }, icon('download'), 'Download CSV') as HTMLButtonElement;
    const form = h('form', { class: 'filters' },
      h('label', { class: 'field' }, h('span', {}, 'Action'), action, list),
      h('label', { class: 'field' }, h('span', {}, 'From'), since),
      h('label', { class: 'field' }, h('span', {}, 'Until'), until),
      h('button', { class: 'btn', type: 'submit' }, icon('search'), 'Show'), file);
    const body = h('div', { class: 'card' }, loading());
    put(view, form, err, body);
    const query = () => ({ action: state.audit.action, since: startOf(state.audit.since), until: startOf(state.audit.until, 1) });
    form.addEventListener('submit', e => { e.preventDefault(); state.audit = { action: action.value.trim(), since: since.value, until: until.value }; render() });
    file.addEventListener('click', async () => {
      state.audit = { action: action.value.trim(), since: since.value, until: until.value };
      file.disabled = true; err.textContent = '';
      try {
        const blob = await api.auditFile(query());
        const a = h('a', { href: URL.createObjectURL(blob), download: fileName() });
        document.body.append(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(a.href), 30000);
        toast('The audit file was downloaded.');
      } catch (e) {
        if (e instanceof AdminError && (e.reasons.since || e.reasons.until)) err.textContent = e.reasons.since || e.reasons.until;
        else failed(e);
      } finally { file.disabled = false }
    });
    const rows: AuditRow[] = [];
    const more = async (before = '') => {
      const page = await api.audit({ ...query(), before, limit: '50' });
      rows.push(...page.audit);
      put(list, ...auditActions(rows).map(x => h('option', { value: x })));
      if (!rows.length) { put(body, h('div', { class: 'empty' }, h('strong', {}, 'Nothing recorded'), 'Every admin action is recorded here with its reason.')); return }
      put(body, auditTable(rows), page.next ? h('div', { class: 'card-f' }, h('button', { class: 'btn sm', type: 'button',
        onclick: (e: Event) => { (e.currentTarget as HTMLButtonElement).disabled = true; void more(String(page.next)).catch(x => failed(x)) } }, 'Show older')) : null);
    };
    try { await more() }
    catch (e) {
      if (e instanceof AdminError && (e.reasons.since || e.reasons.until || e.reasons.action)) { err.textContent = e.reasons.since || e.reasons.until || e.reasons.action; put(body, ); return }
      failed(e, body);
    }
  }

  // ---- Plans and settings -------------------------------------------------------------------------------------------------
  async function plansView(view: HTMLElement) {
    let p: Plans;
    try { p = state.plans = await api.plans() } catch (e) { return failed(e, view) }
    const value = new Map(p.values.map(v => [`${v.plan_key}\n${v.capability_key}`, v.value]));
    const trs = p.capabilities.map(c => h('tr', {}, h('td', { class: 'l cap' }, h('span', { class: 'sym' }, c.display_name), h('span', { class: 'sub' }, c.capability_key)),
      ...p.plans.map(pl => { const k = `${pl.plan_key}\n${c.capability_key}`; return h('td', { class: 'l' }, value.has(k) ? valueText(value.get(k)) : h('span', { class: 'muted' }, '—')) })) as HTMLTableRowElement);
    put(view,
      h('p', { class: 'muted lead' }, 'What each plan holds, as the site reads it now. Plans change through a database migration, not here.'),
      h('div', { class: 'card' }, table(['Capability', ...p.plans.map(pl => `${pl.display_name}${pl.is_default ? ' (default)' : ''}${pl.for_guests ? ' (visitors)' : ''}`)], trs, 'plans')));
  }

  async function settingsView(view: HTMLElement) {
    try {
      const s = await api.settings();
      put(view, h('p', { class: 'muted lead' }, 'This site\'s settings that are no secret. They change in the site\'s configuration, not here.'),
        h('div', { class: 'card' }, h('div', { class: 'card-b facts' },
          kv('Telegram summary', s.telegram_summary ? 'connected' : 'not connected'),
          ...Object.entries(s.settings).map(([k, v]) => kv(k.replace(/_/g, ' '), valueText(v))))));
    } catch (e) { failed(e, view) }
  }

  async function boot() {
    try { state.step = await api.stepState() }
    catch (e) {
      root.removeAttribute('aria-busy');
      const err = e instanceof AdminError ? e : null;
      put(root, header(), notice(err ? err.message : 'The admin page could not reach EDGE. Check the connection and try again.', () => void boot()));
      return;
    }
    if (!state.step.needed) await refreshOverview();
    render();
  }
  return { boot, rerender: () => { /* the theme is CSS only */ } };
}
