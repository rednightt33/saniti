/* Same-origin API/session and response adapters. No credentials or response history in browser storage. */
(() => {
  let auth = null;
  const followers = new Set();
  // re-check R2-14, R2-30: the message of a refusal is its words for the person (the server's message, else the access
  // words), which every page and the Monitor show; the code is .code (and .info.code) for the decisions
  class ApiError extends Error {
    constructor(code, status, info, words) { super(words || code); this.code = code; this.status = status; this.info = info || null; }
  }
  // EXEC-MU-ACCOUNTS Phase 0 (M471, M473): the error contract, the storage registry and the clean-up are the shared
  // module's (apps/edge-bff/shared/edge-session.ts, loaded before this file as /edge-session.js, window.EdgeSession).
  // Only a 401 resets the session (the sign-in page); only a 403 CSRF_INVALID reads the session again and repeats the
  // write once; a plan refusal keeps the session and carries its words (EdgeLabels.access, error.text).
  const ES = () => window.EdgeSession || null;
  try { ES()?.setRole('shell'); } catch { /* the module is missing: the shell still signs in */ }
  // another page cleared the user state (a sign-out in another tab, or another account signed in): this tab drops its
  // in-memory views of the previous account (reset shows the sign-in page) and reads the session again, showing the
  // account signed in now. This tab's own broadcasts never reach it, so there is no loop.
  try { ES()?.onCleared(() => { stopPrefs(); reset(); window.Edge.session().then(a => { if (a) dispatchEvent(new Event('edge-auth')); }); }); } catch { /* not offered */ }
  // re-check R2-16, R2-31 (CONTRACT.md 8a, 12): the access changed (a new X-Edge-Entitlements on this page's answers or
  // a frame's broadcast): the session is read again into `auth`, the model list read again, and the page redraws from
  // them (an account raised to a plan that needs the authenticator is taken to /mfa; a narrowed one loses what it lost)
  let rereading = null;
  const followVersion = version => {
    if (!auth || (version && auth.access?.version === version)) return rereading;
    return rereading ||= (async () => {
      try {
        const fresh = await api('/auth/session');
        if (fresh && identity(fresh) === identity(auth)) {
          auth = fresh; models = {data:null, failed:false, pending:null};
          await settle(Promise.all([loadModels(), loadPrefs(null)]));
          dispatchEvent(new Event('edge-auth'));
        }
      } catch { /* a 401 already reset the page; anything else keeps the session as it is */ }
      finally { rereading = null; }
    })();
  };
  try { ES()?.onVersion(followVersion); } catch { /* not offered */ }
  // re-check R2-17 (CONTRACT.md 3): a frame's own session ended (401): the shell reads its session, and a 401 there takes
  // it to the sign-in page (api() resets on its own 401)
  try { ES()?.onSignedOut(() => { if (auth) api('/auth/session').catch(() => { /* reset by the 401, or kept */ }); }); } catch { /* not offered */ }
  // EXEC-MODELS: the offered models are read once per session, before the work page shows (sign-in or a restored
  // session waits up to 3 s for them), so their arrival never redraws the page while the user types
  let models = {data:null, failed:false, pending:null};
  // a sign-in that waits for the admin's authenticator code (403 MFA_REQUIRED, a pending session): its CSRF token, when
  // the refusal carries one (details.csrf_token), for the /mfa page's enrol and verify writes
  const pending = {csrf:''};
  const reset = () => { auth = null; models = {data:null, failed:false, pending:null}; followers.forEach(close => close()); followers.clear(); dispatchEvent(new Event('edge-auth')); };
  async function api(path, body, method = body === undefined ? 'GET' : 'POST', retried = false) {
    const headers = method === 'GET' ? {} : { 'X-CSRF-Token':auth?.csrf_token || pending.csrf || '', ...(body === undefined ? {} : {'Content-Type':'application/json'}) };
    const res = await fetch('/api/v1' + path, { method, headers, credentials:'same-origin', ...(body === undefined ? {} : {body:JSON.stringify(body)}) });
    const data = await res.json().catch(() => ({}));
    const version = res.headers.get('X-Edge-Entitlements');
    if (version && auth?.access?.version && version !== auth.access.version && path !== '/auth/session' && !PUBLIC_AUTH.test(path)) void followVersion(version);
    if (!res.ok) {
      const info = ES()?.readError(res.status, data, res.headers.get('Retry-After')) || null;
      if (res.status === 401 && !PUBLIC_AUTH.test(path)) reset();
      if (info?.kind === 'csrf' && method !== 'GET' && !retried && auth && !PUBLIC_AUTH.test(path)) {
        // the repeat goes out only for the account this page holds; another login (signed in in another tab) never
        // receives this page's write: its user state is cleared and the page reloads as that account (C1 M1, C2 #2)
        const started = identity(auth);
        let fresh = null;
        try { const r = await fetch('/api/v1/auth/session', {credentials:'same-origin'}); if (r.ok) fresh = await r.json(); } catch { /* the refusal below stands */ }
        if (fresh && identity(fresh) === started) { auth = fresh; return api(path, body, method, true); }
        if (fresh) {
          try { await ES()?.clearUserState(); } catch { /* storage off */ }
          reset();
          try { location.reload(); } catch { /* not a page */ }
          throw new ApiError('USER_CHANGED', 401, info, window.EdgeLabels?.auth?.errors?.USER_CHANGED || null);
        }
      }
      const code = data.error?.code || (info?.legacy && info.kind === 'csrf' ? info.code : res.status === 401 ? 'Authentication required' : 'Request unavailable');
      const words = info && ES()?.isAccessRefusal(info) ? (info.message || (window.EdgeLabels?.access || {})[info.code] || ES().accessText(info)) : null;
      const error = new ApiError(code, res.status, info, words || info?.message || null);
      if (words) error.text = words;
      throw error;
    }
    return data;
  }
  // M473: another login than the last one on this browser clears the previous account's state before anything shows.
  // Phase 1: the identity is the stable owner key once the session answer carries it (owner:<key>), else the login;
  // then the account preferences (contract 4b) are read into this browser, and a local value of this same identity
  // with no server copy goes up once. access.seed (user #1) keeps a browser's state from before the mark (C3 B1).
  const ownerOf = session => session?.owner_key ?? session?.access?.owner_key ?? null;
  const identity = session => { try { return ES()?.identityOf(session?.login || '', ownerOf(session)) ?? String(session?.login || '').trim().toLowerCase(); } catch { return String(session?.login || '').trim().toLowerCase(); } };
  const noteLogin = session => { try { if (session?.login) return ES()?.noteIdentity(session.login, ownerOf(session), {seed:session?.access?.seed === true}) || null; } catch { /* storage off */ } return null; };
  // the preferences routes ship with the Phase 1 session answer (its `access` object): an older server is never asked
  // (a session still waiting for the authenticator, access.next "mfa", reads none: they answer 403 MFA_REQUIRED)
  const loadPrefs = noted => { if (!auth?.access || auth.access.next) return Promise.resolve(false);
    try { return ES()?.prefs.load({uploadLocal:Boolean(noted?.same)}) || Promise.resolve(false); } catch { return Promise.resolve(false); } };
  const stopPrefs = () => { try { ES()?.prefs.stop(); ES()?.edge.forget(); } catch { /* not offered */ } };
  // the auth routes that answer without a session (a 401 there is the form's answer, not a sign-out)
  const PUBLIC_AUTH = /^\/auth\/(sign-in|register|code\/|password\/(forgot|reset)|config|mfa\/)/;
  // EXEC-MU-ACCOUNTS Phase 1: whether registration is open (GET /api/v1/auth/config, public); a 404 or any failure is
  // "off" (the switch is off, or the route is not deployed yet), so nothing changes for the current user
  let config = null;
  const readConfig = () => config || (config = fetch('/api/v1/auth/config', {credentials:'same-origin'})
    // the body is always read, also of a 404: an answer whose body is never read stays open in the browser
    // track guest (decision 1 and the pre-launch decisions of 2026-11-19): with accounts on, whether registration is
    // open (an older server without the key: open), the pre-launch mode, whether a visitor opens the Terminal, and the
    // upgrade box's contact (null: the box says it comes soon)
    .then(r => r.json().catch(() => ({})).then(d => r.ok ? d : {})).then(d => ({multiuser: d?.multiuser === true,
      registration: d?.multiuser === true && d?.registration !== false, prelaunch: d?.prelaunch === true,
      guests: d?.multiuser === true && d?.guests === true,
      upgradeContact: typeof d?.upgrade_contact === 'string' && d.upgrade_contact ? d.upgrade_contact : null,
      // live checker S1: the tabs this site never offers (the live site: the Monitor and the admin pages)
      hiddenTabs: Array.isArray(d?.hidden_tabs) ? d.hidden_tabs.filter(t => typeof t === 'string') : [],
      // the footer's Privacy and Terms links (EXEC option A, 2026-11-20): an address only when set, else none shown
      legal: {privacy: legalUrl(d?.legal?.privacy), terms: legalUrl(d?.legal?.terms)}}))
    .catch(() => ({multiuser:false, registration:false, prelaunch:false, guests:false, upgradeContact:null, hiddenTabs:[],
      legal:{privacy:null, terms:null}}))
    .then(c => { hiddenTabs = c.hiddenTabs; legal = c.legal; return c; }));
  let hiddenTabs = [], legal = {privacy:null, terms:null};
  const legalUrl = u => typeof u === 'string' && (/^https:\/\//.test(u) || /^\/(?!\/)/.test(u)) ? u : null;
  const terminal = s => ['FINISHED','FAILED','INTERRUPTED'].includes(s.state);
  // EXEC-X (M124): the frame stays English (user decision 2026-10-08) but says what the saved response is
  const DOMAIN = {COMPLETED:'Completed',AWAITING_CONFIRMATION:'Awaiting approval',NEEDS_CLARIFICATION:'Needs your reply',LIMITED:'Limited',FAILED:'Failed'};
  const statusLabel = (status, domain, pause) => ['submitted','running','streaming'].includes(status) ? 'Running' : status === 'failed' && !domain ? 'Failed'
    : pause && domain === 'LIMITED' ? 'Paused' : DOMAIN[domain] || (status ? status[0].toUpperCase() + status.slice(1) : '—');
  // M317 (user 2026-10-31: "hijau kalau dia sukses. Merah kalau dia gagal, kuning kalau butuh konfirmasi ... Tidak boleh
  // ada yang warnanya abu-abu"): the one colour of a run's state, for every status dot (conversation list, session bar).
  // info running; negative failed; warning an answer that waits for the user or is not whole (approval, a reply,
  // paused, limited, stopped); positive completed; new a conversation without a question yet. Every state has a colour.
  const statusTone = (status, domain, pause, stopped) => ['submitted','running','streaming'].includes(status) ? 'info'
    : status === 'failed' || domain === 'FAILED' ? 'negative'
    : status === 'completed' ? (pause || stopped || (domain && domain !== 'COMPLETED') ? 'warning' : 'positive') : 'new';
  // the list API's last question state (edge_bff.jobs) in the page's run words, so statusTone reads both alike
  const LIFECYCLE = {QUEUED:'running',RUNNING:'running',RECOVERING:'running',FINISHED:'completed',FAILED:'failed',INTERRUPTED:'failed'};
  // M153 (EXEC-UI-1013B): on iPhone the stream of a run died while the app was in the background and no error event
  // followed (iOS 18), so the page waited for the answer until a refresh. The stream now sends a ping every few
  // seconds; a stream silent for STALE_MS is replaced (with one status read), and so is the stream when the page
  // becomes visible again. Three stream errors in a row still switch to polling.
  const STALE_MS = 15000;
  function follow(id, callback, onError) {
    let closed = false, failures = 0, source, timer, watchdog, version = -1, polling = false, heard = Date.now();
    const url = '/api/v1/runs/' + encodeURIComponent(id) + '/events';
    const close = () => {
      closed = true; source?.close(); clearTimeout(timer); clearInterval(watchdog);
      document.removeEventListener('visibilitychange', wake); removeEventListener('pageshow', wake); followers.delete(close);
    };
    const deliver = data => { if (closed) return; if (data.state_version >= version) { version = data.state_version; callback(data); } if (terminal(data)) close(); };
    const read = async () => {
      if (closed) return;
      try { deliver(await api('/runs/' + encodeURIComponent(id))); }
      catch (error) { onError(error); if (error.status === 401 || error.status === 404) close(); }
    };
    const poll = async () => { await read(); if (!closed) timer = setTimeout(poll, 3000); };
    const open = () => {
      source?.close(); heard = Date.now();
      source = new EventSource(url);
      source.addEventListener('snapshot', event => { heard = Date.now(); failures = 0; try { deliver(JSON.parse(event.data)); } catch { onError(new Error('Invalid status snapshot')); } });
      source.addEventListener('ping', () => { heard = Date.now(); failures = 0; });
      source.onerror = () => { if (++failures >= 3) { source.close(); polling = true; clearInterval(watchdog); poll(); } };
    };
    const resync = () => { if (closed || polling) return; read(); if (!closed) open(); };
    const wake = () => { if (document.visibilityState === 'visible') resync(); };
    watchdog = setInterval(() => { if (Date.now() - heard > STALE_MS) resync(); }, 5000);
    document.addEventListener('visibilitychange', wake); addEventListener('pageshow', wake);
    open();
    followers.add(close);
    return close;
  }
  async function conversations() {
    let offset = 0, result = [];
    do { const page = await api('/conversations?limit=100&offset=' + offset); result.push(...page.items); offset = page.next_offset; } while (offset !== null);
    // MONITOR-REVAMP (user 2026-10-30): the list keeps a branch's kind and parent so it nests under that conversation
    return result.map(ui => ({id:ui.conversation_id,title:ui.title,bookmarked:ui.bookmarked,createdAt:ui.created_at,updatedAt:ui.updated_at,lastMessage:ui.last_message||null,
      lastRun:ui.last_state?{status:LIFECYCLE[ui.last_state]||null,domainStatus:ui.last_run_status||null}:null,
      kind:ui.kind||'MAIN',parent:ui.parent_conversation_id?{conversationId:ui.parent_conversation_id,requestId:ui.parent_request_id}:null,messages:[],runs:[]}));
  }
  // EXEC-UI-1012 C: the first question's answer is headed by the short title Orc's first-message router wrote
  // EXEC 2026-10-20 (user screenshot: "…buying p"): a title made from the question is cut at a word, with an ellipsis
  const shortTitle = (text, limit = 80) => { const t = String(text || '').split(/\s+/).join(' ').trim(); if (t.length <= limit) return t;
    const cut = t.slice(0, limit - 1), space = cut.lastIndexOf(' '); return (space > limit / 2 ? cut.slice(0, space) : cut).replace(/[\s,;:.\-–—]+$/, '') + '…'; };
  const routerTitle = response => shortTitle(response?.mode4?.router?.title) || null;
  function adaptRun(turn, ui = {}) {
    const raw = turn.response;
    const final = raw?.response;
    const failed = turn.status === 'FAILED' || turn.status === 'INTERRUPTED' || raw?.status === 'FAILED';
    return {id:turn.request_id,question:turn.user_message || ui.title || 'Research response',createdAt:turn.created_at,completedAt:turn.completed_at,
      status:turn.status === 'RUNNING' ? 'running' : failed ? 'failed' : 'completed',domainStatus:raw?.status || turn.run_status,paused:Boolean(raw?.execution?.pause),stopped:Boolean(raw?.execution?.stopped),
      mode:'Standard',attachments:[],pinned:(ui.pinned_request_ids || []).includes(turn.request_id),
      error:raw?.error?.code || turn.error_code,errorText:raw?.error?.user_message,raw,result:final ? {title:routerTitle(raw) || shortTitle(turn.user_message) || ui.title || 'Research response',condition:final.answer || final.clarification_question || '',final} : null,
      sources:[...(raw?.evidence || []), ...(raw?.annotations || []), ...(raw?.data_record ? [{name:'Data record',record:raw.data_record}] : [])],
      steps:[{id:'saved-state',label:turn.status === 'RUNNING' ? 'AI request running' : 'Saved response: ' + statusLabel('completed', raw?.status || turn.run_status, raw?.execution?.pause),status:turn.status === 'RUNNING' ? 'running' : failed ? 'failed' : 'completed',detail:'Persisted lifecycle state'}]};
  }
  // every page of one conversation's turns (through: up to that turn), its list row, lineage and side chats
  async function turnsOf(id, through) {
    let after = -1, turns = [], sides = {}, page;
    do { page = await api('/conversations/' + encodeURIComponent(id) + '/messages?limit=50&after=' + after + (through === undefined ? '' : '&through=' + through));
      turns.push(...page.messages); Object.assign(sides, page.side_chats || {}); after = page.next_after; } while (page.has_more);
    return {turns, sides, ui:page.conversation, plan:page.research_plan, lineage:page.lineage || []};
  }
  // EXEC-ASK-BRANCH (user 2026-10-24): a conversation that continues others (Branch, side chat) shows their turns up to
  // each branch point first, marked as inherited (the divider names where they come from); its own turns follow
  async function messages(id) {
    const own = await turnsOf(id);
    const ui = own.ui, inherited = [], sides = {...own.sides};
    for (const step of own.lineage) {
      try { const part = await turnsOf(step.conversation_id, step.through_turn);
        inherited.push(...part.turns.map(t => ({...t, inherited:{conversationId:step.conversation_id, title:part.ui.title}})));
        Object.assign(sides, part.sides); }
      catch { /* a conversation it continues may be gone: its own turns still show */ }
    }
    const turns = [...inherited, ...own.turns];
    return {id, title:ui.title,bookmarked:ui.bookmarked,createdAt:ui.created_at,updatedAt:ui.updated_at,plan:own.plan,
      kind:ui.kind || 'MAIN', parent:ui.parent_conversation_id ? {conversationId:ui.parent_conversation_id, requestId:ui.parent_request_id} : null,
      sideChats:sides,
      messages:turns.map(t=>({id:t.request_id+'-user',role:'user',content:t.user_message,createdAt:t.created_at,runId:t.request_id,inherited:t.inherited || null})),
      runs:turns.map(t=>({...adaptRun(t,ui),inherited:Boolean(t.inherited)}))};
  }
  const stateRun = (snapshot, previous) => ({...previous,
    status:snapshot.error_code === 'STOPPED_BY_USER' ? 'cancelled' : terminal(snapshot) ? snapshot.state === 'FINISHED' && snapshot.run_status !== 'FAILED' && !snapshot.expired ? 'completed' : 'failed' : snapshot.state === 'QUEUED' ? 'submitted' : 'running',
    domainStatus:snapshot.run_status,paused:Boolean((snapshot.response || previous.raw)?.execution?.pause),stopped:Boolean((snapshot.response || previous.raw)?.execution?.stopped),error:snapshot.expired ? 'Conversation expired; the saved response is no longer available.' : snapshot.error_code || snapshot.response?.error?.code,
    errorText:snapshot.expired ? undefined : (snapshot.response || previous.raw)?.error?.user_message,
    completedAt:snapshot.completed_at,raw:snapshot.response || previous.raw,
    result:snapshot.response?.response ? {title:routerTitle(snapshot.response) || shortTitle(previous.question),condition:snapshot.response.response.answer || snapshot.response.response.clarification_question || '',final:snapshot.response.response} : previous.result,
    sources:snapshot.response ? [...(snapshot.response.evidence || []),...(snapshot.response.annotations || []),...(snapshot.response.data_record ? [{name:'Data record',record:snapshot.response.data_record}] : [])] : previous.sources,
    steps:[{id:'state',label:{QUEUED:'Queued',RUNNING:'AI request running',RECOVERING:snapshot.error_code === 'SERVICES_INITIALIZING' ? EdgeLabels.servicesWaiting : 'Recovering delivery',FINISHED:'Saved response: '+statusLabel('completed',snapshot.run_status,snapshot.response?.execution?.pause),FAILED:'Request failed',INTERRUPTED:'Delivery interrupted'}[snapshot.state],status:terminal(snapshot) ? snapshot.state === 'FINISHED' && snapshot.run_status !== 'FAILED' && !snapshot.expired ? 'completed' : 'failed' : 'running',detail:snapshot.updated_at}]
  });
  // live checker S1: a site without the Monitor has no model list (GET /api/v1/models answers 404 there)
  const loadModels = () => models.pending || (models.pending = readConfig().then(c => c.hiddenTabs.includes('monitor') ? null : api('/models'))
    .then(data => { const ok = Array.isArray(data?.models) && data.models.length > 0; models.data = ok ? data : null; models.failed = !ok; })
    .catch(() => { models.failed = true; }));
  const settle = promise => Promise.race([promise, new Promise(resolve => setTimeout(resolve, 3000))]);
  window.Edge = {
    api,follow,terminal,conversations,messages,adaptRun,stateRun,statusLabel,statusTone,shortTitle,
    get auth() { return auth; },
    async session() { try { auth = await api('/auth/session'); } catch { auth = null; } if (auth) { const noted = noteLogin(auth); await settle(Promise.all([loadModels(), loadPrefs(noted)])); } return auth; },
    async signin(login,password) { stopPrefs(); pending.csrf = '';
      try { auth = await api('/auth/sign-in',{login,password}); }
      catch (error) { if (error.info?.code === 'MFA_REQUIRED') pending.csrf = String(error.info.details?.csrf_token || ''); throw error; }
      return Edge.adopt(auth); },
    // after a sign-in, or an email code that signs in directly: the session answer is read (identity, access), the
    // previous account's state cleared when it was another, preferences loaded
    async adopt(answer) { auth = answer && answer.csrf_token ? answer : null; try { const s = await api('/auth/session'); auth = s; } catch { /* the sign-in answer stands */ }
      if (auth) { const noted = noteLogin(auth); await settle(Promise.all([loadModels(), loadPrefs(noted)])); }
      dispatchEvent(new Event('edge-auth')); return auth; },
    config: () => readConfig(),
    // live checker S1: whether this site offers a tab (false only for a tab the config lists as hidden; known once
    // config() has answered, which the shell waits for before its first page)
    offers: tab => !hiddenTabs.includes(tab),
    legal: () => legal,
    // EXEC-MU-ACCOUNTS Phase 1 (contract section 4): the account routes; every refusal carries the server's message
    register: body => api('/auth/register', body),
    // `username`: another username after USERNAME_TAKEN (the code owner chooses it; contract section 4)
    verifyEmail: async (email, code, username) => { stopPrefs(); const answer = await api('/auth/register/verify', {email, code, ...(username ? {username} : {})}); return Edge.adopt(answer); },
    resendCode: (email, purpose) => api('/auth/code/resend', {email, purpose}),
    forgotPassword: email => api('/auth/password/forgot', {email}),
    resetPassword: (email, code, password, password_repeat) => api('/auth/password/reset', {email, code, password, password_repeat}),
    // re-check R2-20: the signed-in account's password change (other sessions end) and sign-out on every device
    changePassword: (current_password, password, password_repeat) => api('/auth/password/change', {current_password, password, password_repeat}),
    async signoutEverywhere() { try { await ES()?.prefs.flush(); } catch { /* best effort */ } stopPrefs();
      try { await api('/auth/sign-out-all', {}); } finally { try { await ES()?.clearUserState({signOut:true}); } catch { /* storage off */ } } reset(); },
    mfaEnroll: () => api('/auth/mfa/enroll', {}),
    // passing MFA rotates the session token (OWASP): the answer's csrf_token replaces the pending one before any write
    mfaVerify: async answer => { const fresh = await api('/auth/mfa/verify', answer); pending.csrf = '';
      if (fresh?.csrf_token) auth = fresh; return Edge.adopt(fresh?.csrf_token ? fresh : auth); },
    notePreference: key => { try { ES()?.prefs.note(key); } catch { /* not offered */ } },
    // M473: sign-out removes every `user` key and the user caches (storage registry), and the last-login mark
    async signout() { try { await ES()?.prefs.flush(); } catch { /* best effort */ } stopPrefs();
      try { await api('/auth/sign-out',{}); } finally { try { await ES()?.clearUserState({signOut:true}); } catch { /* storage off */ } } reset(); },
    createRun: body => api('/runs',body),
    modelList: () => models,
    loadModels: () => loadModels(),
    stopRun: id => api('/runs/'+encodeURIComponent(id)+'/stop',{}),
    bookmark: (id,bookmarked) => api('/conversations/'+encodeURIComponent(id)+'/preferences',{bookmarked},'PATCH'),
    hideConversation: id => api('/conversations/'+encodeURIComponent(id),undefined,'DELETE'),
    // EXEC-ASK-BRANCH: continue an answer in a new conversation (BRANCH) or in its side chat (SIDE)
    branch: (runId, kind, title) => api('/runs/'+encodeURIComponent(runId)+'/branch',{kind,title}),
    pin: (id,pinned) => api('/runs/'+encodeURIComponent(id)+'/preferences',{pinned},'PATCH'),
    exportTable: (conversationId, outputId, columns, titles) => api('/conversations/'+encodeURIComponent(conversationId)+'/outputs/'+encodeURIComponent(outputId)+'/export',{columns,titles}),
    exportUrl: id => /^exp_[0-9a-f]{24}$/.test(id) ? '/api/v1/exports/'+id : null,
    safeUrl: url => { try { const u = new URL(url); return ['http:','https:'].includes(u.protocol) && !u.hostname.endsWith('.railway.internal') ? u.href : null; } catch { return null; } }
  };
  ['edge-auth-monitor-conversations','edge-session','edge-active-run','edge-research-context'].forEach(k=>{localStorage.removeItem(k);sessionStorage.removeItem(k);});
})();
