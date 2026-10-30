/* The answer view contract (EXEC-X, user decision 2026-10-08: "setiap API jangan ter-lock ke suatu object").
   toView(envelope) is the only code that reads Orc's response shape. It returns a view model of display-ready parts:
   texts already worded (edge-labels.js), choices as action descriptors, and unknown fields kept for the generic view.
   The page renders the view model only, so a change in Orc's response is a change here; a change in look is a change
   in the page's HTML/CSS; a change in wording is a change in edge-labels.js. VERSION changes when a part changes shape. */
(() => {
  const VERSION = 1;
  const L = () => window.EdgeLabels;
  const empty = value => value == null || value === "" || (Array.isArray(value) && !value.length) || (typeof value === "object" && !Array.isArray(value) && !Object.keys(value).length);
  const label = key => L().fields[key] ?? String(key).replace(/_/g, " ").replace(/^./, c => c.toUpperCase());
  const number = value => new Intl.NumberFormat("id-ID", {maximumFractionDigits:Math.abs(value) < 1 ? 4 : 2}).format(value);
  function valueText(value) {
    if (typeof value === "boolean") return value ? L().ui.yes : L().ui.no;
    if (typeof value === "number") return number(value);
    // a backend code without words yet is made readable, never shown raw (M125)
    return L().values[value] ?? (/^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+$/.test(String(value)) ? String(value).replace(/_/g, " ").toLowerCase() : String(value));
  }
  const verdict = code => { const [text, tone] = L().verdicts[code] ?? [String(code ?? "—"), "neutral"]; return {code:String(code ?? ""), label:text, tone}; };
  const pick = (object, keys) => Object.fromEntries(Object.entries(object || {}).filter(([key]) => !keys.includes(key)));
  const unique = (lines, seen) => (lines || []).filter(line => { const key = String(line).trim(); if (!key || seen.has(key)) return false; seen.add(key); return true; });
  const threshold = (value, unit, outcomeUnit) => value == null ? null
    : `${number(value)}${L().units[unit || outcomeUnit] ?? (unit || outcomeUnit ? " " + valueText(unit || outcomeUnit) : "")}`;

  function status(envelope, domain) {
    const code = domain || envelope?.status, paused = Boolean(envelope?.execution?.pause);
    const key = code === "LIMITED" && paused ? "PAUSED" : code;
    const [text, tone] = L().status[key] ?? [code || "—", "neutral"];
    return {code:key || "", label:text, tone};
  }

  // ---- research plan ----
  function facts(item) {
    const out = [], ui = L().ui;
    const add = (name, value, note) => out.push({label:label(name), value, note});
    add("condition", item.condition);
    add("outcome", item.outcome);
    add("baseline", item.baseline ?? item.baseline_or_comparator);
    if (item.outcome_horizon_periods != null) add("outcome_horizon_periods", `${number(item.outcome_horizon_periods)} ${ui.periods}`);
    if (item.expected_direction) add("expected_direction", valueText(item.expected_direction));
    if ("success_rule" in item) add("success_rule", item.success_rule
      ? `${L().operators[item.success_rule.operator] ?? item.success_rule.operator} ${threshold(item.success_rule.value, item.success_rule.unit, item.outcome_unit)}`
      : ui.notStated, item.success_rule ? null : ui.successDefault);
    if ("min_effect" in item) add("min_effect", item.min_effect != null ? threshold(item.min_effect, item.min_effect_unit, item.outcome_unit) : ui.notStated,
      item.min_effect != null ? null : ui.minEffectDefault);
    if (item.success_definition) add("success_definition", item.success_definition);
    return out.filter(fact => !empty(fact.value));
  }
  const ITEM_SHOWN = ["title","hypothesis","angle_question","objective","condition","outcome","baseline","baseline_or_comparator","outcome_horizon_periods",
    "expected_direction","success_rule","min_effect","min_effect_unit","outcome_unit","success_definition","experiment_id","angle_id"];
  const PLAN_SHOWN = ["experiments","angles","objective","universe","time_scope","analysis_frequency","assumptions","limitations","confirmation_question",
    "original_question","plan_version","root_hypothesis","root_hypothesis_id","carried_inputs"];
  function plan(raw, envelope, seen) {
    if (!raw) return null;
    const ui = L().ui, kind = raw.angles ? ui.angle : ui.experiment;
    const id = envelope?.continuation?.plan_id || raw.plan_id || null;
    const items = (raw.experiments || raw.angles || []).map((item, index) => {
      const title = item.title || item.hypothesis || item.angle_question || item.objective;
      const more = pick(item, ITEM_SHOWN);
      return {key:item.experiment_id || item.angle_id || index, step:`${kind} ${index + 1}`, title,
        question:item.title ? item.angle_question || item.hypothesis : null,
        objective:item.objective && title !== item.objective ? item.objective : null,
        facts:facts(item), more:empty(more) ? null : more};
    });
    const more = pick(raw, PLAN_SHOWN);
    return {id, label:ui.plan, pendingLabel:ui.planPending, objective:raw.objective || null,
      root:raw.root_hypothesis ? {label:label("root_hypothesis"), text:raw.root_hypothesis} : null,
      summary:[["universe", raw.universe], ["time_scope", raw.time_scope], ["analysis_frequency", raw.analysis_frequency]]
        .filter(([, value]) => !empty(value)).map(([key, value]) => ({label:label(key), value:valueText(value)})),
      items, carried:empty(raw.carried_inputs) ? null : {label:label("carried_inputs"), value:raw.carried_inputs},
      more:empty(more) ? null : more, moreLabel:ui.planMore, itemMoreLabel:ui.designMore,
      notes:{assumptions:{label:ui.planAssumptions, items:unique(raw.assumptions, seen)}, limitations:{label:ui.planLimitations, items:unique(raw.limitations, seen)}},
      confirmation:raw.confirmation_question || null,
      choices:[{key:"APPROVE", label:ui.approve, primary:true, action:{type:"plan", plan:"APPROVE", planId:id, message:ui.approveMessage}},
               {key:"REVISE", label:ui.revise, hint:ui.reviseHint, action:{type:"plan", plan:"REVISE", planId:id}},
               {key:"CANCEL", label:ui.cancel, kind:"ghost", action:{type:"plan", plan:"CANCEL", planId:id, message:ui.cancelMessage}}]};
  }

  // ---- research findings ----
  const BACKEND_SHOWN = ["status","estimate","estimate_kind","ci","confidence_level","p_value","p_adjusted","effective_sample","sample_unit","estimate_unit"];
  function metrics(backend) {
    if (!backend) return [];
    const unit = backend.estimate_unit === "PERCENT" ? "%" : "", out = [];
    if (backend.estimate != null) out.push({label:backend.estimate_kind ? label("estimate") + " (" + String(backend.estimate_kind).toLowerCase().replace(/_/g, " ") + ")" : label("estimate"), value:number(backend.estimate) + unit});
    if (Array.isArray(backend.ci) && backend.ci.some(value => value != null)) out.push({label:`CI ${backend.confidence_level ? number(backend.confidence_level * (backend.confidence_level <= 1 ? 100 : 1)) + "%" : ""}`.trim(), value:`[${backend.ci.map(value => value == null ? "—" : number(value) + unit).join("; ")}]`});
    if (backend.p_value != null) out.push({label:"p", value:number(backend.p_value)});
    if (backend.p_adjusted != null) out.push({label:label("p_adjusted"), value:number(backend.p_adjusted)});
    if (backend.effective_sample != null) out.push({label:label("effective_sample"), value:number(backend.effective_sample) + (backend.sample_unit ? " " + valueText(backend.sample_unit).toLowerCase() : "")});
    return out;
  }
  function findings(list, planIndex) {
    if (!list?.length) return null;
    const ui = L().ui;
    return {label:ui.findings, items:list.map((finding, index) => {
      const id = finding.hypothesis_id || finding.angle_id, item = planIndex?.get(id), reading = finding.interpretation || {};
      const parts = ["answer", "evidence", "usefulness", "follow_up"].filter(key => reading[key]);
      const other = pick(reading, parts), backendMore = finding.backend ? pick(finding.backend, BACKEND_SHOWN) : null;
      return {key:id || index, title:item?.title || item?.hypothesis || item?.angle_question || label(id || ui.finding),
        verdict:verdict(finding.verdict ?? finding.status ?? finding.backend?.status), metrics:metrics(finding.backend),
        parts:parts.map(key => ({label:label(key), text:reading[key]})), other:empty(other) ? null : other,
        backendMore:empty(backendMore) ? null : backendMore, backendMoreLabel:ui.backendMore};
    })};
  }

  // ---- Sources (the Details panel) ----
  function sourceItem(item) {
    const st = item.status || null, rows = {}, named = Boolean(item.label);
    for (const [key, value] of Object.entries(item)) {
      if (["claim","quote","name","label","status","start","end"].includes(key) || (key === "kind" && st)) continue;
      if (named && key === "source" && value && typeof value === "object") {  // M125: the address is in the label
        for (const [inner, v] of Object.entries(value)) if (!["ref","output_id"].includes(inner)) rows[`${key}_${inner}`] = v;
        continue;
      }
      if (value && typeof value === "object" && !Array.isArray(value)) for (const [inner, v] of Object.entries(value)) rows[inner === "ref" ? key : `${key}_${inner}`] = v;
      else rows[key] = value;
    }
    return {title:item.label || item.claim || item.quote || item.name || label(item.kind || L().ui.sourcesEvidence), code:!named && Boolean(item.claim), status:st ? verdict(st) : null, rows};
  }
  function sources(envelope) {
    const ui = L().ui, raw = envelope || {}, evidence = raw.evidence || [], annotations = raw.annotations || [], record = raw.data_record;
    const sections = [];
    // EXEC-Y (user decision B 2026-10-09): web pages are listed here, not in the answer text; news has its own part
    const news = evidence.filter(item => item?.kind === "NEWS"), proof = evidence.filter(item => item?.kind !== "NEWS");
    // EXEC-IMPL-1016 Fase 4.1 (EDGE-CTX B): the tables this answer released come first, each with a request to export
    // it (a message, like a follow-up); the evidence list stays, folded, as the references of the figures
    // an output's label is its verification status (DATA_COVERAGE_VERIFIED), never its name; a JSON output is not a table
    const tables = (record?.outputs || []).filter(o => o && o.ref && raw.request_id && o.request_id === raw.request_id
        && o.type !== 'JSON' && (o.columns || []).length)
      .map(o => {
        const name = String(o.name || o.ref).replace(/_/g, ' ');
        const notes = typeof o.definition?.notes === 'string' ? o.definition.notes.slice(0, 240) : null;
        const rows = Object.fromEntries([[ui.sourceContent, notes], [ui.sourceRows, o.row_count],
          [ui.sourceColumns, (o.columns || []).length || null],
          [ui.sourceAsOf, o.data_as_of]].filter(([, value]) => value !== undefined && value !== null && value !== ''));
        return {title:name, code:false, status:null, rows, ref:o.ref, outputId:o.output_id, actionLabel:ui.askExport,
          action:{type:"message", message:ui.exportMessage.replace("{ref}", o.ref).replace("{name}", name)}};
      });
    if (tables.length) sections.push({title:`${ui.sourcesTables} (${tables.length})`, items:tables});
    if (proof.length) sections.push({title:`${tables.length ? ui.sourcesNumbers : ui.sourcesEvidence} (${proof.length})`,
      items:proof.map(sourceItem), folded:Boolean(tables.length)});
    if (news.length) sections.push({title:`${ui.sourcesNews} (${news.length})`, items:news.map(sourceItem)});
    if (annotations.length) sections.push({title:`${ui.sourcesClaims} (${annotations.length})`, items:annotations.map(sourceItem)});
    // EXEC-FRICTION (M142): what the backend refused on the way to this answer, as Orc wrote it in plain words
    const hurdles = (raw.execution?.hurdles || []).filter(item => item?.text);
    if (hurdles.length) sections.push({title:`${ui.sourcesHurdles} (${hurdles.length})`,
      items:hurdles.map(item => ({title:item.text, code:false, status:null, rows:{}}))});
    // P4: only the parts edge-labels.js names are summarised for the reader; the whole record stays in Detail teknis
    const named = L().record || {};
    const summary = record && Object.fromEntries(Object.entries(record).filter(([key, value]) => named[key] && !empty(value))
      .map(([key, value]) => [named[key], Array.isArray(value) ? `${value.length} ${ui.items}` : typeof value === "object" ? `${Object.keys(value).length} ${ui.items}` : value]));
    return {empty:!sections.length && empty(record), emptyText:ui.sourcesEmpty, sections,
      record:empty(record) ? null : {title:ui.sourcesRecord, summary, raw:record, technicalLabel:ui.technical}};
  }

  // EXEC-IMPL-1016 Fase 4.3 (UI-1015B): Orc's progress of a running answer (/runs/{id}/progress) for the reader: the
  // step running now, the finished steps newest last, and the time since Orc started
  function progressView(data) {
    const ui = L().ui, steps = Array.isArray(data?.steps) ? data.steps : [];
    if (data?.status !== 'RUNNING' && data?.status !== 'FINISHED') return null;
    const note = state => state === 'refused' ? ui.progressRefused : state === 'failed' ? ui.progressFailed : null;
    const current = [...steps].reverse().find(step => step.state === 'running');
    const done = steps.filter(step => step.state !== 'running').map(step => ({label:step.label, note:note(step.state),
      duration:durationText(step.duration_ms)}));
    // EXEC-M181 (plan P4): how long the step running now has taken ("Thinking · 2m 10s"), counted on by the page
    return {current:current ? current.label : null, elapsed:durationText(data.elapsed_ms), done,
      currentStep:current ? {started:Number(current.started_ms) || 0, ms:Number(current.duration_ms) || 0} : null,
      doneTitle:ui.progressDone.replace('{n}', String(done.length)),
      earlier:data.earlier_steps ? ui.progressEarlier.replace('{n}', String(data.earlier_steps)) : null};
  }

  // EXEC-IMPL-1016 Fase 4.2 (EDGE-CTX A): Orc's answer_tables say, per table built from a table instruction, its titles,
  // the output column behind each and the shown rows' positions. A rendered table takes the first unused entry with the
  // same titles and row count; a table the model typed itself has none and cannot be attached.
  const plain = text => String(text ?? '').replace(/[*_`]/g, '').trim();
  function tableSource(tables, head, rowCount, used) {
    if (!Array.isArray(tables)) return null;
    const titles = head.map(plain);
    const index = tables.findIndex((t, i) => !used.includes(i) && Array.isArray(t?.titles) && Array.isArray(t?.rows)
      && t.rows.length === rowCount && t.titles.length === titles.length && t.titles.every((x, k) => plain(x) === titles[k]));
    if (index < 0) return null;
    used.push(index);
    return tables[index];
  }
  function selection(source, rows, picked, title) {
    const chosen = picked.length ? [...picked].sort((a, b) => a - b) : rows.map((_, i) => i);
    return {ref:source.ref, ...(source.output_id ? {output_id:source.output_id} : {}),
      ...(title ? {title:String(title).slice(0, 200)} : {}), columns:(source.columns || []).slice(0, 12),
      rows:chosen.slice(0, 50).map(i => source.rows[i]).filter(Number.isInteger),
      shown_values:chosen.slice(0, 50).map(i => (rows[i] || []).slice(0, 12).map(cell => plain(cell).slice(0, 80)))};
  }
  function selectionLabel(sel) {
    const ui = L().ui;
    if (sel && sel.kind === 'TEXT') {
      const quote = plain(sel.quote).replace(/\s+/g, ' ');
      const short = quote.length > 48 ? quote.slice(0, 47) + '…' : quote;
      return ui.attachedText.replace('{quote}', short)
        .replace('{n}', String((sel.figures || []).length));
    }
    const rows = Array.isArray(sel.rows) ? sel.rows.length : Number(sel.rows) || 0;
    return ui.attachedChip.replace('{title}', sel.title || sel.ref).replace('{n}', String(rows));
  }
  // EXEC-IMPL-1017 Fase 3 (user 2026-10-16: "select as context ... klik kanan kayak claude"): a passage the user
  // selected anywhere in an answer, with the figures in it as Orc listed them (answer_figures) or as an answer
  // table's cells (answer_tables); Orc reads each figure again from its reference
  const ATTACH_SECTIONS = ['ANSWER', 'ASSUMPTIONS', 'LIMITATIONS', 'FINDINGS', 'PLAN', 'OTHER'];
  function textSelection({requestId, section, quote, figures}) {
    const seen = new Set();
    const kept = (figures || []).filter(f => f && typeof f.ref === 'string' && f.ref.length <= 200
      && !/[{}|\n]/.test(f.ref) && !seen.has(f.ref) && seen.add(f.ref)).slice(0, 20)
      .map(f => ({ref:f.ref, shown:plain(f.shown).slice(0, 40) || f.ref.slice(-40)}));
    return {kind:'TEXT', ...(requestId ? {request_id:String(requestId).slice(0, 100)} : {}),
      section:ATTACH_SECTIONS.includes(section) ? section : 'OTHER',
      quote:String(quote || '').replace(/\s+\n/g, '\n').trim().slice(0, 1000), figures:kept};
  }
  // EXEC-UI-1024 2c: the attachments as sent: a comment only when the user wrote one (at most 500 characters)
  function attachmentsPayload(items) {
    return (items || []).map(item => {
      const {comment, ...rest} = item || {};
      const text = String(comment || '').trim().slice(0, 500);
      return text ? {...rest, comment:text} : rest;
    });
  }
  // the reference of an answer table's cell: its released table, the source row and the output column
  function cellRef(source, rowIndex, column) {
    const row = source && Array.isArray(source.rows) ? source.rows[rowIndex] : undefined;
    const name = source && Array.isArray(source.columns) ? source.columns[column] : undefined;
    return Number.isInteger(row) && name ? `${source.ref}.rows[_row=${row}].${name}` : null;
  }

  // EXEC-DURATION (user 2026-10-12): how long a run took, from Orc's execution.duration_ms
  function durationText(ms) {
    if (typeof ms !== 'number' || !Number.isFinite(ms) || ms < 0) return null;
    const seconds = Math.round(ms / 1000);
    if (seconds < 60) return `${seconds}s`;
    const minutes = Math.floor(seconds / 60), rest = seconds % 60;
    if (minutes < 60) return rest ? `${minutes}m ${rest}s` : `${minutes}m`;
    return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
  }

  // ---- the whole answer ----
  function toView(envelope, {domainStatus, planIndex} = {}) {
    const ui = L().ui, final = envelope?.response || {}, execution = envelope?.execution || {}, pause = execution.pause;
    const seen = new Set(), planned = plan(final.research_plan, envelope, seen);
    // the pause question the backend appended is shown once, as the pause part (exact text, no parsing)
    const answer = pause?.question && final.answer?.includes(pause.question) ? final.answer.replace(pause.question, "").trimEnd() : final.answer;
    const lists = [["assumptions", final.assumptions], ["limitations", final.limitations]]
      .map(([key, values]) => ({label:ui[key], items:unique(values, seen)})).filter(list => list.items.length);
    return {
      version:VERSION,
      status:status(envelope, domainStatus),
      meta:{requestId:envelope?.request_id ?? null, model:execution.model ?? null, reasoningLevel:execution.reasoning_level ?? null, lane:execution.lane ?? null, tokens:execution.total_tokens, cost:execution.cost ?? null, duration:durationText(execution.duration_ms)},
      evidence:envelope?.evidence_label ? {code:envelope.evidence_label, label:ui.evidencePrefix + (L().evidence[envelope.evidence_label] ?? envelope.evidence_label),
        // EXEC 2026-10-20 (screenshot T): a positive evidence label carries a green check
        positive:!['UNVERIFIED_EXPLORATORY', 'NOT_VALIDATED'].includes(envelope.evidence_label)} : null,
      claims:(envelope?.annotations || []).filter(item => item?.quote).map(item => [String(item.quote).trim(), item.note || item.kind]),
      // EXEC-UI-1013B: a question that is the whole answer is shown once, in the choices part
      answer:(answer && answer !== final.clarification_question ? answer : null),
      clarification:final.clarification_question ? clarification(final, envelope, ui) : null,
      pause:pause ? {label:ui.paused, region:ui.pausedRegion, reason:pause.reason || null, hint:ui.pauseHint,
        choices:(pause.options || []).map(option => ({key:option.id, label:option.label, title:option.needs_input ? ui.needsInput : undefined,
          action:option.needs_input ? {type:"input", hint:option.label} : {type:"message", message:option.label}}))} : null,
      plan:planned,
      findings:findings(final.research_findings, planIndex),
      lists,
      methodology:final.methodology ? {label:ui.methodology, text:final.methodology} : null,
      artifacts:(envelope?.artifacts || []).map(file => ({id:file.export_id, label:file.file_name || file.filename || file.export_id})),
      next:next(envelope?.follow_ups),
      // EXEC-IMPL-1017 Fase 3: what the user attached to this question, and the attached figures the backend found
      // exactly recomputed from raw data
      attached:(envelope?.attached || []).map(item => selectionLabel(item)),
      reproduced:(envelope?.reproductions || []).filter(r => r?.status === 'MATCH')
        .map(r => ui.reproduced.replace('{figure}', String(r.figure ?? '')))
    };
  }
  // EXEC-UI-1013B (gambar 1): the router's choices that share a route come as numbered lines of the question; Orc also
  // sends them as labels (mode4.choices) with the question alone (mode4.question), so each is a button that sends its
  // label, like a typed reply, and the numbered lines are not shown twice
  function clarification(final, envelope, ui) {
    const routed = (envelope?.options || []).map((option, index) => ({key:option.route || index, label:option.label, kind:"secondary", note:option.route === "EXPLORE" ? ui.exploreNote : undefined, action:{type:"route", route:option.route, message:option.label}}));
    const mode4 = envelope?.mode4 || {};
    const labels = routed.length ? [] : (Array.isArray(mode4.choices) ? mode4.choices : []).filter(label => typeof label === "string" && label.trim());
    const choices = routed.length ? routed : labels.map((label, index) => ({key:"choice" + index, label, kind:"secondary", action:{type:"message", message:label}}));
    const question = typeof mode4.question === "string" ? mode4.question.trim() : "";
    return {text:choices.length && question ? question : final.clarification_question, choices};
  }
  // EXEC-Y Fase 2: what the user could ask next, grouped by kind; a click sends the words as the next message
  function next(items) {
    const ui = L().ui, titles = {FOLLOW_UP:ui.followUps, INSIGHT_IDEA:ui.insightIdeas, DATA_TEST:ui.dataTest};
    const groups = [];
    for (const item of items || []) {
      if (!item?.label) continue;
      const kind = titles[item.kind] ? item.kind : "FOLLOW_UP";
      let group = groups.find(g => g.key === kind);
      if (!group) groups.push(group = {key:kind, label:titles[kind], choices:[]});
      group.choices.push({key:kind + group.choices.length, label:item.label, kind:"secondary", action:{type:"message", message:item.label}});
    }
    const order = Object.keys(titles);
    return groups.length ? groups.sort((a, b) => order.indexOf(a.key) - order.indexOf(b.key)) : null;
  }
  // the experiments and angles of a conversation's plans, so a finding is titled by its plan's words
  function planIndex(envelopes) {
    const index = new Map();
    for (const envelope of envelopes || []) {
      const raw = envelope?.response?.research_plan;
      for (const item of raw?.experiments || raw?.angles || []) {
        if (item.hypothesis_id) index.set(item.hypothesis_id, item);
        if (item.angle_id) index.set(item.angle_id, item);
      }
    }
    return index;
  }
  // EXEC-SHARE-UI (user 2026-10-19): what the share card's footer names: the request and the latest date of the data
  // this answer's tables were read to (data_as_of of its released outputs; any output when none of this request has one)
  function shareInfo(envelope) {
    const outputs = (envelope?.data_record?.outputs || []).filter(o => o && typeof o.data_as_of === 'string' && o.data_as_of);
    const own = outputs.filter(o => o.request_id === envelope?.request_id);
    const dates = (own.length ? own : outputs).map(o => o.data_as_of.slice(0, 10)).sort();
    return {requestId:envelope?.request_id ?? null, dataAsOf:dates.length ? dates[dates.length - 1] : null};
  }
  window.EdgeView = {VERSION, toView, sources, planIndex, durationText, progressView, tableSource, selection, selectionLabel, textSelection, attachmentsPayload, cellRef, shareInfo, format:{empty, label, number, valueText, verdict}};
})();
