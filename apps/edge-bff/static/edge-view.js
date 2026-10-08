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
    return L().values[value] ?? String(value);
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
      choices:[{key:"APPROVE", label:ui.approve, action:{type:"plan", plan:"APPROVE", planId:id, message:ui.approveMessage}},
               {key:"REVISE", label:ui.revise, action:{type:"plan", plan:"REVISE", planId:id}},
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
    const st = item.status || null, rows = {};
    for (const [key, value] of Object.entries(item)) {
      if (["claim","quote","name","status","start","end"].includes(key) || (key === "kind" && st)) continue;
      if (value && typeof value === "object" && !Array.isArray(value)) for (const [inner, v] of Object.entries(value)) rows[inner === "ref" ? key : `${key}_${inner}`] = v;
      else rows[key] = value;
    }
    return {title:item.claim || item.quote || item.name || item.label || label(item.kind || L().ui.sourcesEvidence), code:Boolean(item.claim), status:st ? verdict(st) : null, rows};
  }
  function sources(envelope) {
    const ui = L().ui, raw = envelope || {}, evidence = raw.evidence || [], annotations = raw.annotations || [], record = raw.data_record;
    const sections = [];
    if (evidence.length) sections.push({title:`${ui.sourcesEvidence} (${evidence.length})`, items:evidence.map(sourceItem)});
    if (annotations.length) sections.push({title:`${ui.sourcesClaims} (${annotations.length})`, items:annotations.map(sourceItem)});
    const summary = record && Object.fromEntries(Object.entries(record).filter(([, value]) => !empty(value))
      .map(([key, value]) => [key, Array.isArray(value) ? `${value.length} ${ui.items}` : typeof value === "object" ? `${Object.keys(value).length} ${ui.items}` : value]));
    return {empty:!sections.length && empty(record), emptyText:ui.sourcesEmpty, sections,
      record:empty(record) ? null : {title:ui.sourcesRecord, summary, raw:record, technicalLabel:ui.technical}};
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
      meta:{requestId:envelope?.request_id ?? null, model:execution.model ?? null, tokens:execution.total_tokens, cost:execution.cost ?? null},
      evidence:envelope?.evidence_label ? {code:envelope.evidence_label, label:ui.evidencePrefix + (L().evidence[envelope.evidence_label] ?? envelope.evidence_label)} : null,
      claims:(envelope?.annotations || []).filter(item => item?.quote).map(item => [String(item.quote).trim(), item.note || item.kind]),
      answer:answer || null,
      clarification:final.clarification_question ? {text:final.clarification_question,
        choices:(envelope?.options || []).map((option, index) => ({key:option.route || index, label:option.label, kind:"secondary", action:{type:"route", route:option.route, message:option.label}}))} : null,
      pause:pause ? {label:ui.paused, region:ui.pausedRegion, reason:pause.reason || null, hint:ui.pauseHint,
        choices:(pause.options || []).map(option => ({key:option.id, label:option.label, title:option.needs_input ? ui.needsInput : undefined,
          action:option.needs_input ? {type:"input", hint:option.label} : {type:"message", message:option.label}}))} : null,
      plan:planned,
      findings:findings(final.research_findings, planIndex),
      lists,
      methodology:final.methodology ? {label:ui.methodology, text:final.methodology} : null,
      artifacts:(envelope?.artifacts || []).map(file => ({id:file.export_id, label:file.filename || file.export_id}))
    };
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
  window.EdgeView = {VERSION, toView, sources, planIndex, format:{empty, label, number, valueText, verdict}};
})();
