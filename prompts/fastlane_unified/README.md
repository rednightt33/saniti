# Two fastlane profiles — inspected implementation brief and prompt

**Status: draft for implementation review. No application change, switch change or rollout is authorised by this
document.** User asked for a prompt and prior inspection. The candidate system text is
[DRAFT_SYSTEM_PROMPT.md](DRAFT_SYSTEM_PROMPT.md); it is not imported or rendered by Orc. Inspection identifiers are
in [INFRA_INSPECTION.json](INFRA_INSPECTION.json). Approval to prepare this work is in ../../PLAN.md.

User request, 2026-10-19, verbatim:

> Okay, buatkan prompt ya. Buat 2 lane terpisah. 1 existing, 1 lagi adalah AI router yang digabung dengan AI pelaksana. Jadi bisa fallback jika diperlukan. Also, sebelum buat prompt, please inspect current infra dulu agar prompt tidak contradict dengan kondisi backend.
> Semua yang berkaitan dengan ORC dependensinya harus di cek agar perubahan ini tidak hanya isolated.

## 1. Inspected baseline

Repository `rednightt33/saniti`, branch main, HEAD and fetched origin/main
`7c8712b473166b44deecca7e4a7f609e81df6afe`. Project lucid-patience, environment dev. User-facing inspection date:
19 October 2026, UTC+7. Active application source is Git, not an untracked Railway upload.

| Dependency | Inspected live/source condition | What the proposal must preserve |
|---|---|---|
| EDGE/BFF | Git main; one replica; deployment 22c9671d-c117-4db6-9b6e-cd9e5a53f7d9, source 5679bd5, SUCCESS | Authentication, server-owned identity, durable queue, submission fingerprint, lease/heartbeat, stop, SSE/polling, retry reconciliation, model selection, attachments, exports |
| Orc | Git main; one replica; deployment 4138d8bd-70e9-451d-9e77-faf91f6966c2, source 5679bd5, SUCCESS | Request lifecycle, shared agent/tool loop, negotiated capabilities, budgets, conversation state, result store and audit |
| SQL Governor | Git main; d4c22eaa-11a3-479c-a926-497e8f213f0c, source 2334b44, SUCCESS | Structured requests rather than arbitrary model SQL; catalog/allowlist checks, valid joins, bounded read-only extraction, dataset manifests and separate dataset-access credential |
| Python sandbox | Git main; 84fa7fa3-6bda-46af-8162-7d13d42fde7b, source 454272e, SUCCESS; /data volume | Enforced isolation, governed bundles/sessions, owner scope, outputs, completion/provenance, statistical-test recording, capacity, retention and resource budgets |
| Web Governor | Git main; 46bd709d-2f2e-457b-bd43-a438e48d8520, source 2c093df, SUCCESS; /data volume | Permitted web evidence tools, budgets, providers and independent backend model calls; event store on Postgres-E8GM |
| Audit store | Git main; 776f4e5a-ed3a-4009-8800-a96062cb34e0, source bcb1322, SUCCESS | Existing outbox/ingest contracts, execution/completion IDs, source hashes, readback and exclusion of secrets/private reasoning |
| Main Postgres | Online; read-only metadata query succeeded; transaction_read_only=on | Catalogs, conversation/turn/memory, research audit, ai_audit.ingest_outbox and edge_bff.jobs; no market-data/schema mutation for this proposal |
| Postgres-E8GM | Online; Web Governor points to its private hostname | Existing web/event storage; it is a separate dependency from the main market database |
| Object storage | Orc result, SQL dataset and audit bucket endpoints configured at t3.storageapi.dev | Existing restricted credentials, reference/checksum/retention semantics; this audit did not perform a storage write/read round-trip |
| Model provider | Orc AI_MODEL=deepseek/deepseek-v4.1-flash, AI_MODEL_SWITCH=1; per-message model selection available | User-selected analyst model/level, provider preferences, session identity and pricing; do not change model/provider as a side effect |

All six application services are Online with one running replica. Their service roots have no source-file diff
between their respective deployed commits and the inspected main baseline, except the planned docs-only root commit.
Seven credential links were compared in memory and match: BFF→Orc, Orc→sandbox, Orc→SQL, sandbox→SQL dataset access,
Orc→web, sandbox→audit and SQL→audit. No credential value is recorded here.

The environment health overview reports **one unresolved critical notification on main Postgres**, while the service
is Online and the read-only query succeeds. Its reason is not exposed by the inspected tool; it is neither diagnosed
nor dismissed here. Recheck the notification during rollout preflight. An older staged environment patch has zero
changes and was not applied. None of these observations authorises an unrelated infrastructure fix.

### Live flags and relevant limits

- Orc: first-message router, conversation router, ask-back, Mode 4, fastlane, DataNeed, result store, reuse, run memory,
  session attach, table directives, value references, exploratory tests and insight v2 are enabled.
- AI_ENABLE_CATALOG_PROTOCOL=false; AI_FASTLANE_DRAFT_CHECK=false; AI_FASTLANE_GATE_ADVICE=true;
  AI_ENABLE_EVIDENCE=false. Do not promise an active strict draft/evidence gate simply because code for it exists.
- AI_MAX_ANALYSIS_SECONDS=1800; AI_MAX_TOOL_CALLS=60; AI_MAX_TOOL_ITERATIONS=60;
  AI_MAX_CONTEXT_TOKENS=500000; AI_MAX_HISTORY_TOKENS=150000; AI_MAX_OUTPUT_TOKENS=24000.
  Provider-specific limits can be lower. Request timeout is 600 seconds; fastlane has its existing 90-second
  model-call timeout/lowered-reasoning retry policy. A single AI still makes multiple model/tool calls.
- EDGE timeout=3900 seconds; lease=90; heartbeat=20; poll=2. Do not change deadlines or create another worker.
- Sandbox configured memory limit=4096 MB, concurrent sessions=4, bundle max rows=10000000, open wait=60 seconds;
  runtime metadata remains authoritative for negotiated capabilities and lower per-operation limits.
- SQL configured max tables=7, max joins=6, heavy concurrency=2; dataset/query limits remain separately enforced.
- Presentation source supports 50 rows and 12 columns, default 10 rows. Explicit user scope should override a short
  default within these limits. EDGE can collapse rows; it must not silently substitute a top-N result.
- AI_ENABLE_MANUAL_AGENT=true offers Claude manual only when explicitly chosen. Keep troubleshooting/fallback
  behaviour; it does not replace ordinary per-message models.
- No hard per-request USD ceiling was found in Orc's inspected configuration. Time/token/tool/resource limits
  constrain cost, and usage is recorded. Do not claim a new monetary guarantee or silently introduce a price cap.

## 2. What the current router actually controls

The fast lane still passes through Mode4Orchestrator's first-message and conversation routing. In
`app/mode4.py`, EXPLORE's MODE4 path becomes ANALYSIS on fastlane; in `app/orchestrator.py`, a fresh RESEARCH
request also becomes an analysis-mode data need. Thus these labels do not select three independent compute services.

The routing result also controls ask-back, user-intent notes, design values/facts, referents, pending offers,
continuation behaviour, memory readings and the conversation title. `_apply_turn_kind` intersects available tools
with READ_EFFECTS for CLARIFY/CONVERSATIONAL/FACT. `_explore_mode` uses EXPLORE/INSIGHT to select exploratory prompts
and insight-v2 statistical checking. Dropping router calls alone would lose those functions or retain hidden locks.

Bank-table regression `edge_ac1cb75b15c5898d023bfa70abccd063`: router selected CLARIFY, Python was absent, only
export_result ran, and a 10-row monthly-winner table was displayed. The complete source output had 480 entity-month
rows. The requested wide table was never computed. The stored needs_computation field is null, no mode4_handoff
occurred, yet the prose claimed a transformation was running. This is a routing/fulfilment regression, not evidence
that sandbox remained offline. Preserve the original positive-day-average definition in the regression fixture.

## 3. Two user choices; retain the existing lane protocol

Use two fastlane choices in EDGE, backed by one additional **proposed** request field:

| User choice | Request contract | Behaviour |
|---|---|---|
| Fast — Existing | lane=fast, routing_mode=existing (or routing_mode omitted) | Current routers, prompts, tool desks, checks and behaviour |
| Fast — Unified | lane=fast, routing_mode=unified | The selected analyst model understands intent and performs the work in the same agent loop |

`routing_mode: existing|unified` and `AI_ENABLE_UNIFIED_FASTLANE` are proposals, absent from live configuration/code.
Preserve lane=standard and lane omitted for other callers. Do not add a third lane string and miss the many checks
for `lane == fast` in timeouts, reasoning, statistical evidence and presentation. EDGE previously removed its lane
selector; add just these two fastlane profile choices and preserve the existing model/level selection and layout.
Initial default is Existing; no silent migration of users or current runs. Explicit Unified with a disabled gate
returns a clear supported error before inference; do not silently execute another profile under that identity.

Profile is pinned per submitted request, never inferred from a question or changed by model text. Persist requested
and effective profile in existing JSON where possible. Include explicit routing_mode in BFF and Orc request
fingerprints; Orc's current fingerprint omits lane/model and has no new profile field, whereas BFF hashes the full
input. Keep legacy hashes for old requests without the new field so retries of stored requests still work. Reject
changing profile under the same request/submission ID. Do not reset resource or provider budgets during a retry.

Fallback means selecting Existing for a new request or disabling Unified for new admissions. Do not restart an
in-flight Unified run through Existing: a provider call, extraction or sandbox POST may already have run. Reconcile
its original ID, preserve completed outputs, and make any user-requested rerun a distinct request with lineage.
The existing model/provider retry policies remain separate from routing-profile fallback.

For direct API callers, Unified v1 accepts an ordinary message with analysis_path omitted/AUTO/ANALYSIS.
An explicit legacy RESEARCH/MODE4 path or signed legacy plan execution is incompatible and must receive a clear
error before inference, with Existing as the available path. Do not confuse the server's current default Mode 4
with an explicit caller instruction: Unified deliberately bypasses that default router/pipeline for its own run.

## 4. Required integration work before the prompt can run

| Area | Required change/check |
|---|---|
| BFF API/client/queue | Add strict routing_mode validation and cross-field rule (Unified only with fast); whitelist/forward it; preserve it in durable input, after-stop queued messages, fingerprints and reconciled retries. Preserve server-owned owner/history and all auth/Stop/lease checks. |
| EDGE | Two fastlane profile choices, default Existing; use server-reported capability and handle the ten-minute model/capability cache during rollout. Keep model choice independent. Save/display effective profile with the run; older responses without it remain readable. Wording in edge-labels.js, response adaptation in edge-view.js; round-trip any one-file preview edit. |
| Orc schema/config/entrypoint | Add the field and feature gate. Resolve profile inside normal request lifecycle and model-choice contexts, before legacy default-mode routing can select a Mode4 sub-run. Unified dispatch bypasses first/turn routers and Mode4 judgement, while retaining progress, stop, conversation locking/replay, readiness recovery and source recording. Do not turn off global router switches to simulate this. |
| Shared agent/tool loop | Unified uses the negotiated FASTLANE permission envelope on every ordinary turn. Do not set CLARIFY/FACT/CONVERSATIONAL as an access-limiting preclassification. Keep per-tool effects, ResearchGuard, parameter validation, data contracts and completion checks. No arbitrary SQL, credential access or direct network execution is added. |
| Prompt composition | Compose shared rules plus DRAFT_SYSTEM_PROMPT's judgement module plus the actual response contract. Exclude contradictory legacy read-only and forced-route notes on Unified only. Do not append it under a prompt that still forbids the needed tools. Existing prompt remains byte-for-byte stable for the same flags. |
| Exploration/statistics | Decouple capability and statistical validity from a prior EXPLORE/INSIGHT label. Main AI can choose a descriptive calculation or recorded hypothesis helpers. Keep hypothesis recording, corrections, provenance and actual sample checks based on the tools/results used. Do not force every pivot or chat into hypothesis tests to keep insight_v2 switched on. Review fastlane_note, explore_note, _explore_mode and the statistical gates together. |
| Conversation/memory | Supply relevant prior user text, output definitions/columns, source data, attachments and pending offers directly to the main AI. Keep existing memo/facts parsing, source scopes, output fetch/restore and supporting tables. Do not replace history with only a router summary or discard definitions when switching profiles. |
| Legacy plans/choices | Preserve signed pending-plan approval/revision/cancellation. V1 Unified must refuse an incompatible legacy pending-plan continuation before inference and offer Existing/new conversation, rather than consume/reinterpret it. Test stored continuation auto-attachment, explicit plan_reply and free-text acceptance. For old quick-choice buttons, pass the chosen label/context as bounded application data; do not re-enter old read-only routing. A rejected profile must not strand a RUNNING conversation turn. |
| Response/title/options | Reuse ANSWER/CLARIFICATION/LIMITATION, source references and table/export contracts. No mandatory new route JSON. A free-text clarification uses existing clarification_question; do not demand unimplemented quick-choice fields. Do not fabricate mode4.router.title: use the existing message-title fallback or a separately validated title contract. Add optional effective-profile metadata without claiming an old mode/router ran. |
| Small auxiliary calls | First/turn classification calls are absent in Unified. Legacy plan-reply classification remains on Existing. Catalog-before-web judgement can initially keep its current small checker as a labelled auxiliary call; it is not a first/turn router and must not lock the turn's compute tools. Existing post-answer follow-up generation can also remain. Count both in total cost and explicitly document them; do not claim exactly one inference or no other Orc model calls. Any later merger into the main model needs its own conditional output-schema/tests. |
| Web Governor | Main AI still uses permitted research_web/reference tools; Web Governor's own search/extraction/classification models stay intact. One conversational brain does not mean one model throughout all external evidence services. Preserve web caps, event data and source citations; do not change provider/slot values. |
| SQL + sandbox | Reuse existing APIs/credentials and governed DataNeed ANALYSIS flow. Validate that full-data processing, output reuse/pivot, owner isolation, session capacity/release, attach, rejection, completion and statistics behave identically. No service source change should be needed unless a concrete contract gap is found. |
| Result storage/export | Both profiles read the same authorised conversation outputs with their original definitions. A pivot releases a new table before export; export_result cannot stand in for transformation. Preserve output checksums, expiration and storage callbacks. |
| Audit/metrics | Record requested/effective profile, prompt version/hash and fallback reason in run logs and persisted evidence. AuditOutbox currently selects fields explicitly; ensure metadata reaches its supported summary/event contract and consumer readback instead of adding an unrecognised payload field. Compare model calls, tools, time, token/cache use and total cost, including helpers/web calls; never log private reasoning. |
| Infrastructure | Keep one Orc/BFF deployment, existing workers, storage and private domains. No new compute service, price/Feature04 cron, warehouse schema, permissions or Railway source upload. Changes go through scoped Git paths. Any required config/IaC change is separately reviewed against live state. |

### Existing limits and lifecycle are not replaced by a prompt

The M187 RuntimeRecovery handshake and authenticated execution-readiness check stay shared. If a sandbox misses
startup, both profiles wait through the existing BFF queue; neither is a way around an offline dependency or exhausted
Railway credit. Keep `Initiating sandbox session.` tied to a real session open. Keep timeouts, cancelled work,
ambiguous execution handling and session ownership independent of profile and language-model choices.

The current fastlane enables advisory gate behaviour and disables strict draft checking. A prompt can request
fulfilment checks but cannot prove them. Where the user explicitly supplied an entity set, period, shape or row
coverage, validate observable output metadata against those constraints; missing requirements must cause correction
or an honest limitation. Semantic interpretation remains with the selected AI, not a new keyword router. Do not
disable provenance to make the regression pass, or promise correctness from a prompt alone.

## 5. Acceptance and safe comparison

Use deterministic integration tests first. Paid A/B inference or production deployment needs the user's separate go;
this task only prepares the prompt/design. Compare with identical data, context, chosen model/level and limits.

1. Existing: first/follow-up routes, quick choices, titles, pending plans and prompt snapshot unchanged; standard
   callers and old API payloads still work. Unified off by default; explicit unavailable/invalid combinations fail
   clearly. The BFF accepts/forwards the new field only after an Orc capability advertises it.
2. Unified: no classify_first/classify_turn call and no equivalent hidden preclassification model call; selected
   model receives the original question/context and invokes data tools when needed. Auxiliary calls are separately
   identified. Same IDs and session key; no duplicate inference or calculation on replay.
3. The bank regression: all authorised banking tickers, positive-day daily-return average per calendar month as
   originally requested, preserved monthly ranks, a released wide table, and no monthly-winner substitution. Do not
   hardcode entity counts/tickers/months into the system prompt. A row for every source entity is required, including
   legitimate missing-value cases with a stated reason. Clarify only a materially unspecified overall rank order.
4. Transform an available long result by load_output/pivot/release without re-extracting price history. Explicit
   all rows within current display limits appear; larger requests get accurate truncation/complete export, never a
   false claim that unseen work is running. Table references and unit formatting remain validated.
5. Greeting, factual/reference query, ambiguous request, follow-up explanation, follow-up that needs computation,
   scope/period corrections, attachments and new topic. No unnecessary sandbox for a greeting or hypotheses for a
   simple table. No permanent read-only lock when computation becomes necessary later in the same turn.
6. User hypothesis and open exploration both work, with recorded tests and corrections only when applicable.
   Check that removing router labels does not silently turn off insight-v2 evidence checks.
7. Cross-profile history/output reuse, current versus historical classifications, missing data, unsupported helper,
   capability mismatch, owner mismatch, unavailable dependency, deadline, Stop, ambiguous POST, after-stop message,
   export expiration and legacy pending plan all preserve the existing guarantees.
8. Outcomes: task fulfilment, unsupported-number count, all-entity coverage, correct table grain, extra questions,
   latency, paid model calls, total cost/cache use and retries. No presumption that fewer router calls is cheaper.
   Compare multiple ordinary cases as well as the known failure; do not tune the prompt to one bank question.

Before rollout, inspect pending PLAN/EXEC work and live state, check the Postgres notification and active runs,
review changes, and run the relevant Orc/BFF/SQL/sandbox/audit contract tests. Regenerate AI_TOOLS, AI_MODELS,
AI_ROUTER as applicable; record a separate rendered Unified prompt snapshot without replacing the Existing snapshot,
and rerun router benchmarks for the retained path. Update README/context/changelogs/error ledger and verification.
Roll out Orc capability support before exposing the BFF/EDGE choice; account for capability caching. Enable Unified
for deliberate testing first; Existing stays the default until results and a user decision justify changing it.

## 6. Prompt for the implementation agent

Use this brief and DRAFT_SYSTEM_PROMPT.md as the implementation specification after execution is authorised:

> Implement two selectable fastlane profiles, Existing and Unified, on the inspected Saniti architecture. Preserve
> standard and every existing runtime/data guarantee. Re-inspect main and live deployments, then build the full
> request-to-output path in section 4; do not merely append a prompt or disable global routers. The Unified main
> AI owns conversational judgement and execution, while the backend owns permissions, scope, budgets, lifecycle,
> validity and audit. Use the candidate system module only with the documented backend integration and actual
> conditional response schema. Keep provider/model choices unchanged. Deliver the acceptance evidence in section 5,
> a concrete Git diff, rollback path and exact deployment evidence if rollout was authorised. Do not claim the
> existing banking-table regression is fixed until the resulting released table actually fulfils that request.

This design task does not run that implementation prompt or modify rendered system prompts. No new variables,
request fields, UI controls or runtime behaviour described as proposed above exist until implementation lands.
