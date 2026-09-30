# Multi-Angle Research (research v2)

Status (2026-09-29): on `main` and live on dev with both flags on
(`PY_SANDBOX_MULTI_ANGLE_RESEARCH_ENABLED`, `AI_ENABLE_MULTI_ANGLE_RESEARCH`). Golden run 3 passed (4/4 answered;
defects of runs 1 and 2 recorded as M30–M35, S12, S13 in `ERRORS_AND_SOLUTIONS.md`; see `RAILWAY_CHANGELOG.md`).
Migration `20260929_001` is applied on dev in the scope the user chose after the dry run: the four tools are
registered (inactive) in `Tool_Catalog`; `AI_research_catalog` is unchanged, because it has none of the eight method
ids (§8, C07). Open item from the golden runs: S13 in `ERRORS_AND_SOLUTIONS.md` (G12 fixed on 2026-09-29). Suite20 findings and their
fixes: `MULTI_ANGLE_FIX_PLAN.md` (items 1–7 live on dev since 2026-09-29: the research library table
`AI_research_library` and `get_research_library` (§10), two to six angles, each angle's design checked at feasibility,
no early finalize, negation-aware agreement check, cross-request forward returns).

A Research run examines one root hypothesis from 2 to 6 analytical angles (3 to 6 before 2026-09-29). Each angle has
one approved method, its
own data contract inside a governed bundle, and exactly one backend-authored finding. Analysis (mode ANALYSIS) is
unchanged and has no angle minimum. Everything is behind `AI_ENABLE_MULTI_ANGLE_RESEARCH` (market-ai-orc) and
`PY_SANDBOX_MULTI_ANGLE_RESEARCH_ENABLED` (market-python-sandbox), both off by default; with them off, research v1
(`research_plan/v1`, `rpc1`, findings v1) and Analysis behave exactly as before.

## 1. Decisions confirmed by the user (2026-09-29)

| Topic | Decision |
|---|---|
| Push target | Commit and push only the feature branch; no merge to `main` (auto-deploy) without a separate approval. |
| Finding statuses | Exactly the plan's five: `SUPPORTED`, `PARTIALLY_SUPPORTED`, `INSUFFICIENT_EVIDENCE`, `INVALID`, `NOT_RUN`. Evidence against a hypothesis has no status of its own; it is `INSUFFICIENT_EVIDENCE`, and the finding keeps the observed direction (`evidence_direction`) so the synthesis map can show direction conflicts. |
| Grouped execution | The model writes the code of each bundle group through `run_research_code(bundle_group_id, code)`; the orchestrator's executor promotes drafts, prepares bundles, opens and completes sessions. Groups run one after another (at most one open session per run, S08); `AI_RESEARCH_MAX_PARALLEL_GROUPS` accepts only 1 in this release. |
| Validation levels | `FORMULA_AND_STATISTICS_VERIFIED` only for declarative inputs (governed columns, the restricted expression grammar of `runtime/expression.py`, a forward return computed by the backend); a frame built by model code is `STATISTICS_VERIFIED`; `research_custom` is `EXECUTION_ONLY`. |
| Method catalog | A guarded forward migration (not applied) that marks the eight methods active only when their ids exist in `AI_research_catalog`; its preflight fails and names the missing ids otherwise. No new catalog rows. |

## 2. Discrepancies between the plan and the repository

| Plan statement | Repository | Resolution |
|---|---|---|
| §3.3 "no formal research-statistics helper"; `complete_analysis` never verifies anything | Research findings v1 is live on dev: `saniti.event_summary`, `runtime/research_stats.py`, `app/research_findings.py` recompute the sample category and verdict from a released aggregate table | v1 stays unchanged; v2 reuses its conventions (effective sample, Welch on date means, Wilson/Newcombe, sample categories) |
| §8.2 new `runtime/research_stats.py`, §8.4 `app/research_findings.py` | Both names exist (findings v1) | New modules: `runtime/research_engines.py` (pure engines), `runtime/research_inputs.py` (declarative inputs), `app/research_validation.py` (validator v2); v1 files untouched |
| "angle A / angle B" (findings v1) | v1 uses "angle" for its two readings of one experiment | v2 "angle" means one analytical question of the plan; v1 wording unchanged |
| §3.3 "8 tool iterations and 12 tool calls" | Code defaults; dev runs 20 / 20 (`RAILWAY_CHANGELOG.md`) | No change; the grouped interface needs about 3 + groups tool calls |
| §6.1 `plan_id` in the plan body | The backend issues `rp_...` ids at signing; the model never writes ids | `plan_id` stays in the continuation and the governance declaration, not in the model-written plan |
| §6.1 angle fields | Findings v1 plans also carry `min_effect` | v2 angles carry `min_effect` (nullable) for the sample category; the hit rate uses outcome > 0 |
| §6.5 promote drafts after approval | v1 hands the draft spec to the model, which resubmits it | v2 only: the executor promotes the signed drafts (`POST /v1/research-runs`); v1 unchanged |
| §7.3 parallel groups | S08 (one open session per run) and `PY_SANDBOX_MAX_SESSIONS` 2 for all runs | Sequential groups (see §1) |
| §14.6 end-to-end golden questions | Deployment and live data are outside this change | Golden scenarios run locally: sandbox integration tests on real sessions with fixture data, orchestrator tests with a scripted model; live runs after an approved deployment |

## 3. Contracts

Hashes are SHA-256 over canonical JSON (sorted keys, compact separators, UTF-8), as elsewhere in the repository.

### 3.1 Method registry (both services, version 1)

| method_id | method_family (engine) |
|---|---|
| `conditional_distribution` | `CONDITIONAL_OUTCOME` |
| `threshold_sensitivity` | `CONDITIONAL_OUTCOME` |
| `streak_persistence` | `PERSISTENCE` |
| `regime_comparison` | `GROUP_COMPARISON` |
| `cohort_comparison` | `GROUP_COMPARISON` |
| `quantile_ranking` | `QUANTILE_RANKING` |
| `lead_lag` | `TEMPORAL_DEPENDENCY` |
| `correlation_dependency` | `TEMPORAL_DEPENDENCY` |

`registry_sha256` = hash of the sorted id/family pairs and the engine version. The orchestrator activates v2 only when
the sandbox reports exactly this registry.

### 3.2 `research_plan/v2` (model-written, backend-validated)

Top level: `plan_version`, `original_question`, `objective`, `root_hypothesis_id`, `root_hypothesis`, `universe`,
`time_scope`, `analysis_frequency`, `angles` (2 to 6; `AI_RESEARCH_MIN_ANGLES` / `AI_RESEARCH_MAX_ANGLES` may only
narrow this, and `AI_RESEARCH_MIN_FAMILIES`, off by default, may require that many method families),
`assumptions`, `limitations`, `confirmation_question`.

Angle: `angle_id`, `title`, `angle_question`, `method_id`, `method_family`, `objective`, `condition`, `outcome`,
`baseline_or_comparator`, `expected_direction` (HIGHER, LOWER, DIFFERENT), `outcome_horizon_periods` (1-260),
`outcome_unit` (PERCENT, DECIMAL, OTHER), `min_effect` (nullable), `parameters` (below), `candidate_count`,
`pairwise_comparisons`, `multiple_testing_policy`, `holdout_required`, `minimum_sample_value`,
`minimum_sample_unit`, `why_distinct`.

`parameters` (every field present, null when unused): `thresholds`, `threshold_operator` (`>=`, `<=`), `lags`,
`primary_lag`, `buckets`, `groups`, `comparison` (PAIRWISE, VS_REST, FIRST_VS_OTHERS), `streak_lengths`,
`rolling_window`, `baseline_mode` (COMPLEMENT, ALL), `correlation_method` (PEARSON, SPEARMAN).

Validation: angle count; unique `angle_id`; unique normalized `angle_question`; `method_family` equals the registry's;
the parameters each method requires, and none it cannot use; `candidate_count` and `pairwise_comparisons` at least what
the parameters imply (thresholds, lags, streak lengths; group comparisons); a multiple-testing policy other than NONE
for more than one comparison; per angle at most 50 candidates and 20,000 pairwise comparisons, per plan at most 150
candidates and 20,000 pairwise comparisons; no code, SQL or helper calls in any text.

`angle_signature` = hash of the normalized question, method_id, normalized condition, outcome and comparator, horizon,
unit, direction and the normalized parameters. Two angles with the same signature are rejected; the same method or
family in several angles is allowed.

### 3.3 `research_data_plan/v1` and `angle_data_contract/v1` (backend-produced)

`check_research_feasibility` receives one data requirement per angle (DataNeedSpec v2 requests and relationships, in
the angle's own ids). The planner:

1. validates the structure (every angle of the call, 1-8 requests each, no sampling);
2. normalizes each request to a key (table, entity and time columns, canonical scope, frequencies, resample, and its
   INNER restrictions with their own keys) and merges equal keys across angles: columns are united, ranges united by
   dates, buffers take the larger span, bundle ids are assigned deterministically (`<request_group_id>_<letter>`);
3. tries one bundle group; when the merged spec exceeds the validator's request limit or the estimated rows or parts
   exceed the sandbox bundle limits, packs the angles greedily in plan order using each request's estimated rows,
   never splitting an angle, up to `AI_RESEARCH_MAX_BUNDLE_GROUPS` (an angle that alone exceeds the limits is
   `ANGLE_EXCEEDS_BUNDLE_LIMITS`);
4. validates each group with the sandbox (`POST /v1/data-needs/check`, a draft per group) and estimates it with the
   Execution Planner (the same per-part estimate as extraction);
5. returns `SINGLE_BUNDLE`, `MULTI_BUNDLE` or `INFEASIBLE`, the groups, the angle mapping, the per-angle
   requirements, the merge decisions, the uncovered angles, the estimates, the drafts and spec hashes, every angle's
   contract and `research_data_plan_sha256`.

An angle contract lists the bundle group, the bundle request ids the angle may read, per request the columns, ranges,
buffers, scope hash, frequencies and resample rules, the relationships, `time_basis`, the mapping from the angle's
own request and range ids to the bundle's, the group's `data_contract_sha256` and its own
`angle_data_contract_sha256`.

### 3.4 `rpc2` continuation

Claims: `v` 2, `typ`, `pid`, `ph` (plan hash), `dph` (research data plan hash), `dids` (ordered draft ids), `shs`
(ordered DataNeedSpec hashes), `gm` (angle to group), `ach` (angle contract hashes), `org`, `cid`, `iat`, `exp`,
signed with HMAC-SHA256 (`rpc2.<payload>.<signature>`). The continuation carries the exact plan and the exact
research data plan (in history mode SERVER the conversation store keeps both). Verification recomputes every hash and
compares every bound component; a `rpc1` token is never read as `rpc2` or the reverse.

### 3.5 `research_governance/v2` (built by the orchestrator, reviewed by the sandbox)

`governance_version`, `plan_id`, `root_hypothesis_id`, `root_hypothesis`, `angles[]` (angle id, method, signature,
statistics values, parameters, budgets, holdout, minimum sample, `followup_of_angle_id`, bundle group, contract hash),
`angle_to_bundle_group`, plan totals, and the plan, data plan, spec, draft and contract hashes. The Research Governor
v2 checks the registry, the budgets per angle and per plan, `max_angles_per_plan` (separate from the hypothesis
budget), the multiple-testing policy, reservations of revisions and follow-up semantics for a repeated angle.

### 3.6 `research_findings/v2` (backend-authored, one per approved angle)

`plan_id`, `angle_id`, `angle_question`, `bundle_group_id`, `session_id`, `method_id`, `method_family`, `status`,
`status_reason`, `evidence_direction`, `validation_level`, `sample` (raw, effective, unit, category, minimum detectable
effect, smallest effect of interest), `estimates` (primary estimate with interval, adjusted interval, p-values),
`comparator`, `multiple_testing`, `method_payload`, `warnings`, `limitations`, hashes (plan, data plan, contract,
bundle, code, helper, validator), `released_output_ids`.

## 4. Status rules

1. `NOT_RUN`: the angle's bundle group failed (bundle, session or execution limits), or the run was finalized without
   a finding for the angle.
2. `INVALID`: the angle's input broke its contract (dataset, column, range, entity or date outside it), its
   parameters differ from the approved ones, it was recorded twice, or its declarative input could not be reproduced.
3. `EXECUTION_ONLY` findings (research_custom) are at most `INSUFFICIENT_EVIDENCE`.
4. `INSUFFICIENT_EVIDENCE`: sample INSUFFICIENT or ANECDOTAL, a declared minimum sample not met, no difference that
   the data can distinguish from zero, or an effect against the expected direction (evidence_direction OPPOSITE).
5. `SUPPORTED`: the primary estimate's multiple-testing adjusted interval excludes zero in the expected direction (for
   DIFFERENT, either direction), and every secondary check passes (for example quantile monotonicity, no candidate
   significant in the other direction, the holdout agrees).
6. `PARTIALLY_SUPPORTED`: significant in the expected direction without the adjustment only, or with a failed
   secondary check, or only at a candidate other than the predeclared one.

The minimum effect (M26) does not change a status in this release; it sets the sample category (UNDERPOWERED), as in
findings v1.

## 5. Flags and capability

| Service | Variable | Default |
|---|---|---|
| market-python-sandbox | `PY_SANDBOX_MULTI_ANGLE_RESEARCH_ENABLED` | false |
| market-ai-orc | `AI_ENABLE_MULTI_ANGLE_RESEARCH` | false |
| market-ai-orc | `AI_RESEARCH_MIN_ANGLES` | 2 (2-6; 3 before 2026-09-29) |
| market-ai-orc | `AI_RESEARCH_MAX_ANGLES` | 6 (min-6) |
| market-ai-orc | `AI_RESEARCH_MIN_FAMILIES` | 0 = off (0-5, at most the maximum angles) |
| market-ai-orc | `AI_RESEARCH_MAX_BUNDLE_GROUPS` | 3 (1-6) |
| market-ai-orc | `AI_RESEARCH_MAX_PARALLEL_GROUPS` | 1 (only 1 accepted) |

The sandbox reports `multi_angle_research` in `GET /v1/runtime` (enabled, version 2, angle limits, grouped
execution, findings version, method registry and its hash, the research library hash `library_sha256`, bundle
limits). The orchestrator activates v2 only when the flag is on, DataNeed v2, plan confirmation and plan feasibility
are active, the capability matches exactly, and the active rows of `AI_research_library` equal its own research
library (§10); otherwise it logs `multi_angle_research_inactive` (and `research_library_mismatch` for a library
difference) and keeps v1.

## 6. Rollout and rollback (not executed)

Sandbox first (flag off), verify `GET /v1/runtime`, enable the sandbox flag on dev; then market-ai-orc (flag off),
verify research v1 and Analysis, enable the orc flag; run the golden questions; apply the catalog migration last.
Rollback: orc flag off, then sandbox flag off; v1 contracts stay available.

## 7. market-ai-orc behaviour (implemented)

| Area | Behaviour |
|---|---|
| Startup | `negotiate()` (`app/research_plan_v2.py`) compares the sandbox capability with the local registry (version, grouped execution, findings and governance versions, method ids and registry hash, angle policy). Only a full match registers `check_research_feasibility` (in place of `check_data_feasibility`) and the three run tools; otherwise `multi_angle_research_inactive` is logged and v1 stays. |
| Prompt and schema | The MULTI-ANGLE RESEARCH PLAN and MULTI-ANGLE FINDINGS rules replace the Research Plan, plan feasibility and findings v1 rules (no figures except list numbering). The final schema carries `research_plan/v2` and one `AngleFindingReport` per angle. With the flag off the prompt, schema and tool definitions are byte-identical (tested). |
| Plan turn | A RESEARCH data need is refused before the sandbox (`MULTI_ANGLE_PLAN_REQUIRED`). The plan turn reads the methods with `get_research_library` (the prompt names none). `check_research_feasibility` receives each angle's design and applies the rules the final plan enforces plus the library's data requirements before any data plan is built (M38); a short future buffer is widened to the horizon and reported. A v2 plan is issued only for exactly the angles and the designs of the run's last FEASIBLE research data plan (`angle_design_sha256s`), within `AI_RESEARCH_MIN_ANGLES`..`AI_RESEARCH_MAX_ANGLES` (and `AI_RESEARCH_MIN_FAMILIES`), and with a second, later range for every angle that requires a holdout; two reminders (`PLAN_FEASIBILITY`, `PLAN_FEASIBILITY_2`), then a LIMITATION without a token. A v1 plan while v2 is active (or the reverse) is refused the same way. |
| Continuation | `rpc2` is issued with the research data plan; the continuation returns it to the caller, and the conversation store keeps it with the plan (history mode SERVER). A v1 continuation while v2 is active, or a v2 one while it is not, is never executed: the turn becomes REPLAN (`RESEARCH_PLAN_TOKEN_INVALID`, reason `PLAN_VERSION`). |
| Approved turn | The executor of the verified plan is created for this request only; the tools are discovery, the three run tools, `inspect_session` and `get_session_output`. An approval with no `start_research_run` is reminded once and stays pending (M19; the same continuation goes back). The first `complete_research_run` with `finalize` true while an approved angle is unrecorded (and at least two tool calls remain) returns `INCOMPLETE` `ANGLES_NOT_RECORDED` with the missing angles; the second is accepted (M36). Group sessions left open are closed at the end of the run. |
| Answer gate | One entry per approved angle with the backend status unchanged, all four interpretation parts, the effective sample in `evidence`, governed figures only, no status wording stronger than the backend's (supported wording only for SUPPORTED or PARTIALLY_SUPPORTED; "no effect" wording never), and an agreement between angles only when the synthesis map allows one (a phrase negated in its own clause is not a claim, P09). Two repairs (`FINDINGS`, `FINDINGS_2`), then a LIMITATION that keeps one backend-authored `research_findings` entry per angle. |
| Verification wording | When the run's `calculation_validation` is `STATISTICS_VERIFIED` or `FORMULA_AND_STATISTICS_VERIFIED`, saying that the statistics were verified is allowed (the sandbox moves that claim to `claims_allowed`); the limitations always name the exact level. |
| Evidence label | Unchanged contract: findings figures are `DATA_COVERAGE_VERIFIED` sources. The per-angle validation level is reported in the findings, the limitations and the audit records, not by a new label value. |
| Audit | `execution.research.experiments` (and so `AI_research_run_audit.experiments`) holds one entry per approved angle with `payload_version` `research_findings/v2`, angle, method, family, status, reason, bundle group and research run; the v2 fields are omitted from other entries. `execution.research_plan` gains `plan_version`, `research_data_plan_sha256` and `research_run_id` only for v2. |

## 8. Tool catalog migration (applied on dev, Tool_Catalog only)

`database/migrations/20260929_001_multi_angle_research_catalog.sql` registers `check_research_feasibility`,
`start_research_run`, `run_research_code` and `complete_research_run` as inactive `v1` rows (schemas generated from
the tool definitions; `tests/test_multi_angle.py` fails when they drift) and notes on the latest
`check_data_feasibility` version that it is replaced while the feature is on. It refuses a second application and a
catalog without `check_data_feasibility`.

The first form also set the eight methods of §3.1 to `IMPLEMENTED_BEHIND_FLAG` in `AI_research_catalog`. The dev dry
run (2026-09-29) showed the catalog holds 18 reviewed methods, all `REFERENCE_ONLY`, under other ids and none of the
eight, so the preflight refused. The user decided on 2026-09-29 to register the tools only; the file was rewritten
before any application and applied on dev the same day (`DATABASE_CHANGELOG.md`). `AI_research_catalog` stays
unchanged until the reviewed workbook carries the multi-angle methods. No service reads it for multi-angle research:
market-ai-orc and the sandbox negotiate the method registry by its hash (§3.1), and the model reads the runnable
methods from `AI_research_library` (§10). Migration `20260930_002` (applied on dev 2026-09-29) adds inactive `v2`
rows of `check_research_feasibility`, `run_research_code` and `complete_research_run` and `get_research_library`
`v1`.

## 9. Tests

- market-python-sandbox: `tests/test_research_engines.py`, `tests/test_research_governance_v2.py`,
  `tests/test_research_runs.py` (real sessions on fixture data: promotion, grouped completion, NOT_RUN finalization,
  tampering, replay, group close, flag off); full suite 596 passed.
- market-ai-orc: `tests/test_multi_angle.py` (plan v2 and the pinned signature, rpc2 tampering, negotiation, planner
  merge and split, executor, scripted orchestrator turns, flags-off identity, migration drift); full suite passed.
- Fixes of 2026-09-29 (`MULTI_ANGLE_FIX_PLAN.md`): market-python-sandbox `tests/test_research_library.py` (library = registry, roles, parameters, data requirements, hash, byte identity with market-ai-orc, migration drift) and additions in `tests/test_research_runs.py`, `tests/test_dataneed_sessions.py`, `tests/test_research_view_examples.py`; full suite 615 + 6. market-ai-orc `tests/test_multi_angle_fixes.py` (M36, M38, P09, item 7, library check and tool); full suite 745 passed with the PostgreSQL tests.

## 10. Research library (C07, 2026-09-29)

`app/research_library.py` (byte-identical in both services) describes each method for the model: family, the
question it answers, input roles, required and optional parameters with their rules, data requirements (entity
column, label constancy, outcome kind, entities per date), sample unit, secondary checks, interpretation, misuse
warning and an example question, plus the requirements every method shares. Migration `20260930_001` writes it to
`public."AI_research_library"` (generated by `scripts/generate_ai_research_library_migration.py`; both test suites fail
on drift). The sandbox reports its hash; market-ai-orc reads the table at startup and runs multi-angle research only
when table, sandbox and its own copy match, then serves the rows through `get_research_library`. The library
describes; the engines, the harness recomputation and `research_engines.decide` enforce, and a new row does not
create a method. A change is made in the code and shipped as a new generated migration.

## 11. Findings rendering, value references and session recovery (2026-09-30)

User decisions of 2026-09-30 after suite20b (plan: S16, M39, P10, findings #15, provenance #13; M37 deferred):

- **Findings are rendered by the backend.** The model writes one narrative per angle (`answer`, `usefulness`,
  `follow_up`); market-ai-orc adds each approved angle's `backend` block (status and reason, validation level,
  effective sample, primary estimate, CI, p and adjusted p, evidence direction) and an `evidence` sentence formatted
  by code. An angle the model did not interpret is still shown ("Tidak diinterpretasikan oleh model"), so no angle can
  be left out. The findings gate checks only verdict wording the backend did not give (with the negated-clause and
  zero-count rules, P09/P10) and agreement without the synthesis map. Every LIMITATION after a completed run carries
  the backend blocks (M39).
- **Value references** (`AI_ENABLE_VALUE_REFERENCES`): figures are written as `{{finding.<angle_id>.<path>|format}}`
  and filled in by code, so the provenance check no longer depends on how the model types a number (P11). Details in
  `apps/market-ai-orc/README.md`, "Value references".
- **Session recovery** (S16): a crashed session (`WORKER_CRASHED`, `SESSION_STATE_CORRUPTED`, `PROTOCOL_ERROR`) is
  reopened on the same bundle within `AI_RESEARCH_MAX_SESSION_RESTARTS` (default 1, per group); a session limit
  closes the group; `finalize` closes a group that cannot complete, so a run always ends. The sandbox labels the end
  after the worker exits, keeps its protocol on private pipes, and answers a broken bookkeeping as
  `SESSION_STATE_CORRUPTED` (`apps/market-python-sandbox/README.md`).
- **Audit**: the refused drafts of every final (`final.rejected`, `final.forced`) and the unrendered final are kept in
  market-audit-store (dev, shadow mode).

## 12. Mode 4: answer, research, suggestion (2026-09-30)

User decision 2026-09-30, after the question "Siapa broker yang secara konsisten membeli saham bank ketika market
crash" got a Research Plan that did not say which brokers. Mode 4 (`AI_ENABLE_MODE4`, `apps/market-ai-orc/app/mode4.py`)
answers first and uses research to test the answer:

1. **First round**, one response: the analysis answer (ANALYSIS path); the results of research of at least two angles
   built on that answer, run at once without asking; and one suggested follow-up angle that waits for confirmation.
2. **Next rounds**: the user approves the suggestion, it runs, and the response has its result plus one new suggestion.
3. More than one angle or suggestion only when the user asks for a number; the backend enforces the count (at most 6).
4. A suggestion is always offered, also for a price question (for example whether a BBRI rise is within its normal
   range or an outlier).
5. A new question instead of a reply cancels the suggestion.
6. The ANALYSIS and RESEARCH paths stay.

No gate or engine is new: every step is an ordinary run with its own request_id (`-m4a` analysis, `-m4b` plan, `-m4c`
execution, `-m4d` suggestion, `-m4r` reply classifier). The schema admits a one-angle `research_plan/v2`
(`MIN_ANGLES` 1); the count of each plan is enforced by `check_research_feasibility` and the plan gate, from
`AI_RESEARCH_MIN_ANGLES`/`MAX_ANGLES` or, in mode 4, from the request (`current_angle_bounds`). The sandbox accepts a
one-angle plan only with `PY_SANDBOX_RESEARCH_MIN_ANGLES=1` (default 2); the negotiated capability passes its minimum
to market-ai-orc as `sandbox_min_angles`. Response shape, degradation and budgets: `apps/market-ai-orc/README.md`,
"Mode 4". Tests: `apps/market-ai-orc/tests/test_mode4.py` (a full first round through the real orchestrator with a
scripted model, the routing of every reply, counts, failures, budget, API wrapping) and
`apps/market-python-sandbox/tests/test_units.py`.
