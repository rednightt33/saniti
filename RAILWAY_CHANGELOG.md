# Railway changelog

## 2026-10-01 — G14 deployed on dev: bundle size before extraction, DuckDB first, 5,000,000-row bundles

Plan step 1 (user decision 2026-10-01). Tested locally first: market-ai-orc 878 passed (7 new,
`tests/test_bundle_limits.py`), market-python-sandbox 635 passed (6 new, `tests/test_frame_budget.py`), both with
PostgreSQL / root isolation; imports checked from the requirements the images install.

- `44463ef` market-python-sandbox: bundle limits in the top-level runtime `limits`; frame budget
  (`PY_SANDBOX_FRAME_MEMORY_PERCENT`, default 40) refusing a pandas frame before it is loaded
  (`MaterializationLimitExceeded`, next action `AGGREGATE_IN_SQL`); `materialize` per dataset; a need prepared again
  in its request gets its bundle back. Deployment `7cbc3aff-076b-47d1-9445-5ad4940c127b` `SUCCESS`.
- `e30b6e6` market-ai-orc: bundle limits read from the sandbox and checked before (`PREFLIGHT`) and during
  (`EXTRACTION`) extraction and in `check_data_feasibility`. Deployment `1b647376-71e1-479e-8858-fa6e540b736e`
  `SUCCESS` (startup log without `bundle_limits_unknown`). It interrupted the last step of `ma-out36k-20261001a` m01.
- Memory measured before raising the limit (`DATANEED_ARCHITECTURE.md`): 5,000,000 broker-shaped rows loaded whole
  peak at 2,470 MB RSS, above the 2,048 MB session limit; aggregated in DuckDB first, 192 MB. The sandbox container's
  limit is 24 GB (peak 3.19 GB over the previous 24 hours, Railway metrics).
- Variables on market-python-sandbox `dev`: `PY_SANDBOX_BUNDLE_MAX_ROWS=5000000` (unset, default 2,000,000) and
  `PY_SANDBOX_MAX_MEMORY_MB=4096` (unset, default 2048). The redeploy `b3fe51d7-83e3-4bcd-9ee9-42496216bba6` FAILED:
  the isolation self-test failed `duckdb_memory_limit` (S17) and `/ready` stayed 503; the previous deployment stayed
  live. Fix `34e9411`; deployment `87f3b9cb-4996-4d87-bb77-870c680cd541` `SUCCESS`, `isolation_enforced=true`.
- market-ai-orc redeployed (`b3e0e5b6-decb-448a-8ff7-0d82cbea0b09` `SUCCESS`) so it reads the new limits at startup.
- `railway config pull --force` added `PY_SANDBOX_BUNDLE_MAX_ROWS` and `PY_SANDBOX_MAX_MEMORY_MB` as `preserve()`;
  `railway config plan` reports the configuration up to date.
- Live verification: suite `ma-g14-20261001a` (runner `d3cd5438`), results below when it completes.

## 2026-10-01 — orc-test-runner: M44 scan of the new runs and audit readback of the m4b plan step

- Runner `02d726d3-ce1a-4428-ba52-700e86462215` (suite `ma-integrity-20261001b-scan`, audit only): the M44 scan of the
  `ma-integrity-20261001a` runs (m01 `-m4a`, `-m4c`, `-m4d`, a05, e02 turn 2, g13 turn 2) found 0 positional
  references and 0 affected rows; M44 is FIXED (`ERRORS_AND_SOLUTIONS.md`).
- Runner `8e7419a8-961d-4ac6-b162-c7a979ce0442` (suite `ma-integrity-20261001c-audit`): full trace of
  `ma-integrity-20261001a-m01_broker_bank_crash-1-m4b`; the plan refusal was an angle renamed with unchanged data
  (M49).
- Both read the audit store with the temporary `AUDIT_STORE_READER_KEY`, still to be revoked (`PROJECT_CONTEXT.md`
  outstanding items).

## 2026-10-01 — market-ai-orc: output budget 36,000 tokens, request timeout 420 s (dev test)

User decision 2026-10-01 (M37 test, speed/integrity plan step 0). Every phase already runs `AI_REASONING_EFFORT=high`; the
largest call of `ma-integrity-20261001a` used 21,427 of 24,000 output tokens (89%, reasoning included), so a longer
plan or answer would be cut off.

- `AI_MAX_OUTPUT_TOKENS` 24000 -> 36000 and `AI_REQUEST_TIMEOUT_SECONDS` unset (default 180) -> 420 on market-ai-orc
  `dev`, set with `railway variables --set`; redeploy `8f311756-d5cb-4ce7-8222-cf42076b2ab8` `SUCCESS`. Startup log:
  `ai_model_selected ... reasoning={"effort":"high"} max_output_tokens=36000`.
- Checked before the change: `deepseek/deepseek-v4.1-flash` allows 943,718 completion tokens on Relace (the endpoint
  that served the runs; every endpoint allows at least 131,072); the context ceiling (`AI_MAX_CONTEXT_TOKENS=500000`)
  and the run limit (`AI_MAX_ANALYSIS_SECONDS=1800`, above the 420 s request timeout) are unaffected.
- `.railway/railway.ts`: `railway config pull --force` added `AI_REQUEST_TIMEOUT_SECONDS: preserve()`;
  `railway config plan` reports the configuration up to date.
- Rollback: `AI_MAX_OUTPUT_TOKENS=24000` (and remove `AI_REQUEST_TIMEOUT_SECONDS`).
- Verification: suite `ma-out36k-20261001a` (runner `b307147b`) against `ma-integrity-20261001a`: the model reasoned
  longer with more room; one call reasoned 37,058 tokens and was still cut at 36,000 (m01 `-m4b`, 291 s), another took
  327 s to choose a tool; m01's research-plan step 1,125 s (581 s at 24000); e02 457 s (471 s), a05 186 s (172 s),
  g13 1,431 s (712 s, bundle-limit retries); no `PROVIDER_TIMEOUT`. m01 was interrupted in its last step by the G14
  deployment. Conclusion (M37): a larger output budget does not prevent truncation. The setting stays at 36000 until
  the user decides.

## 2026-10-01 — Answer integrity (M44, P14, P17, G13) deployed on dev; counted rows on

`ANSWER_INTEGRITY_FIX_PLAN.md` (final plan approved by the user 2026-10-01). Each service was tested locally (PostgreSQL
tests included: market-ai-orc 871, market-sql-governor 217), imported from a clean `requirements.txt` venv, pushed to
`main` and deployed one at a time.

- **M44 + P14** `058ffa6`: market-ai-orc `a353864c-8e44-47c5-a9f7-79a6bab1432a` `SUCCESS`. References resolve against
  the complete released table (rows by position, `_row`, unread rows read by the backend), keyed tables by key, a
  display for every value (`null` -> `null`, `NaN`/`inf` -> `undefined`), an unresolved reference marked instead of a
  forced LIMITATION.
- **P17** `3e52d73`: market-ai-orc `2cdd5a15` `SUCCESS`. Claims (CAUSAL, PREDICTIVE, PROOF, VERIFIED_CALCULATION) are
  marked in italics with `annotations`, never rejected; one negation rule before and after the phrase.
- **G13** `70b0980`: market-sql-governor `9d17c517-2055-4b6b-a184-8c1c7b52b076` `SUCCESS` (flag off), then
  `4b5cb52`: market-ai-orc `2646be80-fc79-491d-921d-ff28477507be` `SUCCESS` (`row_basis`). Then, per the approved plan
  and the user's timeout decision, on market-sql-governor `SQL_ESTIMATE_COUNT_ENABLED=true` and
  `SQL_ESTIMATE_COUNT_TIMEOUT_MS=7000` (new variables): deployment `35f24e70-ae60-401f-b426-31d84b7895f2` `SUCCESS`,
  `/ready` 200. `SQL_STATEMENT_TIMEOUT_SECONDS` stays at its default 20.
- Every startup log clean (`ai_model_selected switch=1`, `mode4_active`, no `*_inactive`). Model, provider and
  `AI_MODE_SWITCH` unchanged.
- **Config**: `railway config pull --force` recorded the two Governor variable names (`preserve()`); `railway config
  plan`: up to date.
- Deviations from the plan, recorded in the plan: G13 counts every estimate-only part (`SQL_ESTIMATE_COUNT_MIN_ROWS`
  default 0, not 10% of the part limit, because e02's 32 small parts were too large only in total); no `Tool_Catalog` v4
  (the tool's registered output schema lists only top-level keys; `row_basis` sits inside `bundle_groups`); P17 adds
  the kind `PROOF` ("terbukti"), since the user's example "BBCA terbukti naik" matched no existing pattern.
- Live verification: pending (next entry).

## 2026-10-01 — orc-test-runner: M44 scan of past runs

- Runner code `4aacfb5` (`scan_m44_request_ids`), CLI upload, deployment `2c00228c-7a45-417e-8a56-bd114b493dd7`
  `SUCCESS`, audit-only (no question, no OpenRouter cost), with the reader key that stays on the runner (outstanding
  item in `PROJECT_CONTEXT.md`). 208 candidate request ids from the suites since value references went live
  (suite20c/d/d2/m, mode4, modeswitch, m43g13 and their mode 4 sub-runs): 100 found, 0 errors.
- Result: 12 runs used positional row references; 1 run (`ma-m43g13-20260930a-m01_broker_bank_crash-1-m4a`) had read
  an output page at an offset > 0 and took 6 rows from that page under other brokers' names (SQ→EP, XL→AZ, DH→RF,
  OD→LS, XC→XA, GR→AO). Recorded under M44 in `ERRORS_AND_SOLUTIONS.md`.

## 2026-10-01 — orc-test-runner: audit reader key kept for the answer-integrity work

- **Variable** (user decision, not revoked): `AUDIT_STORE_READER_KEY` (a reference to market-audit-store's reader key)
  added again to `orc-test-runner` with `--skip-deploys`; no deployment was created (latest stays `ada3fd49`). It is
  listed under "Outstanding operational items" in `PROJECT_CONTEXT.md` with its revoke steps.
- **Plan**: `ANSWER_INTEGRITY_FIX_PLAN.md` (M44, P14, P17, G13), not implemented yet.
- **Config**: `railway config pull --force` recorded the variable name in `.railway/railway.ts` (`preserve()`, no
  value); `railway config plan`: up to date.

## 2026-10-01 — orc-test-runner: audit readback of a mode 4 sub-run (M44 root cause)

- **Runner code** `9232e45`: `suite.json` `audit_request_ids` reads the audit of listed runs (a mode 4 step such as
  `…-1-m4a`, which the item/turn naming cannot reach) and `audit_full_trace` dumps the whole TOOL_TRACE. Suite
  `ma-m44-audit-20261001a` is audit-only: it sends no question (no OpenRouter cost).
- **Variable** (user-approved): `AUDIT_STORE_READER_KEY` (a reference to market-audit-store's reader key) added to
  `orc-test-runner` with `--skip-deploys`; then CLI upload, deployment `ada3fd49-36fa-4154-826c-d4958d204751` `SUCCESS`
  (02:17 UTC): run `run_3359aa90…` of `ma-m43g13-20260930a-m01_broker_bank_crash-1-m4a` read back `COMPLETE`
  (205 events: `final.unrendered` 1, `final.rejected` 2, 43 tool calls). The key was deleted afterwards; the runner
  again holds only `MARKET_AI_ORC_API_KEY` and no new deployment was created. No value appears in any log or file.
- **Finding**: M44 root cause verified (`ERRORS_AND_SOLUTIONS.md`): a `get_session_output` page replaced the output's
  reference entry, and the repaired answer's row positions resolved against that page, so the broker table showed
  other brokers' figures under the names given. W21 closed as ACCEPTED by the user.

## 2026-10-01 — market-web-governor: `/v1/ask` separate budgets, cost per call, follow-up questions (P8, W23)

- `08301c3` deployed as `9b581712` `SUCCESS`: search (USD 0.035), answer (0.02) and follow-up (0.005) budgets
  replace the single 0.05 budget; each call's cost in `plan.timing`; "Pertanyaan lanjutan" at the end of the answer.
  No variable changed (the defaults apply; no `WEB_ASK_*` variable is set on the governor).
- Live test `live-ask28-20261001-q1` ("target harga goto setelah batas 50 dibuka", runner deployment `a45c636d`):
  `ANSWERED`, 82 s, USD 0.0516, stop `all_claims_settled` at turn 3, nothing skipped, no budget passed. Search
  0.0327 (plan 0.0003, Exa 0.0077 + 0.0079, reviews 0.0029 + 0.0031, select 0.0032, one read 0.0074), answer 0.0174
  (answer with reasoning high 0.0085 in 52 s, implications 0.0089), follow-up 0.0016 (5 questions). The same
  question on 2026-09-30 (`live-ask27`) skipped reasoning and reading and cost 0.0586.

## 2026-09-30 — market-web-governor: time and provider attempts per step; runner timeout 900 s

- `0c5f4a4` deployed as `b38884ca` `SUCCESS`: `plan.timing` (seconds, calls, provider attempts and failures per
  step) and the `web_ask_answered` log line carry the timing. Live test `live-ask26`: 49 s, no failed attempt. The
  runner's `/v1/ask` timeout went from 300 s to 900 s (R22). No variable changed.

## 2026-09-30 — market-web-governor: `/v1/ask` answers carry (source) links

- `d08fc58` deployed as `1b39926f` `SUCCESS`: each run of [n] in `answer` becomes markdown "(source)" links to the
  cited headlines; `answer_cited` keeps the numbers. Live test `live-ask23-20260930-q1`: `ANSWERED`, 39 s, USD 0.052,
  links render per cited source. Rollback `b2c584e` (deployment `222b8f4f` `SUCCESS`) is recorded above. No variable
  changed.

## 2026-09-30 — market-web-governor: broken-answer guard and 5 Exa results deployed, then rolled back

- `2c46d5b` (guard `ANSWER_DEGENERATE`, turn-0 Exa 5 results, reading off by default) deployed as `a8672c01`
  `SUCCESS`. Live test `live-ask20-20260930-q1..q3`: GOTO answered without the 2024 cancellation found the run
  before; BI rate did not return within the runner's 300 s; nickel answered (USD 0.051). Exa cost per search did
  not fall with fewer results.
- At the user's request the change was reverted (Exa 10 results and article reading back, no guard). No variable
  changed.

## 2026-09-30 — market-web-governor: `/v1/ask` claims, stopping rules, history mode, reading, USD 0.05 budget (W19, W20)

- **Push** `main` fast-forward `2b7cf63..76d90ea` (user-approved direct push; the GitHub connector could not open a PR).
  Deployment market-web-governor `04e5df46` `SUCCESS`; market-ai-orc and market-python-sandbox `SKIPPED`
  (unchanged). No variable changed.
- **Before merge**: the local code ran in-process on `web-governor-test-runner` twice (temporary variable
  references to the governor's variables, deleted afterwards; nothing stored). Static outbound IPs added to the runner
  on 2026-09-29 for a financialfilings.com test were removed again (governor IPs unchanged).
- **Live test** (runner `ae2e1cba`, `live-ask19-20260930-q1..q3`): 3 of 3 `ANSWERED`, 47–96 s, USD 0.039–0.056.
  GOTO treasury: history mode; 2024 cancellation of 10.26 bn shares found with Ministry approval (5 Nov 2024) and
  IDX approval (11 Nov 2024). BI rate: not history, 3 claims, stopped at turn 3, 5.75% held (RDG 22–23 Sep 2026).
  Nickel: RKAB figures explained by what each measures; USD 0.056 (one call over the 0.05 budget).

## 2026-09-30 — REFERENCE gate and mode 4 fixes (M43, P14-P16), G13 scope check; migration 20260930_003

- **Code `2671f7e`** (docs `82ed5cc`): market-ai-orc `6028ddc8-b6dd-4ddc-99ca-a2b94aa87fff` `SUCCESS` (auto-deploy from
  `main`, 15:59 UTC); every other service SKIPPED (watch patterns). Startup log: `mode4_active max_seconds=3600
  sandbox_min_angles=1`, `ai_mode_selected switch=4 effective=4`, `ai_model_selected switch=1`
  (`deepseek/deepseek-v4.1-flash`); no `multi_angle_research_inactive`.
- **Migration `20260930_003`** (`Tool_Catalog` `check_research_feasibility` v3, inactive) through the temporary
  service `ma-migrate-job` (`44a643a8-1151-4359-9b50-ebbef699d9d9`, only a `DATABASE_URL` reference): inspection +
  dry run `bcc703c3-1370-4fa5-b8b9-c4f39243c582` (passed, rolled back), apply `bee0028b-839b-43fc-a0b3-77fbf0872592`
  (read back in the job). Deleted after use; dev lists 18 services again. Details in `DATABASE_CHANGELOG.md`.
- **Variables**: none changed. `AI_MODE_SWITCH` stays 4, `AI_MODEL_SWITCH` 1, model and provider unchanged.
- **Config**: `railway config pull --force` left `.railway/railway.ts` unchanged; `railway config plan`: up to date.
- **Live test `ma-m43g13-20260930a`**: runner `orc-test-runner` deployment `b186f4f8-0bf8-403c-b9d5-4f4cfb951148`
  (CLI upload, 16:05 UTC): the broker question over three turns in mode 4 (M43) and e02 through the RESEARCH path with
  one automatic approval (G13). 0 HTTP errors at market-ai-orc, about USD 0.40 in total.
  - Broker round 1 (mode 4, `SWITCH`): all four steps: analysis ANSWER (585 s, one REFERENCE repair for a selector
    row that did not exist, then clean), a plan of 4 angles (199 s), research COMPLETED 4 of 4 validated, all
    INSUFFICIENT_EVIDENCE (137 s; one REFERENCE and one FINDINGS repair), one suggested angle (443 s; one output cut
    at 24,000 reasoning tokens, M37); 1,364 s, USD 0.27. M43 no longer occurs: the analysis was not forced to
    LIMITATION and the research ran. The answer has a self-contradicting count (M44).
  - Turn 2 "Setuju" (mode 4, `CONTINUATION`): the classifier read APPROVE, the suggestion ran (research COMPLETED 1 of
    1, 35 s) and the next suggestion was issued; 454 s, USD 0.05.
  - Turn 3 "cari 2 angle lain": read as REVISE, a revised plan of exactly 2 angles (418 s, USD 0.04), from the orc log;
    the runner logged nothing after turn 2 (R22).
  - e02 (RESEARCH path, one automatic approval): both requests scoped to BBCA (Governor estimate 2 rows each), one
    bundle group, run COMPLETED 4 of 4 validated (G13 no longer occurs); the answer was forced to LIMITATION by the
    CLAIM gate for "menyebabkan" in a negated sentence after an earlier "prediksi" repair (P17); USD 0.05.

## 2026-09-30 — mode switcher `AI_MODE_SWITCH` on dev (default 4); mode 4 live test

- **Live test `ma-mode4-20260930a`** (runner `eab7b4aa-e4a3-49fd-b93e-082a4c2ae5dc`, 11:53–12:07 UTC, 5 turns, 0 HTTP
  errors, about USD 0.35). BBRI "wajar atau outlier": all four steps (analysis 80 s, plan 241 s, research 24 s,
  suggestion 166 s; 511 s, USD 0.13): a direct answer (0,96%, 73,7th percentile, z 0,45: within the normal range),
  research run at once and one suggested angle. The new question on BBCA cancelled the suggestion
  (`mode4_suggestion_cancelled`) and ran a new round (289 s, USD 0.09; -6,18% for September). The broker question: the
  analysis answered (broker XL) but was forced to LIMITATION by a reference error, so the round ended without research
  (`ERRORS_AND_SOLUTIONS.md` M43); "Setuju" then had no plan and "cari 2 angle lain" became a new analysis.
- **Code `a70b57c`** (mode switcher, `app/modes.py`): `AI_MODE_SWITCH=4` set first on market-ai-orc with
  `--skip-deploys` (new variable; user decision: default 4 on dev), then the auto-deploy
  `90cfdfe2-ee4d-4535-9d0f-c31515595d1c` `SUCCESS`; the log shows `ai_mode_selected switch=4 effective=4`,
  `mode4_active` and `ai_model_selected switch=1`.
- **Smoke** (runner `5dd6497b-1b13-45b5-8011-289007acad46`, prefix `ma-modeswitch-20260930a`): one fact question with
  `analysis_path: "AUTO"` answered in mode 1 while the default is 4 (`execution.mode` `{1, AUTO, CALLER}`, no `mode4`
  block; BBCA close Rp 6.075 on 2026-09-30), 70 s, USD 0.014.
- **Config**: `railway config pull --force` added `AI_MODE_SWITCH` (`preserve()`); `railway config plan`: up to date.

## 2026-09-30 — mode 4 on dev; P12/P13/M40 and the model switcher deployed; suites 20d, 20d2, 20m

- **Code `7dbbc01`** (P12 plan numbers from the JSON values, P13 value-reference fixes, M40 lenient final JSON, model
  switcher `AI_MODEL_SWITCH`): market-ai-orc `6cd70de2-a48e-4f88-86c8-c9474de5bb11` `SUCCESS` (auto-deploy from
  `main`; the sandbox skipped). `AI_MAX_OUTPUT_TOKENS=24000` on market-ai-orc (M37, user decision; reasoning counts in
  it). Runner code `a17d780`/`b218d07` (per-turn timeline in the audit readback) is uploaded by CLI only.
- **suite20d** (runner `4f8745b8-9a1f-4619-8270-3c44beca7cf7`, prefix `ma-suite20-20260930d`, model 1, effort high):
  35 turns, USD 0.74; 12 ANSWER, 3 LIMITATION, 5 FAILED. The 5 failures were OpenRouter HTTP 403 "Key limit exceeded
  (total limit)" (the key's total spending limit, not a code fault); the user raised the limit and the five items ran
  again as **suite20d2** (runner `450c7537-b330-4ac5-90d8-29d470d24267`, prefix `ma-suite20-20260930d2`): 6 turns, 5
  ANSWER, USD 0.09. `AUDIT_STORE_READER_KEY` (a reference to market-audit-store's reader key) was on the runner for the
  readback only; it was removed afterwards with `variableCollectionUpsert` (`replace`, `skipDeploys`), since `railway
  variable delete` has no skip-deploys option.
- **suite20m** (model 2, `xiaomi/mimo-v2.6-pro`, full suite approved by the user): `AI_MODEL_SWITCH=2` on
  market-ai-orc, deployment `16767aab-468b-4c09-953b-aa6184948520` `SUCCESS` (`ai_model_selected` switch=2,
  `reasoning.enabled`); runner `fd68a4cf-f1a1-4f62-b22b-d750fdb4cc36` (prefix `ma-suite20-20260930m`). Stopped at the
  user's request after 4 turns (USD 0.12; model 2 was 1.1 to 8 times slower on r01-r03) by removing the runner
  deployment; `AI_MODEL_SWITCH=1` set back, deployment `0728cf41-1364-4503-a8f9-67451252eb24` `SUCCESS` (model 1,
  DeepSeek, effort high). Audit-only readback of the timelines: runner `45994ba7-4cad-4786-9ac9-4204a8bfe4b4`.
- **Broker question** (user, no automatic approval): runner `f3a5c8ec-7dc7-46d3-9e56-f0a994e82d9e`, one turn, a
  RESEARCH_PLAN_CONFIRMATION in 567 s, USD 0.053; the plan did not name brokers, which led to mode 4.
- **Mode 4 code `b0f905c`** (flag off): market-ai-orc `ad948094-67cc-4053-9faf-02568bd7446c` `SUCCESS`,
  market-python-sandbox `20bd6c7f-293c-4898-b8ac-2529ad5896da` `SUCCESS`. Then on dev:
  - market-python-sandbox `PY_SANDBOX_RESEARCH_MIN_ANGLES=1` (new variable; one-angle plans for mode 4 suggestions),
    deployment `3074a322-ff44-4620-9d73-b62877234b75` `SUCCESS`;
  - market-ai-orc `AI_ENABLE_MODE4=true` (new variable), deployment `dded5d81-8c7f-41f6-9c8d-e22292b9bfff` `SUCCESS`;
    the log shows `mode4_active max_seconds=3600 sandbox_min_angles=1` and `ai_model_selected switch=1`.
    `AI_RESEARCH_MIN_ANGLES` stays unset (2) for every plan outside mode 4; `AI_CONVERSATION_LEASE_SECONDS` stays
    unset, so the lease is 3720 s.
  - Runner code `4e959b3` (multi-turn items, 3900 s timeout), CLI upload `eab7b4aa-e4a3-49fd-b93e-082a4c2ae5dc`,
    prefix `ma-mode4-20260930a` (the broker question over three turns, a price question followed by a new question).
- **Config**: `railway config pull --force` added `PY_SANDBOX_RESEARCH_MIN_ANGLES`, `AI_ENABLE_MODE4`,
  `AI_MODEL_SWITCH` and `AI_MAX_OUTPUT_TOKENS` (as `preserve()`) to `.railway/railway.ts`; `railway config plan`: up
  to date. The plan must not run under `timeout`: the IaC SDK checks the CLI version by executing `$_`, which is then
  `timeout`, and the check fails.

## 2026-09-30 — suite20c on dev: value references, backend-rendered findings, audit readback

- **Runner** `orc-test-runner` deployment `eba6a12f-aebb-4f66-a41d-385910435c1b` (CLI upload of `apps/orc-test-runner`,
  prefix `ma-suite20-20260930c`, the same 20 questions as suite20b, two workers, SERVER mode, one automatic approval),
  05:38–05:53 UTC: 33 turns, 0 HTTP errors, USD 0.92 in total (suite20b: USD 0.64). No secret, DSN, bearer or
  presigned URL in the runner, market-ai-orc, sandbox, Governor or Audit Store logs, nor in the refused drafts.
- **Research (16 questions)**: 13 plans issued and approved, 13 runs `COMPLETED`, **13 answered, 0 LIMITATION** on the
  answer turn (suite20b: 13 runs, 10 answered, 3 LIMITATION). 40 angles, all validated, NOT_RUN 0 (suite20b: 28, 3
  NOT_RUN): SUPPORTED 3, PARTIALLY_SUPPORTED 3, INSUFFICIENT_EVIDENCE 34, INVALID 0; 37 at
  FORMULA_AND_STATISTICS_VERIFIED, 3 at STATISTICS_VERIFIED. r09 (S16 in suite20b) completed with two angles; no
  session ended in the suite (no `session_worker_ended`). e01 refused correctly (PER not in the catalog). r04 and r06
  ended at the plan turn with a LIMITATION forced by PLAN_PROVENANCE (P12: the plan's own threshold lists are lost by
  the parser; new, OPEN). e03 answered (suite20b: plan-provenance LIMITATION). r12 was routed to RESEARCH this time.
  Research questions answered: 13 of 15 (suite20b: 11 of 15).
- **Value references** (P11): 17 final answers used 495 references (414 to backend findings, 81 to released
  outputs). Refusals on answer turns: PROVENANCE 3 (suite20b: 7 repairs + 1 forced), FINDINGS 2 + FINDINGS_2 1
  (suite20b: 2 + 2, one forced), REFERENCE 6 (new gate, all repaired; P13), CLAIM 2, METHODOLOGY_PROVENANCE 2. No
  final was forced on an answer turn.
- **ANALYSIS**: a01, a02 and a04 equal suite20b figure for figure; a03 now sums every market board and equals the
  all-boards ground truth of suite20 (ZP Rp 199 miliar, CC 159, XL 84, RX 73, LG 59; suite20b read the Regular board
  only).
- **Audit Store**: all 33 turns reached `COMPLETE` (0 INCOMPLETE); 114 sandbox archives, 39 Governor dataset
  archives, 33 outbox rows ingested, 0 producer failures. 40 refused finals kept with their drafts (`final.rejected`
  38, `final.forced` 2): FORMAT 11 (5 `clarification_question: Field required`, M40), output-limit cut-offs 3 (M37,
  plan turns), REFERENCE 6, PLAN_PROVENANCE 5 + 2 forced, PLAN_FEASIBILITY 3, PROVENANCE 3, FINDINGS 3, CLAIM 2,
  METHODOLOGY_PROVENANCE 2. Events larger than 16 KiB show a preview in `GET /v1/runs/{id}/events`; the full drafts
  are in the TOOL_TRACE artifact.
- **After the suite**: `AUDIT_STORE_READER_KEY` removed from `orc-test-runner` with `variableCollectionUpsert`
  (`replace`, `skipDeploys`; the CLI delete has no skip-deploys option and a redeploy would rerun the suite): only
  `MARKET_AI_ORC_API_KEY` remains, no new deployment. `railway config pull --force` recorded the new variable names,
  `market-audit-store` and `market-ai-audit-artifacts` in `.railway/railway.ts`; `railway config plan`: up to date.
- **Still open**: M37 (deferred by the user), M40, P12, P13 (`ERRORS_AND_SOLUTIONS.md`).
- **Documentation push** `bcb1322` (README changes under the watched folders): market-ai-orc `e080f48a-d2da-4b03-b2d3-77dff7dac739`, market-python-sandbox `c6bf0827-22d8-4e67-8cc0-62edf0d44498` and market-audit-store `5d9cbc55-3b8a-42e7-ae13-dd8445e083dd` rebuilt from it, each `SUCCESS` at 06:03 UTC with a clean startup and `/ready` healthcheck; no code or variable changed.

## 2026-09-30 — S16/M39/P10 fixes, backend-rendered findings and value references deployed on dev; Audit Store live

- **Code** (`1954087`, pushed to `main`): sandbox S16 (worker hardening, exit labels, `worker.log` tail,
  `SESSION_ENDED` audit), market-ai-orc S16 session recovery (`AI_RESEARCH_MAX_SESSION_RESTARTS`), finalize closes an
  open group, backend-rendered findings (#15), M39, P10, value references (`AI_ENABLE_VALUE_REFERENCES`, off by
  default) and the `final.rejected` / `final.forced` / `final.unrendered` audit events.
  - market-python-sandbox `cbfcc10b-0fee-46cf-a329-8e5326b1923d` `SUCCESS`; market-ai-orc
    `35b8cf18-bebb-46d8-b40a-b33bcad05c93` `SUCCESS`: startup clean, no `multi_angle_research_inactive` or
    `research_library_mismatch`. Value references still off at this point (behaviour unchanged).
- **Audit Store infrastructure** (user decision 2026-09-30, "Aktifkan juga audit store"; runbook of
  `apps/market-audit-store/README.md`):
  - IaC through a pinned plan (`railway config plan --verbose --out`, reviewed, then `railway config apply --plan`;
    plan file sha256 `67ea994a031bf460cbf54bc29c424e76f8b88cf00aa2609b5608c7b3f068969d`, two creates, not
    destructive). A plain `railway config apply --yes` was refused by the agent's permission check as a blind apply;
    the first pinned plan also contained the delete of a temporary job, so the job was deleted first and the plan
    pinned again.
  - Bucket `market-ai-audit-artifacts` (`f29461fa-0ad8-4886-bbf1-2df2b4966357`, region `sjc`, private).
  - Service `market-audit-store` (`956b1479-e8c6-4f6d-bd39-2af46390a22a`): GitHub source, root
    `/apps/market-audit-store`, Dockerfile, watch `/apps/market-audit-store/**`, healthcheck `/ready` (120 s), one
    replica in `sfo`, restart `ALWAYS`, private networking only (`market-audit-store.railway.internal:8080`), no
    public domain. Registered in `.railway/railway.ts`.
  - Variables on `market-audit-store` (names only): `AUDIT_DATABASE_URL` (template on the `market_ai_audit` login with
    `MARKET_AI_AUDIT_DB_PASSWORD`), `MARKET_AI_AUDIT_DB_PASSWORD` (48 hex), `AUDIT_STORE_GOVERNOR_KEY`,
    `AUDIT_STORE_SANDBOX_KEY`, `AUDIT_STORE_READER_KEY` (three distinct 64-hex keys), `AUDIT_BUCKET_NAME`,
    `AUDIT_BUCKET_ENDPOINT`, `AUDIT_BUCKET_REGION`, `AUDIT_BUCKET_ACCESS_KEY_ID`, `AUDIT_BUCKET_SECRET_ACCESS_KEY`
    (references to the bucket), `PORT=8080`. All resolved; no value is recorded here.
  - Migration `20260928_001` through the temporary service `audit-migrate-job`
    (`cbc9aef7-06fb-44d1-a0a6-2f21607af18c`; dry run `98fae03d-2a4b-4333-947a-febc4eb7d6d8`, apply
    `6e4e050a-ec3e-481b-9f7b-eecaef0ed3ad`), then the login through `audit-login-job` (deployment
    `28ba7d0e-9fb6-415b-816c-7e9cec72249b`). Both deleted after use. Details in `DATABASE_CHANGELOG.md`.
  - Deployment `02988b78-ac25-4561-8c0c-ffdaf7de6343` (`7825135`): password authentication failed until the login
    was provisioned, then `/ready` 200 and `SUCCESS`. The later push of `1954087` was `SKIPPED` for this service
    (watch pattern).
- **Producers in shadow mode**, one at a time, each redeployed to `SUCCESS` with a clean startup:
  - market-sql-governor `d6f0c1bf-ba5f-43ec-bcc6-0e410e87e4f2`: `SQL_GOVERNOR_AUDIT_STORE_ENABLED=true`,
    `AUDIT_STORE_URL` (private URL), `AUDIT_STORE_GOVERNOR_KEY` (reference to market-audit-store);
  - market-python-sandbox `11121efe-0f1e-4ba0-8e8a-11fe0e816d56`: `PY_SANDBOX_AUDIT_STORE_ENABLED=true`,
    `AUDIT_STORE_URL`, `AUDIT_STORE_SANDBOX_KEY` (reference);
  - market-ai-orc `3879fc59-e0fc-44b0-9841-6f3bbf80ff2a`: `AI_AUDIT_STORE_ENABLED=true`,
    `AI_AUDIT_STORE_REQUIRED=false`, `AUDIT_OUTBOX_DATABASE_URL` (the same template as `RESEARCH_AUDIT_DATABASE_URL`:
    the `market_ai_orc` login with `MARKET_AI_ORC_DB_PASSWORD`).
  - Rollback: set the three flags to `false`; the migration is additive.
- **Smoke** `audit-smoke-20260930a` (a02, ANALYSIS, runner `3f45e338-77df-4c0f-ac7e-07434de659aa`, USD 0.02,
  05:03 UTC): answered; its audit run reached `COMPLETE` with 29 events (`dataset.archived` from the Governor,
  `execution.recorded` and `completion.archived` from the sandbox, model and tool events from market-ai-orc), 16
  artifacts and 2 executions; its two refused finals (`final.rejected` CLAIM and METHODOLOGY_PROVENANCE) were read in
  full from the TOOL_TRACE artifact through an access grant.
- **orc-test-runner**: `run.py` gained the audit readback; `AUDIT_STORE_READER_KEY` (a reference to
  market-audit-store's reader key) was added for the smoke test and suite20c.
- **Value references on**: market-ai-orc `3bc6620b-1060-4c8c-ac46-a0b3feed56d8` `SUCCESS` 05:37 UTC with
  `AI_ENABLE_VALUE_REFERENCES=true`. `AI_RESEARCH_MAX_SESSION_RESTARTS` is not set (default 1). Model and provider
  unchanged (decision of 2026-09-27).

## 2026-09-29 — Multi-Angle Research fixes: suite20 rerun on dev (suite20b)

- **Runner** `orc-test-runner` deployment `8220743f-93d8-41da-9581-48740a4d922e` (CLI upload of `apps/orc-test-runner`,
  prefix `ma-suite20-20260929b`, same 20 questions, two workers, SERVER mode, one automatic approval), about
  18:50–19:18 UTC: 33 turns, 0 HTTP errors, USD 0.64 in total (suite20: USD 1.10). No secret in the runner, orc or
  sandbox logs. No variable or service setting changed.
- **Research (16 questions)**: 13 plans issued, 8 with two angles and 5 with three (suite20: 11 plans of four or five
  angles); 13 approved runs, 10 answered and 3 LIMITATION: r08 (P10: "0 keluarga metode didukung" read as a supported
  verdict; the LIMITATION kept the three backend findings), r09 (S16: the session worker ended after the model
  inspected the sandbox's modules; the group could not be finalized), r11 (M39: a misquoted figure, forced by the
  provenance gate). The 12 completed runs hold 28 validated angles: SUPPORTED 1, PARTIALLY_SUPPORTED 2,
  INSUFFICIENT_EVIDENCE 25, INVALID 0, NOT_RUN 0; 26 at FORMULA_AND_STATISTICS_VERIFIED and 2 at
  STATISTICS_VERIFIED (suite20: 21 and 15, NOT_RUN 10). r09's three angles are NOT_RUN (S16).
- **Plan turn**: no plan was refused for a method rule after a FEASIBLE check (suite20: 4, M38); r04 used the second
  repair (`PLAN_FEASIBILITY_2`, a changed `pairwise_comparisons`) and passed; every data plan carried the checked
  designs. e01 was refused correctly (PER not in the catalog); e03 ended in a LIMITATION forced by plan provenance
  (thresholds in the answer text), saying broker data end on 2026-08-31, without invented September data; r12 was
  answered through ANALYSIS (the model's own routing, as the suite expects; suite20: no plan).
- **Fixes seen live**: S14 (the janitor ran at 18:48, 19:03 and 19:17 while sessions were open and removed no
  workspace), S15 (e02 and r08, condition in `Feature_03_Stock_Broker_Daily` and price in another table, recorded
  declaratively at FORMULA_AND_STATISTICS_VERIFIED), P09 (r08's negated agreement sentence passed), M36 (no NOT_RUN in
  completed runs), item 7 (two-angle plans accepted).
- **ANALYSIS**: a01–a04 COMPLETED. Not compared with a new ground truth: the morning's truth predates the latest
  trading day (for example BBRI's last close moved from 3.170 to 3.190); the ANALYSIS path was not changed.
- **Still open**: M37 recurred (8 final turns cut off at 8000 output tokens, all reasoning; suite20: 13). New entries
  in `ERRORS_AND_SOLUTIONS.md`: S16, M39, P10.

## 2026-09-29 — Multi-Angle Research fixes deployed on dev (MULTI_ANGLE_FIX_PLAN.md items 1–7)

- **market-python-sandbox** `5bf53b1b-df92-496a-9701-f96e86aaac00` (`2d9ff7a`) `SUCCESS` 18:20 UTC: S14 (janitor
  skips open session workspaces), S15 (cross-request forward return, price-level outcome INVALID
  `OUTCOME_NOT_APPROVED`), research library and its hash in the `multi_angle_research` capability, two-angle
  minimum. Startup clean (`sandbox_started`, `sessions_started`, `/ready` 200). market-ai-orc was not redeployed by
  this push.
- **Migrations** `20260930_001` (`AI_research_library`) and `20260930_002` (Tool_Catalog v2 rows) through the
  temporary service `ma-migrate-job` (`6f1d8d31-f761-4be3-9d07-d8d4310af105`, only a `DATABASE_URL` reference):
  inspection + dry run `b0f9061c-2a40-464a-b86b-c49c84a936a3` (passed, rolled back), apply
  `2fe9621b-1186-4411-80ed-09dbc1bee79d` (read back in the job). Deleted after use; dev lists 16 services again.
  Details in `DATABASE_CHANGELOG.md`.
- **market-ai-orc** `c675120e-4046-489d-a3d1-cb5d78751765` (`9a7d83c`) `SUCCESS` 18:44 UTC: M36, M38, P09 (and forced
  LIMITATION keeps the backend findings), item 7 (`AI_RESEARCH_MIN_ANGLES` default 2, `AI_RESEARCH_MIN_FAMILIES`
  default off), research library check at startup and `get_research_library`. No `multi_angle_research_inactive`
  and no `research_library_mismatch` at startup, so the table, the sandbox and market-ai-orc carry the same library
  hash. The sandbox push was SKIPPED for market-ai-orc and this push SKIPPED for the sandbox (watch patterns).
- **Variables**: none changed. `AI_RESEARCH_MIN_ANGLES` is not set on dev, so the new default 2 applies;
  `AI_RESEARCH_MIN_FAMILIES` is not set (off). Model and provider unchanged (decision of 2026-09-27).
- **Documentation push** after suite20b (`02256de`): it touched `apps/market-python-sandbox/README.md`, so the watch
  pattern rebuilt market-python-sandbox with unchanged code: `3d376c2a-4f00-4c7e-8106-2cf44af9b9e7` `SUCCESS`
  19:31 UTC (after the suite, so no run was affected); market-ai-orc SKIPPED.
- **Config**: `railway config pull --force` left `.railway/railway.ts` unchanged; `railway config plan`: up to
  date (the temporary service was created and deleted, the runner was a CLI upload).

## 2026-09-29 — Multi-Angle Research: 20-question suite on dev (suite20)

- **Runner** `orc-test-runner` deployment `5f2cfafe-e67f-4078-a5a7-542da21f250d` (CLI upload of `0afa2cf`, prefix
  `ma-suite20-20260929a`, two workers, SERVER mode, one automatic approval), 13:43–14:40 UTC: 31 turns, 0 HTTP
  errors, USD 1.10 in total, no secret in the runner, orc or sandbox logs. No variable or service setting changed.
- **ANALYSIS (4/4)**: a01 (top 5 energy by 20-day return), a02 (financials mean 20-day volatility 45.93 %, DEFI
  highest), a03 (TLKM net buying by broker, August 2026), a04 (BBRI weekly returns) all COMPLETED and matched a
  read-only ground truth exactly (temporary service `suite20-truth-job` `cb313ad2-c7b9-4c12-8e1e-1e856c509f86`,
  deployment `c96829cd-d0c7-40ae-b9a0-68b1b9deab7b`, only a `DATABASE_URL` reference, READ ONLY transaction;
  deleted afterwards, 16 services again).
- **Research (16)**: 11 plans issued (all `research_plan/v2`, 4–5 angles); e01 (PER) correctly refused as
  unavailable data; r06, r10, r12 and e04 got no plan although feasibility was FEASIBLE (M38, M37). Of the 11
  approved runs, 9 answered and 2 were LIMITATION: r04 (session workspace deleted by the sandbox janitor, S14) and
  r08 (negated agreement wording refused, P09). Ten completed runs, 42 angles: SUPPORTED 5, PARTIALLY_SUPPORTED 2,
  INSUFFICIENT_EVIDENCE 29, NOT_RUN 6 (M36), INVALID 0; 21 at FORMULA_AND_STATISTICS_VERIFIED, 15 at
  STATISTICS_VERIFIED. Every status in the answers equals the backend's; one unsupported number (r06, forced
  LIMITATION).
- **Guards**: e02 refused to prove causation or predict a price and ran a historical association plan; e03 said the
  September 2026 window is empty (broker and price data end 2026-08-31 for that plan) and answered from earlier data.
- New entries in `ERRORS_AND_SOLUTIONS.md`: S14, M36, M37, M38, P09; G12 recurred (r08, e02).

## 2026-09-29 — Multi-Angle Research: migration 20260929_001 applied on dev (Tool_Catalog only)

- **Decision**: the user chose "Tool_Catalog only" after the dry run (C07): the migration was rewritten to register
  the four inactive market-ai-orc tools and leave `AI_research_catalog` unchanged; pushed as `7ec52bb` (`main` and
  branch `claude/upbeat-dijkstra-iybq2f`).
- **market-ai-orc redeploy**: the push touched `apps/market-ai-orc/tests/` (drift test), so the watch pattern
  rebuilt market-ai-orc: `ccb8962d-e280-40d2-951a-1b320fca36fa` (`7ec52bb`) `SUCCESS`, `GET /ready` 200. Application
  code and variables unchanged; both multi-angle flags stay on.
- **Temporary job** `ma-migrate-job` (`4ff15ec3-2000-4e0c-a605-f0433eaa1c77`, only a `DATABASE_URL` reference to
  Postgres): inspection + dry run `24186829-5dc9-4707-ad01-e9dbb6c13141` (passed, rolled back), apply
  `23b4cc8f-25c1-4d46-87bb-bbf49a166331` (read back: `Tool_Catalog` 70 → 74 rows, 25 active before and after).
  Deleted after use; the dev environment again lists 16 services. Details in `DATABASE_CHANGELOG.md`.
- **Config**: no variable, domain or service setting changed in this step. `railway config pull --force` recorded what was already live: the two flags set earlier today (`PY_SANDBOX_MULTI_ANGLE_RESEARCH_ENABLED`, `AI_ENABLE_MULTI_ANGLE_RESEARCH`, as `preserve()`, no values) and `ipv6EgressEnabled: true` on market-web-governor (not changed here). `railway config plan`: up to date.

## 2026-09-29 — Multi-Angle Research flags on in dev; golden run 1 (user-approved: flags, golden, migration)

- **Flags** (dev, one service at a time): `PY_SANDBOX_MULTI_ANGLE_RESEARCH_ENABLED=true` on market-python-sandbox →
  `66a36c30-6a3a-40f7-8cb2-6481b9e929b9` `SUCCESS`; then `AI_ENABLE_MULTI_ANGLE_RESEARCH=true` on market-ai-orc →
  `91e13ace-514c-4b93-9304-63409007f916` `SUCCESS`, no `multi_angle_research_inactive`; the first question's
  `research_plan_feasibility` event carried `plan_version="research_plan/v2"`, so the capability negotiation passed.
- **Runner**: `orc-test-runner` now runs `apps/orc-test-runner` (standard library only; `MARKET_AI_ORC_API_KEY`
  reference unchanged). Golden run 1 = deployment `6b2d5c17-68c1-4270-be59-1c24a59cbf76`, prefix
  `ma-golden-20260929a`, 4 questions, 2 workers, SERVER mode with one automatic approval; about USD 0.24 in total.
  - g1 (bank falls > 5 %, RESEARCH): plan issued (6 angles, 1 bundle group, `SINGLE_BUNDLE`) after two plan
    rejections; approved run `rrun_6422cbf04a08cb9fa3cec82f` recorded some angles but never called
    `complete_research_run` → LIMITATION, all six angles `NOT_RUN` (M33, S12).
  - g2 (bank momentum): FAILED `INVALID_FINAL_RESPONSE` (unused parameters filled, M30; union errors, M31).
  - g3 (volume spike): FAILED `INVALID_FINAL_RESPONSE` (plan cut off at 8000 output tokens, M32).
  - a1 (YTD returns of three banks, ANALYSIS): COMPLETED, 21.6 s, $0.017 — ANALYSIS unaffected.
- **Fixes of run 1** (`b9e6ff3`, M30–M33, S12): market-python-sandbox `b07f70dc-df55-4990-9ada-6438515317af`
  and market-ai-orc `61f9768b-4dcc-4182-9151-eac56642a74a` `SUCCESS`, no `python_sandbox_not_ready`.
- **Golden run 2** (`f5fdca51-9a05-43a8-a5c7-abcb37a105b1`, prefix `ma-golden-20260929b`): all three plans issued
  with four angles (no plan failure); all three approved runs `COMPLETED` with backend findings at
  `STATISTICS_VERIFIED` (g1 4/4 validated; g2 3 validated + 1 INVALID `DUPLICATE_ANGLE_OUTPUT`, S13; g3 4/4), every
  angle `INSUFFICIENT_EVIDENCE` (underpowered, no significant effect); the answers were honest but each was forced to
  LIMITATION by the findings gate (M34, M35). a1 (ANALYSIS) COMPLETED. About USD 0.25.
- **Migration dry run** (temporary service `ma-migrate-job` `cd26149a-dad3-4d2d-95b5-f72adf2a4979`, deployment
  `38ab664c-c282-46e2-b538-6b942ef77515`, reference `DATABASE_URL` only): `AI_research_catalog` has 18 methods, all
  `REFERENCE_ONLY`, and none of the eight engine ids; the preflight refused as designed, nothing changed (read back
  identical). Applying needs a decision on the method ids.
- **Fixes of run 2** (`c94d781`, M34, M35): market-python-sandbox `12202417-3391-4ccc-a5a2-44070d94ec26` and
  market-ai-orc `f09a1565-0a05-4746-b9fd-bb7deb63895c` `SUCCESS`. Temporary `ma-migrate-job` deleted afterwards.
- **Golden run 3** (`7cdbf7a2-b8ab-41e5-afd2-e72df66d3667`, prefix `ma-golden-20260929c`, about USD 0.20): **4/4
  COMPLETED with an ANSWER**, gate `ANNOTATED`, label `DATA_COVERAGE_VERIFIED`, every reported status equal to the
  backend's, no forced LIMITATION.
  - g1: `drop_streak` SUPPORTED (a fall of more than 5 % continues more often after longer streaks; effective sample
    57 dates, BH-adjusted), `drop5_forward` INSUFFICIENT_EVIDENCE (INSUFFICIENT_SAMPLE: its checked data lacked the
    close column, so the outcome could not be the approved forward return; the answer says so), two angles NOT_RUN
    (not recorded, finalized).
  - g2: three INSUFFICIENT_EVIDENCE (underpowered), `a4_volatility_regime` PARTIALLY_SUPPORTED (not past the
    multiple-testing correction).
  - g3: four INSUFFICIENT_EVIDENCE; `spike_years` recorded with `research_custom` → EXECUTION_ONLY, as designed.
  - a1 (ANALYSIS): COMPLETED.
- **Result**: golden passed. Migration `20260929_001` is not applied: the live catalog has none of the eight method
  ids (see the dry run above); it waits for the user's decision. Flags stay on in dev.

## 2026-09-29 — Multi-Angle Research code on dev, flags off (user-approved)

- **Push** `main` fast-forward `8398768..426c88f` (commits `96231fe` sandbox, `426c88f` market-ai-orc; see
  `MULTI_ANGLE_RESEARCH.md`). Rollback references: sandbox `7cded3fc`, orc `ef7ff785` (both `348f03bb`).
- **Deployments**: market-python-sandbox `7f957898` `SUCCESS`, market-ai-orc `ca355581` `SUCCESS` (09:39 UTC).
  Logs: sandbox `sandbox_started` with `isolation_enforced=true` and its store upgraded to schema 4 without error;
  both answer `GET /ready` 200. Other services were not rebuilt (watch patterns).
- **Variables**: none changed. `PY_SANDBOX_MULTI_ANGLE_RESEARCH_ENABLED` and `AI_ENABLE_MULTI_ANGLE_RESEARCH` are
  unset (off), so research v1 and ANALYSIS run as before. Migration `20260929_001` is not applied.
- Next (needs a separate approval): enable the sandbox flag, then the orc flag, run golden questions, apply the
  migration last.

## 2026-09-29 — market-web-governor: `/v1/ask` relevant forward timeline and answer dates checked (W17, W18)

- **Live test before the fix** (runner `e80fe82b`, `live-ask13-20260929-q1`, "bagaimana outlook industry nikel", on
  deploy `fa27e4fa`): `ANSWERED`, 54 s, USD 0.026, 68 of 500 sources cited; timeline held forecasts ("2035",
  "2040", "25 tahun") and unrelated items (W17); one answer date was not the source's date (W18).
- **Deployment** market-web-governor: PR #35 (`8f5ad0b`) `6509a451` `SUCCESS`. No variable changed.
- **Live test after #35** (runner `44ad5ef5`, `live-ask14-20260929-q1`, same question): `ANSWERED`, 66 s, USD 0.032,
  140 of 500 sources cited, no warnings; every date in the answer is a source date; timeline 10 returned, 6 kept, all
  about nickel quotas, royalties, ESG reporting, the critical-minerals exchange and IMIP output. Remaining: one
  deadline without a year ("31 Maret") is kept as undated.

## 2026-09-29 — market-web-governor: `/v1/ask` sector turn by code, subject share, answers without [n]

- **Deployments** market-web-governor: PR #27 (`a7e8419`) went live through `6e488000` (a later `main` merge from
  another session superseded `5cbae50e`); PR #28 (`7b596d2`) `e1e9e7fd` `SUCCESS`. No variable changed.
- **Live test after #27** (runner `04ce37b5`): turn 2 always ran, but generic sector queries filled 422 of 500
  "Cimory" sources and the answer had no industry section; fixed by #28.
- **Live test after #28** (runner `49dc876d`, `live-ask7-20260929-q1..q3`): 3 of 3 `ANSWERED`, 39–66 s, USD
  0.023–0.035 each, 3 rows in `web_ask`, no `[n]` markers in `answer`. "Cimory" has an "Industry & policy context"
  section (MBDK excise postponed to 2027, MBG, raw-material and packaging costs); PTRO explains 2026 YTD −51% then
  rebound, with the new ESDM contractor rule; BI Rate unchanged (5.75%, RDG 22–23 Sep 2026). Where the model used a
  source number as a noun ("dari [487]"), removing it leaves a gap; not yet fixed.

## 2026-09-29 — market-web-governor: `/v1/ask` name and ticker, industry and policy turn, investor-first answers

- **Deployment** market-web-governor `21ea0c81` (PR #25, `91b2cf8`) `SUCCESS`; no variable changed.
- **Live test** (runner `fb457b6c`, `live-ask5-20260929-q1..q3`): 3 of 3 `ANSWERED`, 13–37 s, USD 0.022–0.029 each,
  3 rows in `web_ask`. "Cimory" searched CMRY and led with results and corporate actions, but the model returned no
  turn-2 queries (one turn only, 32 requests) although the local run of the same code did; the turn-2 rule is an
  instruction, not enforced by code. "kenapa saham ptro naik" ran an industry and policy turn and reported that the
  sources disagree on the one-year direction (2025 up, 2026 down). BI Rate unchanged (5.75%, RDG 22–23 Sep 2026).

## 2026-09-29 — market-web-governor: `/v1/ask` researches in up to 3 turns over 3-month windows (user-approved)

- **Deployment** market-web-governor `9220e7ca` (PR #23, `28dc45d`) `SUCCESS`; no variable changed
  (`WEB_ASK_MAX_SOURCES` defaults to 500).
- **Live test** (runner `c9d458ce`, `live-ask3-20260929-q1..q4`, four questions in parallel): 4 of 4 `ANSWERED`,
  13–15 s each, USD 0.015–0.032 each (about USD 0.11 in total), 80 Google News requests per question without a
  rate-limit failure, 186–500 sources from October 2024 to September 2026, 4 rows in `web_ask`. PTRO answers now
  cover October 2025 to September 2026 and add industry context (coal prices, minerba policy); BI Rate (hold at
  5.75%, RDG 22–23 Sep 2026) and ULTJ (7–8 Oct 2025 reports) unchanged.

## 2026-09-29 — market-web-governor: lean `POST /v1/ask` next to the web-need flow (user-approved)

- **Migration** `event_store/002_web_ask.sql` on Postgres-E8GM through the runner (`4620705a`, phase `migrate_sql`):
  table `web_ask` (15 columns); grants `web_event_writer` SELECT, INSERT, DELETE and `web_event_reader` SELECT on
  `web_ask` only (`web_event_item` unchanged: writer INSERT, reader SELECT). The temporary runner variable
  `EVENT_STORE_ADMIN_URL` was deleted afterwards; the runner keeps `EVENT_STORE_READER_URL` and
  `WEB_GOVERNOR_API_KEY`.
- **Deployment** market-web-governor `68bffe16` (PR #21, `c43d792`) `SUCCESS`. No variable changed on the governor;
  the answers use the existing `WEB_EVENT_STORE_URL` and slot 1 (DeepSeek V4.1 Flash).
- **Live test** (runner `b0035ebc`, `live-ask1-20260929-q1..q5`, five questions in parallel): 5 of 5 `ANSWERED`,
  4.9–15.8 s each, USD 0.015–0.016 each (about USD 0.08 in total), 69–80 sources and 2–46 citations each, no
  warnings; 5 rows in `web_ask` with `expires_at` 30 days after creation.

## 2026-09-28 — market-web-governor: event store, source policy, pre-event timeline, classification (P1–P4)

- **Main database name restored (R18):** the market-data PostgreSQL service had been renamed `Web_Fetch` in the
  dashboard; renamed back to `Postgres` (user decision). Railway rewrote every `${{...}}` reference automatically.
- **Event store (P1):** new service `Postgres-E8GM` (`4b193143-be17-456b-bc00-c1760ef5db82`, created by the user) holds
  `web_event_item` only. Migration `apps/market-web-governor/event_store/001_web_event_item.sql` applied through the
  runner (`89bd1633-ba83-4ce5-8443-5edca354140a`, phase `migrate_event_store`); 60 columns, roles `web_event_writer`
  (INSERT) and `web_event_reader` (SELECT) verified. The runner's temporary admin variables were deleted afterwards.
- **Variables** (names only): market-web-governor `WEB_EVENT_STORE_URL` (writer role), `WEB_CLASSIFIER_SLOT` 2,
  `WEB_CLASSIFIER_CHECK_SLOT` 1; web-governor-test-runner `EVENT_STORE_READER_URL` (reader role). No other service
  changed; market-ai-orc model and provider unchanged.
- **Deployments** of market-web-governor, each `SUCCESS`: `22c6420e-b6d6-412e-a334-f41ccc010eb4` and
  `239b643e-ef6c-40c9-9ce2-7c6a7857a688` (P1–P4), `68e31764-f191-49c4-ba2b-30b3ee676809` (W13 deadlines),
  `63303443-5cef-4829-9a00-48722744cf3f` (W14 batches, page dates), `3a6adb73-9ac4-41cf-865c-b11f17ba49f4` (W14 reasoning
  off), `c3425088-f93b-411e-a122-dfc04a46218c` (W15 publication window), `ffab5dea` (W15 earlier-form queries, PR #19).
- **Live ULTJ pre-event runs** (runner `precursor` phase, anchor 2026-09-18, look-back 12 months): run 1 hung (W13), runs
  2–4 classified too little or found no pre-event source (W14, W15), run 5 (`wn_642dfd96…`) 40 items, 38 classified,
  0 pre-event, USD 0.0614, 40 rows in `web_event_item`.
- Run 6 (`wn_fe134a7d…`, deployment `ffab5dea`): 40 items, 40 classified in 100 s, 0 pre-event, USD 0.0619 plus
  USD 0.0098 classification, 40 rows written. Diagnosis (W16): OpenRouter's web search ignores the date window; the
  search query decides the results. No Railway change was made for the diagnosis.

## 2026-09-29 — Bank anomaly question: ANALYSIS vs RESEARCH path, with ground truth

- d01 (`analysis_path` ANALYSIS, runner `4bb56c4f`): 61 s, $0.026, 40 anomalies (|stock − bank median| ≥ 25 pp over 1M,
  3M, 6M, YTD, 1Y). d02 (`analysis_path` RESEARCH, runner `09eed220`): plan 78 s + execution 84 s, $0.092; two
  hypotheses on the 5-day follow-through of ±20 pp deviations, `h_up_anomaly` INCONCLUSIVE (ANECDOTAL, 5 effective
  dates), `h_down_anomaly` without verdict (one event), plus anomaly tables for 1W/1M/3M.
- Ground truth: temporary service `anom-truth-job` (`182c0014-df32-41ae-8607-26cbe0833aa4`, deployment `7e1ca4ef`,
  read-only, deleted after the run): every d01 return, median and difference matches except where d01 excluded a stock
  as `NO_PRIOR_CLOSE` (G11: BSWD 3M/6M, BCIC 1Y), which moves the 6M and 1Y medians by 0.26 and 0.15 pp. New
  findings G11 and M29.

## 2026-09-29 — Sector rolling correlation (c01) and its ground truth

- Question c01 on dev through the runner (`de1a7285`, `analysis_path` ANALYSIS): 280 s, $0.105, 26 tool calls, 5
  extractions without refusal, 10 executions (modules `pandas`, `numpy`, `itertools`, `datetime`, `matplotlib`).
- Ground truth: temporary service `corr-truth-job` (`730835a5-0919-48c2-8015-2ffb35f3a127`, deployment `2e2afb35`,
  read-only session, deleted after the run) recomputed the equal-weighted 60-day rolling correlations from
  `Price_Stock_Indonesia_IDX` and `IDX_Stock_Universe`: every yearly figure (2018 0.444 … 2026 0.811), the monthly
  minimum (2024-03 0.227) and maximum (2026-04 0.890) and the last-window extremes match the answer. Robustness variants
  (median, 20-day traded-value weight, liquid stocks only) keep 2025–2026 as the highest-correlation years (value
  weight 2026 0.621 vs 0.197–0.334 in 2021–2024). No market-capitalisation column exists in the database.

## 2026-09-29 — A4 evidence, part preflight (A0/A2), join limit 6, imported-module audit (C)

- **A4** (read-only): temporary service `a4-explain-job` (`b4d58765-2308-4c0e-ab11-e7d6c36530af`, deployment
  `3e3b9480`, deleted after the run) ran bounded `EXPLAIN` / `EXPLAIN (ANALYZE, BUFFERS)` in READ ONLY transactions
  with `statement_timeout` 20 s. Result in `DATABASE_INDEX_ACCEPTANCE.md`: the planner cost of broker × banks is not
  monotonic in the window (1 day 40,326; 1 week 227,842; 1 month 37,036). No index or limit changed.
- **Code** (user-approved plan `EXTRACTION_AND_AUDIT_PLAN.md`; merged into `main` as `348f03b`; tests orc 697,
  Governor 213, sandbox 548 passed; flag-off tool definitions identical): market-sql-governor
  `5a420253-10fd-46f1-abc8-5c92d3f39e5a`, market-python-sandbox `5d74db9c-4b8b-4ad4-ba09-aa917d789804`,
  market-ai-orc `de1aaa52-5dd0-48d4-a896-8f6a31cf3bc7`, all `SUCCESS`.
- **Variables** (dev, one service at a time, each redeploy `SUCCESS`):
  - market-sql-governor: `SQL_MAX_JOINS=6`, `SQL_MAX_TABLES=7` → `372b62f8-b2af-43a3-b482-01c68e1933ca`;
  - market-python-sandbox: `PY_SANDBOX_MODULES_AUDIT_ENABLED=true` → `7cded3fc-ac04-45d7-9c54-431513889e9d`;
  - market-ai-orc: `AI_ENABLE_PREFLIGHT_PARTS=true` → `ef7ff785-c722-4189-8534-a7864d53f907`.
- `railway config pull --force` / `railway config plan`: up to date.
- **Live rerun of the broker question** (runner `84aadf53-2fc4-4426-bb18-64f45dab29cb`, `b03_broker_screen_preflight`):
  failed in 0.4 s before any model call: OpenRouter HTTP 403 "Key limit exceeded (total limit)" (M27). Live
  verification of A0/A2 and C waits until the key's limit is raised.
- **After the key limit was raised (M27 fixed)**, the same question in conversation `b04` (runner `c60cf7c9`,
  `b89d1c7f`, `014b6ea3`, `b4f85616`): the model asked for X, the benchmark and the period (user: X ≥ 10 days, return
  ≥ 10%, last 3 years); IHSG is not in the catalog, so it asked again and the user chose no benchmark (C). Research
  Plan approved automatically; answer in 160 s, $0.064, verdict INCONCLUSIVE (UNDERPOWERED, 32 effective dates).
  Governor: 31 estimate-only parts for the feasibility draft and 31 for the need, every estimate before the first
  extraction, then 31 extractions `APPROVED`, 0 refusals, 0 discarded rows. The model used `Feature_02_Broker_Rolling`,
  so the refused raw-table shape of b01 was not exercised. Sandbox executions recorded `modules`
  (`datetime`, `numpy`, `pandas`). New finding M28 (success threshold not bound to the backend's success rule).

## 2026-09-28 — Research findings v1 and caller-chosen analysis path on dev; suite9

- **Research findings v1** (user-approved design; commits `35ff278` sandbox, `f36600f` orc; merged into `main` as
  `2746ac1`): market-python-sandbox `43add1d5-4071-4fde-bc86-a325fb424a15` and market-ai-orc
  `13774e5c-d4ec-4698-b6cf-e5e1a107fe96` `SUCCESS`; Governor `SKIPPED`. Tests before the push: orc 687, sandbox
  research subset 81 passed.
- **Flags** (dev only, one at a time): `PY_SANDBOX_RESEARCH_FINDINGS_ENABLED=true` on market-python-sandbox, redeploy
  `550e8eda-17b0-492c-8d40-10f8b5b2b2ed` `SUCCESS`; then `AI_ENABLE_RESEARCH_FINDINGS=true` on market-ai-orc, redeploy
  `e3a7b24b-1aed-48db-99e2-43da86b58884` `SUCCESS` with no `research_findings_inactive` log (the sandbox capability
  was found). The fixed minimum sample of 30 no longer refuses an approved plan (M21); every research answer carries
  the backend's sample category and verdict (M22).
- **suite9** (runner `54d6c5bb-7fe0-477d-a771-e223b283fc76`, 20 questions, 11 of them research, history_mode SERVER):
  20/20 answered, 0 HTTP errors, 0 unsupported numbers, total cost $0.62. Backend verdicts: SUPPORTED 3 (r05, r06,
  r10 `up_gt5`), NOT_SUPPORTED 1 (r10 `down_gt5`), INCONCLUSIVE 8 (r01, r02 ×2, r03, r07 ANECDOTAL, r08, r09, r11),
  NOT_EVALUATED 1 (r04, INSUFFICIENT: one event); every model verdict equal to the backend's. Guards: prompt
  injection, a future date and a buy recommendation refused; p01 limited (point-in-time sector history starts
  2026-09-29). Findings: M24 (INCONCLUSIVE worded as "not supported" in r02), M25 (final status keeps the last
  completion only), M26 (SUPPORTED below the user's `min_effect`, r05).
- **Broker screening question** (runner `1687311e-0ca5-4dda-afe6-58f2f522c36a`, model chooses the path): answered
  after 1,644 s, 46 tool calls, $0.105, with a table of 282 broker × X combinations and 563 checked numbers, all
  sourced; the model alternated between plan feasibility and analysis first (M23).
- **Caller-chosen path** (user-approved; commit `5c1410f`): `analysis_path` ANALYSIS or RESEARCH on
  `POST /v1/agent/run`, behind `AI_ENABLE_ANALYSIS_PATH`. market-ai-orc `69f54431-eb4d-4f74-a685-b48b966840b3`
  `SUCCESS` (sandbox, Governor `SKIPPED`); orc tests 692 passed, flag-off tool definitions identical. Then
  `AI_ENABLE_ANALYSIS_PATH=true` on market-ai-orc, redeploy `d1ac8372-7caa-48fa-aab4-61da960299dd` `SUCCESS` with no
  `analysis_path_inactive` log.
- **Broker question again with `analysis_path` ANALYSIS** (runner `1443b8db-bcd0-4475-a161-40e14168fd8c`, the
  original question without the "screening" hint): COMPLETED in 631 s (was 1,644 s), 35 tool calls (was 46), $0.110,
  no path refusal, no plan step; table of broker results with 177 checked numbers, all sourced; the answer and the
  backend line state that the figures are descriptive, without significance tests. The two runs chose different
  definitions (X, the benchmark, cumulative versus daily net buy), so their broker rankings differ.
- `railway config pull --force` / `railway config plan`: up to date (the pull also removed duplicated sandbox and orc
  blocks in `.railway/railway.ts` and captured resources other sessions added).

## 2026-09-28 — IP2 merged into main; Governor dependency fix (R19)

- **Approval:** the user approved pushing the IP2 branch to `main` so `main` carries the S09 fix while the resample
  rules exist on dev (Audit Store flags stay off).
- `main` fast-forwarded `5229423..c403f27` (IP2 + the web-governor PRs; only conflict `RAILWAY_CHANGELOG.md`, both
  sides kept). Tests after the merge: orc 678, Governor 209, sandbox IP2 subset 25 passed.
  - market-sql-governor `d0f9fb31-64a0-4884-a56f-1a95024d1a10` **FAILED** its `/ready` health check:
    `ModuleNotFoundError: httpx` (R19). The previous deployment kept serving.
  - market-python-sandbox `f85accbf` and market-ai-orc `60d19e42` `SKIPPED` (watch paths); they keep running the
    identical IP2 code from the CLI uploads `e7d4ce58` / `9d8e9182`.
- Fix `b42e72e` (`httpx==0.28.1` in the Governor requirements, verified by importing `app.main` in a clean
  virtualenv): market-sql-governor `d9f39bd9-139f-43c0-91a7-caeed39a2309` `SUCCESS`, `/ready` 200, no error or
  secret in the start-up log. Sandbox `33ec5ab2` and orc `2f129f07` `SKIPPED`.
- `main` and `claude/upbeat-dijkstra-iybq2f` now point to the same code; the next change under
  `apps/market-python-sandbox` or `apps/market-ai-orc` on `main` redeploys IP2, not the pre-IP2 code.

## 2026-09-28 — market-web-governor: evidence retention 30 days (user-approved)

- `WEB_RETENTION_HOURS` 168 → 720 on market-web-governor only; redeploy `f60ae1a1-365d-4c11-9dcd-4cd57cd9ce46` `SUCCESS`
  (rollback reference `e1d0d071`). Stored web needs, evidence and documents now expire 30 days after creation; the
  ULTJ research of 2026-09-28 is kept until about 2026-10-28.

## 2026-09-28 — market-web-governor: governor-side fetch, 7 model slots, shared evidence budget (PR #8)

- **Code** `dfdc89e` (PR #8, user-approved proposals A, B, C; 25 tests): governor-side fetch with verified quotes
  (`GET /v1/documents/{id}`), seven model slots with `model_slot` on requests, evidence budget shared across criteria,
  full excerpts kept in storage, results per search up to 30 and output tokens up to 8000. Deployment
  `33f7c937-5847-4515-9c91-01604d5aec43` `SUCCESS` (rollback reference `4fd9d7b4`).
- **Variables** (market-web-governor only; approved): `WEB_MAX_RESULTS_PER_SEARCH` 30, `WEB_MAX_EVIDENCE_ITEMS` 40,
  `WEB_MAX_OUTPUT_CHARACTERS` 64000, `WEB_OPENROUTER_MAX_OUTPUT_TOKENS` 8000, `WEB_OPENROUTER_TIMEOUT_SECONDS` 90 (an
  8,000-token answer needs more than 40 s), `WEB_DEFAULT_SLOT` 1, `WEB_SLOT_1_LABEL`, `WEB_SLOT_2_MODEL`
  `xiaomi/mimo-v2.5`, `WEB_SLOT_2_LABEL`, `WEB_SLOT_3_MODEL` `z-ai/glm-5.3-flashx`, `WEB_SLOT_3_LABEL`. Set after the
  code deploy because the old code refused them; redeploy `e1d0d071-3e33-4802-aedd-8b7b4f783f33` `SUCCESS` (volume
  mounted, `GET /ready` 200). `railway config pull --force` / `railway config plan`: up to date.
- **Live ULTJ / Frisian Flag research** (runner `b322aa45`, `live-ultj-20260928-*`, slots 1–3 in parallel): DeepSeek 4 of
  5 criteria (36 evidence), GLM 3 of 5 (26 evidence); MiMo and the remaining criteria failed with HTTP 402 because the
  OpenRouter account ran out of credit (W11). Governor fetch downloaded and stored `bi.go.id` (143 KB, HTTP 200) on
  every slot, but the model read was refused by the same 402; the FrieslandCampina page is script-rendered and was
  reported `DYNAMIC_PAGE_OR_EMPTY` without a model call. Cost of the run about USD 0.07.
- **Blocking:** the OpenRouter credit also serves market-ai-orc; top-up needed before further live use.

## 2026-09-28 — market-web-governor: deeper retrieval and a larger output budget (user-approved)

- **Variables** (market-web-governor only, set with the API; model and provider unchanged,
  `deepseek/deepseek-v4.1-flash` through OpenRouter/Exa): `WEB_OPENROUTER_MAX_OUTPUT_TOKENS` 1800 → 4000,
  `WEB_MAX_RESULTS_PER_SEARCH` 5 → 10, `WEB_MAX_EXCERPT_CHARACTERS` 2500 → 5000. Rollback reference
  `254e5f0b-e3d8-48d6-8e65-9e4d162ad2a7`; redeploy `23d0a4f6-5c78-48f1-8707-baf8a94aacba` `SUCCESS` (volume mounted,
  `GET /ready` 200).
- **Live T6** (`live-smoke-20260928-r5-t6-bbca-webneed`, 10 results per search, runner `webneed` phase): 5 of 5
  provider calls completed (W02 fixed; output 3,318–4,033 tokens, so the margin is thin); 17 web searches; USD 0.068
  (was 0.054). New limit W09: the 20-item evidence budget was used by the first two criteria and the 32,000-character
  response cap emptied every excerpt, so criteria 4 and 5 have no evidence. Not changed; proposed to the user.
- **Runner:** `webneed` phase; Test 8 now probes limits above the new maxima.

## 2026-09-28 — market-web-governor live end-to-end test on dev; three fixes (AI-Orc unchanged)

- **Scope:** live test of `market-web-governor` (`1c43a00e-9deb-4b17-84f0-acfa35142ac6`) through OpenRouter/Exa.
  AI-Orc, SQL Governor, Python sandbox, PostgreSQL, buckets and every other service were not changed by this task;
  the Web Governor has no public domain and no database credentials. Request IDs: `live-smoke-20260928-*`,
  `-r2-*`, `-r3-*`, `-r4-*`.
- **Execution path:** the agent container cannot reach Railway SSH (R16). With the user's approval a kept private runner
  `web-governor-test-runner` (`8409cd61-66d1-48eb-8db7-97e607bbc6b3`) was created: restart `NEVER`, no domain, one
  reference variable `WEB_GOVERNOR_API_KEY` (value not recorded), code in `apps/web-governor-test-runner`, deployed with
  `railway up`. Runs: `414fc509` (round 1), `f807533e` (persistence), `47ce02f3` (round 2), `dca2fafa`, `a528d2c2`
  (smoke).
- **Preconditions (read-only):** source `rednightt33/saniti` `main`, root `/apps/market-web-governor`; volume
  `market-web-governor-data` (`c02e7a3c-6330-4f92-a3ca-0990af002b5a`) mounted at `/data`;
  `WEB_GOVERNOR_STORE_PATH=/data/web-governor.sqlite3`; `RAILWAY_RUN_UID=0`; no service or custom domain; deployment
  `73dd34f3-45b2-42df-ae7b-b519b096d4df` `SUCCESS` (rollback reference). 8 unit tests passed.
- **Round 1 (deployment `73dd34f3`):** authentication (401 without or with a wrong key, 200 with the key),
  readiness, capabilities, idempotency (identical replay byte-identical without a provider call; changed content 409
  `IDEMPOTENCY_CONFLICT`) and budgets (every over-limit request 422 with its code, nothing stored) passed. Defects:
  truncated provider output reported as `NOT_FOUND` / `CONTRADICTED` (W01), exact fetch without evidence and with an
  uncited summary (W03), `web_search_requests` always 0 (W04), search/fetch without request-ID log lines (W05).
- **Persistence:** plain redeploy of this service only, `73dd34f3` → `79b86178-659d-4e65-90c6-5e7e4a5a53cf`
  `SUCCESS`; web need `wn_52846614753a479e85e34e6d5e16e45b` and evidence `ev_65b28ef5d9cc4d69ac5c82e0e56b4011`
  read back byte-identical (response SHA-256 match; evidence `content_sha256` `ad890795…`). They matched again after
  the fix deployment.
- **Fixes:** PR #3 (`8a6c301`, W01/W03/W05, per-call diagnostics), PR #4 (`733a373`, W04, records), PR #5
  (`31db707`, W08 search-overrun warning, R17 corrected). Tests 8 → 16. Web Governor deployments: `a5db8024` (from
  #3; a manual deploy of the same commit, `9efabd95`, was redundant, R17), `a8de41ba` (#4), final
  `254e5f0b-e3d8-48d6-8e65-9e4d162ad2a7` `SUCCESS` (#5); each log shows the volume mount and `GET /ready` 200. For
  every merge, market-ai-orc, market-sql-governor and market-python-sandbox deployments were `SKIPPED` (no watched
  change).
- **Round 2 (deployment `9efabd95`, commit `8a6c301`):** the diagnostics confirmed W01 (`incomplete_reason`
  `max_output_tokens`, about 2,000 reasoning tokens against `WEB_OPENROUTER_MAX_OUTPUT_TOKENS=1800`): 4 of 5 T6
  criteria are now `BLOCKED` with `RETRY_PROVIDER` instead of misreported. W03 confirmed: `openrouter:web_fetch` ran but
  returned no citation, so the fetch reports `EXACT_URL_NOT_CITED` and withholds the summary. Smoke runs confirmed W04
  (`web_search_requests` 2) and W08 (the warning fires).
- **Open (not changed, need a decision):** W02 output budget (a provider configuration change), W03 fetch evidence,
  W06 fast-search two-domain rule, W07 publication dates and per-item stance. Provider cost of all live calls about
  USD 0.16.
- **Logs:** no key, bearer header, provider secret, stack trace or provider body in the Web Governor or runner logs.
- **Config:** `railway config pull --force` added `web-governor-test-runner` and recorded two variables already live on
  market-ai-orc and market-python-sandbox (`preserve()`). `railway config plan` (not applied) lists one deletion,
  `ip2-truth-job`, a service created at 14:36 UTC outside this task; it was left alone. Deployments of market-ai-orc
  (`9d8e9182`, 14:26) and market-python-sandbox (`e7d4ce58`, 14:22) in the same window came from that other work,
  not from this task.
## 2026-09-28 — IP2 solution 1 on dev: derived weekly/monthly (branch deploy, Audit Store off)

- **Approval:** the user chose "Deploy IP2 ke dev dulu" on 2026-09-28: deploy the IP2 sandbox and orc from branch
  `claude/upbeat-dijkstra-iybq2f`, apply migration `20260928_002` and switch derived frequency on, then run 20 new
  questions. Solution 2 (Audit Store, migration `20260928_001`, all `*_AUDIT_*` variables) stays off and uncreated.
- **Code** `8516bde` (IP2 branch merged with `main` `004156f`), deployed by **CLI upload** (clean `git archive` of the
  app folder in its repository layout, `railway up <dir> --path-as-root`, so the service root directory and watch
  path apply). The services stay connected to GitHub `main`; `main` does not contain IP2.
  - Rollback references: market-python-sandbox `76784468-b6bc-473c-91c2-2195d6153610` (`4dfa7af`), market-ai-orc
    `9d6e0b35-7e48-49bc-ba47-1b178c436b6b` (`afb15a7`). market-sql-governor is not redeployed (its catalog contract
    already carries `resample_aggregation`).
  - Order: migration (DATABASE_CHANGELOG), then sandbox, then orc, because the orc reads the sandbox capability once
    at start-up.
  - market-python-sandbox `e7d4ce58-4fb4-4ce2-be6c-34f1f269112c` `SUCCESS` (build 43 s): `isolation_enforced=true`,
    0 interrupted analyses, `/ready` 200.
  - market-ai-orc `9d8e9182-4b5c-45bb-8211-e2471930877d` `SUCCESS`: `/ready` 200, no `*_inactive` event.
  - Start-up logs of both held no bearer token, OpenRouter key or DSN with a password.
- **Variables** (set with `--skip-deploys` before each upload; values are `true`):
  `PY_SANDBOX_DERIVED_FREQUENCY_ENABLED` on market-python-sandbox, `AI_ENABLE_DERIVED_FREQUENCY` on market-ai-orc.
  `AI_MODEL` unchanged (`deepseek/deepseek-v4.1-flash`), `AI_PROVIDER_SORT` not set.
- **Temporary service** `ip2-migrate-job` (`753f7c2c-fd1f-4812-9c0d-b717f70073c0`, only a `DATABASE_URL`
  reference): dry run `a38641e8`, apply `ecb6c078`; deleted at 14:21:47 UTC.
- **IaC:** `railway config pull --force` added the two variables as `preserve()` and also recorded
  `web-governor-test-runner`, a service created outside this task; `railway config plan`: up to date.
- **Live test, suite8** on `orc-test-runner` (`96e3ba29-62b9-4737-94a8-d8de7a1244a6`, two workers, 20 new questions:
  24 turns plus 3 plan approvals, 14:29–14:41 UTC, $0.399 in total; model `deepseek/deepseek-v4.1-flash`):
  - Weekly/monthly (w01–w05, m03 turn 2, r01): every answer carried `derived_frequency` provenance (1D→1W/1M,
    semantics version 1, incomplete periods named) and matched a read-only ground truth exactly: BBCA weekly returns,
    TLKM monthly volume (9 months), BBRI weekly OHLCV, BMRI monthly foreign net per board (September correctly "not
    available": broker data ends 2026-08-31), ASII weekly RSI(14) 36.93 (Wilder), Energy top-3 weekly returns. r01
    (weekly foreign flow → next-week return, 532 events) ran end to end after one approval.
  - Other checks: m01 (returns, volatility, ratio over three turns, reusing one session and one extraction) and f01,
    f02, p03, g01 matched the ground truth; p01 refused with `POINT_IN_TIME_UNAVAILABLE`; p02 reported history from
    2026-09-28 only; g01–g04 refused hidden reasoning, a credential/system-prompt request, fundamentals and a future
    date. No `SESSION_CAPACITY_EXCEEDED`, no failed session close, no secret in any log.
  - Findings recorded in ERRORS_AND_SOLUTIONS (all OPEN): C06 stale coverage end date (2026-09-25) in answers, S10
    `resampled_returns` namespace/columns friction (9 of 70 executions `SCRIPT_ERROR`, all recovered), M21 plan with
    a minimum sample below the Research Governor floor (r02 needed a second approval), P08 gate refusing a sign-less
    restatement of a released difference (r03 forced to LIMITATION).
  - Ground truth: temporary service `ip2-truth-job` (`f3dac636-d675-4009-a1bf-4be00e823906`, only a `DATABASE_URL`
    reference, every query in a READ ONLY transaction), deployment `8b5d56ec-2fd7-4c88-8daf-0bd83547673c`; deleted
    at 14:38:34 UTC.
- **Rollback:** redeploy the two rollback references (or set both flags to `false` and redeploy; the `main` code
  ignores them). The seeded rules can stay only while the sandbox runs `8516bde` or later: `main` still has defect S09
  (see ERRORS_AND_SOLUTIONS), so a sandbox deploy from `main` needs the rules reverted by a forward migration or the
  fix merged first.

## 2026-09-28 — standalone market-web-governor created on dev (AI-Orc unchanged)

- **Scope:** created only `market-web-governor` (`1c43a00e-9deb-4b17-84f0-acfa35142ac6`). No existing service,
  PostgreSQL object, market-data permission, or AI-Orc configuration changed. The service is private and is not yet
  registered as an AI-Orc tool.
- **Source:** `rednightt33/saniti`, branch `main` after PR #2 was squash-merged as `6be2420`, root
  `/apps/market-web-governor`, watch path `/apps/market-web-governor/**`, Dockerfile build, runtime V2, one SFO replica,
  restart `ALWAYS`, `/ready` health check (120 s).
- **Contract:** provider-neutral v1 WebNeed plan/execute API, fast search and exact-URL fetch; OpenRouter is the first
  adapter. Evidence responses include criterion coverage, evidence/citation IDs, policy application, hashes, lineage,
  provider usage and next action. SQLite stores web needs, provider calls and evidence; retention is 168 hours.
- **Variables:** added on this service only (values not recorded): `WEB_GOVERNOR_API_KEY`, `OPENROUTER_API_KEY`
  (Railway reference to the existing OpenRouter key), `PORT`, `WEB_PROVIDER`, `WEB_GOVERNOR_STORE_PATH`,
  `WEB_OPENROUTER_MODEL`, `WEB_OPENROUTER_ENGINE`, `WEB_OPENROUTER_TIMEOUT_SECONDS`,
  `WEB_OPENROUTER_MAX_RETRIES`, `WEB_OPENROUTER_MAX_OUTPUT_TOKENS`, `WEB_MAX_CRITERIA`, `WEB_MAX_SEARCHES`,
  `WEB_MAX_RESULTS_PER_SEARCH`, `WEB_MAX_EVIDENCE_ITEMS`, `WEB_MAX_OUTPUT_CHARACTERS`,
  `WEB_MAX_EXCERPT_CHARACTERS`, `WEB_RETENTION_HOURS`, `WEB_CLEANUP_INTERVAL_SECONDS`, and `RAILWAY_RUN_UID=0`
  so the process can write to Railway's root-owned volume mount.
- **Verification:** 8 unit/API tests passed locally, Python compilation and `git diff --check` passed. The first two
  deployments resolved `main` before the branch source update and could not find the Dockerfile. The next image built
  but failed its health check on an IPv6-only Uvicorn listener (R15). Commit `d0a1ae5` bound the image to
  `0.0.0.0:8080`; deployment `1f8802e2-6dfa-49c5-948a-0afbafc7f8c0` reached `SUCCESS`, and the deploy log records
  `GET /ready` 200. After storage was attached, deployment `b09b515f-cc34-4178-ab4b-1eafbcd1ec48` reached `SUCCESS`;
  its deploy log records the volume mount, application startup, and `GET /ready` 200.
- **Durable storage:** attached `market-web-governor-data` (`c02e7a3c-6330-4f92-a3ca-0990af002b5a`) at `/data`.
  `/data/web-governor.sqlite3` now survives container restarts and redeploys.
- **Final deployment:** after switching the Railway source to `main`, deployment
  `73dd34f3-45b2-42df-ae7b-b519b096d4df` reached `SUCCESS`; the log confirms the volume mount, application startup,
  and `GET /ready` 200. The service remains private with no public domain.

## 2026-09-28 — S08 fix on dev: one open analysis session per run

- **Code** `afb15a7` (market-ai-orc only; no flag, no variable change): before another `open_analysis_session`, an
  earlier uncompleted session of the run with no successful execution (or an `INCOMPLETE` completion) is closed, and
  one with successful executions refuses the open with `ANALYSIS_SESSION_ALREADY_OPEN` until `complete_analysis`.
  Deployed by the GitHub connection: market-ai-orc `9d6e0b35-7e48-49bc-ba47-1b178c436b6b` `SUCCESS`;
  market-sql-governor `0e72ac3f` and market-python-sandbox `9b31b83e` `SKIPPED` (unchanged). Tests: orc 669 passed.
- **Live check on `orc-test-runner`** (`d8d2efc9-c1f9-4762-8e8d-7c32ee250c10`, suite7, two workers, the suite6 pair
  that met S08): k01 ANSWER, 19 of 19 days identical ($0.024); p02 ANSWER with the `CURRENT_STATE_COLUMN` limitation
  ($0.006); no `SESSION_CAPACITY_EXCEEDED`. In this run p02 opened one session only, so the refusal and close paths
  were exercised by the unit tests, not live. `PY_SANDBOX_MAX_SESSIONS` unchanged (2).

## 2026-09-28 — IP1 Stage D on dev: point-in-time reference history, time_basis

- **Code** `4dfa7af` (flag `AI_ENABLE_POINT_IN_TIME`, default off; with it off the tool definitions and system prompt
  are identical to the previous deploy; before migration `20260927_006` the Governor contract is unchanged), deployed
  by the GitHub connection: market-sql-governor `f7c12ba4-c088-4f8c-8963-28656291c6db`, market-python-sandbox
  `76784468-b6bc-473c-91c2-2195d6153610`, market-ai-orc `14c93904-e694-49f3-921d-fbce436a6858` (replaced by the flag
  redeploy below, same commit); each reached `SUCCESS`. Tests: orc 667, Governor 200, sandbox 499 passed.
- **Migration** `20260927_006` through `relcat-job` (read-only inspection `9f44200f` / `4d67db35`, dry run `4792bd22`,
  apply `5a41e7d8`, live golden `0a76c2d3`; see DATABASE_CHANGELOG).
- **Flag**: `AI_ENABLE_POINT_IN_TIME=true` on market-ai-orc (dev) with the CLI; redeploy
  `7fb90fe1-ccab-4c9f-8f14-cd073ed9e258` `SUCCESS`, no `*_inactive` log (the sandbox reports `point_in_time` version 1).
  `.railway/railway.ts` lists it as `preserve()`; `railway config pull --force` and `railway config plan`: up to date.
- **Live checks on `orc-test-runner`** (model `deepseek/deepseek-v4.1-flash`, unchanged):
  - suite6 (`5e956053-c23a-4ab1-8635-364b6851e274`, two workers):
    - p01, a point-in-time question for August 2026: refused by the validator with `POINT_IN_TIME_UNAVAILABLE`
      (history answers dates from 2026-09-29); the answer is a LIMITATION that says so, extracts nothing and offers a
      descriptive run with current classifications instead of switching silently; $0.012.
    - p02, average `return_20d_pct` per Feature 01 sector: ANSWER with the `CURRENT_STATE_COLUMN` warning and its
      limitation line (the sector is today's); provenance 29 checked, 0 unsupported.
    - s01, top gainers 1–25 September: ANSWER, unchanged behaviour.
    - k01 (the suite5 composite-key check): LIMITATION `SESSION_CAPACITY_EXCEEDED`, because the concurrent p02 run held
      both sandbox session slots (S08, OPEN; not caused by this change).
  - suite6b (`ca36d4bf-c337-42ff-b462-1b028d43a914`, k01 alone): ANSWER, 19 of 19 days identical as in suite5;
    provenance 65 checked, 0 unsupported; $0.023.
  - suite6c (`74784da7-5830-44b7-83b5-15978926965a`, p02 alone, the runner now records `time_basis`): final status
    `time_basis` `HISTORICAL_DESCRIPTIVE`, warnings `CURRENT_STATE_COLUMN`, data coverage PASS; $0.009.
- **`relcat-job` deleted** (`bce027de-84d9-4320-a055-fd5aee485adb`, 2026-09-28 08:41 UTC): the temporary migration
  service of IP1 Stages A–D, idle after its last job, held only a `DATABASE_URL` reference. `railway config pull
  --force` removed its block from `.railway/railway.ts`; `railway config plan`: up to date.

## 2026-09-27 — IP1 Stages B and C on dev: composite keys, preaggregation, aggregation rules

- **Code** `9262fd8` (flag `AI_ENABLE_COMPOSITE_KEYS`, default off; with it off the tool definitions and system prompt
  are identical to the previous deploy), deployed by the GitHub connection: market-sql-governor
  `921e67dd-b95f-4385-9d95-a73c1e1e747f` `SUCCESS` (composite restrictions, draft lineage), market-python-sandbox
  `a8009715-a414-4cfa-8222-d2ae275e7341` `SUCCESS` (`data_need_spec/v2`, `join`/`preaggregate` helpers), market-ai-orc
  `a477521d-f3e6-4885-834d-f66ed17c1883` (replaced by the flag redeploy below, same commit).
- **Migration** `20260927_005` through `relcat-job`: dry run `1331bc3c-53d8-455c-b09b-7ca478360f99`, apply
  `91eac33f-2dc7-44d1-800d-f2d5e51aa091`; golden check `603d3578-ff2e-4a78-8c81-1ba8bf8e35d2` `SUCCESS` (see
  DATABASE_CHANGELOG).
- **Flag**: `AI_ENABLE_COMPOSITE_KEYS=true` on market-ai-orc (dev) with the CLI; redeploy
  `052c9e06-6326-4df1-9990-e3a74c45f98f` `SUCCESS`, no `*_inactive` log (the sandbox reports `data_need_spec_versions`
  v1 and v2). `.railway/railway.ts` lists it as `preserve()`. `railway config pull --force` also added the temporary
  `relcat-job` block; it stays in `.railway/railway.ts` until the service is deleted after IP1 Stage D.
- **suite5** on `orc-test-runner` (`d57b5c15-fea8-4708-9102-679d435d6769`), both `COMPLETED` / `ANSWER`, data coverage
  `PASS`, methodology provenance 0 unsupported:
  - k01: Feature 02 foreign net value summed per day vs Feature 03 `foreign_net_value`, BBCA Regular, August 2026:
    19 days identical, total 1,244,364,610,000 IDR; $0.020, 137 s.
  - k02: Broker Summary ↔ Feature 02 joined on five keys (broker AK, BBRI, Regular, August 2026): 33 rows, Foreign and
    Domestic kept apart; $0.025, 39 s.

## 2026-09-27 — Research Plan feasibility, methodology note, M19/P06 fixes and IP1 Stage A on dev

- **Code** `fd23d12` (all new flags default off, prompt and tool definitions unchanged with them off), deployed by the
  GitHub connection: market-ai-orc `888e758d-420e-4201-8beb-65657871a271`, market-python-sandbox
  `e38b7356-bb22-4558-9a3d-5b2828b1e215` (SQLite schema version 2, `data_need_drafts`), market-sql-governor
  `34dbc458-dbbb-4890-bb26-62babbd91767` (`estimate_only`); each reached `SUCCESS`.
- **Flags**: set `AI_ENABLE_METHODOLOGY=true` and `AI_ENABLE_PLAN_FEASIBILITY=true` on market-ai-orc (dev) with the CLI;
  redeploy `d5a5c5c4-ffac-41c0-bdd1-0dadd93b0052` `SUCCESS`, no `*_inactive` log at startup (the sandbox reports
  `plan_feasibility` version 1). `.railway/railway.ts` lists both as `preserve()`; `railway config pull --force` and
  `railway config plan` reported no drift.
- **G09** found by the first live run (suite3 on `orc-test-runner`, deployment `3392d5cc-365f-45a9-a0a9-49e897b8a32a`):
  every feasibility check failed because the orc Governor client refused `WITHIN_LIMITS`. Fix `834fc18`; market-ai-orc
  `62154ade-8b06-47b1-b51f-287c88058bd8` `SUCCESS`.
- **Before the catalog change** (suite3b, `db4dcf10-a681-4eda-b0ce-5a906a9265a8`): a bank volume-spike question went
  FEASIBLE check → plan bound to its draft → approval executed with a methodology note (provenance 8 checked, 0
  unsupported; 100 answer numbers checked, 0 unsupported). The mining question asked which broker was meant
  (CLARIFICATION).
- **IP1 Stage A migration** `20260927_004` through the temporary service `relcat-job`
  (`bce027de-84d9-4320-a055-fd5aee485adb`, `DATABASE_URL` reference only): dry run `ee637bf6-…`, apply
  `d02876fe-e2e4-493d-8c7f-9d49c841fbb0` (see DATABASE_CHANGELOG). `relcat-job` is kept, idle, for the Stage B–D
  migrations of this plan and is deleted after them.
- **After** (suite4, `366cb0f4-6366-4ad4-a1ea-4ac080d32794`, with one scripted clarification answer "test every
  broker"): the mining question got a FEASIBLE plan (73 stocks, 2024-09 to 2026-08) and, on approval, statistics
  (C05 FIXED). Costs: plan $0.041, execution $0.019.

## 2026-09-27 — `orc-test-runner` (kept) and the first test suite on dev

- Requested by the user: 10 technical-screening questions, 5 deep research questions, 5 multi-turn conversations and
  one broker/mining research question; the service is kept for reuse.
- **Service** `orc-test-runner` (`09358b92-09d4-4da2-b547-bf8f621e226c`): a one-off runner, restart policy `NEVER`,
  reference `MARKET_AI_ORC_API_KEY` only. `suite.json` lists items (`single`, `research` with one automatic approval,
  `multi`), all in `history_mode: SERVER`, with two workers. Run a new suite with
  `railway up <dir> --path-as-root --service orc-test-runner`. Added to `.railway/railway.ts` by `railway config pull`.
- **suite1** (deployment `812e54fe-3069-43a3-a016-034d0b5ccf29`): 37 turns, $0.70, 2,413 s of run time.
  - 34 `ANSWER` or plan turns; every screening question and every multi-turn follow-up answered with provenance clean.
    Redisplay turns needed 1–2 tool calls.
  - Two forced LIMITATIONs: m04.2 (the gate was right: board and sector totals not in a released output) and r04 (P06,
    a gate false positive on scientific notation).
  - The broker/mining question was approved but never executed (C05, M19).
- **suite2** (deployment `f18c80aa-12c9-4eac-8b4b-5c491f56110a`): the broker/mining question again with an explicit
  approval, $0.07. It stopped again before any data need and named the missing catalog relationship (C05).
- `railway config plan`: up to date.

## 2026-09-27 — market-ai-orc and market-python-sandbox: conversation reuse on in dev (phases S1/S2)

- Approved by the user: phase S05, then H2 and S1/S2. Implementation plan of 2026-09-27, sections 9–10.
- **Code, flags off** (`23290ad`, auto-deploy from `main`): market-python-sandbox `d8017f23-89c5-429e-86e4-434cf34d7b6b`
  and market-ai-orc `46a2633d-37d7-4492-a060-e6a6445e919f`, both `SUCCESS`, `/ready` 200.
  - The sandbox upgraded its dataneed SQLite to schema version 1 at startup (additive columns, two new tables) with
    no error.
  - Tests: orc 639 passed, sandbox 473 passed. Flag-off tool definitions and system prompt were identical to the
    previous deploy.
- **Variables:**
  - market-python-sandbox `PY_SANDBOX_ENABLE_CONVERSATION_REUSE=true`, redeploy `c989d7f8-b6c9-437b-9ebb-f07d9b698579`
    `SUCCESS`;
  - then market-ai-orc `AI_ENABLE_CONVERSATION_REUSE=true`, redeploy `4f821959-3d3e-47ca-9211-4d3f1511777d`
    `SUCCESS`; no `conversation_reuse_inactive` log, so the capability handshake passed.
  - `railway config pull --force` and `railway config plan`: clean after the two names were added to
    `.railway/railway.ts`.
- **Fixes found by the PoC** (`b19872f`, `dbceac3`): M18 (released values of a session's second completion replaced
  the first's) and S07 (inherited coverage came only from the last passed epoch). Redeploys: market-ai-orc
  `95a3afe3-b5fb-41ec-a0ed-4c2ed2ad7377` and market-python-sandbox `bd2af73d-5065-46c5-a3ee-c615dea03bbe`, both
  `SUCCESS`. Both services restarted, which the PoC used as the recovery case.
- **Live PoC** through the temporary service `reuse-poc-job` (`d2835c1e-1251-4f97-b406-84801e53c115`, deployments
  `56d1da0e…`, `1971041f…`, `3020a7de…`, `c2544717…`, `f9aef565…`; references `MARKET_AI_ORC_API_KEY` only;
  deleted). All turns ran in `history_mode: SERVER` with no caller history. About $0.15 in total. Verified from the
  responses and from the orc and sandbox logs (`conversation_resources`, `conversation_reuse_summary`,
  `bundle_reused`, `session_attached`, `bundle_built`).
  - **A, analysis continuation** (one conversation):
    - A1 "return YTD 2026 semua saham bank sampai 28 Agustus 2026": one extraction (`bundle_built`), two completions
      in one session. The answer was forced to LIMITATION by M18, since fixed.
    - A2 "ambil yang return YTD-nya minimal 10%": 4 banks, `ANSWER`, 23 s, 4 tool calls, $0.004. It read the
      released outputs of A1 (`READ_RELEASED`), with no extraction and no Python run. Provenance 28 numbers checked,
      0 unsupported.
    - A3 "tampilkan tanggal basis dan harga akhirnya": `ANSWER` from the same released outputs, 19 s, 3 tool calls.
  - **D, warm session** (same conversation), "volatilitas harian YTD 4 saham tadi":
    - `bundle_reused` and no `bundle_built`, so no extraction;
    - `session_attached` on A1's session `sess_a8de…`, epoch 3, with the request's own approved need;
    - `COMPLETED` with `inherited_coverage` naming A1's completions, `ANSWER`, 59 s, $0.036, provenance clean.
    - Its first completion failed coverage (S07, since fixed).
  - **C, recovery** after both services restarted (the M18 and S07 redeploys; the warm session was closed by the
    restart):
    - C1 "ambil yang minimal 5%" and C2 "tabel return YTD lengkap": `ANSWER` from A1's released outputs. The
      history came from PostgreSQL after the orc restart. C2 checked 148 numbers, 0 unsupported.
    - C3 "volatilitas AMAR, BTPN, BBTN": `bundle_reused` (the bundle survived the restart), then a new session on
      the bound bundle (`bound_bundle: true`), coverage `PASS`, `ANSWER`, 26 s, $0.014.
  - **B, research** (new conversation, the r19 question):
    - plan `PENDING`;
    - "Setuju, jalankan.": `EXECUTE_APPROVED`, coverage `PASS`, three completions in the request, provenance 99
      checked, 0 unsupported; plan `EXECUTED`;
    - "Tampilkan lagi rincian angka hasil eksperimen tadi": `READ_RELEASED`, no new experiment;
    - "ubah ambangnya: RSI(14) di bawah 25": a **new plan** awaiting approval, with no tool call and nothing run in
      the warm session.
  - Not exercised live: artifact expiry after 24 h (covered by tests: `NO_MATCH` `EXPIRED`, expired outputs
    unreadable), eviction under slot pressure, and the S05 close of an unfinished session (covered by tests).
- `railway config pull --force` and `railway config plan` after deleting the temporary service: up to date.
- The docs commit `3ac92f2` touched `apps/market-ai-orc/README.md`, so it redeployed market-ai-orc `db6d8dcf-4d3e-412e-a666-61b77689c004` (`SUCCESS`, same code as `dbceac3`).

## 2026-09-27 — market-ai-orc: Research Plan continuation kept by the server (phase H2)

- Approved by the user: phase H2. No new variable, secret or migration: the plan lives in the existing
  `AI_conversation.state` column; `CLIENT` mode is unchanged.
- **Code** `0b87d96` (auto-deploy from `main`): market-ai-orc `4024ed1b-1848-42d4-8690-b4c25070e3e0` `SUCCESS`,
  `/ready` 200. Tests 630 passed.
- **Live PoC** through the temporary service `h2-poc-job` (`5f3d3c97-a2bf-48fc-8c57-c187085852f3`, deployment
  `db5726c9-fe7c-4b3f-8768-b884cb1d1995`, reference `MARKET_AI_ORC_API_KEY` only, deleted), one conversation, the
  r19 research question (RSI(14) BBRI below 30, 10-day return), about $0.039:
  - turn 0: a Research Plan, 12.4 s; `conversation.research_plan` `PENDING`;
  - turn 1, "Setuju, tetapi ubah periodenya menjadi Januari 2024 sampai Agustus 2026." with no plan or token from
    the caller: the classifier read `REVISE`, a revised plan (new `plan_id`, period from January 2024) replaced the
    first, 16.4 s;
  - `plan_reply` APPROVE of the first plan: `409 RESEARCH_PLAN_STALE` naming the latest plan, 0.1 s, no turn stored;
  - turn 2, "Oke, setuju. Jalankan rencana yang terbaru.": `EXECUTE_APPROVED` (classifier), the experiment ran on
    the revised period, data coverage `PASS`, `DATA_COVERAGE_VERIFIED`, 14 tool calls, 50.8 s;
  - `plan_reply` APPROVE of the executed plan: `409 RESEARCH_PLAN_NOT_PENDING`, 0.1 s, nothing re-ran;
  - `GET …/messages`: 3 turns, `research_plan` `EXECUTED`.
  - An incomplete `continuation` object in a `SERVER` request was refused by the request schema (`422`) before the
    `CONTINUATION_SOURCE_CONFLICT` check; that check is covered by the tests.

## 2026-09-27 — market-ai-orc: S05 and P03 fixes, catalog protocol off, discovery v2 active

- Approved by the user: fix S05, turn `AI_ENABLE_CATALOG_PROTOCOL` off and keep catalog discovery v2, leave
  `pgweb_reader` as is, and fix P03.
- **Variable** on market-ai-orc: `AI_ENABLE_CATALOG_PROTOCOL=false` (was `true`), set with `--skip-deploys`;
  `AI_ENABLE_CATALOG_DISCOVERY_V2` stays `true`.
- **Code** `7778795` (auto-deploy from `main`): market-ai-orc `3550dfb6-5fb9-4dd2-aba8-892440f7a321` `SUCCESS`,
  `/ready` 200, with the variable above. Tests 625 passed. The tool definitions are identical to the previous deploy;
  the system prompt changes only by the P03 rounding sentence.
  - S05: a run closes the sessions it opened that did not complete; capacity refusals are bounded.
  - P03: display rounding allowed in both number rules.
- **Migration** `20260927_003` through the temporary service `catv2act-migrate-job`
  (`9898bd29-440f-4024-853b-b91f18d564b0`, deployment `1ec73049-bbad-4484-a452-a6355e57c803`, references
  `DATABASE_URL` only, deleted). See `DATABASE_CHANGELOG.md`.
- `railway config pull --force` and `railway config plan`: already up to date (no new variable name).

## 2026-09-27 — market-ai-orc: server-side conversation history switched on in dev (phase H1)

- Approved by the user: phase H1 with a new role, secret and migration; owner from the caller's `X-Saniti-Owner`
  header (default without it); retention 30 days.
- **Code, store off** (`f479714`, pushed with `2ea9324`): market-ai-orc `5d726604-2983-4164-8eec-b484601d58a3`
  `SUCCESS`, `/ready` 200; Governor and sandbox `SKIPPED`. Tests 618 passed; `CLIENT` requests unchanged.
- **Secret** `MARKET_AI_CONVERSATION_DB_PASSWORD` on market-ai-orc: 48 random hex characters generated in-process and
  passed on stdin, never printed; `--skip-deploys`; verified present by name and length.
- **Migration** `20260927_002`, login provisioning and the catalog/schema refresh through the temporary service
  `conv-migrate-job` (deleted). See `DATABASE_CHANGELOG.md`.
- **Variables on market-ai-orc** in one `railway variable set`:
  - `CONVERSATION_DATABASE_URL` (secret): a reference template,
    `postgresql://market_ai_conversation:${{MARKET_AI_CONVERSATION_DB_PASSWORD}}@${{Postgres.RAILWAY_PRIVATE_DOMAIN}}:5432/${{Postgres.PGDATABASE}}`.
    Read back: it resolves for the new login with the same password and has no unresolved reference. Its value was
    never printed.
  - `AI_ENABLE_CONVERSATION_STORE=true`. `AI_CONVERSATION_RETENTION_DAYS`, `AI_CONVERSATION_LEASE_SECONDS` and
    `AI_CONVERSATION_UPKEEP_SECONDS` are not set (30 days, `AI_MAX_ANALYSIS_SECONDS` + 120 s, 3600 s).
  - Redeploy `628cbaff-031f-4f17-b47a-db071e202b7d` (commit `2ea9324`): `SUCCESS`, `/ready` 200, no upkeep error.
- **Live PoC** through the temporary service `conv-poc-job` (`28b6b235-ec8d-4eb7-94d7-92e82beed592`, deployment
  `af9df419-d6a9-4faf-951f-69f11ff9e85d`, reference `MARKET_AI_ORC_API_KEY` only, deleted), about $0.04:
  - turn 0 (new conversation): BBCA close on 2026-08-28, 6,475; `persistence: SAVED`;
  - turn 1, "Bagaimana dengan BBRI pada tanggal yang sama?" with no caller history: BBRI 3,190 on 2026-08-28, so the
    server history carried the date;
  - the same request again: the stored response in 0.1 s (`replayed: true`, identical); other content under the same
    `request_id`: `409 REQUEST_ID_CONFLICT`;
  - another owner: `404 CONVERSATION_NOT_FOUND` for the message and for `GET …/messages`; the owner's `GET …/messages`:
    both turns `COMPLETED`;
  - `SERVER` with a caller history: `400 HISTORY_SOURCE_CONFLICT`;
  - two messages two seconds apart: the first answered (turn 2), the second `409 CONVERSATION_BUSY`;
  - a `CLIENT` request: answered, no `conversation` key.
- `railway config pull --force` added `AI_ENABLE_CONVERSATION_STORE`, `CONVERSATION_DATABASE_URL` and
  `MARKET_AI_CONVERSATION_DB_PASSWORD` to `.railway/railway.ts` as `preserve()`; `railway config plan` reports the
  configuration up to date. The project is back to its 13 services.
- Rollback: set `AI_ENABLE_CONVERSATION_STORE=false` (one redeploy): `SERVER` requests get `HISTORY_MODE_UNAVAILABLE`,
  stored conversations stay until their retention ends.

## 2026-09-27 — market-ai-orc: P02 fix, keyword discovery, catalog flags switched on in dev

- Approved by the user: execute P02; run the local A/B; apply migration `20260927_001`; switch on both catalog flags;
  run the 20-question stress test.
- **P02** (`f8a924c`, provenance gate: a table's row-number column is not checked as a figure): market-ai-orc
  `e227431b-93b0-41e8-9ae9-f4a296f32e97` `SUCCESS`; Governor and sandbox `SKIPPED`. Tests 602 passed.
- **Local A/B** (no Railway change; real model, local Governor and sandbox, synthetic `dataneed_e2e` catalog of 8
  tables, 6 questions per arm). A = the dev flags (`AI_FINAL_CONTRACT_IN_PROMPT` on); B = A plus both catalog flags.

  | | A | B1 | B2 | B3 |
  |---|---|---|---|---|
  | Discovery calls | 24 | 24 | 22 | 25 |
  | First DataNeed refused | 0 | 0 | 0 | 0 |
  | Guard refusals / cache hits | — | 0 / 0 | 0 / 0 | 0 / 0 |
  | Cost | $0.057 | $0.060 | $0.078 | $0.070 |
  | Sum of run times | 164 s | 145 s | 236 s | 327 s |

  - B1 exposed M17: a phrase query matched nothing, so the model rediscovered without filters. B2 ran after the
    keyword fix, B3 after adding formula matches to discovery (`35e5db0`).
  - The protocol did not reduce discovery calls with this model: it still called `get_system_capabilities`, split
    `get_catalog_details` per table or section, and resolved tickers with `get_dimension_values`. The guard never
    fired because every run read the details before submitting.
  - Run-time differences follow the provider (model time 157 s in A against 231–320 s in B2/B3 for a similar number
    of model calls), so time and cost are within noise. Every arm gave 5 answers and 1 Research Plan.
  - The user chose to switch the flags on in dev anyway, as the stronger measurement on the real catalog.
- **Keyword discovery** (`35e5db0`) and the regenerated migration (`5e55228`): market-ai-orc
  `217c3e55-7828-4635-a484-a4bb6cc33919` `SUCCESS`, `/ready` 200; Governor and sandbox `SKIPPED`. Tests 606 passed;
  with the flags off the tool definitions and prompt were byte-identical to before.
- **Migration** `20260927_001` through the temporary service `catv2-migrate-job` (`4241e0be-b969-4a22-b104-3f21749f9fd0`,
  deployment `3d9641ba-0ac7-466a-9756-8453014e51f8`, reference `DATABASE_URL` only, deleted). See
  `DATABASE_CHANGELOG.md`.
- **Variables on market-ai-orc**: `AI_ENABLE_CATALOG_DISCOVERY_V2=true` and `AI_ENABLE_CATALOG_PROTOCOL=true` in one
  `railway variable set`. Redeploy `8b118d1b-4c8b-42aa-a252-a934b753321f` (commit `5e55228`): `SUCCESS`, `/ready` 200,
  no `catalog_protocol_inactive` event. Read back by name: both `true`; `AI_FINAL_CONTRACT_IN_PROMPT` and
  `AI_LOG_PROVIDER` `true`; `AI_PROVIDER_SORT` and `AI_CATALOG_SUMMARY_IN_PROMPT` unset; `AI_MODEL`
  `deepseek/deepseek-v4.1-flash`.
- `railway config pull --force` added both names to `.railway/railway.ts` as `preserve()`; `railway config plan`
  (with the R06 workaround) reports the configuration up to date. The project is back to its 13 services.
- Rollback: delete the two variables (one redeploy). The `Tool_Catalog` v2 rows stay, inactive.
- **20-question stress test** (the technical-indicator and broker-flow questions of 2026-09-26) through the temporary
  service `catalog-q20-job` (`8bef25b2-e7bf-421b-8610-fa586e86ba02`, deployment
  `29543684-2ab3-46aa-a8d6-37ddcb0dae48`, reference `MARKET_AI_ORC_API_KEY` only, deleted afterwards), 07:56–08:17 UTC.
  Compared with the run of 2026-09-26 (`9b5ccd9d`), which had both catalog flags and the final contract off:
  - Outcome of the 21 collected responses: 11 ANSWER, 8 LIMITATION, 2 Research Plans; cost $0.469 in 1,132 s of wall
    time (before: 20/20 answered, $0.369, 2,932 s). The r19 approval turn failed (60 model calls, 33 attempts to open
    a session) and its response line was not collected; its $0.031 is included in the orchestrator's usage logs.
  - The failures are sandbox capacity: two analysis sessions whose executions failed (t11, b14) were never closed and
    held both sandbox slots until their 900 s idle timeout. b15–b18 and r20 then got `SESSION_CAPACITY_EXCEEDED` on
    every attempt, and r19 retried until its budget ran out. This is a session lifecycle defect exposed by the faster
    run, not a catalog effect (`ERRORS_AND_SOLUTIONS.md` S05). t11's values were correct (%K 46.67, %D 63.55) but its
    failed session made the answer a LIMITATION.
  - t01 was forced to LIMITATION by the provenance gate over the warm-up lengths it quoted (P05), with a correct value.
  - Of the answers checked against the 2026-09-26 ground truth: t02, t04, t05, t06, t10 and b13 exact; t07 (73.15 against
    73.14) and t12 (EMA50 3,159.17 against 3,159.10) now match where the earlier run deviated; t03 and the t08 RSI values
    still differ by warm-up (E2); t09 found 15 of 16 banks. b13, forced to LIMITATION before (E1), is now an answer.
  - Discovery on the 13 comparable questions (t01–t12, b13): 55 discovery tool calls before and after, 175 against 179
    model calls, 4.25 M input tokens in both. The guard refused two data needs (t01, t05), each followed by one more
    details call; no cache hit. The protocol saved no discovery calls.
  - The cost difference comes from the provider, not the flags: OpenRouter served this run from Novita, Parasail and
    Together (before: DeepInfra and Together), with a cache ratio of 0.82 against 0.92 and model time 545 s against
    1,404 s for the same questions.
  - The catalog flags stay on in dev until the user decides; switching them off is one redeploy.

## 2026-09-27 — market-ai-orc: catalog discovery v2 and the discovery protocol deployed dark (commits df76c77, d01414d)

- Requested by the user: apply the implementation plan of 2026-09-27. This deploys phases C1–C3 only, behind two new
  flags that default off; the conversation and sandbox-reuse phases (H1, H2, S1, S2) wait for the user's decisions.
- New flags, **not set in dev**:
  - `AI_ENABLE_CATALOG_DISCOVERY_V2`: discovery filters and paging, formula search, table metadata, column
    completeness, join-semantics and resample fields;
  - `AI_ENABLE_CATALOG_PROTOCOL`: the prompt rule, per-run reuse of catalog results and the `CATALOG_DETAILS_REQUIRED`
    guard. Startup refuses it without the v2 flag.
- **Before the push:**
  - market-ai-orc: 588 passed (local PostgreSQL 16);
  - with both flags off, the tool definitions and the system prompt were compared byte for byte with `59e9443`
    (DataNeed, Research Plan confirmation, named-period returns and the final contract on): identical.
- Auto-deploy from `main`:
  - market-ai-orc `1e1f4739-3769-41a6-8612-36b133925da4` (commit `d01414d`): `SUCCESS`, healthcheck `/ready` 200,
    startup without error;
  - Governor `bac076b9` and sandbox `d218855c`: `SKIPPED` (outside their watch paths).
- Variables read back by name: both new flags unset; `AI_FINAL_CONTRACT_IN_PROMPT` and `AI_LOG_PROVIDER` `true`;
  `AI_PROVIDER_SORT` and `AI_CATALOG_SUMMARY_IN_PROMPT` unset; `AI_MODEL` `deepseek/deepseek-v4.1-flash`.
- No variable, service or configuration change, so `.railway/railway.ts` is unchanged.
- Database: migration `20260927_001` (Tool_Catalog v2 rows, inactive) is in the repository and **not applied**; see
  `DATABASE_CHANGELOG.md`.
- Rollback: none needed while the flags are off; otherwise delete the flag variables (one redeploy).

## 2026-09-27 — market-ai-orc: final-response contract in the prompt and provider logging switched on in dev

- Approved by the user: `AI_FINAL_CONTRACT_IN_PROMPT=true` and `AI_LOG_PROVIDER=true`, both set in one `railway variable set` on market-ai-orc.
- Not set, by the user's decisions:
  - `AI_PROVIDER_SORT`: the model stays `deepseek/deepseek-v4.1-flash` on OpenRouter's default routing;
  - `AI_CATALOG_SUMMARY_IN_PROMPT`: no catalog tables in the system prompt.
- Redeploy `018b6d6d-9cff-4649-89d1-cc983972a277` (application code `baa6454`, docs `9025b6f`): `SUCCESS`, `/ready` 200.
- Read back by name after the change:
  - the two flags are `true`;
  - `AI_PROVIDER_SORT` and `AI_CATALOG_SUMMARY_IN_PROMPT` are unset;
  - `AI_MODEL` is `deepseek/deepseek-v4.1-flash`.
- Effects:
  - the system prompt now carries the final JSON contract and the Research Plan field form (about 550 tokens, no digits);
  - after each response, a background thread looks up every model call on OpenRouter `/generation` and logs `ai_model_call_provider`.
- `railway config pull --force` added both names to `.railway/railway.ts` as `preserve()`. `railway config plan` reports the configuration up to date.
  - The first `plan` run failed with the known false CLI-version error (`ERRORS_AND_SOLUTIONS.md` R06).
  - Running it with `_` set to the Railway CLI 5.59.0 binary succeeded. The three legacy source drifts are gone because those services were deleted on 2026-09-26.
- Rollback: delete the two variables (one redeploy).

## 2026-09-26 — Stress-test fixes and run-time/cost controls deployed with the new flags off (commits 86d23ad, baa6454)

- Requested by the user after the stress test:
  - fix the currency-sign misreading in the provenance gate (E1);
  - reduce `run_python` script errors (E4);
  - implement the run-time and cost controls R1–R4, each behind a market-ai-orc flag that defaults off.

  The indicator warm-up issue (E2) was only documented. All errors and their status are in `ERRORS_AND_SOLUTIONS.md`.
- **Tests before the push:** market-ai-orc 560 passed (local PostgreSQL 16), market-python-sandbox 463 passed. After `baa6454`, the efficiency and catalog tests (31) passed again.
- **Automatic deployments** from `main`:
  - `86d23ad`:
    - market-ai-orc `fa0493d8-68c9-4d14-a271-1243d04c14bc`: `SUCCESS`, `/ready` 200;
    - market-python-sandbox `86eb4ddf-bba6-4d31-8c46-1dd04e91224d`: `SUCCESS`, `/ready` 200;
    - market-sql-governor `e8003028`: `SKIPPED` (no change).
  - `baa6454` (the catalog summary also states each table's subject values):
    - market-ai-orc `9491c5e8-c793-4b61-b9bf-a3c104d51ae0`: `SUCCESS`; its `/ready` line was not read back;
    - market-python-sandbox `bfd06a07`: `SKIPPED`, so `86eb4ddf` stays active;
    - the Governor was not changed, and its event for this commit was not read back.
- **No variable was changed.**
  - Setting `AI_LOG_PROVIDER`, `AI_FINAL_CONTRACT_IN_PROMPT`, `AI_CATALOG_SUMMARY_IN_PROMPT` and `AI_PROVIDER_SORT` on market-ai-orc was refused by the agent's permission check before anything was sent. All four flags are unset in `dev`, so every model request is unchanged.
  - The user then decided (2026-09-27) not to use `AI_PROVIDER_SORT`: the model stays `deepseek/deepseek-v4.1-flash` on OpenRouter's default routing (see `AGENTS.md`).
  - `CATALOG_DATABASE_URL`, which the catalog summary needs, is present on market-ai-orc (checked by name).
- **Local A/B rehearsal** (no Railway change): real model, local Governor and sandbox, the synthetic `dataneed_e2e` database, six questions per configuration. A is the `dev` flags. B adds the final contract and the catalog summary. C is B plus `AI_PROVIDER_SORT=throughput`.

  | | A | B | C |
  |---|---|---|---|
  | Time (sum) | 161 s | 124 s | 118 s |
  | Cost | $0.0689 | $0.0537 | $0.0540 |
  | Model calls | 65 | 44 | 54 |
  | Discovery calls | 23 | 11 | 20 |
  | Final re-asks | 7 | 0 | 0 |
  | Cache ratio | 0.923 | 0.924 | 0.958 |

  - Every configuration answered the same questions: 5 answers and 1 Research Plan.
  - The first B/C run found that the summary lacked each table's subject values, so every first DataNeedSpec failed with three `INVALID_FIELD_VALUE`; `baa6454` fixed it.
  - OpenRouter's documentation does not say whether `provider.sort` keeps `session_id` sticky routing. In C every run stayed on one provider.
- The documentation commit `14c9b3e` touched the market-ai-orc README, so it redeployed the same application code: market-ai-orc `843c89c3-dc16-4338-a20b-5c642f87b059` `SUCCESS`, `/ready` 200; the sandbox and the Governor were `SKIPPED`.
- No temporary service was created and no configuration changed, so `railway config pull`/`plan` was not needed.

## 2026-09-26 — Technical-indicator and broker-flow stress test on dev (temporary jobs)

- Requested by the user: 20 questions that need history before the asked period (warm-up for RSI, MACD, Bollinger, SMA200, ATR, Stochastic and EMA; rolling broker and foreign flows; two research questions answered after an approved plan), plus the user's Pine Script `ta.dmi(14, 14)` ADX question. The model computed everything in the sandbox; answers were then checked against a read-only ground truth.
- Temporary one-off services, each deleted afterwards:
  - `stress-tech-job` (`517f5ea5-b62b-4a9d-bb5a-11e583468ec8`, deployment `9b5ccd9d-88de-41eb-af67-7e61d023373d`): the 20 questions; reference variable `MARKET_AI_ORC_API_KEY` only;
  - `stress-truth-job` (`cd655926-5bac-48e0-bec0-ae21909a250f`, deployment `e7ce66ef-0ed0-47aa-8b35-480ffa674e68`): read-only ground truth with TA-Lib 0.8.1, numpy 2.4.6 and pandas 3.0.6 (the sandbox's versions); reference `DATABASE_URL` only;
  - `adx-job` (`7a9d157e-bfab-4753-94fa-cc108e72cb15`, deployment `68a5e133-f184-4c5c-a5e5-b9d15e88a121`): the ADX question and its read-only ground truth (a Pine `ta.dmi` replica and TA-Lib ADX); references `DATABASE_URL` and `MARKET_AI_ORC_API_KEY`.
- **Outcome:** 20/20 completed without a run error; cost $0.369 (ADX question $0.016).
  - Exact against the ground truth: RSI BBCA, MACD TLKM, Bollinger ASII, SMA200 BMRI, the 10 bank golden crosses, the 16 bank 52-week highs, the BBRI volume spikes, Stochastic ADRO, all six broker questions, both research answers, and ADX (177 days below 30 in 2025).
  - Small deviations from a short warm-up chosen by the model (the prompt gives no rule): RSI BBRI January (53.27 vs 53.33), ATR UNVR (72.67 vs 73.14), the RSI values of the IDX-wide oversold list (same 9 stocks and the same 10 lowest), and EMA50 ANTM (3,264.11 vs 3,159.10; the conclusion is unchanged).
  - The foreign-flow answer for BBCA had correct numbers but was forced to LIMITATION by the provenance gate: a negative value written as `−Rp 34756780567` was read as positive.
- **Performance:** extraction (17 s) and Python execution (6 s) were under 1% of 2,932 s wall time. Model calls took the rest: 320 calls, average latency 1.3–23.8 s depending on the moment; about 15% of model time and 19.5% of cost regenerated a final answer (a prose answer re-asked in the structured format, plus gate re-asks).
- No service, variable, deployment of an existing service, schema or data was changed. The project is back to its 13 services.

## 2026-09-26 — Research Plan confirmation and named-period returns rolled out on dev

- Scope approved by the user (Phase 3–6 prompt): deploy with both new flags off, apply migration `20260926_002`, set the signing key, enable the flags one at a time, run live tests and the 20-question regression. The fix for a regression found on the way was approved separately.
- **Code, flags off**, commit `8a78aec` pushed to `main` (auto-deploy):
  - market-python-sandbox `918245ef-01b5-494c-9eb1-b7bc358c0715`: `SUCCESS`, `/ready` 200 (it returns 200 only after the isolation self-test passes);
  - market-ai-orc `dbd12006-0f80-484e-a2c3-284f37397917`: `SUCCESS`, `/ready` 200;
  - market-sql-governor `e3e04ec2-0356-4715-a881-023f14d6a32f`: `SKIPPED` (no change). The active Governor deployment is still `2136ce9e-f54f-4d5a-80e6-611df5348647`.
- **Migration** `20260926_002` through the temporary service `plan-migrate-job` (`251281c4-9dac-46e2-9e3a-f0008b28aa9f`), deployment `7a507c80-0f0f-428e-a40a-5619fe03cb0d`, with only the reference `DATABASE_URL=${{Postgres.DATABASE_URL}}`; deleted afterwards. See `DATABASE_CHANGELOG.md`.
- **Variables on market-ai-orc** (values not recorded):

  | Variable | Action | Deployment | Status |
  |---|---|---|---|
  | `AI_RESEARCH_PLAN_SIGNING_KEY` | set as a secret: 64 random hex characters generated in-process and passed on stdin, never printed; `--skip-deploys` | — | verified present, 64 hex; absent from the startup logs |
  | `AI_REQUIRE_RESEARCH_PLAN_CONFIRMATION` | set `true` | `31f66bab-366e-4c9d-8610-27e38e0122af` | `SUCCESS`, `/ready` 200 |
  | `AI_ENABLE_STANDARD_PERIOD_RETURN` | set `true` | `98963bb9-27b0-4bb9-a64a-51b87f1d4145` | `SUCCESS`, `/ready` 200 |

  `AI_RESEARCH_PLAN_TTL_SECONDS` is not set (default 3600). Rollback: delete the two flags (the key may stay).
- **Live scenarios** through the temporary service `plan-live-job` (`4e6b9d86-1f19-497f-88e8-032346d91f95`, deployment `18ef7374-e3aa-4f99-a822-b1a546aab03a`; reference variables `DATABASE_URL` and `MARKET_AI_ORC_API_KEY`, redacted; plan tokens redacted in its output; deleted afterwards). Plan, tampered token, other conversation, altered plan, cancel, revise, explicit approval, free-text approval, bypass attempt and an analysis question behaved as designed; the Governor and sandbox logged no event for any request without an approved plan. Details: `DATANEED_ARCHITECTURE.md`, addendum. Cost about $0.10.
- **20-question regression** through the temporary service `plan-q20-job` (`2e9b4989-4b28-4341-8159-13b1ef6d6c8e`, deployment `7522a9a6-c734-40ee-ac7a-49af3de521f2`; same reference variables; deleted afterwards). $0.33, 409 numbers checked, 0 unsupported. Q4, Q5 and Q8 matched the ground truth on the standard basis. Q20 regressed to LIMITATION (`TOOL_RESULT_TOO_LARGE`).
- **Fix** `37ef2d4` (orc only; approved by the user): market-ai-orc `f6e2069f-db0b-4149-b802-67ea54a99c83` `SUCCESS`, `/ready` 200; sandbox `d045e51e-ba9a-4f26-81c5-a61883557cd1` and Governor `a7ce5f88-e487-46e4-b1e9-85ce3ad35d77` `SKIPPED`. Rerun of Q20 and Q5 through the temporary service `plan-q20-rerun-job` (`24919bdc-a176-4196-8d2d-84f3770af6bd`, deployment `d3ca8a40-555f-4f3f-8b2c-af9aca575d6b`, deleted): Q20 `ANSWER`, Q5 16/16 exact, $0.03.
- **Read-only check** of the boundary finding through the temporary service `buffer-check-job` (`d7a06428-1ebf-4937-a65e-532d64c5cbce`, deployment `06d2a32d-3a73-4bd4-abdd-9032fcac60c8`, reference `DATABASE_URL` only, one read-only query; deleted).
- **Observed, not done by this work:** `market-ai-backend` (`2cefa0cd-…`), `market-query-sandbox` (`c6bf3085-…`) and `market-analytics-worker` (`75fc5bbc-…`) were deleted between 06:29 and 06:30 UTC by the user (confirmed by the user), and the `market-analytics-input` bucket is no longer in the project.
- **Configuration sync.** `railway config pull --force` updated `.railway/railway.ts`: it added `AI_ENABLE_STANDARD_PERIOD_RETURN`, `AI_REQUIRE_RESEARCH_PLAN_CONFIRMATION` and `AI_RESEARCH_PLAN_SIGNING_KEY` to market-ai-orc as `preserve()`, and removed the three deleted services and the bucket. `railway config plan` reports the configuration up to date; the three accepted source drifts of the deactivated services are gone with them.
- The project is back to its 13 services; every temporary service was deleted.

## 2026-09-26 — 20-question live test of the DataNeed flow on dev (temporary job)

- Requested by the user. It also counts toward the dev soak test (see `DATANEED_ARCHITECTURE.md`, Exit plan).
- **Temporary one-off service** `dataneed-q20-job` (`79e79613-96e8-4237-b7b4-bd085bfe0032`):
  - reference variables only (`DATABASE_URL=${{Postgres.DATABASE_URL}}` for read-only ground-truth sessions, `MARKET_AI_ORC_API_KEY`, `PY_SANDBOX_API_KEY`), all redacted;
  - deployment `8ecc0087-6a02-4949-b3a9-8a73f6d71f0e`;
  - deleted with `railway service delete`.
- 20 questions through `/v1/agent/run`, sequentially, with the flags unchanged (`AI_ENABLE_DATANEED=true`, `AI_ENABLE_LOOKUP_FACT=false`). The questions covered facts, sums, counts, multi-ticker and sector analyses, volatility, correlation, moving averages, broker flows, two research questions, and causal, predictive, ambiguous and out-of-catalog questions.
- **Outcome:** 20/20 completed without error, 15 ANSWER (`DATA_COVERAGE_VERIFIED`) and 5 LIMITATION.
  - The 13 answers with a deterministic ground truth match it exactly, and the research answer on volume spikes agrees within its window boundaries.
  - The broker questions for September correctly answered LIMITATION: broker data ends 2026-08-31.
  - Prediction and fundamentals were correctly refused.
  - The causal question refused the causal claim. The provenance gate then forced a LIMITATION over one self-computed figure.
  - The ambiguous "best stock" question was answered with a self-chosen definition instead of a clarification.
- **Usage:** 586 numbers checked, 1 unsupported; total cost $0.28; median 46 s (14–438 s); median 11.5 tool calls; input cache ratio 91.6%.
- Findings, not yet acted on: clarification for subjective criteria, one default period-return convention, allow display rounding, localize the gate notices.

## 2026-09-26 — Apply Tool_Catalog migration 20260926_001 on dev through a temporary job

- **Temporary one-off service** `dataneed-tools-job` (`65be8872-aa0b-4466-86f2-592a212545bd`):
  - its only variable was the reference `DATABASE_URL=${{Postgres.DATABASE_URL}}`, redacted from its output;
  - it was deployed by `railway up --path-as-root` and deleted with `railway service delete`.
- Deployment `f32c1d3a-3d77-4329-b3bd-d6c0070612e9` was read-only. Deployment `c4c3d6c2-7690-4652-b353-bf7acb86a89c` applied the migration and read it back (see `DATABASE_CHANGELOG.md`).
- No other service, variable or deployment was changed. The project's service list is back to what it was before the job.

## 2026-09-26 — DataNeed switched on in dev; lookup_fact disabled after the parity test

- Scope approved by the user (DataNeed rollout, phase 5): switch the flags on in `dev`, run the PoCs, and disable `lookup_fact` after a parity test.
- **Fix deployed first**, commit `4aa3272` (code only): an INNER relationship now restricts both requests. A real-model rehearsal against the local Governor and sandbox had found that a spec written reference-left delivered prices for every ticker. Automatic deployments, each `SUCCESS`:
  - market-python-sandbox `181527f0-20a8-4c09-af7e-70e91f3bbaa6`;
  - market-sql-governor `2136ce9e-f54f-4d5a-80e6-611df5348647` (README only);
  - market-ai-orc: `SKIPPED` (no change).
- **Variables** (set with `railway variable set`, each triggering a redeploy):

  | Service | Variable | Value | Deployment | Status |
  |---|---|---|---|---|
  | market-python-sandbox | `PY_SANDBOX_DATANEED_ENABLED` | `true` | `e9faab10-bf91-40bb-a620-40d5b48b4e43` | `SUCCESS` |
  | market-ai-orc | `AI_ENABLE_DATANEED` | `true` | `84f5470c-45be-456d-96b3-605e1113244e` | `SUCCESS` |
  | market-ai-orc | `AI_ENABLE_LOOKUP_FACT` | `false` | `d21aefdf-c134-4f21-9b75-a44cc7eacf2c` | `SUCCESS` |

  - The sandbox was switched on first, so the orchestrator's startup readiness check saw it ready.
  - The sandbox started with `isolation_enforced=true`, and `sessions_started` closed 0 orphan sessions.
  - The orc logged no `python_sandbox_not_ready`, and `/ready` returned 200.
  - Startup logs held no secret-like values.
  - `railway config pull --force` added the three names to `.railway/railway.ts` as `preserve()`. `railway config plan` shows only the three accepted source drifts of the deactivated legacy services, which were not applied.
- **Temporary one-off service** `dataneed-poc-job` (`15021c62-c3d8-41ab-ba28-e2e91eb74eb8`):
  - reference variables only (`DATABASE_URL=${{Postgres.DATABASE_URL}}` for read-only ground-truth sessions, `MARKET_AI_ORC_API_KEY`, `PY_SANDBOX_API_KEY`), all redacted from its output;
  - deployed by `railway up --path-as-root` and deleted with `railway service delete`.
- **PoC on dev** (deployment `1260d059-ebd4-4ea5-8250-3f8109bb72bf`): real model, real data, reference date 2026-09-25, with `lookup_fact` still on. The ground truth comes from read-only SQL and pandas.

  | Question | Result | Label | Tool calls | Seconds | Cost (USD) | Ground truth |
  |---|---|---|---|---|---|---|
  | YTD of bank stocks vs. the same period last year | ANSWER; coverage PASS; warnings FREQUENCY_GAPS, HISTORICAL_REFERENCE_USES_CURRENT_STATE, HISTORY_BUFFER_SHORTFALL | DATA_COVERAGE_VERIFIED | 18 | 237 | 0.0168 | 48 `Banks` tickers, both requests restricted. Every figure equals the ground truth with the model's stated base, the previous year's last close (deployment `c1f86a6a`) |
  | Research: BBCA's 10-day return after RSI-14 falls below 30 | ANSWER as a historical pattern; unmet minimum sample, no holdout and no correction disclosed | DATA_COVERAGE_VERIFIED | 16 | 240 | 0.0166 | 10 event days in the same 5 episodes |
  | Stocks per sector | ANSWER | DATA_COVERAGE_VERIFIED | 10 | 22 | 0.0110 | exact (844 tickers, 12 values) |
  | BBRI's average weekly volume in August 2026 | ANSWER | DATA_COVERAGE_VERIFIED | 11 | 37 | 0.0124 | exact (5 ISO weeks, mean 693,500,400) |
  | Top 10 one-month returns across the IDX | ANSWER; FREQUENCY_GAPS disclosed | DATA_COVERAGE_VERIFIED | 12 | 140 | 0.0089 | the all-ticker ranking is exact; the headline ranking also excludes tickers without a full month, as stated |
  | BBCA close on 2026-09-25 | ANSWER via `lookup_fact` | FACT | 4 | 22 | 0.0022 | exact (6,250) |

  Every answer passed the number-provenance gate with 0 unsupported numbers.
- **`lookup_fact` parity** (deployments `c1f86a6a-788c-49c7-ba47-314d36b98cd1` with the tool on and `8e5bfa0f-a59f-4082-817c-037b88d019f6` with it off). All six answers equal the ground truth:

  | Question | `lookup_fact` on | DataNeed only |
  |---|---|---|
  | BBCA close on 2026-09-25 | 6,250, FACT, 3 calls, 14 s, $0.0009 | 6,250, DATA_COVERAGE_VERIFIED, 9 calls, 35 s, $0.0060 |
  | BBRI average daily volume, 22–25 Sep 2026 | 173,824,325, DATABASE_AGGREGATE, $0.0026 | 173,824,325, DATA_COVERAGE_VERIFIED, $0.0029 |
  | TLKM's highest high in September 2026 | 2,720 on 15 Sep, DATABASE_AGGREGATE, $0.0084 | 2,720 on 15 Sep, DATA_COVERAGE_VERIFIED, $0.0082 |

  `AI_ENABLE_LOOKUP_FACT=false` stays set in `dev`. `/v1/lookup` stays in the Governor, so setting the variable back to `true` (or deleting it) is the rollback.
- Rollback of the whole switch: delete `AI_ENABLE_DATANEED` on market-ai-orc, which restores the Analysis Spec path, then `PY_SANDBOX_DATANEED_ENABLED` on market-python-sandbox. Sessions and bundles in `/data` are kept; no database change is involved.
- OpenRouter usage for the PoC, parity and local rehearsals: about $0.2 of the $10 key limit.

## 2026-09-26 — Apply migration 20260925_003 on dev through a temporary job

- Scope approved by the user: apply the DataNeed catalog migration on `dev` through a temporary one-off service, as in earlier releases.
- **Temporary one-off service** `dataneed-migrate-job` (`e567e0e8-c9ed-4dbf-a72c-de95420de2ae`):
  - it held reference variables only (`DATABASE_URL=${{Postgres.DATABASE_URL}}`, `MARKET_AI_ORC_API_KEY`, `PY_SANDBOX_API_KEY`, `SQL_GOVERNOR_API_KEY`), all redacted from its output;
  - it was deployed by `railway up --path-as-root` from a local directory and deleted with `railway service delete`.
- Deployment `9144cfee-1d9b-402e-b8fc-7d00fcccb899` (read-only):
  - inspected the catalog state before the migration;
  - `/ready` returned 200 on market-sql-governor, market-python-sandbox and market-ai-orc;
  - the sandbox reported `isolation_enforced=true` for the phases 3–5 deployment `e03c61f8`;
  - `POST /v1/data-needs` answered 404 because the flag is off.
- Deployment `f6ef3174-a00a-4823-ae30-0588cb18279b` applied the migration, read it back, checked the Governor's catalog contract, and ran the catalog/schema refresh (see `DATABASE_CHANGELOG.md`).
- No variable, deployment, volume, domain or restart policy of another service was changed. The job's logs held no secret-like values.

## 2026-09-26 — DataNeed architecture phases 3–5 deployed dark (commit daa05cc)

- Same approved rollout: merged to `main` (fast-forward) with every DataNeed flag off; `main` auto-deployed the changed services to `dev`.
- Code:
  - sandbox: persistent analysis sessions (`/v1/sessions`, execute, inspect, outputs, complete, close), the ExecutionManifest, processing coverage and the final status. The routes answer 404 without `PY_SANDBOX_DATANEED_ENABLED`. The image adds the session users `session1`…`session4` (uid 20201–20204);
  - orc: the session tools and the DataNeed mode of the orchestrator (exclusive tools, DATA NEED RULES, the DataNeed answer gate, `execution.analysis_final_status`), all behind `AI_ENABLE_DATANEED`.
- Tests before the merge: market-ai-orc 453 passed; market-python-sandbox 435 passed.
- No variable was added or changed. `AI_ENABLE_DATANEED` and `PY_SANDBOX_DATANEED_ENABLED` stay unset (read back by name on 2026-09-25). `PY_SANDBOX_SESSION_*` and the orc's `PY_SANDBOX_SESSION_TIMEOUT_SECONDS` use their code defaults.
- Automatic deployments of `daa05cc`:
  - market-python-sandbox `e03c61f8-37ec-4d8a-803f-e26605950867`: `SUCCESS`; the Railway health check on `/ready` returned 200;
  - market-ai-orc `48b22523-0828-4981-97b4-d55756deda07`: `SUCCESS`; `/ready` 200;
  - market-sql-governor `72078656-8cd9-4af6-a097-2563132b03fb`: `SKIPPED` (no change under its watch path).
- The startup logs held no secret-like values. The sandbox's `isolation_enforced=true` was read back afterwards by the migration job's read-only run (entry above).
- Migration `20260925_003` was applied afterwards (entry above).
- Rollback: redeploy the phase 2 deployments (sandbox `c2ab2125`, orc `df85aac2`), or revert `daa05cc` on `main`. The flags are off, so the live Analysis Spec path did not change.

## 2026-09-25 — DataNeed architecture phase 2 deployed dark (commit 07fd68b)

- Same approved rollout as phase 1: merged to `main` with every DataNeed flag off; `main` auto-deployed the three services to `dev`.
- Code:
  - the Governor's `POST /v1/extract`, callable with the orc key only. Only the orc Execution Planner calls it, and the planner is registered only with `AI_ENABLE_DATANEED`;
  - the Governor's validator manifest now also carries `row_count` and `truncated`;
  - the orc Execution Planner and `prepare_data_bundle`;
  - the sandbox's governed bundles, Data Quality Profiler and delivery coverage (`POST`/`GET /v1/bundles`, 404 without `PY_SANDBOX_DATANEED_ENABLED`).
- No variable was added or changed; `AI_ENABLE_DATANEED` and `PY_SANDBOX_DATANEED_ENABLED` stay unset. The new limits use their code defaults: `SQL_EXTRACT_*` and `PY_SANDBOX_BUNDLE_*`. With the flag off the sandbox creates no bundle directory.
- Migration `20260925_003` is still not applied.
- Automatic deployments of `07fd68b`, each `SUCCESS` with `/ready` 200:
  - market-sql-governor `a1db4a3e-02fa-4e82-9cd7-ed5af7aa3bf5`;
  - market-python-sandbox `c2ab2125-6ba9-4d31-b74e-438d8060f054`, with `isolation_enforced=true` and 0 interrupted analyses;
  - market-ai-orc `df85aac2-31d9-464b-bdf6-9d00484febd1`.
- The startup logs held no secret-like values.
- Rollback: redeploy the phase 1 deployments (Governor `a01d1535`, sandbox `fa9a1576`, orc `a2bdd594`), or revert `07fd68b` on `main`.

## 2026-09-25 — DataNeed architecture phase 1 deployed dark (commit d7d18ea)

- Scope approved by the user: build the DataNeed architecture in phases, merge each phase to `main` with its flags off (GitHub `main` auto-deploys the three services to `dev`), and verify health.
- Code: the sandbox's DataNeedSpec validator and Research Governor with `POST /v1/data-needs` and `GET /v1/data-needs/{need_id}`; the orc tool `submit_data_need_spec`; the Governor's catalog contract reading the join-semantics columns of migration `20260925_003` when they exist.
- Flags, both unset on `dev` and read back by name: `PY_SANDBOX_DATANEED_ENABLED` (sandbox, default off: the routes answer 404 and no DataNeed state is created) and `AI_ENABLE_DATANEED` (orc, default off: the tool is not registered). No variable was added or changed.
- Migration `20260925_003_add_relationship_join_semantics.sql` is in the repository but **not applied**. Until it is, the catalog contract is unchanged.
- Automatic deployments of `d7d18ea`, each `SUCCESS`, `/ready` 200:
  - market-sql-governor `a01d1535-83f4-42a0-aa69-3862b750cfe0`;
  - market-python-sandbox `fa9a1576-8091-457b-a735-aef212be27a7`, with `isolation_enforced=true` and 0 interrupted analyses;
  - market-ai-orc `a2bdd594-54b9-47f1-90ff-283c7ed8bb54`.
- The deactivated backend and workers created no deployment. The startup logs held no bearer token, OpenRouter key or DSN with a password.
- Rollback: redeploy the previous deployments (Governor `747732ed`, sandbox `035fd115`, orc `a9128831`), or revert `d7d18ea` on `main`. The flags are off, so the live Analysis Spec path did not change.

## 2026-09-25 — Retire market-ai-backend and its workers; connect market-sql-governor, market-python-sandbox and market-ai-orc to GitHub main

- Scope approved by the user:
  - migrate every market-ai-orc dependency on `market-ai-backend`;
  - deactivate `market-ai-backend`, `market-query-sandbox` and `market-analytics-worker` by removing their active deployments and disconnecting their GitHub source, keeping the services, variables and history;
  - purge the retained provider reasoning in `Analysis_Model_Call` now, instead of waiting for the backend's 30-day hourly cleanup (see `DATABASE_CHANGELOG.md`);
  - leave `Tool_Catalog` unchanged;
  - connect the three market-ai-orc services to GitHub `main`.
- **Read-only inspection** (unrendered variables of every service, code, `Tool_Catalog` readers, logs):
  - The only market-ai-orc dependency on the backend was `OPENROUTER_API_KEY = ${{market-ai-backend.OPENROUTER_DEEPSEEK}}`.
  - No other service references a variable of the three legacy services. The two workers depend only on the backend, through a literal `MARKET_AI_BACKEND_URL`.
  - `Tool_Catalog` is read only by market-ai-backend.
  - The backend had been idle since 2026-09-14. Its log held only the two workers' `claim` polls (HTTP 204).
  - Bucket `market-analytics-input` holds 1 object (269 bytes, 2026-09-14) that no `AVAILABLE` snapshot row references. It was left in place.
- **market-ai-orc `OPENROUTER_API_KEY`** is now the service's own literal secret.
  - It was set through the API with `skipDeploys`, read in-process from the backend value and never printed.
  - Read-back: no market-ai-orc variable references `market-ai-backend`, and the resolved value's hash equals the backend's `OPENROUTER_DEEPSEEK`.
  - `GET https://openrouter.ai/api/v1/key` accepted the key; this makes no model call. The key's remaining credit limit was about $2.27.
- **GitHub sources:** `rednightt33/saniti` branch `main`, one service at a time, each after its root directory and watch path were set.
  - Every other setting was compared before and after and was unchanged: Dockerfile, start command, health check, restart policy, replicas, region, schedule and sleep.
  - Each connection deployed `f553258`, whose application code equals the deployed `a5e11a4`.

  | Service | Root / watch path | Rollback reference | New deployment | Verified |
  |---|---|---|---|---|
  | market-sql-governor | `/apps/market-sql-governor` / `/apps/market-sql-governor/**` | `293ba2e2` | `4732bb12-a96c-439d-8b71-635e115a23be` `SUCCESS` | Health check `/ready` 200; dataset janitor ran |
  | market-python-sandbox | `/apps/market-python-sandbox` / `/apps/market-python-sandbox/**` | `beec8e84` | `c24452ca-85b3-4473-874f-8ebc1bc700ab` `SUCCESS` | Volume mounted; `isolation_enforced=true`; 0 interrupted analyses; `/ready` 200 |
  | market-ai-orc | `/apps/market-ai-orc` / `/apps/market-ai-orc/**` | `3669447c` | `643133af-c2a2-4992-9035-9565f3d08950` `SUCCESS` | Clean start; `/ready` 200; first deployment with its own `OPENROUTER_API_KEY` |

- **Temporary one-off service** `legacy-retire-job` (`ad612a88-be0f-4a73-acfe-8acbcdc8a5a9`):
  - It held only `DATABASE_URL = ${{market-ai-backend.DATABASE_URL}}`, the backend's own least-privilege login. The purge therefore ran with exactly the privileges of the backend's cleanup.
  - Deployment `582b8b26-e849-45c0-993f-847f76335391` read the legacy queues, purged the reasoning, and read back.
  - The service was then deleted with `railway service delete`. Its output held counts and timestamps only; no DSN or credential appeared.
  - The queues were empty before the deactivation:
    - `Analysis_Request`: 52 `SUCCESS`, 65 `FAILED`, 5 `CANCELLED`; the latest from 2026-09-14.
    - `Analytics_Job`: 14 `SUCCESS`, 5 `FAILED`.
    - `Analytics_Dataset_Snapshot`: 19 `DELETED`.
    - No row was `PENDING`, `PROCESSING` or `AVAILABLE`.
- **Deactivated**, in dependency order. Each source was disconnected first, then the active deployment removed:

  | Service | Removed deployment | After |
  |---|---|---|
  | market-analytics-worker | `43c3a864-4851-4a01-a615-e532e9d42845` | `REMOVED`, no source |
  | market-query-sandbox | `4ab6ebb2-e41c-4563-a573-241eb7b17f46` | `REMOVED`, no source |
  | market-ai-backend | `8b423a58-19c7-4527-9fa5-12c7776ca815` | `REMOVED`, no source |

  - None of the three has a running deployment left. Their remaining non-`REMOVED` deployments are `SKIPPED` watch-path events and `FAILED` builds from 2026-09-14.
  - Root directory, watch path, all variables (99 on the backend, including `OPENROUTER_DEEPSEEK` and `OPENAI_API_KEY`) and deployment history are kept.
  - Rollback: reconnect `main` and deploy the backend first, then the two workers. Their database objects, logins and `Tool_Catalog` rows were not changed.
- Postgres, pgweb, db-ops-runner, the price crons, the Telegram services, `feature-01-worker` and `ai-data-coverage` were not touched. The environment has 15 services.
- **Configuration sync.** `railway config pull --force` updated `.railway/railway.ts`:
  - The three market-ai-orc services now carry `source: github(...)` with their root directories and watch paths.
  - The three deactivated services have no `source`.
- **Known drift.** `railway config plan` reports 3 changes, not "up to date", with exit code 0, so the daily state-tracking workflow still passes. For each deactivated service it proposes `source.rootDirectory` → null and `source.type` "github" → null.
  - The IaC format keeps the root directory inside the source block, so it cannot represent a disconnected service that keeps its root directory.
  - Setting the backend's root directory to an empty value did not clear `source.type`, so the value was restored at once. No deployment was triggered.
  - Cause, from the environment config: each deactivated service keeps a `source` block holding only `rootDirectory`, with no repository, and the IaC engine reads that as a GitHub source. The services are truly disconnected: push `e8c3d47` changed `apps/market-ai-backend/README.md` and created no deployment.
  - The user first approved `railway config apply`. The pinned plan (0 add, 3 change, 0 destroy, not destructive) marks each of the three changes `deployEffect: deploy`, so applying it would also start a deployment of each deactivated service. With no source, that deployment would most likely rebuild the service's last deployment, a failed 2026-09-14 build, but it could also restart its old image.
  - The plan was not applied. The user chose to keep the drift. Do not apply it without handling those deployments.
- **Autodeploy verified.** The documentation push `e8c3d47` changed the three services' READMEs and triggered their first GitHub deployments. Each reached `SUCCESS` with `/ready` 200:
  - Governor `747732ed-2c6f-40f1-a116-23fc1cbc0d3d`;
  - sandbox `035fd115-b064-4bab-bd27-278be3380413`, with `isolation_enforced=true` and 0 interrupted analyses;
  - orc `a9128831-e7c0-4e9b-87d1-d220f5bd8b44`.
  - The deactivated services created no deployment for that commit.
  - The startup logs held no bearer token, OpenRouter key or DSN with a password.

## 2026-09-25 — Deploy the two-path release: migrations 20260925_001/002, market-sql-governor, market-python-sandbox, market-ai-orc (commit a5e11a4)

- Scope approved by the user: apply both migrations, deploy the three services, refresh the catalog and schema documentation, delete the temporary service, and sync the configuration. The user skipped the 10-question stress test, so no model run was made on `dev` after the deploy. The same code was tested with the real model on a read-only copy of the live data earlier the same day (entry below). It was also tested in local real-model reproductions.
- **Pre-deploy checks:**
  - No new Railway variable is needed. The code defaults `AI_MAX_OUTPUT_TOKENS=8000`, `AI_ENABLE_LOOKUP_FACT=true`, `AI_ENABLE_REQUEST_DATA=false` and `AI_MAX_REPAIR_ATTEMPTS=3` now apply to market-ai-orc: the model-facing `request_data` is off, and analysis data comes from `prepare_analysis_data`.
  - The sandbox SQLite schema did not change.
  - The migrations were rehearsed again on a scratch database with the job's own code.
- **Rollback references**, recorded before deploying: Governor `8682d991-986d-4c4d-8916-d3f9335dabb6`, sandbox `3cd9de07-73d0-4a73-8dc8-7f6fcba298a2`, orc `3e06e8d6-dfa5-4826-b7c2-28e4e7ac171b`.
  - The three roll back together: the orc's V2 spec tools need the sandbox's V2 parser and the Governor's catalog contract and scope lineage.
  - The migrations are additive: older versions ignore the new columns and inactive rows.
- **Temporary one-off service** `two-path-deploy-job` (`437fba8c-a6a8-4347-b1d5-79c53d75f671`):
  - It held reference variables only (`DATABASE_URL`, `MARKET_AI_ORC_API_KEY`, `PY_SANDBOX_API_KEY`, `SQL_GOVERNOR_API_KEY`), redacted from its output, and was deleted with `railway service delete`.
  - Deployment `b3a4370d-4217-48b4-8cb4-7b5c6137e814` applied the migrations (see `DATABASE_CHANGELOG.md`).
  - Deployment `746ed7b0-9fcf-47f5-9e52-16863544bce6` ran the smoke checks and the catalog/schema refresh.
- **Deployed** by local upload (`railway up <app> --path-as-root`, clean `git archive` of `a5e11a4`), one at a time. Each deployment reached `SUCCESS`:
  - Governor `293ba2e2-11e3-47f5-b272-16c43bea25e6`: clean start, Railway health check on `/ready` passed, and the dataset janitor ran.
  - Sandbox `beec8e84-d84a-4f33-89cd-f6497f1d6c7c`: `isolation_enforced=true`, 0 interrupted analyses, `/ready` 200.
  - Orc `3669447c-a5e4-4913-aead-f66131a97961`: clean start, `/ready` 200.
  - No variable, secret, volume, domain, schedule or restart policy was changed.
- **Smoke checks** over the private network (read-only, no model call):
  - `/ready` returned 200 on all three services, and the sandbox runtime reports `isolation_enforced=true`.
  - The Governor's new `POST /v1/catalog/dimension-values` (`IDX_Stock_Universe.Sector`) returned `VALUES_READY` with the 12 stored values, including the string `0`.
  - The sandbox read the catalog contract from the Governor and refused a deliberately wrong V2 spec with `INVALID_SPEC` / `UNKNOWN_COLUMN`. Refused specs are not stored.
- The job's output (both deployments) and the three new deployments' startup logs were scanned. There was no bearer token, OpenRouter key, DSN with a password, AWS key id, or presigned-URL signature. An in-process comparison against the three services' secret and URL variable values also found none.
- **Wrap-up:** the environment is back to 15 services. `railway config pull --force` left `.railway/railway.ts` unchanged, and `railway config plan` reports the configuration up to date.

## 2026-09-25 — Two-path live test: temporary job with the feature-branch stack (no deploy, no live write)

- Approved by the user as the live test of the two-path architecture (feature branch `claude/upbeat-dijkstra-iybq2f`, commit `1ae56c1`). A local run was not possible: this environment's egress allows HTTPS only, so PostgreSQL could not be reached through the existing TCP proxy.
- The temporary service `two-path-live-job` (`b6b512f7-5c97-49c5-9b27-9ab7182b528a`) ran once and was deleted afterwards.
  - Deployment `8b177cf0-00e8-4ab9-b3c8-149396e87716` did the run.
  - The first deployment `5e1090df-8ce4-4eb6-ac90-2e937fb2ae33` crashed before reading anything: the image's `/tmp` was not writable for the in-container PostgreSQL socket.
  - It held only references: `GOVERNOR_DATABASE_URL` (market-sql-governor), `CATALOG_DATABASE_URL` and `OPENROUTER_API_KEY` (market-ai-orc). It printed no secrets; a scan of the captured logs found none.
- **What it did:**
  - It read live PostgreSQL only in `default_transaction_read_only` sessions, with the Governor's least-privilege role and the orc catalog role. It copied into a PostgreSQL 16 cluster inside the container:
    - the five AI catalogs, `AI_research_catalog` and `AI_formula_reference`;
    - `IDX_Stock_Universe` (844 rows) and `IDX_Broker_Profile`;
    - `Price_Stock_Indonesia_IDX` from 2025-01-01 (329,394 rows) and `Feature_01_Stock_Daily` from 2025-06-01 (257,280 rows).
  - It applied migration `20260925_001` (subject metadata) to that copy only.
  - It ran market-sql-governor, market-python-sandbox (isolation enforced, all checks PASS) and market-ai-orc from the branch, with the dev model `deepseek/deepseek-v4.1-flash` (reasoning `high`) and the dev limits.
- **Results** (ground truth computed with SQL on the same copy):
  - All five sector questions of the 2026-09-24 stress test were answered `CALCULATION_VERIFIED`, and every number equals the ground truth:
    - counts per sector;
    - top 3 sectors by August return, after one return-basis clarification: Transportation & Logistic +14.02%, Basic Materials +12.72%, Infrastructures +8.99%;
    - top 5 banks over one month: BSIM +38.0%, BNBA +17.9%, BTPN +6.0%, NOBU +5.0%, BEKS +4.5%;
    - Energy vs Technology mean daily-return volatility: 0.03275 vs 0.03547;
    - banks vs property daily-return correlation since 1 January 2026: 0.7988 over 170 dates.
  - Before (2026-09-24, deployed code): 5 of 5 ended in `LIMITATION`, 251 s, $0.0721, 67% of prompt tokens cached.
  - After: 5 of 5 answered plus 1 clarification, 619 s, $0.0801, 87% cached.
- The environment is back to 15 services. `railway config plan` reports the configuration up to date. No service, variable, deployment of an existing service, database row, or schema was changed.
- **Follow-up: repair friction (local only; Railway was only read).**
  - In every live run the first `create_analysis_spec` call was rejected, and several spec rejections had no machine code.
  - A local reproduction with the dev model found the causes:
    - `const` was dropped from the provider schema;
    - OpenRouter closes a tool call cut off at `AI_MAX_OUTPUT_TOKENS` (3000, reasoning included) and still reports it completed;
    - the provider does not enforce the strict schema;
    - two parameters had defaults without a `default_id`;
    - `MEAN` and `AVG` were both in use;
    - the shared spec rules had no machine codes.
  - `OPENROUTER_API_KEY` was read in-process from the Railway variables and never printed.
  - Commits `6b6a52f` and `ab38c50` fix these:
    - a truncation guard (`MODEL_OUTPUT_TRUNCATED`);
    - an `AI_MAX_OUTPUT_TOKENS` code default of 8000. `dev` does not set the variable, so the new default takes effect at the next market-ai-orc deploy;
    - coded, actionable spec rejections.
  - The same six runs (five questions plus the Q3 follow-up) on a synthetic fixture:
    - `create_analysis_spec` repair calls: 14, then 8 after the first fix, then 6 after the second;
    - model iterations: 64, then 58, then 55;
    - cost: $0.094, then $0.084, then $0.090;
    - uncoded rejections: 8, then 0.
  - Every answer was `CALCULATION_VERIFIED`. The remaining rejections are ordinary model mistakes, each repaired in one turn.
- At that point the two-path code was merged to `main` without a deploy (deployed later the same day; see the release entry above). market-sql-governor, market-python-sandbox and market-ai-orc still ran the deployments recorded on 2026-09-24 (`8682d991`, `3cd9de07` and `3e06e8d6`, all `SUCCESS`, read back from Railway), and migrations `20260925_001` and `20260925_002` were not yet applied.

## 2026-09-24 — Stress test: 10 price and sector questions (no deploy, no change)

- Requested by the user before a full code review. The temporary job `stress-test-job` (`162aa153-fc78-4739-aecd-d4478f461e39`, deployment `e85a9fd1-6985-4a1d-bbc8-ba014487b241`) was deleted afterwards. It held references to `MARKET_AI_ORC_API_KEY` and `DATABASE_URL`, used the latter only in a read-only session, and printed no secrets.
- It sent 10 questions to `market-ai-orc` (`3e06e8d6`) in sequence, and read ground truth for the checkable ones from PostgreSQL. Totals: 481 s, $0.12476, 629,120 of 875,714 prompt tokens cached (0.718).
- **Results:**
  - Correct numbers, equal to the database: BBRI and TLKM closes on 2026-09-23 (`FACT`), BBCA +15.625% from the 1 July to the 31 August close (`CALCULATION_VERIFIED`), and TLKM's September average close 2,589.375 (`DATABASE_AGGREGATE`).
  - Appropriate behaviour: a clarification for "which sector is most attractive now", and a limitation for "technology versus IHSG", since IHSG is not in the data.
  - Not answered, all five sector questions: tickers per sector, top sectors by August return, top 5 banks by one-month change, energy versus technology volatility, and banks versus property correlation.
- **Why the sector questions failed, from the orc, sandbox and Governor logs:**
  - Four ended with `LIMITATION` without calling `create_analysis_spec`. One called it once; the orc argument validation refused the call, and the model did not retry.
  - The Analysis Spec cannot express a sector-filtered universe (only `ALL_IN_SOURCE` or a ticker list) or a per-sector output grain.
  - The model has no path to enumerate a sector's tickers: datasets never reach it, previews are 20 rows, and `lookup_fact` takes at most 5 entities.
  - The answers say the work "was not run yet" rather than that the path is unsupported.
- **Data note:** `IDX_Stock_Universe` has 3 tickers whose `Sector` is the string `0`.
- No service, variable, or data was changed. `railway config plan` reports the configuration up to date; the environment is back to 15 services.

## 2026-09-24 — Deploy the PoC fixes: sandbox intent dates and universe, warm-up remedy, cache-friendly final re-ask (commit 9085ee7)

- Scope approved by the user: fix the defects found by the Research AI PoC, and act on the structured-final cache miss (F.2). Local suites: sandbox 225 (19 new), orc 383.
- **Sandbox** (`1614b9c`):
  - Day-level date ranges are read as one period: "1 Juli sampai 31 Agustus 2026", "July 1 to August 31, 2026", "1-15 Juli 2026", "sejak 3 Maret 2026", and single days.
  - Outcome horizons ("dalam 5 hari … berikutnya") and a move "dalam sehari" are no longer taken for the analysis period.
  - "tiap/setiap/every/each saham" means each named ticker when tickers are named.
  - An `INSUFFICIENT_WARMUP_HISTORY` refusal now names the entities and a `suggested_from` estimated from their own trading density, and offers `EXCLUDE_TICKERS`. The gate stays strict.
- **Orc** (`9085ee7`): the first re-ask for the final JSON is sent exactly like a tool turn: same tools, no `text.format`, tools not offered. Only an invalid answer, or a tool call there, falls back to the strict schema.
  - Evidence: OpenRouter's endpoint list shows Relace (tools, but no `response_format` or `structured_outputs`). A local probe with the production prefix gave these results:
    - Strict final turn: moved provider 6/6.
    - Tools kept with `tool_choice: "none"`: definitions dropped, provider moved 3/3.
    - Tool-turn-shaped re-ask: stayed on Relace 5/5 with about 93% cached and a valid JSON 5/5.
- **Rollback references:** sandbox `3d38acaf-eff8-43f8-9f36-2319af6c7f8f`, orc `c79aac06-dc7b-4c76-9b61-2f1e18f2c1c3`.
- **Deployed** by local upload (`git archive` of `9085ee7`). Both reached `SUCCESS`:
  - Sandbox `3cd9de07-73d0-4a73-8dc8-7f6fcba298a2` (`isolation_enforced=true`, `/ready` 200).
  - Orc `3e06e8d6-dfa5-4826-b7c2-28e4e7ac171b` (`/ready` 200).
  - No variable changed.
- **Live verification:** the temporary job `fix-verify-job` (`0a677eb3-55b2-47c0-9c53-3e8608d32de1`, only a reference to `MARKET_AI_ORC_API_KEY`, deleted afterwards) re-ran the two PoC requests that had failed, with the exact same wording, plus the z-score request.

  | Run | Before | After | Calls | Cached / prompt | Cost |
  |---|---|---|---|---|---|
  | poc-2 custom formula (upper-shadow ratio, BBCA and BBRI, "1 Juli sampai 31 Agustus 2026") | `LIMITATION`, spec refused 15 times | `ANSWER`, `CALCULATION_VERIFIED`, gate `ANNOTATED`; last values on 2026-08-31: BBCA 0.2883, BBRI 0.1964 | 14 | 378,368 / 423,786 (0.893) | $0.02370 |
  | poc-3 event study (fall over 7% in a day, 5-day forward return, 2025-01-02 to 2026-07-31) | `LIMITATION`, no spec attempted | `ANSWER` (details below) | 15 | 401,280 / 432,582 (0.928) | $0.02922 |
  | z-score, 3 tickers, 3 months | `CALCULATION_VERIFIED` | `CALCULATION_VERIFIED`, gate `PASSED` | 10 | 151,552 / 177,887 (0.852) | $0.00796 |

  - poc-3 details:
    - Research Governor `APPROVED` (`HISTORICAL_PATTERN`, H1).
    - The first analysis was `FAILED` (`CALCULATION_MISMATCH`, caught by the validator); the second was `PASS` / `CALCULATION_VERIFIED`, evidence `PARTIALLY_SUPPORTED` / `PATTERN`.
    - 8,048 events against a baseline of 300,168 observations. Mean 5-day forward return +0.519% against +0.617%, delta −0.097 pp, CI95 −0.445 to +0.251. So the pattern was not better than the baseline, and the answer said so.
  - **Caching:** every run kept one static prefix (`distinct_static_prefixes=1`) and one provider for all its calls (Together, Together, Relace), per OpenRouter's generation records.
    - The final re-ask now reuses the cache. In the z-score run, the re-ask after a prose draft had 24,064 of 25,723 prompt tokens cached; the same turn had 0 cached before this fix.
    - The earlier runs had cache ratios of 0.700 and 0.752.
- The job's output and the orc logs were scanned: no bearer token, OpenRouter key, or DSN with a password. `railway config plan` reports the configuration up to date; the environment is back to 15 services.

## 2026-09-24 — Deploy market-ai-orc prompt-caching-aware model calls (commit 73b3c4e)

- Scope approved by the user: the model-call layer of `market-ai-orc` only, keeping the OpenRouter Responses API.
  - Every call of a run sends `session_id` = `request_id`.
  - Usage now includes cached and cache-write tokens, fresh tokens, cost, latency, and a static-prefix fingerprint per call, with a run summary.
  - No custom prompt cache. `market-ai-backend` was not changed.
  - Orc suite: 382 passed.
- **Verified against OpenRouter documentation** (prompt-caching and usage-accounting pages):
  - `session_id` in the body is accepted by both the Chat and Responses APIs and becomes the sticky-routing key.
  - DeepSeek caching is implicit, and a cache read is billed at 0.1x input.
  - Responses reports cache use in `usage.input_tokens_details`, and `usage.cost` is always present.
  - The Responses body carries no `provider` field. The serving provider comes from `GET /api/v1/generation?id=<provider_response_id>`.
- Rollback reference: orc `7fe7f1f6-0adf-4dd5-b118-4aa01b99d51d`. Deployed `c79aac06-dc7b-4c76-9b61-2f1e18f2c1c3` by local upload (clean `git archive` of `73b3c4e`); it reached `SUCCESS` with `/ready` 200. No variable changed.
- **Live PoC:** the temporary job `cache-poc-job` (`292d969e-90ab-4db5-861d-85552c285bee`, only a reference to `MARKET_AI_ORC_API_KEY`, deleted afterwards) ran `cache-poc-1`, "Hitung z-score rolling 20 hari … BBCA, BBRI, TLKM … 3 bulan terakhir". Result: `ANSWER`, `CALCULATION_VERIFIED`, gate `PASSED`, 8 model calls, 7 tool calls, 107.5 s. Per call, from the orc logs and OpenRouter's generation records:

  | Call | Prompt | Cached | Fresh | Completion | Cost (USD) | Provider | Prefix |
  |---|---|---|---|---|---|---|---|
  | 1 | 10,841 | 0 | 10,841 | 101 | 0.00102114 | Relace | `6078453d` |
  | 2 | 12,090 | 10,752 | 1,338 | 254 | 0.00033149 | Relace | `6078453d` |
  | 3 | 15,378 | 12,032 | 3,346 | 837 | 0.00078608 | Relace | `6078453d` |
  | 4 | 16,355 | 15,360 | 995 | 419 | 0.00041634 | Relace | `6078453d` |
  | 5 | 17,284 | 16,640 | 644 | 499 | 0.00043227 | Relace | `6078453d` |
  | 6 | 20,483 | 17,152 | 3,331 | 1,833 | 0.00127901 | Relace | `6078453d` |
  | 7 | 23,884 | 20,480 | 3,404 | 751 | 0.00082863 | Relace | `6078453d` |
  | 8 (structured final) | 15,727 | 0 | 15,727 | 803 | 0.00143208 | DekaLLM | `ad094799` |

  - Totals: 132,042 prompt tokens, of which 92,416 cached (ratio 0.6999), 39,626 fresh and 5,497 completion; cost $0.00652703; average latency 12.4 s.
  - Every call carried the same `session_id`, and OpenRouter recorded it on each generation. Calls 1–7 had a byte-identical static prefix and stayed on one provider.
  - `cache_write_tokens` was 0 on every call; DeepSeek endpoints report no cache writes.
- **Baseline for comparison:** the same prompt before this change (`poc-1-standard`, orc `7fe7f1f6`, no `session_id`), looked up in OpenRouter's generation records.
  - 7 calls: 114,506 prompt tokens, 86,060 cached (ratio 0.7516), cost $0.00560759.
  - Calls 1–6 stayed on Relace through OpenRouter's default conversation-hash stickiness, since the first system and user messages are stable within a run. The last call went to OpenInference.
  - **Conclusion:** in this single-sample comparison, `session_id` did not measurably raise the cache ratio. Excluding the final call, the ratio is 0.795 with `session_id` and 0.771 without, which is within run-to-run variation. What it adds is explicit stickiness from the first call and session grouping in OpenRouter's logs.
- **Cache miss, evidenced and not fixed:** in both runs, and in a local probe, the final call lost the cache.
  - It is the structured-final turn: the model drafted prose on a tool turn, so the orchestrator asks again with tools withdrawn and a strict `text.format` JSON schema.
  - That changes the static prefix (the fingerprint differs). With `provider.require_parameters=true`, it also moved to another provider, presumably one that supports structured outputs, so sticky routing could not apply.
  - In `cache-poc-1` that single call carried 40% of the fresh prompt tokens and 22% of the cost.
  - Changing it touches structured output and tool choice, which the user excluded from this change. It is reported for a separate decision.
- No other service, variable, or schedule was changed. `railway config plan` reports the configuration up to date.

## 2026-09-24 — Deploy the Research AI release: Research Governor, event studies, evidence assessment, claim gate, run audit (commit bc589d3)

- Scope approved by the user: apply migration `20260924_004`, deploy `market-sql-governor`, `market-python-sandbox` and `market-ai-orc`, set the 3x capacity limits and `RESEARCH_AUDIT_DATABASE_URL`, and run the live PoC.
  - Local suites on the release tree: sandbox 206, orc 373, Governor 135 passed. The migration was rehearsed on a scratch database.
  - `origin/main` had no new commits, so the release is the feature branch fast-forwarded.
- **Pre-deploy checks:**
  - OpenRouter's models API reports `deepseek/deepseek-v4.1-flash` with a 1,048,576-token context window, so `AI_MAX_CONTEXT_TOKENS=500000` is below the model limit. Listed pricing is $0.14/M input, $0.42/M output, and $0.0042/M cache read.
  - No caller of `/v1/agent/run` exists in the repository besides the temporary jobs. The private network has no proxy timeout, and the job's HTTP timeout is 1900 s, above `AI_MAX_ANALYSIS_SECONDS`.
  - A SQLite file in the old schema, written by the code at `ca10721`, opened cleanly with the new code: columns were added, old rows read back, and reopening was idempotent.
- **Rollback references**, recorded before deploying: Governor `ddd1d851-a0c8-4dc8-9361-e2333018db7a`, sandbox `d7f57f10-6fc1-4bee-a231-a76b3716c3d5`, orc `7f463b78-19a9-4b15-8e30-5b0d8b8254ea`.
  - The orc v3 tool contract, sandbox research fields, and Governor units ship together, so these three roll back together.
  - Rolling back does not remove `AI_research_run_audit`. With an older orc, the table simply stops receiving rows.
- **Variables**, all set with `--skip-deploys` before deploying:
  - `market-python-sandbox`: `PY_SANDBOX_MAX_ANALYSES_PER_REQUEST=18`, `PY_SANDBOX_MAX_SPECS_PER_REQUEST=30`, `PY_SANDBOX_MAX_CPU_SECONDS_PER_REQUEST=3600`. These were code defaults (6, 10, 1200) and are now explicit.
  - `market-ai-orc`:
    - `AI_MAX_TOOL_CALLS` 20 → 60.
    - `AI_MAX_TOOL_ITERATIONS` 20 → 60.
    - `AI_MAX_CONTEXT_TOKENS=500000` (was the code default 64000).
    - `AI_MAX_ANALYSIS_SECONDS=1800` (was the code default 600).
    - `RESEARCH_AUDIT_DATABASE_URL` (secret): a reference template, `postgresql://market_ai_orc:${{MARKET_AI_ORC_DB_PASSWORD}}@${{Postgres.RAILWAY_PRIVATE_DOMAIN}}:5432/${{Postgres.PGDATABASE}}`. It is the same template as `CATALOG_DATABASE_URL`: the `market_ai_orc` login now also holds the INSERT-only `market_ai_research_audit_writer` role. A read-back confirmed it resolves, equals the catalog DSN, and has no unresolved reference. Its value was never printed.
- **Deployed** by local upload (`railway up <app> --path-as-root`, clean `git archive` of `bc589d3`), one at a time. Each deployment reached `SUCCESS`:
  - Governor `8682d991-986d-4c4d-8916-d3f9335dabb6`.
  - Sandbox `3d38acaf-eff8-43f8-9f36-2319af6c7f8f`. Startup logged `isolation_enforced=true`, 0 interrupted analyses, and `/ready` 200.
  - Orc `7fe7f1f6-0adf-4dd5-b118-4aa01b99d51d`, `/ready` 200.
- **Temporary one-off service** `research-deploy-job` (`8a6534be-787a-4971-8666-6de0b60c9537`): reference variables only (`DATABASE_URL`, `MARKET_AI_ORC_API_KEY`, `PY_SANDBOX_API_KEY`, `SQL_GOVERNOR_API_KEY`), redacted from its output, deleted afterwards. Deployments:
  - `539a778e` applied migration 004. Its own read-back query failed on a wrong column name after the commit.
  - `22721042` read back read-only.
  - `0618e56d` ran the live PoC.
  - `6b682dc0` ran the controlled event study and the catalog/schema sync.
- **Live PoC** (§71 of the Research AI spec) over the private network with the real model, reported as observed:

  | Run | Result | Tool calls | Tokens | Time | Note |
  |---|---|---|---|---|---|
  | poc-1 standard: "z-score rolling 20 hari … BBCA, BBRI, TLKM … 3 bulan terakhir" | `ANSWER`, `CALCULATION_VERIFIED`, gate `PASSED` | 7 | 119,253 | 113.5 s | 186/186 values recalculated and matching; experiment `RETAINED`; audit row written |
  | poc-2 custom formula: upper-shadow ratio 10-day mean, BBCA and BBRI, "dari 1 Juli sampai 31 Agustus 2026" | `LIMITATION` | 15 | 545,324 | 140.1 s | **Failed.** Every spec was refused `ANALYSIS_SPEC_MISMATCH` by the sandbox intent review, for two reasons. First, "tiap saham" is read as an all-stocks universe. Second, "1 Juli sampai 31 Agustus 2026" is read as August 2026 only. The model correctly did not bend the user's parameters. |
  | poc-3 event study: "turun lebih dari 7% dalam sehari … 5 hari … 2 Januari 2025 sampai 31 Juli 2026" | `LIMITATION` | 5 | 126,494 | 48.8 s | **Not exercised.** The model never called `create_analysis_spec` and answered with a limitation after catalog discovery. |
  | poc-4 ambiguous: "Saham bank mana yang bagus sekarang?" | `CLARIFICATION` | 3 | 49,933 | 32.6 s | Asked for the criterion, period and universe; disclosed that fundamentals are unavailable |
  | poc-5 pairwise correlation across all IDX stocks in 2025 | `LIMITATION` | 4 | 71,483 | 29.5 s | Refused by spec validation (`INVALID_SPEC`: a pairwise output needs a TICKERS universe), not by the Research Governor. The model did not propose a bounded universe. |

- **Controlled checks** through the live services (direct API, labelled as injected; they test the gates, not the model):
  - An approved z-score spec for BBCA/BBRI/TLKM received a Governor dataset of 258 rows, `COMPLETE`. The manifest reports `unit: null` for `close`, because `AI_column_catalog.unit` is empty for the price table, so the unit preflight has nothing to compare yet.
  - Injected wrong window 10 → `FAILED`, `CALCULATION_MISMATCH` on 186/186 values, diagnosis `PARAMETER_DIFFERS` (`window`, spec 20, values match 10), evidence `INVALID`.
  - The correct window 20 → `PASS`, `CALCULATION_VERIFIED`, evidence `SUPPORTED`/`OBSERVATION`.
  - A `HISTORICAL_PATTERN` research spec without an event study → Research Governor `REPLAN_REQUIRED`, `MISSING_BASELINE_DEFINITION`, `next_action=REVISE_SPEC`, with the 18-experiment and 4-hypothesis budget shown.
  - **Controlled live event study** (`poc-direct-event`), for all IDX stocks from 2025-01-02 to 2026-06-30: a 20-day z-score below −1.5, followed by the 5-day forward return from the next open.
    - Spec `APPROVED`; the Research Governor reserved experiment 1/18 and hypothesis 1/4. Resubmitting the same spec replayed the same `spec_id`, so no budget was consumed twice.
    - First data request, one unfiltered 602-day range: the SQL Governor answered `NEEDS_NARROWING`/`DATE_RANGE_TOO_LARGE`, because unfiltered requests are capped at 400 days.
    - Split into two requests and bound as one logical input: 201,031 + 108,740 rows, 843 tickers, both `COMPLETE`.
    - The sandbox preflight refused it `INSUFFICIENT_WARMUP_HISTORY`. 26 thinly traded tickers had fewer than 19 observations inside the recommended request range (from 2024-11-23). Their remedy text, "request data from 2024-11-23 or earlier", repeats the range already requested.
    - A retry starting 90 days earlier (199,039 + 160,495 rows) still left 2 tickers (CSMI, TFCO) short and was refused the same way.
    - Evidence was `INSUFFICIENT_EVIDENCE` both times; no finding was produced. The event-study recalculation itself was therefore not reached on live data; it is covered by the local fixture tests only.
    - The two attempts ran as analyses 1 and 2 of that request's 18.
- **Run audit:** each of the 5 orc runs wrote one `AI_research_run_audit` row through the `market_ai_orc` login.
  - poc-1 carries its experiment (code hash, dataset id and checksum), budget, and `sandbox_summary_status=REPORTED`.
  - The other four carry `NOT_USED`, because no analysis ran. Refused specs are not stored by the sandbox, so they are visible only in logs, not in the audit row.
- **Catalog and schema refresh** (deployment `6b682dc0-2159-4aa0-9232-b74a94998e97`):
  - `scripts/sync_database_catalog.py` reported `Catalog reconciled: 628 physical columns, 21 updated`, the physical facts of the new table's columns. `scripts/sync_database_schema.py` reported `Synchronized 38 tables`.
  - The regenerated `DATABASE_SCHEMA.md` came back as gzip+base64 chunks and was verified locally by sha256 (`37347e25…`, 153,842 bytes). Its only changes are timestamp drift and the new `AI_research_run_audit` section.
- Deleted `research-deploy-job` with `railway service delete`; the environment is back to its 15 services. Then ran `railway config pull --force`: `.railway/railway.ts` now preserves the new variable names (three `PY_SANDBOX_MAX_*`, `AI_MAX_ANALYSIS_SECONDS`, `AI_MAX_CONTEXT_TOKENS`, `RESEARCH_AUDIT_DATABASE_URL`), without values. `railway config plan` reported the configuration up to date.
- The job's output (all six deployments) and the three new deployments' logs were scanned: no bearer token, OpenRouter key, DSN with a password, AWS key id, or presigned-URL signature. A direct in-process comparison against the 13 secret and URL variable values of the three services also found none of them in any log. The 64-hex strings in the logs are sha256 checksums (spec, code, dataset, query).
- No other service's variables, source, schedule, volume, domain, or restart policy was changed.

## 2026-09-24 — Deploy the fact/analysis split: Governor dataset-only + lookup, sandbox v2 validation gate, orc answer gates (commit 1361644)

- Scope approved by the user: one joint release of migration 009, `market-sql-governor`, `market-python-sandbox` v2, and `market-ai-orc`. Before deploying, `origin/main` was found eight commits ahead (the `AI_research_catalog` and `AI_formula_reference` rollouts, deployed to `market-ai-orc` as `89ed23b6` at 09:17 UTC). The feature branch merged `origin/main` cleanly as `1361644`, so the release keeps those features. The orc, Governor, and sandbox suites pass on the merged tree (363, 118, 164 tests; local PostgreSQL 16 for the database tests). Governor and sandbox code was not touched by those main commits.
- Rollback references, recorded before deploying: Governor `92aaf788-b147-4437-88ec-6d36bbad6e96`, sandbox `4310a9f6-43e6-438f-b55e-8155155beeaf`, orc `89ed23b6-3ff5-481e-96af-733888dae794`. Note: Governor v2 no longer returns inline rows and sandbox v2 requires a `spec_id`, so these three must be rolled back together.
- Deployed by local upload (`railway up <app> --path-as-root`, clean `git archive` of `1361644`). Each deployment reached `SUCCESS`:
  - Governor `ddd1d851-a0c8-4dc8-9361-e2333018db7a`.
  - Sandbox `d7f57f10-6fc1-4bee-a231-a76b3716c3d5`. Startup logged `isolation_enforced=true` with no interrupted analyses.
  - Orc `7f463b78-19a9-4b15-8e30-5b0d8b8254ea`.
  - Each service answered `200` on `/ready`, both from Railway's health probe and over the private network.
- No variable, secret, volume, domain, schedule, or restart policy of these services was changed. The orc keeps `AI_MAX_TOOL_CALLS=20` and `AI_MAX_TOOL_ITERATIONS=20`; the sandbox and Governor run on their code defaults.
- The temporary one-off service `split-deploy-job` (`836e701d-926c-4ffe-b0c0-f50487185e20`) held reference variables only (`DATABASE_URL`, `MARKET_AI_ORC_API_KEY`, `PY_SANDBOX_API_KEY`, `SQL_GOVERNOR_API_KEY`) and redacted them from its output. It ran four jobs:
  - Migration 009 (see `DATABASE_CHANGELOG.md`).
  - The live acceptance run below.
  - Three read-only catalog inspections, in `default_transaction_read_only` sessions.
  - The first migration run's output was never collected by Railway's log pipeline, and later runs lost some long lines. The job now waits before exiting and prints one row per line.
- Live acceptance over the private network (deployment `5a71843e-74e9-488c-9f35-90952fe12551`):
  - **Governor, direct calls:**
    - A small `/v1/query` returns `DATASET_READY` with no `rows` field.
    - `/v1/lookup` VALUE (BBCA close on 2026-09-23) and AGGREGATE (SUM of volume, 2026-09-15..23) both return `FACTS_READY` and equal the PostgreSQL values.
    - Five refusals behave as specified:
      - too many values → `LOOKUP_TOO_LARGE` / `USE_ANALYSIS_PATH`;
      - an `order_by` field → `LOOKUP_NOT_ALLOWED` / `USE_ANALYSIS_PATH`;
      - STDDEV → `LOOKUP_NOT_ALLOWED` / `USE_ANALYSIS_PATH`;
      - a table outside the allowlist → `TABLE_NOT_APPROVED`;
      - an unknown column → `UNKNOWN_COLUMN`.
  - **Sandbox:** `/v1/runtime` reports `isolation_enforced=true` and validator checks `validator_seccomp_filter_active`, `validator_socket_inet_denied`, `validator_uid_non_root`.
  - **Orc, real model** (`deepseek/deepseek-v4.1-flash`); six runs, every one HTTP 200 with `number_provenance.unsupported=[]`. Every first data call was on the intended path. Results:

    | Run | Result | Tool calls | Time | Note |
    |---|---|---|---|---|
    | "Berapa harga close BBCA kemarin?" | `ANSWER`, `FACT` | 4 | 43.5 s | |
    | "total volume BBCA minggu ini" | `ANSWER`, `DATABASE_AGGREGATE` | 4 | 13.1 s | Discloses the partial week |
    | BBCA–BBRI daily-return correlation, Jun–Aug 2026 | `ANSWER`, `CALCULATION_VERIFIED`, gate `PASSED` | 6 | 26.2 s | |
    | "average of the preview rows, without Python" | `ANSWER`, `DATABASE_AGGREGATE` | 7 | 27.1 s | Refused to compute from preview rows; used a lookup AVG |
    | 20-day rolling z-score, 5 tickers, 3 months | `ANSWER`, `CALCULATION_VERIFIED`, gate `PASSED` | 6 | 30.7 s | |
    | RSI(14) < 30 + bullish engulfing, all IDX | `LIMITATION`, `UNVERIFIED_EXPLORATORY`, gate `ANNOTATED` | 12 | 44.2 s | Custom engulfing rule; `PATH_DEPENDENT_WARMUP`, `STALE_LATEST_OBSERVATION`; tools withdrawn at `CONTEXT_BUDGET` after 251k cumulative tokens |

- The logs of the three services and of the job were scanned for bearer tokens, provider keys, DSNs with credentials, bucket secrets, and presigned-URL signatures: no match. The Governor logs `sql_governor_lookup` events with fact ids and a values hash, not the values.

## 2026-09-24 — Deploy market-ai-orc with AI_formula_reference FORMULAS support (commit cb97fac); clear its watchPatterns

- Added `FORMULAS` support to `market-ai-orc` (`catalog.py`/`catalog_rows.py`/`orchestrator.py`), mirroring the `RESEARCH` rollout: `discover_catalog`'s `formula_catalog` count, `get_catalog_details`'s `FORMULAS` section with `formula_ids` narrowing, and `AI_formula_reference` in `read_catalog_rows`. 253 tests pass locally, 60 skipped (no disposable Postgres). Bumped the FastAPI app version to `0.2.0`.
- Recorded rollback reference before deploying: the previously active deployment was `9db01c3c-7392-4e99-9741-822ce0a4274c`.
- **Deploy incident:** three consecutive `railway up` attempts (deployments `4aa76438`, `7ad8b624`, `3a14cb15`), each with genuinely new commits, were marked `SKIPPED` by Railway with reason "No changes to watched files" — a known Railway CLI/platform issue (railwayapp/cli#787) where the `build.watchPatterns` change-detection misfires for local-upload (`railway up`) deploys, not just the git-push-triggered deploys it's meant for. Two attempts to clear `watchPatterns` via `railway config apply --yes` reported success but never actually changed the live value (confirmed by `railway config plan` still showing drift immediately after). The user cleared `market-ai-orc`'s **Watch Paths** directly from the Railway dashboard (Settings → Build), which the CLI could not do — this is what actually fixed it. Deployment `89ed23b6-3ff5-481e-96af-733888dae794` then built and deployed normally and reached `Online`.
- `watchPatterns` is deliberately left cleared (not restored) for this service: `market-ai-orc` has `source: null` (no GitHub source, local-upload only, confirmed via `railway service list --json`), so the pattern was never actually filtering anything meaningful — it only exposed this false-skip bug. `.railway/railway.ts` now reflects this (no drift after `railway config pull --force` + `railway config plan`).
- Verified all three tools end-to-end against live dev data (see `DATABASE_CHANGELOG.md` for exact results), using a temporary service (`orc-verify-2`, deleted after) that imported the identical deployed `app/` code and called it directly through `CATALOG_DATABASE_URL` — not a synthetic/disposable database.
- The three `Tool_Catalog` rows for these tools were extended (`FORMULAS` support added, `runtime_commit` stamped) in the same task at the user's explicit request; they were already `is_active=true` from the earlier `AI_research_catalog` rollout. See `DATABASE_CHANGELOG.md` migration `20260924_003`.
- No other service's schedule, source, variables, secrets, restart policy, domain, or database reference was changed. No production environment was touched.

## 2026-09-24 — Deploy market-ai-orc with AI_research_catalog RESEARCH support (commit aa7b231)

- Reviewed [PR #1](https://github.com/rednightt33/saniti/pull/1) (`codex/ai-research-catalog`, opened by the ChatGPT Codex connector) line by line and applied its `market-ai-orc` code changes directly to `main` at the user's explicit request, rather than merging the PR branch: `orchestrator.py` prompt update, `catalog.py`/`catalog_rows.py` RESEARCH-section support in `discover_catalog`, `get_catalog_details`, and `read_catalog_rows`. 249 tests passed locally, 58 skipped (no disposable Postgres), matching the PR's own report.
- Recorded rollback reference before deploying: the previously active deployment was `a292e767-071f-4afb-8978-8e93901c34c6`.
- Deployed via `railway up ./apps/market-ai-orc --path-as-root --service market-ai-orc` (local upload — this service has no GitHub source, so the `main` push alone does not deploy it). New deployment `9db01c3c-7392-4e99-9741-822ce0a4274c`, reached `Online`; startup logs show a clean `Uvicorn running` and a `200` on `/ready`.
- Verified all three tools end-to-end against live dev data (see `DATABASE_CHANGELOG.md` for exact results), using a temporary service (`orc-verify`, deleted after) that imported the identical deployed `app/` code and called it directly through `CATALOG_DATABASE_URL` (`${{market-ai-orc.CATALOG_DATABASE_URL}}`, the real read-only `market_ai_orc` login) — not a synthetic/disposable database.
- The three `Tool_Catalog` rows for these tools were activated (`is_active=true`) in the same task at the user's explicit request; see `DATABASE_CHANGELOG.md` migration `20260924_002`.
- PR #1 is superseded by this direct-to-main deployment; see its closing comment for the exact commit.
- **Sandbox network constraint** (context for the temporary-service workaround, same as the earlier pgweb deployment): this session's outbound network supports plain HTTPS request/response only; raw-TCP and WebSocket-based paths to Postgres are blocked by this environment's egress policy. All Railway CLI operations used here (`railway up`, `railway add`, `railway domain`, `railway logs`) are plain HTTPS.
- No other service's schedule, source, variables, secrets, watch path, restart policy, domain, or database reference was changed. No production environment was touched.

## 2026-09-23 — Deploy market-python-sandbox and the Python analysis tools (81475ae)

- **Governor dataset-access key:** generated a new 64-hex `SQL_GOVERNOR_DATASET_ACCESS_KEY` on `market-sql-governor`. It was set through stdin with `--skip-deploys` and never printed. A check confirmed it differs from `SQL_GOVERNOR_API_KEY`.
- **New resources** (user-approved pinned IaC plan, plan file sha256 `729913afd92dfa9d…`, change set `sha256:1299b527…`; 2 safe creates, 0 changes, 0 destroys):
  - Volume `market-python-sandbox-data` (`853e57c0-eb4c-4b48-a4ce-6bd7ffe282d8`, region `sfo`, mounted at `/data`).
  - Service `market-python-sandbox` (`225b1be1-d7f5-4b2d-a4c7-052eb53af818`):
    - Dockerfile build; start command `uvicorn app.main:create_app --factory` on `:8080`.
    - Health check `/ready` (300 s), which returns `503` unless the isolation self-test passed.
    - One replica in `sfo`, restart `ALWAYS`.
    - Private only (`market-python-sandbox.railway.internal:8080`), no public domain, no GitHub source. It is deployed by local upload.
- **`market-python-sandbox` variables:**
  - `PORT=8080` and `SQL_GOVERNOR_URL=http://market-sql-governor.railway.internal:8080`.
  - `SQL_GOVERNOR_DATASET_ACCESS_KEY` is a reference to `${{market-sql-governor.SQL_GOVERNOR_DATASET_ACCESS_KEY}}`.
  - `PY_SANDBOX_API_KEY` is a new 64-hex secret, set through stdin.
  - No `PY_SANDBOX_*` limit is overridden, so the code defaults apply.
  - The service holds no PostgreSQL or bucket credential.
- **`market-ai-orc` variables** (with `--skip-deploys`):
  - `PY_SANDBOX_URL=http://market-python-sandbox.railway.internal:8080`.
  - `PY_SANDBOX_API_KEY` is a reference to `${{market-python-sandbox.PY_SANDBOX_API_KEY}}`.
  - `AI_MAX_TOOL_CALLS=20` (previously the default of 12), approved by the user with this deployment.
- **Deployments** (each reached `SUCCESS`):
  - Governor `92aaf788-b147-4437-88ec-6d36bbad6e96` (dataset manifest/access endpoints, tombstones). Rollback: `4c66fb87-fbe2-481a-b412-067c0d61de14`.
  - Sandbox `4310a9f6-43e6-438f-b55e-8155155beeaf`. Its startup log records `isolation_enforced=true` and pinned library versions (Python 3.12.14, numpy 2.4.6, pandas 3.0.6, polars 1.44.2, pyarrow 25.0.1, duckdb 1.5.5, scipy 1.17.1, statsmodels 0.15.0, matplotlib 3.11.2, TA-Lib 0.8.1).
  - market-ai-orc `a292e767-071f-4afb-8978-8e93901c34c6`: the same watch-path-compatible staging upload as before. Rollback: `44e44fdf-330b-4fb0-b6f5-83e4fde81c10`, or unset `PY_SANDBOX_URL` to unregister the two analysis tools.
- **Temporary one-off service `sandbox-acceptance-job`** (`0e909127-145c-4b86-a87f-ed4f69322523`, deployment `c6cf05e3-16a5-43c0-b328-8bda4e8ef1b4`):
  - Reference variables only, restart `NEVER`.
  - It applied migration 008 (see `DATABASE_CHANGELOG.md`) and ran the live acceptance over the private network.
  - It was deleted afterwards; the service list confirms 15 services and no temporary job.
- **Live acceptance** (real OpenRouter model, real data):
  - A. "RSI(14) < 30 and latest-bar bullish engulfing": `COMPLETED`/`ANSWER`, 127 s, 9 tool calls. The screen covered 841 of 844 tickers. 53 matched RSI < 30 and 12 matched bullish engulfing. The answer honestly reported 0 tickers matching both. It disclosed that RSI smoothing was seeded at the start of the extracted window.
  - B. "Latest close > 2 SD above the 20-day rolling mean": `COMPLETED`/`ANSWER`, 112 s, 5 tool calls. It found 42 tickers, using sample SD (ddof=1). The full table is a `result_id`.
  - C. "Daily returns, last 10 trading days, all stocks": `COMPLETED`/`ANSWER`, 330 s, 8 tool calls. It covered 842 tickers × 10 dates, and a model-chosen cross-check against `return_1d_pct` found 0 mismatches.
  - Observation: the answers disagree on the newest date. A and C say 2026-09-22, while B's dataset contains 2026-09-23 rows. The run did not establish whether this came from the model's chosen window, source freshness at extraction time, or Feature 01 lag. The architecture addendum's reference-date and actual-scope validation targets this class of gap.
- **Direct checks:**
  - A 27,498-row dataset produced a full `TABLE` with a 50-row preview, in 709 ms.
  - An unknown dataset returned `DATASET_NOT_FOUND`; a malformed id returned `422`.
  - Sockets to PostgreSQL, the bucket endpoint, and the Governor from analysis code returned `FORBIDDEN_OPERATION`. Listing `/data` also returned `FORBIDDEN_OPERATION`.
  - Importing `psycopg` returned `FORBIDDEN_IMPORT`.
  - An over-allocation returned `MEMORY_LIMIT_EXCEEDED`, and `subprocess` returned `FORBIDDEN_OPERATION`.
  - An infinite loop returned `RUNTIME_LIMIT_EXCEEDED` at 120,039 ms. A healthy job completed afterwards.
  - Key separation: the orc API key on the access endpoint returned `401`, and the access key on `/v1/query` returned `401`.
- **Logs:** the Governor logged 15 `sql_governor_dataset_access` events and the sandbox logged 16 `sandbox_analysis` events. Neither service's logs contain presigned URLs, `X-Amz` parameters, bearer strings, or key values.
- Ran `railway config pull --force`. `.railway/railway.ts` now preserves the new orc variables (`PY_SANDBOX_URL`, `PY_SANDBOX_API_KEY`, `AI_MAX_TOOL_CALLS`) and the volume's live defaults, and the follow-up `railway config plan` reported `dev` up to date. No other service, domain, schedule, or source was changed.

## 2026-09-23 — Isolation probe for market-python-sandbox (temporary, deleted)

- **Why:** Before the sandbox was designed, a read-only probe checked which isolation primitives Railway containers allow. The Railway docs describe containers only as "non-privileged".
- **Temporary service:** `sandbox-isolation-probe` (`546162a2-7128-40e0-948a-de521cbe2be1`, deployment `b92eccc9-9b6c-424c-905f-33ca3245b6f6`, image `python:3.12-slim`, restart `NEVER`, no variables). It printed one JSON line and exited. It never printed environment values.
- **Results on `dev`:**
  - Kernel `6.18.5+deb13-cloud-amd64`, x86_64 (not gVisor). The container runs as root with capability set `0x800405fb` (Docker defaults without NET_RAW, MKNOD, and AUDIT_WRITE).
  - The runtime already applies its own seccomp filters (`Seccomp: 2`, 3 filters). cgroup is not writable. The limits are `memory.max` 24 GB, `cpu.max` 24 CPUs, and `pids.max` 1000.
  - Dropping to UID 65534 works. `/proc/1/environ` is unreadable to that user (`EACCES`), and `RLIMIT_AS` is enforced.
  - A process-level seccomp filter installs as non-root. It denies AF_INET, AF_INET6, and AF_NETLINK sockets and `execve`, while AF_UNIX stays allowed in the probe.
  - `unshare(CLONE_NEWNET)` as root returns `EPERM`, and `unshare(CLONE_NEWUSER|CLONE_NEWNET)` as non-root returns `EACCES`. **Network namespaces are not available.** Outbound TCP from the container works, and Railway has no egress firewall.
- **Cleanup:** The service was deleted with `railway service delete`. `railway config plan` reported `dev` up to date.
- The design recorded in `apps/market-python-sandbox/README.md` follows from these results: seccomp socket denial per analysis process, not a network namespace.

## 2026-09-23 — market-sql-governor: one-week dataset expiry and MIN/MAX on dates

- Railway buckets do not support lifecycle configuration: the storage-bucket docs list "Bucket lifecycle configuration" under "Not yet supported". Expiry is therefore done by the Governor's own janitor (`apps/market-sql-governor/app/janitor.py`).
  - It runs at startup and then every hour (`SQL_DATASET_CLEANUP_INTERVAL_SECONDS=3600`).
  - It deletes `datasets/ds_*/data.parquet` and `manifest.json` once the manifest's `expires_at` has passed.
  - Default retention is now one week (`SQL_DATASET_RETENTION_HOURS=168`). Both values are code defaults, so no Railway variable was added.
- Deployed commit `f2c4012` as `4c66fb87-fbe2-481a-b412-067c0d61de14`: `SUCCESS`, `/ready` `200`.
  - The first live janitor pass logged `sql_governor_dataset_cleanup datasets_seen=9 datasets_deleted=0 errors=0`, which proves bucket list and read work.
  - Datasets written before this change keep the 24-hour `expires_at` recorded in their manifests.
- Temporary one-off service `orc-mig007-job` (`72942e81-6cbf-48fa-af3c-1e6e638cfa05`, deployment `414b7d62-c82b-45c6-a480-d6af500106d4`) applied migration 007 and checked MIN/MAX live (see `DATABASE_CHANGELOG.md`). It was deleted afterwards, and `railway config plan` reported `dev` up to date.

## 2026-09-23 — Deploy market-sql-governor and request_data

- **New resources** (user-approved pinned IaC plan `sha256:c9e8e1bb…`: 2 creates, 0 changes, 0 destroys):
  - Bucket `market-sql-datasets` (`62b028ba-313f-4c6a-81b3-48a9645411c1`, region `sjc`).
  - Service `market-sql-governor` (`1a322795-4f93-4c51-a25e-5fcfc5ab4722`): Dockerfile build, `uvicorn app.main:create_app --factory` on `:8080`, health check `/ready` (which also checks the database), 1 replica in `sfo`, restart `ALWAYS`.
  - The service is private (`market-sql-governor.railway.internal:8080`) with no public domain. It has no GitHub source and no watch path; it is deployed by local upload.
- **`market-sql-governor` variables:**
  - `SQL_GOVERNOR_API_KEY` (64 hex characters) and `MARKET_SQL_GOVERNOR_DB_PASSWORD` were generated and set through stdin; they were never printed.
  - `GOVERNOR_DATABASE_URL` is a reference template: `postgresql://market_sql_governor:${{MARKET_SQL_GOVERNOR_DB_PASSWORD}}@${{Postgres.RAILWAY_PRIVATE_DOMAIN}}:5432/${{Postgres.PGDATABASE}}`.
  - `SQL_DATASET_BUCKET_{NAME,ENDPOINT,REGION,ACCESS_KEY_ID,SECRET_ACCESS_KEY}` reference `${{market-sql-datasets.*}}`.
  - `PORT=8080`. No `SQL_*` limit is overridden, so the code defaults apply.
- **`market-ai-orc` variables:** `SQL_GOVERNOR_URL=http://market-sql-governor.railway.internal:8080`, and `SQL_GOVERNOR_API_KEY=${{market-sql-governor.SQL_GOVERNOR_API_KEY}}`.
- **Temporary one-off services** (reference variables only, restart `NEVER`, deleted after use):
  - `orc-governor-setup` (`c54d2e20-947b-49ed-8867-19f9cbfaff53`, deployment `9f070d4a-1df1-42fe-a33e-6cdb67d96503`): migrations 005/006, login provisioning, privilege checks, and live calibration (see `DATABASE_CHANGELOG.md`).
  - `orc-acceptance-job` (`5931c9ca-b88e-40c5-8c55-60b55eb64563`, deployment `f01d48e9-8eb8-43f5-9399-edadcd14254b`): live acceptance tests over the private network.
- **Deployments:**
  - Governor `d8ae37a4-1321-4e89-8138-6abcfec4f850` (commit `0b0ba24`): `SUCCESS`, `/ready` returned `200`.
  - market-ai-orc `44e44fdf-330b-4fb0-b6f5-83e4fde81c10` (commit `0b0ba24`; the app code is identical to `f63bebc`): `SUCCESS`, `/ready` returned `200`.
  - Rollback references: market-ai-orc `b33d1736-1229-4ca1-b796-569b9df0a6f2`, or unset `SQL_GOVERNOR_URL` to unregister `request_data`.
- **Live acceptance** (real OpenRouter model, real data):
  1. "Ambil 20 latest daily close BBCA." → `COMPLETED`/`ANSWER` in 23 s with 4 tool calls. The Governor returned `INLINE_RESULT` (estimated scan 2,282 rows, 20 rows, 93 ms), and the answer lists the 20 real closes (2026-09-22 back to 2026-08-21).
  2. "Ambil historical price universe IDX … rolling correlation." → `COMPLETED` in 65 s.
     - The full-history request got `NEEDS_NARROWING`/`DATE_RANGE_TOO_LARGE` (3,186 days, limit 400 without a ticker filter).
     - The model revised the request and got `DATASET_READY`: 214,023 rows × 3 columns, 844 entities, `COMPLETE`, 530 KB Parquet in `market-sql-datasets`.
     - Its limitations state that rolling correlation was not calculated because no analysis tool exists.
  - Direct Governor checks: no bearer key returned `401`; an F02 × F03 join returned `REJECTED`/`PREAGGREGATION_REQUIRED`; a spec with a `sql` field returned `REJECTED`/`INVALID_REQUEST_SPEC`.
  - Governor logs carry the orc run `request_id` (for example `live-acceptance-1`).
- Ran `railway config pull --force`. `.railway/railway.ts` now includes the bucket, the service, and all preserved variables, and the follow-up plan reported `dev` up to date. No other service, domain, schedule, or source was changed.

## 2026-09-23 — market-ai-orc: AI_MAX_TOOL_ITERATIONS = 20

- At the user's request, set `AI_MAX_TOOL_ITERATIONS=20` on `market-ai-orc`. The code default is 8.
- Railway redeployed the same image as `b33d1736-1229-4ca1-b796-569b9df0a6f2`, which reached `SUCCESS` with a clean start and `GET /ready` `200`.
- `AI_MAX_TOOL_CALLS` stays at its default of 12, so a page-by-page catalog read now ends through the graceful paths instead of `MAX_ITERATIONS`: the tool-call budget (`TOOL_CALL_BUDGET`) or the context soft limit (`CONTEXT_BUDGET`), whichever comes first.
- Ran `railway config pull --force`. `.railway/railway.ts` now preserves `AI_MAX_TOOL_ITERATIONS`, and the plan reported `dev` up to date.

## 2026-09-23 — Deploy market-ai-orc context budget and 16 KB catalog pages (c1b4e93)

- **Deployment:**
  - What changed:
    - Soft context limit `AI_CONTEXT_SOFT_LIMIT_RATIO` (default `0.8`): tools are withdrawn and the run finalizes with `LIMITATION` instead of failing.
    - New execution field `execution.tools_withdrawn_reason`.
    - Code default of `CATALOG_PAGE_MAX_BYTES` changed from 32000 to 16000.
  - No Railway variable was added or changed, so both new defaults apply.
  - Upload method: the same watch-path-compatible staging upload as before.
  - Deployment `4d2a7665-696f-4f5f-b9fc-8df6a35db7b0` reached `SUCCESS`, with a clean Uvicorn start and `GET /ready` returning `200`.
  - Rollback reference: `2d6c60ca-4b44-4473-a2de-8e6482075d92`.
- **Temporary one-off service `orc-db-update`** (`b7efbd14-a030-4540-8880-f39485cea5a9`):
  - It had only reference variables (`${{Postgres.DATABASE_URL}}` and `${{market-ai-orc.MARKET_AI_ORC_API_KEY}}`) and restart policy `NEVER`, and ran as deployment `fc6e2821-4fe4-480d-b426-51945a29468d`.
  - It applied migration 004 and ran two live smoke tests. It was deleted afterwards.
  - `railway config plan` reported `dev` up to date.
- **Smoke test 1: regression** (broker accumulation question).
  - Result: `COMPLETED`/`ANSWER` in 48 s, 5 model calls, 9 tool calls, `tools_withdrawn_reason = null`.
  - Behavior is unchanged from the Phase 2+3 run.
- **Smoke test 2: stress** ("read the complete `AI_calculation_catalog`, every page").
  - Result: `FAILED` with `MAX_ITERATIONS` after 8 model calls, each reading one page.
  - Provider-reported input per call grew about 5k tokens per 16 KB page, from 2.0k to 37.3k. That is below the 51.2k soft limit, so `AI_MAX_TOOL_ITERATIONS = 8` ended the run before the context budget applied.
  - This is not a regression. With 32 KB pages the same request would have hit `CONTEXT_LIMIT` after about four pages. But the iteration cap still fails hard instead of degrading. This is recorded as an open follow-up, not changed in this deployment.

## 2026-09-23 — Deploy market-ai-orc Phase 2+3 (catalog discovery, full catalog access, 20-row preview)

- **Variables on `market-ai-orc`**, both set with `--skip-deploys`:
  - `MARKET_AI_ORC_DB_PASSWORD`: a new random 48-character secret, set through stdin and never printed.
  - `CATALOG_DATABASE_URL`: a reference template, `postgresql://market_ai_orc:${{MARKET_AI_ORC_DB_PASSWORD}}@${{Postgres.RAILWAY_PRIVATE_DOMAIN}}:5432/${{Postgres.PGDATABASE}}`. It resolves to the private host `postgres.railway.internal`.
  - No other variable changed.
- **Deployment:**
  - Deployed commit `456081d` (Phase 2+3 only; the later context-budget change is not deployed).
  - Upload `98ec3d4f-8009-43d3-8fd7-8827f54c0ffd` was `SKIPPED` ("No changes to watched files"): the service watch path `/apps/market-ai-orc/**` also applies to CLI uploads, and a `--path-as-root` upload of `apps/market-ai-orc` places files at `app/...`.
  - The code was then uploaded with its repository layout under `apps/market-ai-orc/`, plus a root wrapper Dockerfile that builds the same image as `apps/market-ai-orc/Dockerfile`.
  - Deployment `2d6c60ca-4b44-4473-a2de-8e6482075d92` reached `SUCCESS`. Uvicorn started cleanly and `GET /ready` returned `200`.
- **Temporary one-off service `orc-db-setup`** (`a916cd58-4b22-4e45-bbd9-d57e330b57b1`):
  - Created with only reference variables (`${{Postgres.DATABASE_URL}}` and three `${{market-ai-orc.*}}` references) and restart policy `NEVER`. It ran once as deployment `11b4d8ad-c908-49eb-a9f9-174a3248ce04`.
  - It applied the three database migrations, provisioned `market_ai_orc`, and ran the live verification, privilege checks, and `EXPLAIN` evidence (see `DATABASE_CHANGELOG.md`).
  - It then smoke-tested the deployed service over the private network and finished with `SETUP COMPLETE`.
  - It was deleted afterwards; the service list confirms it is gone.
- **Live smoke test** ("Explain which tables and calculations are available for analyzing broker accumulation, and show me example records."):
  - Result: `COMPLETED`/`ANSWER` in 24 s, 5 model calls, and 9 real tool calls (`get_system_capabilities`, `discover_catalog`, 3 × `get_catalog_details`, 4 × `preview_table_rows`).
  - Tokens: 63.8k in total, with a peak single-call input of about 22k.
  - The limitations correctly stated that no SQL or Python analysis ran, that the previews are example rows, and that Feature 02/03 are `UNVERIFIED`/`MANUAL_REFRESH_REQUIRED`.
- Ran `railway config pull --force`. `.railway/railway.ts` now preserves `CATALOG_DATABASE_URL` and `MARKET_AI_ORC_DB_PASSWORD`, and the follow-up `railway config plan` reported `dev` up to date. No other service, domain, schedule, or source was changed.
- **Rollback:** redeploy `60f622a5-eed1-4077-8b5b-cb0c0c2faf57` (Phase 1). The catalog tools are registered only when `CATALOG_DATABASE_URL` is set.

## 2026-09-23 — Deploy market-ai-orc Phase 1 orchestrator

- Created only `market-ai-orc` (service ID `41dc17ee-3bac-41ef-90ec-8b9356815c71`) in Railway `dev`. The user-approved pinned IaC plan (`sha256:f1547b72…`) was exactly one safe create, zero changes, zero destroys.
- Configuration: region `sfo`, one replica, Dockerfile build, start command `uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8080`, health check `/ready` (120 s), restart `ALWAYS`. It is private: no public domain. Other services reach it at `market-ai-orc.railway.internal:8080`.
- There is no GitHub source yet; the code was uploaded from `apps/market-ai-orc` at commit `1a857f9`. Connect GitHub `main` at root `/apps/market-ai-orc` with watch path `/apps/market-ai-orc/**` in a separate approved change.
- Variables: `PORT`, `AI_MODEL=deepseek/deepseek-v4.1-flash`, and `AI_REASONING_EFFORT=high` are literals. `OPENROUTER_API_KEY` is a Railway reference to `${{market-ai-backend.OPENROUTER_DEEPSEEK}}`, so the existing OpenRouter key is reused without copying it; a hash comparison confirmed the resolved value matches. `MARKET_AI_ORC_API_KEY` is a new random 64-character bearer secret, set through stdin. No secret value was printed or committed.
- Deployment `60f622a5-eed1-4077-8b5b-cb0c0c2faf57` reached `SUCCESS`. The logs show a clean Uvicorn start, and Railway's `GET /ready` health check returned `200`.
- Before deployment, the same code passed three local live acceptance runs against OpenRouter with the existing key. Each run was `COMPLETED`/`ANSWER` with one real `get_system_capabilities` call, reported database, Python, and web search as unavailable, and used about 2.9–3.0k tokens.
- Two OpenRouter incompatibilities were found live and fixed in code (details in `apps/market-ai-orc/README.md`):
  - No DeepSeek V4.1 Flash endpoint supports `parallel_tool_calls`, which caused a 404 under `require_parameters`.
  - A strict `text.format` sent in the same turn as tools prevented any tool call.
- Pulled the live Railway configuration into `.railway/railway.ts`; the follow-up plan reported `dev` already up to date. No existing service, variable, database, domain, schedule, or data was changed.

## 2026-09-23 — Deploy AI data coverage cron

- Created only `ai-data-coverage` (service ID `d2e57c12-cebf-4434-a66a-ba2d6d2f176d`) in Railway `dev`; the reviewed IaC plan was exactly one add, zero changes, and zero destroys.
- Connected GitHub `rednightt33/saniti` branch `main` at root `/apps/ai-data-coverage`, Dockerfile build, start command `python coverage_job.py --mode nightly`, `NEVER` restart policy, and schedule `30 0 * * *` UTC (07:30 Asia/Jakarta). `DATABASE_URL` is present as the existing Postgres service reference; no credential value was printed or committed.
- Initial deployment `31aab1e5-4baa-43b8-b770-1b8183d717b2` built commit `7d8f29513e5f2f07a365ab6829f6e33a68ca7f30` and reached `SUCCESS`.
- A manual local full run and nightly-mode run both succeeded against Railway PostgreSQL before deployment. The job writes only `AI_data_coverage` and does not scan or modify Feature 01–03.
- Pulled the live Railway configuration into `.railway/railway.ts`; the follow-up plan reported the `dev` environment already up to date. No existing service, schedule, endpoint, volume, secret value, raw row, or Feature row was changed.

## 2026-09-14 — Three-path Market AI execution architecture

- Added service `market-query-sandbox` (`c6bf3085-4784-43f3-90a1-da74456f6c4d`) for isolated custom joins, windows, and descriptive transformations.
- Re-scoped `market-analytics-worker` (`75fc5bbc-2ff9-4850-b007-011735506ce6`) as the statistical validation worker.
- Configured distinct sealed worker credentials and separate query-sandbox/statistical row, byte, estimated-scan, ticker, date-range, runtime, memory, and output limits on `market-ai-backend`.
- Neither worker receives `DATABASE_URL` or private bucket credentials; each can claim only its own `Analytics_Job.execution_class` through a separate backend endpoint.
- Backend deployment `e69b3c4f-5c9d-47b9-a8d0-a9c04c9b763d` reached `SUCCESS` after correcting the local monorepo upload scope. Initial worker local-upload builds failed because Railway treated the repository root as a Node application; no running worker was replaced by those failed builds.
- Final worker deployment IDs and end-to-end acceptance results are recorded below after the configuration-managed GitHub deployments complete.

This file records intentional changes to the Railway project. Git history preserves every revision. Never include secret values.

## 2026-09-14 — Provision private generic analytics handoff

- Created private Railway bucket `market-analytics-input` in `sin` and service `market-analytics-worker`. Bucket credentials are configured only on `market-ai-backend`; the worker receives only a separate internal worker token and the backend private URL.
- Added independent, configurable analytics limits without changing interactive query or LLM token limits: 50,000 rows, 30 columns, four datasets, 20 MiB input, 2,000,000 estimated rows, 120 seconds, 2 GiB, 500 result rows, 256 KiB result, 24-hour maximum snapshot retention, one-hour terminal grace, and 90-day compact-result retention.
- Added `AI_MAX_DISCOVERY_CALLS=4` plus a compact per-request analytics handoff. It tells the model when to use ordinary queries versus the generic worker, how to prefilter/select columns, how QC and anomalies behave, how idempotent job labels work, and when to stop. Repeated exact catalog discovery uses the session cache and `list_tools` no longer dumps inactive/deferred capabilities.
- Local integration used the real Railway PostgreSQL and private bucket with a local copy of both services. The known workstation CA issue required explicit `AWS_CA_BUNDLE` for Boto3; TLS verification remained enabled. Final worker Golden Test passed and verified the no-database-credentials boundary.

## 2026-09-14 — Harden analyst finalization and complete compaction A/B

- Deployed the priority 1–6 hardening sequence through commits `e9fda44`, `37d7be8`, `c744c6f`, `9a84c82`, and `88a5514`. The backend now reserves finalization budget, requires tool use before evidence, locks data tools after sufficient evidence, requires `complete_analysis`, validates evidence-ready dates, records exact bounded final-output failures, and stores a decisive audit digest. Priority 7 remained intentionally deferred.
- Raised only `AI_MAX_CUMULATIVE_INPUT_TOKENS` to 150,000 and added the configurable A/B switch plus two finalization reserves and two bounded final-response retries. Database-query, LLM-facing result, Analytics Worker, 64k active-context, cumulative-output, provider-call, and wall-clock policies remain separate.
- Canary request `e8835b86-e4ad-4dcb-bba2-81212c8b88d8` finished `SUCCESS`/`FINAL` after the final evidence-date fix: 16,553 input tokens, 2,178 output tokens, 4 tool calls, 5 iterations, and 5,823 peak active-context tokens.
- Ran the same fixed ten-question DeepSeek suite with cross-iteration compaction disabled and with `PRESERVE_DECISIVE`. Disabled completed 7/10 using 902,667 input tokens and 996.363 seconds total; preserve completed 8/10 using 857,164 input tokens and 573.907 seconds. All 15 successful answers had durable, correctly cited evidence and both modes made zero data/QC calls after the evidence gate.
- Only two preserve-mode requests actually compacted. S5 still failed after exceeding the 150k cumulative-input ceiling, and F4 lost explicitly requested numeric columns that the non-compacted answer retained. The apparently additional S2 success did not use compaction and reflects provider-output variance. Strict answer review was six complete/one partial/three failed for disabled versus five complete/three partial/two failed for preserve.
- Restored `AI_CONTEXT_COMPACTION_MODE=DISABLED` as the current `dev` setting. Deployment `e962dc56-8c02-4f22-a943-e4a2a1d1c332` reached `SUCCESS` on runtime commit `88a5514`; documentation commit `9eb55e6` then deployed as `945dad67-b1e9-410d-bcbf-26a40ee3215a` and also reached `SUCCESS`. Per-tool result shaping remains enabled; only cross-iteration compaction is disabled.
- All 180 A/B provider calls stored bounded reasoning details, concise decision summaries, usage, and 30-day expiry in `Analysis_Model_Call`. Unit tests passed 58/58, live backend verification passed, and deterministic Golden Test run `801f4f11-5d8a-4774-9fa6-58bf60f68f47` passed 16/16. Full results and unresolved gaps are in `MARKET_AI_AB_TEST_2026-09-14.md`.
- The first local Railway read hit the known Avast TLS `UnknownIssuer`; setting `SSL_CERT_FILE` to the verified CA bundle restored the connection without disabling TLS validation. No secret, provider/model, database/Feature value, schedule, volume, endpoint, or unrelated service was changed.

## 2026-09-14 — Deploy per-model-call audit and global conditional QC

- Added five non-secret `market-ai-backend` variables without exposing their values as secrets: `AI_CUMULATIVE_COMPACTION_THRESHOLD_PERCENT`, `AI_STORE_REASONING_DETAILS`, `AI_REASONING_RETENTION_DAYS`, `AI_REASONING_MAX_BYTES_PER_CALL`, and `AI_REASONING_CLEANUP_INTERVAL_SECONDS`. Database/query, Analytics Worker, 64k active-context, 100k cumulative-input, 12k cumulative-output, 32-call, and 20-iteration ceilings were not increased.
- Git commit `fe8cb06` deployed as `97f4892d-ff28-4d47-85f4-eaf18f9a9f7b` and reached `SUCCESS`; startup completed and private `/health` returned HTTP 200. It added per-provider-call audit, 75%-cumulative-input semantic compaction, bounded reasoning retention, and global conditional/scoped QC behavior.
- First post-deploy streak smoke `56cf2a0c-76f0-483c-9e84-ff7e2780227d` completed seven successful data tools but failed at iteration 5 because DeepSeek returned truncated `record_evidence` JSON. The database and query results were valid. Audit rows captured per-call usage/reasoning without storing credentials.
- Commit `baadbff` made malformed provider tool arguments recoverable and stored only argument length/SHA-256 in failed-step audit, not partial content. Deployment `4d49e4a1-afdd-4abb-b92b-974edc63eb09` reached `SUCCESS`; startup and private `/health` HTTP 200 passed.
- Identical rerun `9ad62d13-cc26-492c-8f3a-769d9d4e3741` completed `SUCCESS`/`FINAL` in 8 iterations and 9 tool calls with 68,273 input tokens, 4,166 output tokens, 72,439 combined tokens, and 15,688 peak active-context tokens. It created exactly eight retry-safe `Analysis_Model_Call` rows; per-call reasoning formats/token usage/tool-family stages and 30-day expiry were populated where the provider supplied them. No broad 2015–2026 QC scan ran.
- Live backend verification PASS, Feature Catalog semantic audit PASS at 91/91 calculation-verified definitions, and deterministic Golden Test run `5d2a8f03-58af-4807-ae8e-7dc4ab5f1491` passed 16/16. Local application tests passed 41/41.
- After `config pull --force`, the first IaC plan repeated the known false CLI-version failure because Node resolved PowerShell `_` rather than the verified CLI. Setting `_` to the actual Railway 5.54.1 executable made `config plan` report `dev` fully up to date. No certificate verification was disabled.
- No secret value, provider/model, Feature value/formula, Feature 2 v2 activation, schedule, volume, endpoint, or unrelated Railway service changed.

## 2026-09-14 — Deploy generic condition-run screening and compact semantic preflight

- Added only two non-secret `market-ai-backend` limits: `CONDITION_RUNS_MAX_DATE_RANGE_DAYS=7305` and `CONDITION_RUNS_MAX_EPISODES=200`. Existing ticker, estimated-row, timeout, backend-byte, LLM-result, cumulative-token, and context limits remain independent and unchanged.
- Git commit `4843c4e` deployed as `3fdef450-76c3-4685-b741-b5baf732c96c` and reached `SUCCESS`. The new generic `find_condition_runs` tool evaluates catalog-approved AND conditions over consecutive per-ticker trading observations and returns compact episodes; it does not accept model-written SQL or require Analytics Worker/raw-table access.
- The first identical DeepSeek streak smoke `edf80a9f-91f2-4078-b432-5db4bc3195c4` found the correct BBCA episodes but reached the unchanged 100,000 cumulative-input gate before finalization (101,627 input tokens, 4,702 output tokens, 14 calls, 9 iterations). Audit identified redundant semantic preflight and an over-broad quality request; no token or query limit was increased.
- Git commit `0ce0abe` deployed as `8231132b-974c-49fb-a48b-022ad68f31c7` and reached `SUCCESS`. Data handlers now auto-load compact semantics for only referenced catalog columns; complete definition retrieval remains available for detailed methodology, while missing/inactive catalog entries still reject execution.
- The exact rerun `2d7f8adf-5119-4a60-9ac4-c1b789497ff5` finished `SUCCESS`/`FINAL`: 11 tool calls, 9 iterations, 85,591 cumulative input tokens, 4,129 output tokens, 89,720 combined tokens, and 18,476 peak active-context tokens. It stored evidence `438daac1-8e52-4207-8a88-25130dc7dfb8` and reported the two qualifying BBCA positive-return runs at 2019-05-23 through 2019-06-11 (8 observations) and 2023-04-06 through 2023-04-26 (9 observations).
- Local tests passed 33/33; deterministic golden run `4ff14bf3-8c5e-4248-b506-08af06b65dec` passed 16/16; live catalog audit remained 91/91 calculation-verified definitions with zero incomplete rows. Both deployments completed startup and returned private `/health` HTTP 200.
- Final linked-context `railway config plan` reported the `dev` environment already up to date. The first read-only attempt hit the workstation's known TLS `UnknownIssuer`; retrying with the verified local CA bundle succeeded without disabling certificate validation or changing Railway state.
- No secret value, provider/model, raw/Feature value, calculation worker, schedule, public endpoint, volume, or unrelated Railway service changed.

## 2026-09-14 — Enable bounded INSIGHT stopping policy

- Added non-secret `market-ai-backend` configuration `AI_ANALYSIS_MODE=INSIGHT`, `AI_MIN_INSIGHT_DATA_CALLS=2`, and `AI_MAX_ANALYSIS_SECONDS=600`. The 32-tool-call, 20-iteration, 100,000 cumulative-input, 12,000 cumulative-output, 64,000 hard-context, and independent query limits were not increased.
- Git commit `d3f0e53` deployed as `353675ba-ecfc-4065-aa5f-52dbb9259d9c` and reached `SUCCESS`. It separated durable `record_evidence` calls from new `complete_analysis` finalization and enforced two distinct successful analytical query hashes for data/screening questions in INSIGHT mode.
- First INSIGHT smoke `a2118f3d-344a-4838-8816-ebb949123541` correctly continued past its first observation, but accumulated 102,812 input tokens across 15 tool calls before completion because it attempted extra Feature definitions, retried invalid calls, and wrote three separate evidence rows. It failed at the unchanged 100,000-input hard gate; no limit was raised.
- Git commit `ffa8b10` deployed as `72e25310-328b-4d75-9b15-459864151cec` and reached `SUCCESS`. Direct ticker retrieval now omits Screening schemas until required, evidence is normally consolidated, and a successful evidence result tells the model whether the distinct-query stopping condition has been met.
- Exact smoke rerun `19b5ef94-a6c3-4cb8-8396-aad7414f2a08` finished `SUCCESS`/`FINAL`: 12 tool calls, 11 iterations, 98,681 cumulative input tokens, 4,183 output tokens, 102,864 combined tokens, and 18,174 peak active-context tokens. It ran two distinct analytical queries, consolidated one evidence item, passed `complete_analysis`, and automatically compared BBCA with large-bank peers after the initial direct result. The final answer reported 2026-08-31 as the common Feature 1–3 date, BBCA close 6,475 and 20-trading-day return +0.39%, a source-valid elevated-volume anomaly, and no predictive claim.
- Git commit `b3b7b18` added the independent 600-second whole-analysis circuit breaker and deployed as `c94b5423-a1dc-4006-b0b4-97c5caf03b0c`; deployment, startup, and `/health` 200 all passed. The 180-second provider timeout remains per call. Local tests passed 30/30; live catalog/backend verification and deterministic golden acceptance passed.
- The local smoke harness initially stopped waiting at 240 seconds while its Railway request was still healthy and later completed successfully. Its default wait is now 720 seconds, longer than the 600-second orchestration budget, so harness timeout is no longer misreported as an application failure.
- Final `railway config pull --force` and `railway config plan` reported `dev` already up to date. No secret, provider/model, database/Feature value, schedule, volume, endpoint, or unrelated service changed.

## 2026-09-14 — Enable advanced orchestration limits and verify four-bank insight

- Increased only the per-analysis orchestration circuit breakers on `market-ai-backend`: `AI_MAX_TOOL_CALLS` from 12 to 32 and `AI_MAX_TOOL_ITERATIONS` from 8 to 20. Deployment `87d3e4dd-ceda-4efb-9710-3e08110b10fe` reached `SUCCESS`. This does not activate the deferred ADVANCED/Analytics Worker tools; the separate 100,000 cumulative-input, 12,000 cumulative-output, 64,000 hard-context, database query, and timeout limits remain unchanged.
- First advanced-profile request `b24fd791-4536-4cac-a76c-b776e397e038` completed discovery, quality validation, semantic preflight, and the four-bank query, but OpenRouter/DeepSeek omitted required `record_evidence.evidence_type`. The handler's direct key access raised fatal `KeyError`; the requested market values were not published as a completed answer.
- Added backend validation so missing/invalid evidence fields produce a recoverable tool error before database access. Migration `database/migrations/20260914_030_validate_evidence_requests_in_backend.sql` records that runtime contract. Git commit `bf6f8b8` deployed as `6d209137-0ed8-4b1a-ab6e-b8d64194875b` and reached `SUCCESS`; unit tests passed 25/25.
- Exact-question rerun `87b682d6-2092-453b-ba00-d71dab1f8f6d` finished `SUCCESS`/`FINAL` with 9 tool calls, 10 iterations, 81,280 input tokens, 3,989 output tokens, 85,269 total tokens, and 13,697 peak active-context tokens. It stayed below every cumulative/context limit, cited one same-request evidence row, stored version/methodology snapshots, and identified BBCA and BBNI as descriptive price-volume divergence candidates on 2026-09-11 without making predictive claims.
- Final `railway config plan` reported the `dev` environment already up to date. No database row/query limits, raw or Feature values, model/provider, secret, schedule, volume, endpoint, or other Railway service was changed.

## 2026-09-14 — Complete OpenRouter DeepSeek end-to-end acceptance

- Deployed the approved OpenRouter/provider and Feature-semantic hardening sequence only to `market-ai-backend`: `234e3181-be5e-4a6c-be50-84d70ca2da0f` (`b8d9b10`), `dc857d94-fa52-4820-84bf-256384324d1d` (`ae87d89`), `e515a45c-e6ee-41b0-a432-6c9d19b07f10` (`538a8de`), `1198728d-aa9b-4a32-b8e3-0574007448b2` (`6e0d236`), `533ee5c0-6f3d-4a0a-8803-bfa8f302ad73` (`5a5d61a`), `c0e0279b-ee78-4ac9-b9e2-4c002379ec0c` (`1f03cfc`), and final `937d5add-76a6-48a7-94c2-4c507897def7` (`0017a40`). Every listed deployment reached `SUCCESS`.
- Preserved the strict parser after smoke `fc4d2245-ed78-46af-87a6-7987e95b8e81` returned a Markdown-wrapped final; only bare JSON or one exact JSON fence is accepted and Pydantic validates the complete final contract.
- Preserved the 12-call limit after smoke `6a8ba0d7-3154-450b-bed4-832bb38b4360` exhausted it. Exact table identifiers, whitespace-keyword OR discovery, and non-duplicated validation/estimation reduced redundant calls. A transient workstation outage then blocked GitHub/Railway HTTPS; per-command OpenSSL plus the trusted local CA restored Git push without printing the PAT.
- Smoke `5d974b45-d034-4df3-abbc-a15ccbaa5687` exposed two additional issues: verbose discovery output hid relevant identifiers during compaction, and a 69-character premature final failed the schema. Discovery now preserves compact candidate identifiers, complete selected-column semantics still come from `get_feature_definition`, malformed finals receive bounded corrective feedback, and final evidence IDs must exist for the current request.
- Smoke `95165771-09b7-482f-8583-34d7c80d24a8` proved a direct one-ticker/one-date request could not fit a redundant progressive-family expansion and estimate inside eight iterations. Direct retrieval now begins with Query/Screening, bounded `query_features` performs its own enforcement, and ADVANCED is not exposed for ordinary retrieval. Neither the 8-iteration nor 12-call limit was raised.
- Smoke `a31ac1d7-cb6e-4b59-a353-58e4f4875eac` successfully reached `query_features` but showed `record_evidence` was unreachable because its AUDIT family was neither core nor requestable. Only `record_evidence` is now always exposed; `get_analysis_history` remains non-core.
- Smoke `cbc44cb6-541f-448f-9914-8b4d01d2572a` successfully queried BBCA and created two evidence rows but used its final iteration looking for a nonexistent final-answer tool. Recording evidence now explicitly transitions the following model call to strict finalization without data-tool schemas.
- Final durable smoke `fb599cc3-7853-4d7c-b710-4bfd153823ee` finished `SUCCESS`/`FINAL` through the deployed Railway worker using `openrouter` and `deepseek/deepseek-v4.1-flash`: 8 tool calls, 6 iterations, 39,562 input tokens, 2,208 output tokens, 41,770 total tokens, and 12,529 peak active-context tokens. The answer used the common safe date `2026-08-31`, cited an evidence ID actually stored for that request, retained point-in-time/survivorship and source-valid-anomaly warnings, and stored both version and methodology snapshots.
- Post-deploy checks PASS: 24 backend unit tests; deterministic golden run `c16b20e2-1c49-4088-8eb2-4328471d61e1` at 15/15; 91/91 calculation-verified Feature definitions with zero semantic gaps; exact Feature 1–3 catalog/physical coverage; identifier-preserving discovery; `record_evidence` always exposed; history not core; raw-column rejection; and live `Nego`/`Regular`/`Tunai` aggregation. Final `railway config plan` reported the `dev` environment already up to date. No secret value, raw/Feature value, schedule, volume, endpoint, or other Railway service was changed.

## 2026-09-14 — Configure OpenRouter DeepSeek for market AI

- Confirmed the project-owner-supplied `OPENROUTER_DEEPSEEK` secret exists on `market-ai-backend`; its value was never printed or committed.
- Bounded live provider probes passed for both strict function calling and strict final structured output using `deepseek/deepseek-v4.1-flash`. Usage accounting was returned by the provider.
- Set only four non-secret `market-ai-backend` variables with deployment initially suppressed: `AI_PROVIDER=openrouter`, `AI_MODEL=deepseek/deepseek-v4.1-flash`, `AI_REASONING_EFFORT=high`, and `AI_MAX_FEATURE_METADATA_TOKENS=5000`. The existing OpenAI secret remains available for an explicit future provider switch; there is no silent fallback.
- Updated `.railway/railway.ts` to preserve the generic provider variables and `OPENROUTER_DEEPSEEK`. Railway config plan reported no infrastructure drift; no other service, schedule, volume, endpoint, or variable was changed.

## 2026-09-13 — Deploy private market AI backend and isolate OpenAI quota blocker

- Created private service `market-ai-backend` (service ID `2cefa0cd-c9fc-4b84-992e-fdf08535a064`) in project `lucid-patience`, environment `dev`. It has one `sfo` replica and no public domain.
- Set a least-privilege `DATABASE_URL`, generated `MARKET_AI_INTERNAL_API_KEY`, and all approved database-query, LLM-result, context, cumulative-token, model, timeout, and worker-lease variables. Values of the secrets were never printed or committed. The project owner subsequently added `OPENAI_API_KEY` directly as a Railway secret.
- Initially left the GitHub source disconnected so no knowingly failing deployment was created before the OpenAI credential existed. After the credential was confirmed, the exact planned source/build/deploy diff was limited to this service: GitHub `rednightt33/saniti`, root/watch path `/apps/market-ai-backend`, Dockerfile, private `/health`, `ALWAYS` restart, and the uvicorn start command.
- Pulled the live state into `.railway/railway.ts`. The first `config plan` invocation failed because the IaC SDK resolved PowerShell's `_` process variable instead of the Railway CLI binary; setting `_` to the verified Railway CLI 5.54.1 executable fixed evaluation, and the resulting plan reported no drift.
- Connected GitHub `rednightt33/saniti` branch `main`, applied the reviewed zero-add/three-change/zero-destroy service-only plan, and verified initial deployment `db143fa6-3eff-4cf3-9ebe-c1d56d53b171` reached `SUCCESS`. Runtime logs showed application startup and Railway `GET /health` HTTP 200.
- Local SSH inspection was unavailable because the workstation has no Railway SSH key. A durable smoke request was therefore inserted through the least-privilege public database proxy and was claimed by the running Railway worker, proving the queue-to-worker path.
- Smoke request `6a5df01f-e4c5-4296-b2a0-c4bdd5d5a756` stopped before any tool call because OpenAI returned HTTP 429 with `insufficient_quota` / `credit_balance_exhausted`. The service, key presence, database access, worker lease, and request lifecycle were operational; paid OpenAI API credits are the remaining external end-to-end gate.
- Updated the transport to report safe OpenAI error type/code/message plus request ID and to avoid retrying non-transient quota exhaustion. Transient 429 responses retain bounded retry behavior.
- Deployed that diagnostic patch from Git commit `e270c1bbeeaecbff74b184eeed09f37df32cf757` as `8bbb044a-b8bf-49f9-b4ab-b85d234ec1a5`; it reached `SUCCESS`, completed startup, and passed `/health` with HTTP 200. Post-deploy smoke request `07ea98c7-d940-4f50-8ae3-6c3cf5db70e3` recorded the exact quota codes with zero model input/output tokens and zero tool calls, confirming immediate safe failure instead of wasteful retries.
- No existing Railway service, schedule, source, network endpoint, volume, raw/Feature value, or Feature automation was changed.

## 2026-09-13 — Activate always-on Feature 01 calculation worker

- Created `feature-01-worker` (service ID `de4e34ee-435b-408f-a77f-63e6698a2dab`) in project `lucid-patience`, environment `dev`. It deploys `rednightt33/saniti` branch `main` from `/apps/feature-01-worker`, with matching watch path, Dockerfile build, `python worker.py`, one `sfo` replica, `ALWAYS` restart, and no cron schedule or public domain.
- Set only `DATABASE_URL` as a Railway reference to the existing `Postgres` service; no credential value was copied to GitHub. Price cron services, schedules, source, variables, and TradingView behavior were unchanged.
- Initial deployment `5465b07b-5919-4dc1-a513-871ba7ca4ad2` of Git commit `6c1ee21d202641eaf545882892e349a2f0795f06` reached `SUCCESS`. Runtime logs showed `worker_started`, then `claim_started` and `calculation_completed` for a committed metadata-only BBCA 2026-09-11 re-ingestion.
- Live database read-back: the reopened BBCA queue key returned to `DONE` with `source_attempt_count=1`; `Feature_Status` was `SUCCESS` with zero outstanding items; `Feature_Calculation_Log` recorded `SUCCESS` and one refreshed Feature row. The queue had two `DONE` items, one ticker `SUCCESS`, and no pending/processing/failed item at verification. No OHLCV value was changed by the test.
- Pulled the live Railway configuration into `.railway/railway.ts`; `railway config plan` reported no drift. The pull also captured the pre-existing `DB2` and `db-ops-runner` resources, which were not modified.

## 2026-09-13 — Record database-side price ingestion timestamps

- Updated the shared `apps/idx-price-cron` bulk upsert so `idx-price-cron` and `idx-price-recovery-cron` assign `Price_Stock_Indonesia_IDX.ingestion_time` from PostgreSQL `statement_timestamp()` on both insert and `(ticker, date)` conflict update.
- Deployed Git commit `a988a0e2fc37d1ba58db70e365f1d63be98bc9fa` to DAILY as deployment `ae37f76e-caa2-4397-b93d-c5e588d95fe4` and RECOVERY as deployment `08c05d86-fc2b-44d1-9a9a-d4e2ea7fb74e`; both reached `SUCCESS`.
- Preserved the preceding successful deployments as rollback references: DAILY `3b73e6c5-a60e-459b-ac1b-314c362cf3e9` and RECOVERY `65de3099-051e-45a7-81b2-b135f3bcced4`.
- Kept both cron schedules, start commands, service variables and secrets, watch paths, restart policies, monitoring flow, and Telegram behavior unchanged.
- No **Run now** action or TradingView query was issued during deployment.

## 2026-09-09 — Connect application services to GitHub monorepo

- Connected all four application services to `rednightt33/saniti` on branch `main`, one service at a time, and waited for each resulting deployment to reach `SUCCESS` before continuing.
- Set `idx-price-cron` and `idx-price-recovery-cron` to root `/apps/idx-price-cron` with watch path `/apps/idx-price-cron/**`; their successful source deployments are `3b73e6c5-a60e-459b-ac1b-314c362cf3e9` and `65de3099-051e-45a7-81b2-b135f3bcced4`.
- Set `telegram-monitor` to root `/apps/telegram-monitor` with watch path `/apps/telegram-monitor/**`; deployment `9c25be22-9fba-48fc-81a3-1a1b555dd59d` reached `SUCCESS` after Railway passed its `/health` check.
- Set `telegram-trigger` to root `/apps/telegram-trigger` with watch path `/apps/telegram-trigger/**`; deployment `f5bf0056-460f-437f-b2bd-4d0a8334e73d` reached `SUCCESS`, Railway passed its `/health` check, and the public health endpoint returned HTTP 200 with status `ok`.
- Saved the preceding active deployments as rollback references: DAILY `db51a5fe-b845-44c3-abcc-5a91a3883bba`, RECOVERY `1c3e79af-19aa-4482-906a-bab7584c51c4`, monitor `c03b134b-0879-4e58-aca5-add943f74afa`, and trigger `3e8fd2fe-1cb6-47e7-9233-209bf259d404`.
- Preserved all environment-variable and secret keys, cron schedules, start commands, health checks, domain, private networking, restart/serverless settings, and PostgreSQL configuration. No **Run now** action or TradingView query was issued.
- Pulled the resulting live configuration into `.railway/railway.ts`.

## 2026-09-09 — Show IDX job start and finish times in Telegram

- Extended `telegram-monitor` messages with separate `Triggered at` and `Finished at` timestamps in Asia/Jakarta, sourced from `Monitoring_Price_ALL.run_time` and `finished_at`.
- Kept the existing headline, duration, missing-ticker list, delivery ledger, DAILY/RECOVERY schedules, and trigger flow unchanged.
- Added regression coverage for UTC-to-WIB conversion and verified the formatter against a live monitoring row without sending a duplicate Telegram message.
- The first upload attempt (`aa896904-a563-48b1-8b0c-fa77ca712092`) failed before Railway could create its code snapshot; the previous deployment remained active.
- Retried once and verified deployment `c03b134b-0879-4e58-aca5-add943f74afa` reached `SUCCESS`.

## 2026-09-09 — Telegram controls for manual IDX price runs

- Created public serverless service `telegram-trigger` (service ID `5a3f820c-2bb2-494b-b771-15fa6a5eb48a`, service-instance ID `78bd93d5-f74a-42fb-ad25-2be856bbda07`).
- Deployed the final webhook build as `3e8fd2fe-1cb6-47e7-9233-209bf259d404`; Railway reported `SUCCESS`, and `/health` returned `ok`.
- Registered `https://telegram-trigger-dev.up.railway.app/telegram/webhook` with Telegram for messages and button callbacks. Telegram reported zero pending updates and no webhook error; the bot command menu exposes `start`, `run_price`, and `run_recovery`.
- Added fixed controls for `idx-price-cron` and `idx-price-recovery-cron`. Only the configured owner Chat ID is accepted; arbitrary service names are never accepted from Telegram input.
- Stored the bot token, webhook secret, environment-scoped Railway project token, Chat ID, database reference, allowlisted service-instance IDs, and cooldown as Railway variables. No secret value is stored in Git.
- Added webhook-retry deduplication through `Telegram_Command_Log.telegram_update_id` and a 15-minute per-service rapid-click cooldown.
- Kept Telegram acknowledgement delivery independent from Railway acceptance so a temporary chat-message failure cannot relabel or repeat a successfully started cron job.
- Sent the `/start` menu successfully and ran one end-to-end RECOVERY test. The first command was accepted, an identical replay was ignored, execution `9926d137-6316-4c04-a1c2-099d87bd4735` completed for 2026-09-08, and `telegram-monitor` recorded the final message as `SENT`.
- The scheduled DAILY and RECOVERY start commands, 17:00/06:00 Asia/Jakarta schedules, exact candle-date rule, and existing completion-notification flow were not changed. No DAILY query was run during this deployment.
- Pulled the live Railway configuration into `.railway/railway.ts`; the follow-up plan reported no drift.

## 2026-09-09 — Correct Telegram private endpoint port

- Confirmed manual DAILY execution `1d50802c-caa7-4d1f-9d5d-055b0402eb4f` completed with 829 of 844 symbols but its Telegram request still failed.
- Root cause: both cron services had resolved `TELEGRAM_NOTIFY_URL` to `http://telegram-monitor.railway.internal:/notify` because the referenced service-level `PORT` variable was empty. The request therefore used the wrong port.
- Set both DAILY and RECOVERY notification URLs to the explicit private listener port `8080`; the resulting service deployments `db51a5fe-b845-44c3-abcc-5a91a3883bba` and `1c3e79af-19aa-4482-906a-bab7584c51c4` reached `SUCCESS` without querying TradingView.
- Re-sent the completed manual DAILY execution without running the price query. Telegram delivery was recorded as `SENT`; a repeat returned `duplicate`, confirming anti-duplicate handling.

## 2026-09-09 — Fix Telegram private-network wake and message spacing

- Diagnosed manual DAILY execution `c225b4c9-a009-4295-93f0-59ad4b6bb209`: TradingView processed 844 tickers in about six minutes and wrote 822 exact-date rows with 22 missing; Telegram added about nine seconds before failing with private-network `connection refused`.
- Changed only `telegram-monitor`: it now listens on Railway IPv6 private networking while preserving IPv4 compatibility where available.
- Added one blank line between the status summary and the `Missing:` ticker list.
- Notification calls remain active for both MANUAL and SCHEDULED executions of DAILY and RECOVERY. Query, worker, candle-date, and upsert behavior are unchanged.
- Deployed the fix as `282174bb-10e1-43e1-b498-f90b0742ff94`; Railway reported `SUCCESS` and `/health` returned HTTP 200.

## 2026-09-09 — Event-driven Telegram notifications for IDX price jobs

- Created the separate `telegram-monitor` service (service ID `a6b4e061-721f-4173-82f8-07ccb45740fc`) with no cron schedule, `/health` health check, `ALWAYS` restart policy, and Railway serverless sleep enabled.
- Stored the Telegram bot token, Chat ID, and shared caller secret only as Railway variables; no secret value is stored in GitHub or PostgreSQL.
- Configured `idx-price-cron` and `idx-price-recovery-cron` to send their committed `Monitoring_Price_ALL.execution_id` over Railway private networking. The caller retries temporary wake/network failures and does not roll back price data if notification delivery fails.
- Deployed `telegram-monitor` successfully as deployment `c4bf00cd-3452-4279-8342-ad21c55af9df`; Chat ID activation produced successful redeployment `19cc3f3c-c848-43fd-8fe4-5e9abd531551`, and the final shared-secret rotation produced successful deployment `6c4886fa-ebf4-45ba-b01c-1501c0a71974`.
- Deployed notification-enabled DAILY build `14ec1625-9b26-4f9f-9d53-7a3f63665266` and RECOVERY build `7a126d48-0a67-473c-a62c-004abf68a000`; both reached `SUCCESS` without executing TradingView.
- Sent one end-to-end test from historical RECOVERY execution `80d7d401-d1a2-4ac8-a276-dfbb4e89299b`. A second request returned `duplicate`, confirming the anti-duplicate ledger.
- Removed stale `valiant-connection` declarations from `.railway/railway.ts` because that service and volume are no longer present in the live `dev` environment; no live resource was deleted.

## 2026-09-09

### Correct recovery cron completion status

- Confirmed the scheduled recovery completed its database work in about two seconds, wrote 12 missing symbols as `NEEDS_REVIEW`, closed its PostgreSQL connection, and released its advisory lock.
- Corrected `NEEDS_REVIEW` to exit with code `0` because it is a completed, monitored business outcome rather than a crashed process.
- Kept a non-zero process exit exclusively for an actual `FAILED` status or an unhandled exception.
- Added regression tests for both reviewable and failed outcomes.
- Verified a no-database, no-TradingView Railway smoke execution (`7da53b07-351d-4682-93e2-9af2776e0700`) reached `EXITED` in about two seconds.
- Restored the production recovery start command and verified final RECOVERY deployment `9527e31d-fdd2-46bc-84c3-7ca29c486161` and DAILY deployment `b5d09e04-a255-4441-9dbe-dde0708b05a7` reached `SUCCESS`.

## 2026-09-08

### Guarantee IDX cron process termination

- Diagnosed `idx-price-recovery-cron` remaining `Active` after its 06:05 Asia/Jakarta work had already emitted `run_completed` and recorded 13 symbols as `NEEDS_REVIEW`.
- Added a guarded entrypoint that flushes stdout/stderr and explicitly terminates the process after database contexts close, including non-zero `NEEDS_REVIEW` and failure paths.
- Replaced the stuck recovery instance without issuing another TradingView query.
- Verified DAILY deployment `c831e1ed-0b76-42dc-9ac9-7006906832eb` and RECOVERY deployment `f751f9a1-c8d3-423a-9ccf-fd98d492d75c` reached `SUCCESS`.
- Verified both cron services returned to waiting state and recovery remains scheduled for 06:00 Asia/Jakarta.

## 2026-09-07

### Broker-summary authentication-stop repair

- Stopped both local historical supervisors after detecting repeated Stockbit HTTP 401 responses.
- Corrected the runner so authentication exhaustion reaches the supervisor as exit code 3 instead of being treated as an ordinary per-date failure.
- Replaced the Stockbit credential only in the new local process environments; its value was not persisted.
- Restarted both non-overlapping historical supervisors with three API workers each and verified successful recovery loads in both ranges.
- No Railway service, deployment, domain, or environment-variable values changed.

### Manual-safe IDX price services

- Changed `idx-price-cron` to explicit DAILY mode with schedule `0 10 * * *` UTC (17:00 Asia/Jakarta). Its **Run now** action performs a full current-day universe query.
- Created `idx-price-recovery-cron` (service ID `a8e6e32a-fcd8-4c33-9ecc-1488a4b2db05`) in environment `dev`, with explicit RECOVERY mode and schedule `0 23 * * *` UTC (06:00 Asia/Jakarta). Its **Run now** action retries only the preceding weekday's DAILY missing symbols; Saturday, Sunday, and Monday target Friday.
- Both services use the existing PostgreSQL variable reference, Dockerfile build, and `NEVER` restart policy.
- Added exact candle-date validation, `(ticker, date)` upsert protection, per-execution monitoring history, and a shared PostgreSQL advisory lock.
- No manual TradingView query was triggered during deployment.
- Verified final DAILY deployment `c9764e81-3b34-44b2-9402-c1fc212622f6` and final RECOVERY deployment `a8fc3609-2809-4bfa-b387-578631a8baa3` reached `SUCCESS`.
- Pulled the live configuration into `.railway/railway.ts`; the follow-up Railway configuration plan reported no drift.
- Triggered **Run now** on `idx-price-cron` after deployment. Execution `f4fd425d-edfe-433a-9925-99d052c794c5` ran in explicit DAILY mode, queried all 844 universe tickers, updated 824 exact-date candles, and correctly retained 20 no-current-candle symbols as missing with `PARTIAL` status.

### Historical broker-summary workers split

- Replaced the single local 2025-08-31 through 2018-01-01 supervisor with two concurrent, non-overlapping local supervisors.
- Recent range: 2025-08-31 through 2021-01-01 descending; older range: 2020-12-31 through 2018-01-01 descending.
- Set each process to three API workers so combined Stockbit concurrency remains six.
- Kept separate status and log paths, disabled local CSV output, and retained the five-consecutive-401/403 stop rule for both processes.
- Both supervisors use the existing Railway PostgreSQL TCP proxy. No Railway service, deployment, domain, or environment-variable values changed.

## 2026-09-06

### GitHub tracking contract established

- Added mandatory AI read order and same-task GitHub update rules.
- Added separate database and Railway changelogs.
- Added forward-only SQL migrations for database schema history.
- Imported the current project as a secret-safe `.railway/railway.ts` snapshot.
- Extended the daily GitHub Action to capture Railway configuration drift and database schema changes.
- Kept live secrets and raw production data outside GitHub.

### PostgreSQL daily-price table

- Loaded 668,967 daily price rows into the PostgreSQL service in environment `dev`.
- Renamed the table to `Price_Stock_Indonesia_IDX` for the requested capitalization.
- No Railway service, deployment, domain, or environment-variable values changed.

### Broker-summary supervisor

- A local Windows supervisor was introduced for the Stockbit backfill.
- This is a process on the user's PC, not a Railway service or deployment.
- It resumes incomplete dates and recreates the temporary PostgreSQL TCP proxy after connection failure.

### Broker-summary authentication recovery

- Replaced the expired Stockbit session credential in the local Windows supervisor; no credential value was committed.
- Restarted the supervisor and preserved all dates already marked `COMPLETED`.
- Confirmed the existing Railway PostgreSQL TCP proxy and database connection remained healthy.
- Verified automatic recovery from the earliest `NEEDS_REVIEW` date before allowing the backfill to continue.
- No Railway service, deployment, domain, or environment-variable values changed.

### Automated IDX daily prices

- Created service `idx-price-cron` in environment `dev` (service ID `43c86c6f-3221-4403-83c3-cd3056441558`).
- Deployed the final Python/Docker TradingView price updater; verified deployment `ddd2ba96-d64e-414a-a5c7-87e15eeb23f8` reached `SUCCESS`.
- Connected `DATABASE_URL` to the existing Railway PostgreSQL service using a Railway variable reference; no credential value is stored in GitHub.
- Set cron schedule `0 10,23 * * *` UTC, corresponding to 17:00 Asia/Jakarta for the full `DAILY` run and 06:00 Asia/Jakarta the following day for missing-symbol `RECOVERY`.
- Set restart policy to `NEVER` so a failed recovery cannot create an unapproved third TradingView query.
- The first full TradingView query is scheduled for 2026-09-07 at 17:00 Asia/Jakarta. Existing price history through 2026-09-04 remains unchanged.
- Pulled the resulting live Railway state into `.railway/railway.ts`; the follow-up configuration plan reported no drift.

### Parallel historical broker-summary backfill

- Added a second local Windows supervisor for a descending, database-only backfill from 2025-08-31 through 2018-01-01.
- Kept the existing ascending backfill active and assigned separate status/log files to each process.
- Added a five-consecutive-401/403 stop rule to both supervisors so an invalid Stockbit token stops querying instead of marking the remaining date range `NEEDS_REVIEW`.
- Historical CSV export is disabled; only operational status and logs are retained locally.
- No Railway service, deployment, domain, or environment-variable values changed.
