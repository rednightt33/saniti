/* Preview mode of the EDGE page (preview/edge_preview.py build): the real page and its scripts, with the BFF replaced
   by saved dev responses (tests/fixtures/orc_responses.json) held in the built file. No login, no server, no AI call.
   Times are fixed so two builds of the same page render the same DOM. */
(() => {
  const FX = window.__EDGE_FIXTURES__;
  const now = Date.parse('2026-10-08T12:00:00Z');
  const iso = minutes => new Date(now - minutes * 60000).toISOString();
  const turn = (id, message, name, minutes) => ({request_id:id, user_message:message, created_at:iso(minutes), completed_at:iso(minutes - 1),
    status:'COMPLETED', run_status:FX[name].status, response:{...JSON.parse(JSON.stringify(FX[name])), request_id:id}});
  const conversations = [
    {id:'conv_preview_paused', title:'Jawaban yang dijeda (pilihan sebagai tombol)', turns:[turn('edge_p1', 'Siapa broker yang paling sering beli saat bank crash, dan apa tipenya?', 'paused', 5)]},
    {id:'conv_preview_confirm', title:'Rencana dengan nilai yang perlu dikonfirmasi', turns:[turn('edge_c1', 'ubah ambang suksesnya jadi minimal satu persen', 'plan_confirm', 12)]},
    {id:'conv_preview_v1', title:'Volume BBRI ≥ 2× → naik 5 hari? (rencana lalu hasil)', turns:[
      turn('edge_v1a', 'Uji ini: kalau volume BBRI minimal 2 kali rata-rata volume 20 hari sebelumnya, apakah harganya naik dalam 5 hari berikutnya? Pakai data 2023 sampai 2024 saja. Buatkan rencana ujinya.', 'plan_v1', 30),
      turn('edge_v1b', 'Setujui rencana riset', 'answer_table', 25)]},
    {id:'conv_preview_v2', title:'Riset multi-sudut: rencana lalu temuan per sudut', turns:[
      turn('edge_v2a', 'Periksa dari beberapa sisi lain apakah beli besar RB di bank BUMN diikuti return 5 hari lebih tinggi.', 'plan_v2', 60),
      turn('edge_v2b', 'Setujui rencana riset', 'findings_v2', 55)]},
    {id:'conv_preview_f1', title:'Temuan satu eksperimen', turns:[turn('edge_f1', 'Apakah hipotesis BBCA ini didukung data?', 'findings_v1', 90)]},
    {id:'conv_preview_ann', title:'Klaim yang ditandai (catatan saat disentuh)', turns:[turn('edge_a1', 'Broker mana yang paling konsisten beli saat crash?', 'annotated', 120)]}
  ];
  const ui = Object.fromEntries(conversations.map(c => [c.id, {bookmarked:false, pinned:[]}]));
  const jobs = {};
  let counter = 0;
  const json = (body, status = 200) => Promise.resolve(new Response(JSON.stringify(body), {status, headers:{'Content-Type':'application/json'}}));
  const meta = c => ({conversation_id:c.id, title:c.title, bookmarked:ui[c.id].bookmarked, created_at:c.turns[0].created_at,
    updated_at:c.turns.at(-1).completed_at, pinned_request_ids:ui[c.id].pinned});
  const canned = (text, request_id) => ({request_id, status:'COMPLETED', execution:{model:'pratinjau-statis'},
    response:{response_type:'ANSWER', answer:text, clarification_question:null, assumptions:[], limitations:[], research_plan:null}});
  function reply(body, request_id) {
    const action = body.plan_reply?.action;
    if (action === 'APPROVE') return {...JSON.parse(JSON.stringify(FX.answer_table)), request_id};
    const said = action === 'REVISE' ? `revisi rencana: "${body.plan_reply.revision_instruction}"` : action === 'CANCEL' ? 'membatalkan rencana' : `"${body.message}"`;
    return canned(`**Pratinjau statis.** Anda mengirim ${said}.\n\nDi aplikasi asli, AI menjawab di sini. Halaman ini tidak memanggil AI atau server mana pun.`, request_id);
  }
  window.fetch = async (input, init = {}) => {
    const url = new URL(typeof input === 'string' ? input : input.url, 'https://edge.local');
    const path = url.pathname.replace(/^\/api\/v1/, ''), method = (init.method || 'GET').toUpperCase();
    const body = init.body ? JSON.parse(init.body) : {};
    let m;
    if (path === '/auth/session') return json({login:'pratinjau', csrf_token:'static', capabilities:[]});
    if (path === '/auth/sign-in') return json({login:'pratinjau', csrf_token:'static', capabilities:[]});
    if (path === '/auth/sign-out') return json({authenticated:false});
    if (path === '/runs' && method === 'GET') return json({active:null});
    if (path === '/conversations') return json({items:conversations.map(meta), next_offset:null});
    if ((m = path.match(/^\/conversations\/([^/]+)\/messages$/))) {
      const c = conversations.find(x => x.id === decodeURIComponent(m[1]));
      return c ? json({conversation:meta(c), messages:c.turns, has_more:false, next_after:null, research_plan:null}) : json({error:{code:'NOT_FOUND'}}, 404);
    }
    if ((m = path.match(/^\/conversations\/([^/]+)\/preferences$/))) {
      const id = decodeURIComponent(m[1]); if ('bookmarked' in body) ui[id].bookmarked = body.bookmarked;
      return json({...meta(conversations.find(x => x.id === id))});
    }
    if ((m = path.match(/^\/runs\/([^/]+)\/preferences$/))) {
      const id = decodeURIComponent(m[1]), c = conversations.find(x => x.turns.some(t => t.request_id === id));
      ui[c.id].pinned = body.pinned ? [...new Set([...ui[c.id].pinned, id])] : ui[c.id].pinned.filter(x => x !== id);
      return json({...meta(c)});
    }
    if (path === '/runs' && method === 'POST') {
      const request_id = 'edge_static_' + (++counter);
      let c = conversations.find(x => x.id === body.conversation_id);
      if (!c) { c = {id:'conv_static_' + counter, title:body.message.slice(0, 80), turns:[]}; conversations.unshift(c); ui[c.id] = {bookmarked:false, pinned:[]}; }
      const response = reply(body, request_id);
      const t = {request_id, user_message:body.message, created_at:new Date(now).toISOString(), completed_at:new Date(now).toISOString(), status:'COMPLETED', run_status:response.status, response};
      c.turns.push(t);
      jobs[request_id] = {request_id, conversation_id:c.id, state:'FINISHED', state_version:2, run_status:response.status, response, completed_at:t.completed_at, updated_at:t.completed_at};
      return json({request_id, conversation_id:c.id, state:'QUEUED', state_version:0, created:true}, 202);
    }
    if ((m = path.match(/^\/runs\/([^/]+)$/))) return json(jobs[decodeURIComponent(m[1])] || {}, jobs[decodeURIComponent(m[1])] ? 200 : 404);
    return json({error:{code:'NOT_AVAILABLE_IN_PREVIEW'}}, 404);
  };
  // the run "finishes" shortly after it is sent, through the same snapshot event the real stream uses
  window.EventSource = class {
    constructor(url) {
      this.listeners = {}; const id = decodeURIComponent(url.split('/runs/')[1].split('/')[0]);
      setTimeout(() => this.emit({...jobs[id], state:'RUNNING', state_version:1}), 250);
      setTimeout(() => this.emit(jobs[id]), 1100);
    }
    emit(data) { (this.listeners.snapshot || []).forEach(fn => fn({data:JSON.stringify(data)})); }
    addEventListener(name, fn) { (this.listeners[name] ||= []).push(fn); }
    close() { this.listeners = {}; }
  };
  addEventListener('DOMContentLoaded', () => {
    const note = document.createElement('div');
    note.textContent = 'Pratinjau statis M124: data contoh dari dev, tanpa server dan tanpa AI. Pilih percakapan di kiri.';
    note.style.cssText = 'position:fixed;left:50%;top:66px;transform:translateX(-50%);z-index:9999;background:#111;color:#fff;font:12px system-ui,sans-serif;padding:6px 12px;border-radius:999px;opacity:.85;pointer-events:none;max-width:calc(100vw - 32px);text-align:center';
    document.body.appendChild(note);
    // open the first conversation so the page starts on an answer
    const open = () => { const first = document.querySelector('.conversation-list .conversation'); if (first) first.click(); else setTimeout(open, 150); };
    setTimeout(open, 300);
  });
})();
