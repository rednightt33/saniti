/* Same-origin API/session and response adapters. No credentials or response history in browser storage. */
(() => {
  let auth = null;
  const followers = new Set();
  class ApiError extends Error {
    constructor(code, status) { super(code); this.status = status; }
  }
  // EXEC-MODELS: the offered models are read once per session, before the work page shows (sign-in or a restored
  // session waits up to 3 s for them), so their arrival never redraws the page while the user types
  let models = {data:null, failed:false, pending:null};
  const reset = () => { auth = null; models = {data:null, failed:false, pending:null}; followers.forEach(close => close()); followers.clear(); dispatchEvent(new Event('edge-auth')); };
  async function api(path, body, method = body === undefined ? 'GET' : 'POST') {
    const headers = method === 'GET' ? {} : { 'X-CSRF-Token':auth?.csrf_token || '', ...(body === undefined ? {} : {'Content-Type':'application/json'}) };
    const res = await fetch('/api/v1' + path, { method, headers, credentials:'same-origin', ...(body === undefined ? {} : {body:JSON.stringify(body)}) });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      if (res.status === 401 && path !== '/auth/sign-in') reset();
      throw new ApiError(data.error?.code || (res.status === 401 ? 'Authentication required' : 'Request unavailable'), res.status);
    }
    return data;
  }
  const terminal = s => ['FINISHED','FAILED','INTERRUPTED'].includes(s.state);
  // EXEC-X (M124): the frame stays English (user decision 2026-10-08) but says what the saved response is
  const DOMAIN = {COMPLETED:'Completed',AWAITING_CONFIRMATION:'Awaiting approval',NEEDS_CLARIFICATION:'Needs your reply',LIMITED:'Limited',FAILED:'Failed'};
  const statusLabel = (status, domain, pause) => ['submitted','running','streaming'].includes(status) ? 'Running' : status === 'failed' && !domain ? 'Failed'
    : pause && domain === 'LIMITED' ? 'Paused' : DOMAIN[domain] || (status ? status[0].toUpperCase() + status.slice(1) : '—');
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
    return result.map(ui => ({id:ui.conversation_id,title:ui.title,bookmarked:ui.bookmarked,createdAt:ui.created_at,updatedAt:ui.updated_at,lastMessage:ui.last_message||null,messages:[],runs:[]}));
  }
  // EXEC-UI-1012 C: the first question's answer is headed by the short title Orc's first-message router wrote
  const routerTitle = response => String(response?.mode4?.router?.title || '').split(/\s+/).join(' ').trim().slice(0, 80) || null;
  function adaptRun(turn, ui = {}) {
    const raw = turn.response;
    const final = raw?.response;
    const failed = turn.status === 'FAILED' || turn.status === 'INTERRUPTED' || raw?.status === 'FAILED';
    return {id:turn.request_id,question:turn.user_message || ui.title || 'Research response',createdAt:turn.created_at,completedAt:turn.completed_at,
      status:turn.status === 'RUNNING' ? 'running' : failed ? 'failed' : 'completed',domainStatus:raw?.status || turn.run_status,paused:Boolean(raw?.execution?.pause),stopped:Boolean(raw?.execution?.stopped),
      mode:'Standard',attachments:[],pinned:(ui.pinned_request_ids || []).includes(turn.request_id),
      error:raw?.error?.code || turn.error_code,errorText:raw?.error?.user_message,raw,result:final ? {title:routerTitle(raw) || turn.user_message?.slice(0,80) || ui.title || 'Research response',condition:final.answer || final.clarification_question || '',final} : null,
      sources:[...(raw?.evidence || []), ...(raw?.annotations || []), ...(raw?.data_record ? [{name:'Data record',record:raw.data_record}] : [])],
      steps:[{id:'saved-state',label:turn.status === 'RUNNING' ? 'AI request running' : 'Saved response: ' + statusLabel('completed', raw?.status || turn.run_status, raw?.execution?.pause),status:turn.status === 'RUNNING' ? 'running' : failed ? 'failed' : 'completed',detail:'Persisted lifecycle state'}]};
  }
  async function messages(id) {
    let after = -1, turns = [], page;
    do { page = await api('/conversations/' + encodeURIComponent(id) + '/messages?limit=50&after=' + after); turns.push(...page.messages); after = page.next_after; } while (page.has_more);
    const ui = page.conversation;
    return {id, title:ui.title,bookmarked:ui.bookmarked,createdAt:ui.created_at,updatedAt:ui.updated_at,plan:page.research_plan,
      messages:turns.map(t=>({id:t.request_id+'-user',role:'user',content:t.user_message,createdAt:t.created_at,runId:t.request_id})),runs:turns.map(t=>adaptRun(t,ui))};
  }
  const stateRun = (snapshot, previous) => ({...previous,
    status:snapshot.error_code === 'STOPPED_BY_USER' ? 'cancelled' : terminal(snapshot) ? snapshot.state === 'FINISHED' && snapshot.run_status !== 'FAILED' && !snapshot.expired ? 'completed' : 'failed' : snapshot.state === 'QUEUED' ? 'submitted' : 'running',
    domainStatus:snapshot.run_status,paused:Boolean((snapshot.response || previous.raw)?.execution?.pause),stopped:Boolean((snapshot.response || previous.raw)?.execution?.stopped),error:snapshot.expired ? 'Conversation expired; the saved response is no longer available.' : snapshot.error_code || snapshot.response?.error?.code,
    errorText:snapshot.expired ? undefined : (snapshot.response || previous.raw)?.error?.user_message,
    completedAt:snapshot.completed_at,raw:snapshot.response || previous.raw,
    result:snapshot.response?.response ? {title:routerTitle(snapshot.response) || previous.question.slice(0,80),condition:snapshot.response.response.answer || snapshot.response.response.clarification_question || '',final:snapshot.response.response} : previous.result,
    sources:snapshot.response ? [...(snapshot.response.evidence || []),...(snapshot.response.annotations || []),...(snapshot.response.data_record ? [{name:'Data record',record:snapshot.response.data_record}] : [])] : previous.sources,
    steps:[{id:'state',label:{QUEUED:'Queued',RUNNING:'AI request running',RECOVERING:'Recovering delivery',FINISHED:'Saved response: '+statusLabel('completed',snapshot.run_status,snapshot.response?.execution?.pause),FAILED:'Request failed',INTERRUPTED:'Delivery interrupted'}[snapshot.state],status:terminal(snapshot) ? snapshot.state === 'FINISHED' && snapshot.run_status !== 'FAILED' && !snapshot.expired ? 'completed' : 'failed' : 'running',detail:snapshot.updated_at}]
  });
  const loadModels = () => models.pending || (models.pending = api('/models')
    .then(data => { const ok = Array.isArray(data?.models) && data.models.length > 0; models.data = ok ? data : null; models.failed = !ok; })
    .catch(() => { models.failed = true; }));
  const settle = promise => Promise.race([promise, new Promise(resolve => setTimeout(resolve, 3000))]);
  window.Edge = {
    api,follow,terminal,conversations,messages,adaptRun,stateRun,statusLabel,
    get auth() { return auth; },
    async session() { try { auth = await api('/auth/session'); } catch { auth = null; } if (auth) await settle(loadModels()); return auth; },
    async signin(login,password) { auth = await api('/auth/sign-in',{login,password}); await settle(loadModels()); dispatchEvent(new Event('edge-auth')); return auth; },
    async signout() { await api('/auth/sign-out',{}); reset(); },
    createRun: body => api('/runs',body),
    modelList: () => models,
    loadModels: () => loadModels(),
    stopRun: id => api('/runs/'+encodeURIComponent(id)+'/stop',{}),
    bookmark: (id,bookmarked) => api('/conversations/'+encodeURIComponent(id)+'/preferences',{bookmarked},'PATCH'),
    hideConversation: id => api('/conversations/'+encodeURIComponent(id),undefined,'DELETE'),
    pin: (id,pinned) => api('/runs/'+encodeURIComponent(id)+'/preferences',{pinned},'PATCH'),
    exportUrl: id => /^exp_[0-9a-f]{24}$/.test(id) ? '/api/v1/exports/'+id : null,
    safeUrl: url => { try { const u = new URL(url); return ['http:','https:'].includes(u.protocol) && !u.hostname.endsWith('.railway.internal') ? u.href : null; } catch { return null; } }
  };
  ['edge-auth-monitor-conversations','edge-session','edge-active-run','edge-research-context'].forEach(k=>{localStorage.removeItem(k);sessionStorage.removeItem(k);});
})();
