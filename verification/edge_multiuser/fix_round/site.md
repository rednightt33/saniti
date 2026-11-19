# Fix round of the round-2 re-check: track `site` (beta/live split, start-up, background loops)

Branch `fix-site` from `97b4ecb5` (rel-base: p3c-int plus the failing tests of re-check rounds 1 and 2). Nothing was
pushed, deployed or applied to a remote database; every migration below ran only on the disposable cluster `fx_site`.

The design follows the architecture the user agreed on 2026-11-19 (EXEC.md EXEC-MU-ACCOUNTS "Production environment"):
one Railway environment; the beta is the service edge-bff (its Railway address, the admin only, `EDGE_MULTIUSER` off as
today); the live site is a second service, edge-bff-live, on app.edgefinance.id with `EDGE_MULTIUSER` on; only the website
is doubled. A setting `EDGE_SITE` (beta|live, default beta) tells the two apart. On live the AI Monitor, the admin routes
and every lab item are refused; AI stays admin-only (D1). No guardrail beyond what the findings need.

## The design in one place

| Part | Where | What |
|---|---|---|
| `EDGE_SITE` | `app/config.py` | `beta` (default) or `live`; anything else stops the start |
| Impossible pairings | `config.validate` | live without `EDGE_MULTIUSER=true`; beta with it (outside `EDGE_ENVIRONMENT=local`, where the tests run a switch-on beta); `EDGE_AI_WORKER_ENABLED=true` on live; `EDGE_EMAIL_MODE=log` with the switch on outside `local` (was: outside dev/local) unless the explicit `EDGE_EMAIL_LOG_ALLOWED=true` (a test of the live site before its Resend key, no real person; logged `email_log_mode_allowed` at every start) |
| Per-loop switches | `config.py`, `main.py start_loops` | `EDGE_AI_WORKER_ENABLED` (unset: beta on, live off), `EDGE_BACKTEST_LOOP_ENABLED`, `EDGE_HOUSEKEEPING_ENABLED` (default true), `EDGE_EMAIL_ENABLED` (existing; the sender runs only with the switch on, so only on live). `EDGE_WORKER_ENABLED=false` still turns every loop off (local runs, the tests). All parsed with `switch_of`: a typo stops the start |
| Queues carry their site | migrations `20261119_020` (`edge_bff.jobs.site`), `20261119_021` (`edge_bff.backtest_jobs.site`), default `'beta'` | `Store.submit/claim(site)`, `_promote` keeps the site; `BacktestStore(store, site)` claims, reaps and prunes only its site's jobs; the AI worker's claim is bound to the app's site (`worker.claim`, like `worker.access`) |
| Sessions bound to their site | `store.session` | the switch-off resolver accepts only `user_id IS NULL` sessions (R2-1); the switch-on resolver already joins the account, so a beta session never resolves on live |
| Seed mark | migration `20261119_022`, `accounts.py seed` | `identities.seed_verifier_sha256`; the seed copies `EDGE_PASSWORD_VERIFIER` only over its own copy (R2-2) |
| Live site mask | `principal.py beta_only`, `live_view`, `Auth.site_view`, `Auth.need`; `allow.py allow_of`; `main.py on_this_site` | capability keys of the tabs `monitor` and `admin`, the admin rights of `rights.py` (`backtest.flow_point_in_time`) and every lab-stage item are never held on live, `'*'` included (`'*'` reads as every catalog flag that is not beta-only, so the shell shows no Monitor); `need()` of such a capability answers 404 `NOT_FOUND` before the session is read; `/monitor` and `/c/<id>` answer 404; `allow` is never `"*"` on live; the second factor is decided by the account's own grants (user #1 still needs MFA on live) |
| Start-up | `main.py start_up`, `/ready` | readiness, seeds and names, then the loops, in one attempt under a lock; retried every `EDGE_POLL_SECONDS` and on each `/ready`; `/ready` answers 503 until it succeeded; no loop (the backtest loop included) runs before (R2-3, R2-36) |
| Housekeeping | `worker.py Housekeeping`, `store.py purge/PURGES` | its own task; each purge (sessions, throttle, pending) in its own transaction and try, batches of 500 (20 per turn), next try after a doubling backoff on failure, logged `housekeeping_failed` by class; an advisory try-lock skips a purge the other site is running (R2-33) |
| Backtest loop | `backtest.py BacktestLoop.run` | prune (batched, site-scoped), reap and claim each in its own try; a failing prune backs off (R2-33 general class) |
| Indexes | migration `20261119_023` | the six foreign keys to `edge_bff.users` (R2-34) |
| `/version` | `main.py` | `{"site", "commit"}` from `RAILWAY_GIT_COMMIT_SHA` |
| Shared secrets | `config.shared_key_marks`, `startup_done` log | a 12-hex HMAC mark of each of `EDGE_SESSION_SECRET`, `EDGE_CODE_SECRET`, `EDGE_MFA_KEY` in each start line, so the two services' lines show whether they hold the same values (R2-8, R2-26) |
| railway.ts | `.railway/railway.ts` | `edge-bff-live` as a comment block (variables set later by the main agent) |

## Findings

### R2-1 (switch-off resolver accepts switch-on sessions)
- Root cause (verified, refuters agree): `store.session` checked only token, revocation and expiry; `principal.resolve`
  (switch off) then accepted any row of `EDGE_OWNER`, including a switch-on session of user #1 still waiting for MFA,
  idle, or of a disabled account. The column comment of 20261116_003 says a switch-off session has `user_id` NULL.
- Fix: `store.session` adds `AND user_id IS NULL` (the layer that owns the session read). With the decided pairing this
  also binds a session to its site: beta sessions have no account, live sessions do (the switch-on resolver joins it).
- Tests: `tests/test_r2_skew.py::test_a_switch_on_session_that_has_not_passed_mfa_opens_nothing_with_the_switch_off`
  (passes; its control, a switch-off sign-in, still works); `tests/test_beta_live_site.py::test_a_session_opens_only_the_site_that_made_it`.
- Records: ERRORS entry (status fixed in fix-site); the Phase 6 runbook must still revoke `WHERE user_id IS NOT NULL`
  before any pre-Phase-1 build starts (those builds cannot be patched). README switch table updated.

### R2-2 (switch-off seed overwrites a password set with the switch on)
- Root cause: `AccountStore.seed` ran `UPDATE identities SET verifier = env` at every switch-off start, with nothing to
  tell the seed's own copy from a password the account set (change or reset).
- Fix: migration `20261119_022` adds `identities.seed_verifier_sha256` (sha256 of the verifier the seed last wrote,
  never the verifier) and fills it for the seed's identity (the switch has never been on outside tests). The seed copies
  only while `sha256(verifier) = seed_verifier_sha256`; a change or reset writes another verifier, so the identity is
  the account's from then on (`account_seed_password_kept` logged). The switch-off sign-in still reads
  `EDGE_PASSWORD_VERIFIER` directly. This changes a recorded rule (README switch table, seed docstring: both updated).
- Tests: `test_r2_skew.py::test_a_switch_off_start_keeps_the_password_user_one_changed_with_the_switch_on`,
  `test_r2_trace_beta_live.py::test_a_start_of_the_beta_site_keeps_the_password_user_one_set_on_the_live_site`;
  `test_principal.py::test_the_seed_is_made_once_across_replicas_and_follows_the_configured_password` (a rotated env
  verifier is still copied over the seed's own copy) stays green.
- Records: ERRORS (the rule change, refuter spec's note that the test encodes a design change: accepted with the
  beta/live design), DATABASE_CHANGELOG/SCHEMA (the column), README.

### R2-7, R2-13, R2-23, R2-38 (two sites claim each other's rows)
- Root cause: the queues had no site column; every claim took any row (`store.claim`, `BacktestStore.claim`, the outbox)
  and the claiming service decided by its own switch and code; `EDGE_WORKER_ENABLED` started every loop together.
- Fix: `site` on `edge_bff.jobs` and `edge_bff.backtest_jobs` (migrations 020/021, default `'beta'`: every row so far is
  the admin's); each site claims (and for backtests also reaps and prunes) only its own; per-loop switches; the AI loop
  only on beta (validate refuses it on live, and live answers 404 to every Monitor route, so live never queues a run);
  the email sender only with the switch on, i.e. only on live (the outbox needs no site column: only live writes and
  reads it); the housekeeping in its own task with a try-lock per purge. R2-38 part (3) (3c's 20261118_001 removes rows
  the 3b code reads) needs no code: record the expand-then-contract rule (below).
- Tests: `tests/test_r2_trace_beta_live.py` (moved from `pending/`, changed to the decided pairing: the checker wrote
  it for a switch-on beta and a switch-off live, the pairing the decision reverses and `config.validate` now refuses;
  the rule it holds is the same), `tests/test_beta_live_site.py::test_each_site_claims_only_the_runs_it_queued`,
  `::test_the_beta_backtest_loop_neither_reaps_nor_prunes_the_live_sites_jobs`.
- M340 (no active user run before a deploy or a Postgres restart) reads `edge_bff.jobs`, a shared table, so it already
  counts both sites' runs; it does not read `backtest_jobs` (unchanged; not part of these findings).

### R2-8, R2-26 (per-service secrets key shared rows; the log-mode guard trusts dev)
- What can be validated from one process: `config.shared_key_marks()` puts a 12-hex HMAC mark of each of
  `EDGE_SESSION_SECRET`, `EDGE_CODE_SECRET`, `EDGE_MFA_KEY` into the `startup_done` line of every start; two services with
  the same values log the same marks. With the decided pairing, `EDGE_CODE_SECRET` and `EDGE_MFA_KEY` are read only by
  the switch-on site (live); `EDGE_SESSION_SECRET` is read by both (the sign-in throttle and CSRF).
- R2-26's own point: the log mode was allowed with the switch on in `EDGE_ENVIRONMENT=dev`, the Railway environment of
  both sites. Now only `local` (tests and developer machines), or with the explicit `EDGE_EMAIL_LOG_ALLOWED=true` (the
  finder's and refuter code's suggested form: a copied configuration never carries it by accident). That switch is what
  makes the user's ask of 2026-11-19 ("since kita sudah ada weblive, bisa langsung test disana?") possible before the
  Resend key is in: edge-bff-live with the switch on and log mode, every code read from `email_outbox.payload`, no real
  person registering, the switch removed before anyone else is let in.
- Test: `test_beta_live_site.py::test_the_start_line_shows_whether_both_sites_hold_the_same_shared_secrets`,
  `::test_the_site_setting_refuses_the_pairings_the_decision_rules_out`; `test_auth_flows.py::test_the_settings_need_their_secrets_only_with_the_switch_on` (its prod case still refused).
- Records: CONTRACT 16 (below); railway.ts comment block (references `${{edge-bff.NAME}}`).

### R2-3, R2-36 (start-up readiness read once; loops dead while /ready says ready; lenient loop switches)
- Root cause: lifespan read `store.ready` once and gated the loops on it, while `/ready` re-read it on every
  healthcheck; the backtest loop started whatever readiness said; `EDGE_WORKER_ENABLED`/`EDGE_EMAIL_ENABLED` took any
  value but `true` as off.
- Fix: `start_up()` (one attempt under a lock: readiness, seed, names, seed plan, then the loops), made in the lifespan
  and retried in the background every `EDGE_POLL_SECONDS` and on each `/ready`; `/ready` answers 503 until it succeeded;
  no loop runs before (the backtest loop too: store.ready reads no backtest table, so the "a missing backtest table keeps
  only the backtest feature off" reason of the old comment still holds). With the switch on, a failing seed fails the
  attempt (nothing could sign in); with it off the site starts. Logged `startup_not_ready` (first and every 30th),
  `startup_done`; `email_sender_off` (error) when the switch is on and the sender is not. The loop switches use
  `switch_of`.
- Tests: `test_r2_skew.py::test_a_start_during_a_database_outage_runs_the_ai_worker_once_it_is_ready`,
  `::test_a_build_that_is_not_ready_claims_no_backtest_job` (a recorded design change, refuters: acceptable),
  `test_c2_ops_recheck.py::test_the_email_sender_runs_once_ready_answers_after_a_database_error_at_start`,
  `::test_the_ai_worker_runs_once_ready_answers_after_a_database_error_at_start`,
  `::test_a_typo_in_a_loop_switch_stops_the_start[EDGE_EMAIL_ENABLED|EDGE_WORKER_ENABLED]`,
  `test_beta_live_site.py::test_a_typo_in_a_loop_switch_stops_the_start[...]` (the new switches),
  `::test_a_seed_that_fails_with_the_switch_on_keeps_the_site_not_ready`.
- Not done here: `scripts/restart_postgres.py` reads only edge-bff's `/ready` after a restart (R2-36 sub-point, PROPOSAL
  2.8 d). It belongs with creating edge-bff-live (its domain is not known to the script yet, and the cron is uploaded with
  `apps/postgres-memory-cron/deploy.sh`, a Railway step).
- Records: EXEC's "a build deployed before the migration never takes traffic" now holds whatever the migration's timing
  (the build serves 503 until its readiness passes and starts no loop before).

### R2-33 (a failing hourly cleanup stops every queued AI run)
- Root cause: `Worker.run` ran `cleanup_sessions` and the claim in one try; `cleaned_at` was set only on success, so a
  failing cleanup was retried every poll and the claim never reached; the three purges were one 5 s transaction.
  `BacktestLoop.run` had the same coupling (prune, reap, claim).
- Fix: the purges left the AI loop for `Housekeeping` (its own task, also on live where there is no AI loop); each purge
  is its own transaction (`Store.purge`), in batches (`LIMIT`, via the key) of 500, at most 20 batches a turn, its own
  try, next attempt after a doubling backoff up to the hour, and a try-lock so two sites never run the same purge at
  once. `BacktestLoop.run`: prune (site-scoped, batches of 200), reap and claim each in its own try. `purge_pending` and
  `throttle.purge` take an optional `limit` and return the rows deleted; `Store.cleanup_sessions` stays (one call runs
  every purge to its end, each batch in its own transaction).
- Tests: `test_c2_ops_recheck.py::test_a_failing_hourly_cleanup_does_not_stop_the_run_queue` (the worker no longer
  runs a cleanup at all), `test_beta_live_site.py::test_a_failing_purge_stops_neither_the_others_nor_its_own_next_try`,
  `::test_a_purge_another_instance_runs_is_skipped_and_every_purge_is_bounded`,
  `::test_a_failing_prune_or_reap_does_not_stop_the_backtest_claims`.
- Test changed: `test_edge.py::test_sessions_are_cleaned_when_the_loop_starts_whatever_the_clock_reads` held the AI
  loop to "purge at the start, then once an hour"; the purges left that loop (decision: housekeeping in its own task,
  R2-33), so the test now holds `Housekeeping` to the same rule
  (`test_sessions_are_cleaned_when_the_housekeeping_starts_whatever_the_clock_reads`). No expectation was weakened.

### R2-34 (no index on the foreign keys to edge_bff.users)
- Fix: migration `20261119_023`: `sessions(user_id)`, `email_codes(user_id)`, `admin_audit(actor_user_id)`,
  `admin_audit(target_user_id)`, `subscriptions(user_id, starts_at DESC)`, `user_capability_overrides(created_by_user_id)`;
  its `$verify$` block refuses any single-column foreign key to `edge_bff.users` without a leading non-partial index.
  `users(email) WHERE status='pending'` not added (optional in the finding; not measured as needed).
- Test: `test_c2_ops_recheck.py::test_every_reference_to_an_account_has_an_index`.
- If the R1-42 fix (another track) removes the `admin_audit` foreign keys, its two indexes may go with them (the test
  accepts that).
- Evidence: section "EXPLAIN evidence" below.

## Tests changed (not weakened), with the reason
- `tests/test_r2_trace_beta_live.py` (from `pending/`): changed to the decided pairing (beta off, live on); the checker's
  pairing (beta on, live off) is now refused by `config.validate`. Same rule, same assertions on the outcome.
- `tests/test_edge.py`: the hourly-cleanup test moved from the AI loop to `Housekeeping` (above).
- `tests/test_backtest.py`: the tests that drop and recreate the backtest tables with 20261026_005 now also put the
  site column back (`recreate`: 20261026_005 then 20261119_021), so later tests see the schema the migrations leave.
- `tests/conftest.py`: the four new migrations.

## Readings of the decision made here (for the main agent to confirm or change)
- The live mask covers every key of the `monitor` tab, `monitor.example` included (the fixed Monitor example with its
  upgrade prompts): on live no plan can open the Monitor, so the example would offer what the site does not have
  (PROPOSAL 2.6 "a site mask strips ... monitor.*"). Changing it means carving `monitor.example` out of `BETA_ONLY_TABS`.
- `backtest.flow_point_in_time` (rights.py's one admin right) is masked on live as an admin feature.
- User #1 may sign in on the live site (with the second factor, as an account whose grants need it) and sees it masked.
  Nothing in the decision forbids it; listed in decisions_needed.
- Until edge-bff-live runs, the beta keeps the housekeeping (`EDGE_HOUSEKEEPING_ENABLED` defaults to true on both
  sites, so the running service keeps its behaviour); the try-lock keeps the two sites from running one purge at once.

## Merging with the other tracks
- `tests/conftest.py`: four migration lines after 20261118_002; other tracks add theirs in their own ranges.
- `app/accounts.py`: the seed (R2-2) and `purge_pending(connection, limit=None)` (a `limit` and the rowcount; R2-33's
  batches). A new purge (R2-35's outbox and email-code retention, Phase 4/5) is one entry in `store.PURGES` taking
  `(connection, limit)` and returning the rows deleted; it then runs in `Housekeeping` on its own.
- `app/principal.py`: `beta_only`, `live_view`, `Auth.site_view`, the 404 branch of `Auth.need`, `Principal.live`;
  `Auth.refresh_names` also keeps the catalog's flag keys. `app/allow.py`: `allow_of` never sends `"*"` for a live
  principal. A track that changes how a principal is built keeps `Auth.site_view` around every principal it returns.
- `app/store.py ready` now reads `edge_bff.jobs.site` and `edge_bff.identities.seed_verifier_sha256`: a build with this
  code is not ready (503) before migrations 020-022.
- Not done here (needs the live service's domain and a Railway upload): `scripts/restart_postgres.py` reads only
  edge-bff's `/ready` after a restart (R2-36 sub-point; PROPOSAL 2.8 d).

## Records to write (records track)
- ERRORS_AND_SOLUTIONS.md: R2-1, R2-2, R2-3, R2-7, R2-8, R2-13, R2-23, R2-26, R2-33, R2-34, R2-36, R2-38 with the root
  causes and fixes above (status: fixed on fix-site, not deployed). Lesson for Part D: a background loop or start step
  over a table more than one service shares filters on the row's owner (site) or has one owner by configuration; a loop
  is started only after the readiness the healthcheck reports; maintenance never shares a try or a transaction with the
  primary work; every foreign key gets an index on its referencing column.
- EXEC.md EXEC-MU-ACCOUNTS "Production environment": the consequences built (the table above); the variables of
  edge-bff-live (railway.ts comment block); set `EDGE_HOUSEKEEPING_ENABLED=false` on edge-bff once edge-bff-live runs
  (the live site is the housekeeping's one owner; until then the beta keeps it, and the try-lock keeps the two from
  running one purge at once); both sites run the same `EDGE_MULTIUSER` value never (validate: beta off, live on); the
  expand-then-contract rule for migrations (R2-38 part 3): a migration that removes or renames rows or columns an older
  edge-bff reads waits until no running edge-bff reads them (20261118_001 deletes the four 3b families: never pair a
  live edge-bff older than the 3b follow-up with it); 3c deploy step 4 (terminal-api requires the owner headers) waits
  until every edge-bff sends them; the Phase 6 rollback runbook revokes sessions `WHERE user_id IS NOT NULL` before any
  pre-Phase-1 build starts (R2-1).
- RAILWAY_CHANGELOG.md: the edge-bff-live declaration (comment) in railway.ts; nothing changed on Railway.
- DATABASE_CHANGELOG.md / DATABASE_SCHEMA.md: migrations 20261119_020 (`edge_bff.jobs.site`), 021
  (`edge_bff.backtest_jobs.site`), 022 (`edge_bff.identities.seed_verifier_sha256`), 023 (six indexes), with the EXPLAIN
  evidence below; not applied on dev.
- CONTRACT.md: section 1 replace "The tables are small: users and sessions number in the thousands at most." with "Every
  foreign key to `edge_bff.users` has an index whose leading column is the referencing column (20261119_023; the
  pending purge and the principal's reads by account); other indexes only after EXPLAIN." Section 16: add `EDGE_SITE`,
  `EDGE_AI_WORKER_ENABLED`, `EDGE_BACKTEST_LOOP_ENABLED`, `EDGE_HOUSEKEEPING_ENABLED` (edge-bff and edge-bff-live), and
  `EDGE_EMAIL_LOG_ALLOWED` (live, a test with no real person only), and
  "edge-bff-live holds `EDGE_SESSION_SECRET`, `EDGE_CODE_SECRET`, `EDGE_MFA_KEY` as Railway references to edge-bff's
  (`${{edge-bff.NAME}}`): they key rows of the shared tables; the `startup_done` line of each start shows their marks".
  Section 2: the switch-off resolver accepts only sessions without an account; on the live site every principal is
  `live_view` (no beta-only capability). Section 5: the sender runs only with the switch on (the live site).

## EXPLAIN evidence

Bounded `EXPLAIN (ANALYZE, BUFFERS)` on a disposable database `explain_site` of the cluster `fx_site` (PG 16.15,
default settings), the migrations of the suite applied, filled at the finder's sizes (R2-34): 20 000 active and 7 000
pending accounts (created 25 h ago), one password identity each, 100 000 sessions, 107 000 email codes (7 000 live
register codes of the pending accounts, 100 000 consumed reset codes), 50 000 admin_audit rows, 20 000 subscriptions
(half active, half expired, all ended), 50 000 AI jobs and 50 000 backtest jobs (80 queued each, 40 of them `live`).
Each statement run once in a transaction rolled back, after `ANALYZE`; then 20261119_023 applied, `ANALYZE`, and the
same statements again. The script is the fix round's scratch `explain_r2_34.py` (not committed); the database was
dropped afterwards.

| Statement | Before | After |
|---|---|---|
| `purge_pending` of 200 accounts (`LIMIT 200`) | 5 830.7 ms; the referential triggers: sessions 2 063.8 ms and email_codes 2 064.6 ms (a Seq Scan each per deleted account), admin_audit 659.7 + 731.2 ms, subscriptions 282.1 ms, the indexed ones (identities, mfa_*) 1.6-7.2 ms | 27.4 ms; every trigger 0.6-8.5 ms |
| `owner` resolve of an account whose plan ended (the `lapsed` CTE) | 4.68 ms, 260 buffers, `Seq Scan on subscriptions` | 0.66 ms, 16 buffers, `Index Scan using subscriptions_user_id_starts` |
| `create_session`'s cap (revoke beyond 5) | 8.96 ms, 2 044 buffers, `Seq Scan on sessions` | 0.13 ms, 8 buffers, `Bitmap Heap Scan` on `sessions_user_id` |
| `revoke_all` | 9.27 ms, 2 066 buffers, `Seq Scan on sessions` | 0.24 ms, 40 buffers, `Bitmap Heap Scan` on `sessions_user_id` |
| AI claim of site `live` (`store.claim`) | 0.05 ms, 4 buffers, `Index Scan using edge_bff_claim` | same (no index added) |
| backtest claim of site `live` (`BacktestStore.claim`) | 0.15 ms, 41 buffers, `Index Scan using backtest_jobs_claim` and `backtest_jobs_one_running_owner` | 0.11 ms, same plan |

The two claims show why the site columns need no index: the existing partial claim indexes hold only the active rows,
and the site is a filter on those. The purge's own read of `edge_bff.users` (status pending, created over 24 h ago) stays
a Seq Scan of 27 000 rows inside the 27 ms; no `users(email) WHERE status='pending'` index was added (not measured as
needed; AGENTS.md: no speculative index).

## Suites

- edge-bff pytest (`EDGE_TEST_POSTGRES_URL` on `fx_site`, port 55562; Chromium `/opt/pw-browsers/chromium`), the whole
  `tests/` folder: base `97b4ecb5` 70 failed, 682 passed, 2 skipped; `fix-site` 59 failed, 712 passed, 2 skipped. No new
  failure. Fixed: the ten tests of this track (`test_r2_skew.py` 4, `test_c2_ops_recheck.py` 6: the failing hourly
  cleanup, the two loop-switch typos, the index test, the two start-up blips) and the known flaky
  `test_composer_layout.py::test_submit_history_and_fixed_headers[mobile]` (passed this time). New tests that pass:
  `test_beta_live_site.py` (17), `test_r2_trace_beta_live.py` (2). The 59 left belong to other tracks' findings and
  failed on the base too: test_c2_e2e_people (2), test_c2_ops_recheck (2: the outbox index, the sign-in burst),
  test_c2web_browser (7), test_c_p1s_preferences_plan (1), test_c_p2_recheck (3), test_c_p2_terminal_wire_domain (6),
  test_c_p3a_probes (4), test_c_p3b_recheck (1), test_cdb_ci_coverage (3), test_cdb_grants_and_records (5),
  test_cp0_reserved_owner (4), test_cp0_terminal_relay (2), test_cp1a_phase1_auth_check (10), test_r2_life (2),
  test_r2_race (7).
- scripts tests (`python3 -m pytest scripts/tests`): 94 passed, 1 skipped.
- terminal-api, backtest-worker, screener-worker and the page vitests: not touched by this track, not run.
