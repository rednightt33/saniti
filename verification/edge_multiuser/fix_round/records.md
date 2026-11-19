# Fix round of the ultracode re-check: track `records` (records, CI and database records)

Branch `fix-records` from `97b4ecb5` (rel-base: p3c-int plus the re-check's failing tests of rounds 1 and 2). Nothing
was pushed, deployed or applied to a remote database, and no Railway call was made; the migration below ran only on the
disposable cluster `fx_records` (port 55565). The findings and their three refuters' verdicts:
`verification/edge_multiuser/access_tiers/recheck/r1_findings.json` with `r1_verdicts.json`, and round 2's
`r2_result.json` (commit `1f344e92`).

This track owns `CONTRACT.md` and edits no other shared record (ERRORS_AND_SOLUTIONS.md, EXEC.md, RAILWAY_CHANGELOG.md,
DATABASE_CHANGELOG.md, DATABASE_SCHEMA.md); what each of them must say is under "Records to write" at the end.

## Commits

| Commit | What |
|---|---|
| `d71bc836` | R1-2: the runner-key test waits in `pending/`; `apps/market-ai-orc/tests/test_main_key_readers.py` holds the code side |
| `22d4defe` | R1-15, R1-27: a hook route verifies by a dependency built from `HOOK_ROUTES`; the route walk covers the whole table |
| `5f204d11` | R1-41, R1-42, R1-43, R1-45, R1-46: migration `20261119_040`, the provisioning script refuses column grants, direct tests of three database backstops; dry-run jobs for dev |
| `64e5fe94` | R1-28: the run stream's `monitor.view` re-check held by a live-server test |
| `9d31dc07` | work in progress saved at the usage-limit stop (the two-user walk, the owner-aware FakeOrc) |
| `26c38da5` | R1-21: the two-user walk over every route and owned kind; the scratch probe removed |
| `51451d52` | R1-39, R1-40, R1-44: CI runs the page suites, edge-bff's browser tests and Orc's Postgres tests; the shell copy's generated_file test |
| `77e57322` | R2-40: the contract requirements no test held, and two code fixes they found |
| `511848a0` | CONTRACT.md to the code and the decisions of 2026-11-19; R2-6, R2-27, R2-28, R2-41, R1-6; `tests/test_contract_records.py` |

## Per finding

### R1-2 (blocks-switch-on): orc-test-runner still holds MARKET_AI_ORC_API_KEY
- Root cause (verified): Phase 0 step 4 left the main key on orc-test-runner until a runner suite passed with the test
  key; no later step removed it (`.railway/railway.ts` declares it beside `MARKET_AI_ORC_TEST_KEY`).
- Fix, code side only (the variable is a Railway change with the user's go): `apps/market-ai-orc/tests/test_main_key_readers.py`
  holds that no file the runner runs (`apps/orc-test-runner`, `scripts/`, `verification/`) reads the main key and that
  `run.py` reads only the test key, so the deletion cannot break the runner (the code refuter: no runner suite is needed
  first). The re-check's `test_cp0_runner_key.py` waits in `verification/edge_multiuser/access_tiers/pending/` (the spec
  refuter: in `apps/market-ai-orc/tests/` it would hold every edge-bff check, and no code change can make it pass); it
  goes back unchanged in the commit that records the deletion. CONTRACT 7 "Open before the switch goes on" lists it.
- Records: ERRORS M475/M477 stay "code done; the variable still on orc-test-runner" until the deletion.

### R1-6 (records): the Phase 3 Orc capabilities header neither built nor recorded as deferred
- Fix: CONTRACT 7 marks `X-Saniti-Capabilities` (models, levels including `max`, modes, the fast lane) **deferred** under
  D1 with the usage ledger and the daily cap, says what 3a built (the route gates and the model checks) and that the
  export is already gated by `monitor.chat` (the code refuter); the clause stays as what the later phase builds (the spec
  refuter), and the live site holds no Monitor at all (section 17).

### R1-15 (non-blocking): the route walk accepted a hook route whatever its handler did
- Root cause: the walk checked only that `HOOK_ROUTES` named a callable verifier for the path.
- Fix (membership now implies verification): `app/hooks.py signed(path, secret)` is the dependency every hook route
  carries, built from its `HOOK_ROUTES` entry, verifying the raw body before the handler (401 `HOOK_SIGNATURE_INVALID`);
  `app/auth_flows.py` uses it for the Resend webhook. `tests/test_route_table.py` refuses a hook route without `signed`
  for its own path and verifier, and a registered hook that is no route.
- Tests: `tests/test_cp1a_phase1_auth_check.py` (the re-check's R1-15 case), `tests/test_route_table.py::test_every_registered_hook_is_a_route`,
  `::test_the_walk_refuses_what_it_must`.

### R1-21 (records): the two-user acceptance test left out owned kinds and every cross-owner write by id
- Fix (the refuters' derived form): `apps/edge-bff/tests/test_two_users_every_route.py`. The owned kinds are every
  `edge_bff` table with an owner key (information_schema; A makes a row of each through the routes, a new table fails
  until it does); the routes are every `/api` route and method of `app.routes`, B calling each with A's values in its
  path parameters. Checked after every call: A's rows and what Orc holds for A unchanged, none of A's content in B's
  answer, an owned id answers exactly what an id nobody made answers (a create-or-replace PUT: the 409 an own second
  create gets) and never a success, `no-store` on every answer (R2-40 item 6); B's backtest is given B's trials only.
  `conftest.FakeOrc` is owner-aware as Orc is (a row a test puts in `saved` without an owner stays readable by every
  owner, so the single-owner tests keep working); the export download runs against an owner-aware stand-in of Orc's
  route. Both people use one TestClient (one event loop, as production), with their own cookie jars: two TestClients
  ran two loops and the shared worker clients failed across them.
- Mutation checks (run, then restored): the layout read without its owner filter, and `prior_trials` without its owner
  filter, each fail the walk.

### R1-27 (non-blocking): the route walks were scoped by module or path
- Fix: `tests/test_route_table.py` walks every `/api` route of the app: each carries a capability `need`, or is public,
  a hook, or named in `PRINCIPAL_ONLY` with the reason it needs none; a new route without an entry fails with the entry
  to add. Test: `tests/test_c_p3a_probes.py` (the re-check's route-walk case passes).

### R1-28 (non-blocking): the SSE monitor.view re-check held by no test
- Fix: `tests/test_run_stream_live.py::test_the_run_stream_ends_once_the_plan_loses_monitor_view` runs edge-bff on a real
  local server (TestClient buffers a stream to its end) and ends the stream when the plan loses `monitor.view`; it fails
  when `still_signed_in` stops asking for the capability.

### R1-39 (blocks-switch-on): CI ran neither the page suites nor edge-bff's browser tests
- Root cause (verified): no workflow step ran vitest in `apps/edge-bff/terminal` (nor overview, radar, watchlist), and the
  edge-bff job installed `requirements.txt` only, so every Playwright test skipped.
- Fix: `.github/workflows/backend-tests.yml` job `edge-bff-pages` (Terminal, Overview, Radar, Watchlist: `npm ci && npm
  run build && npx vitest run`); job `edge-bff` installs `requirements-dev.txt`, Chromium through Playwright
  (`EDGE_TEST_CHROMIUM` from Playwright's own path) and builds the Terminal and Watchlist pages the browser tests open
  (timeout 60 min). Both jobs are in the check suite edge-bff's deploy is to wait for.
- Tests: `tests/test_cdb_ci_coverage.py` (the re-check's test passes); added, per the refuters' correction (the first
  test locked one instance): `test_every_package_with_a_test_script_is_run_by_a_workflow` (every `apps/**/package.json`
  with a test script is run by a workflow step in its folder; read from the workflows by a small job/step reader) and
  `test_the_edge_bff_job_runs_its_browser_tests`. Mutation: the Radar step's folder renamed fails the general test.

### R1-40 (blocks-switch-on): market-ai-orc's Postgres tests were skipped in CI
- Root cause (verified): the job had no Postgres and no `ORC_TEST_POSTGRES_URL`. The three `test_request_data` errors
  that kept it off were a missing dependency of those tests: they run the SQL Governor's package end to end, which needs
  `pyarrow` (not in Orc's requirements).
- Fix: a `postgres:16` service and `ORC_TEST_POSTGRES_URL` in the job; `apps/market-ai-orc/requirements-dev.txt` names
  `../market-sql-governor/requirements.txt` (the pins agree). Result here: 2193 passed, none skipped, with Postgres.
- Test: `tests/test_cdb_ci_coverage.py::test_ci_runs_orc_conversation_ownership_against_postgres` (also requires the
  service and the Governor's requirements).

### R1-41 (non-blocking): the grant guards did not see column-level privileges
- Fix: migration `20261119_040` part 4 (its `$verify$` block refuses any column privilege held by `edge_bff_runtime`,
  `edge_bff_login` or PUBLIC outside the system schemas); `scripts/provision_edge_bff_login.py` refuses one the login
  holds directly, through a role or through PUBLIC.
- Tests: `tests/test_cdb_grants_and_records.py::test_provisioning_refuses_a_privilege_held_on_columns_only`,
  `::test_the_migration_verify_block_refuses_an_audit_column_update`.
- Test changed (the R1-41 refuter's correction): the latter ran the `$verify$` block of 20261116_003, which is applied
  and can never change (AGENTS.md History rules); it now runs 20261119_040's block, with the same assertion.
- Dev read-back job (not run; the main agent's, after the apply): `verification/edge_multiuser/jobs/column_grants_readback.params.json`.

### R1-42 (non-blocking): admin_audit rewritten by a user deletion
- Root cause: `actor_user_id`, `target_user_id` (and `user_capability_overrides.created_by_user_id`) were foreign keys
  `ON DELETE SET NULL`; the action runs as the table owner, so the hourly pending purge rewrote audit rows.
- Fix: migration `20261119_040` part 1 drops those foreign keys; the ids stay as plain numbers (pseudonymous, never
  rewritten; the refuters: pseudonymise rather than null). Rule recorded in CONTRACT 1.
- Tests: `tests/test_db_backstops.py::test_an_admins_deletion_never_rewrites_what_the_audit_and_the_overrides_say_it_did`,
  `::test_no_audit_or_provenance_column_references_the_users_with_a_referential_action`,
  `tests/test_cdb_grants_and_records.py::test_purging_a_pending_registration_never_changes_an_audit_row`.
- Interplay: `fix-site`'s 20261119_023 indexes `admin_audit(actor_user_id)`, `(target_user_id)` and
  `user_capability_overrides(created_by_user_id)` for their foreign keys; with 040 after it the indexes stay (harmless;
  the site track's test accepts the foreign keys gone).

### R1-43 (non-blocking): plan catalog changes left no trace
- Fix: migration `20261119_040` part 2: trigger `plan_capabilities_trace` raises `version` by one and sets `updated_at`
  when a value changes; `user_capability_overrides.updated_at`, set by `user_capability_overrides_trace` when its value,
  reason or end changes; who changed it is the Phase 4 `admin_audit` row of the same transaction (no `updated_by`
  column: the audit row is the one record of the actor).
- Tests: `tests/test_db_backstops.py::test_an_override_change_sets_updated_at_and_a_plan_change_raises_version_once`,
  `tests/test_cdb_grants_and_records.py::test_a_changed_plan_value_leaves_a_trace`.

### R1-44 (non-blocking): static/edge-session.js compared with its build by no CI job
- Fix: `apps/edge-bff/tests/test_shell_copy_build.py` (marked `generated_file`) runs `node shared/build-shell.mjs --check`
  and shows that a hand edit of the copy's body is caught; `.github/workflows/generated-files.yml` job `edge-bff` runs
  edge-bff's generated_file tests after `npm ci` in the Terminal folder (its esbuild); `EDGE_TEST_REQUIRE_NODE=1` turns a
  missing node or esbuild into a failure there and in the backend job (a skip only on a developer machine).
  `scripts/tests/test_generated_files.py generators()` now also finds any tracked script, wherever it lives, that reads
  a `--check` flag itself (argparse, `sys.argv`, `process.argv`; test files left out): it finds `build-shell.mjs` and
  nothing else new. `conftest.py` registers the `generated_file` mark for edge-bff.
- Test changed (the R1-44 refuters: the test locked the workflow-step form instead of the property, and AGENTS.md's own
  form is a generated_file test): `tests/test_cdb_ci_coverage.py::test_ci_compares_the_shell_copy_with_its_build` accepts
  a workflow step or a generated_file test that generated-files.yml runs with the Terminal's `npm ci` and the
  require-node switch.
- Records: ERRORS M473's sentence "test_storage_registry.py fails ... when static/edge-session.js is not the build of the
  source" is corrected: it compares the source sha256 of the first line only; the whole-file comparison is
  `test_shell_copy_build.py`.

### R1-45 (records): records that contradicted themselves or the decisions
- Fix in the database (forward migration, 20261117_003 untouched): `20261119_040` part 3 resets the live comment of
  `capabilities.kind` (a wrong shape reads as the most restrictive value, M480) and the `means` of
  `terminal.history_days` (counted back from the newest published date, D2 = A).
- Records: ERRORS M468-M475, M477, M478, M480 and M481 each get one current status in place (heading and Status line;
  nothing deleted): the headings read "OPEN; fixed on branch, not deployed; deployed 2026-11-16 on dev" while the body
  Status lines still say "OPEN ... not deployed".

### R1-46 (records): three database backstops no test locked
- Tests: `tests/test_db_backstops.py::test_a_registration_token_stays_only_on_a_pending_account` (`users_registration_pending`),
  `::test_an_email_code_takes_at_most_five_tries` (the attempts cap), `::test_one_seed_row_at_most_even_past_the_owner_key_trigger`
  (`users_one_seed`, with the trigger bypassed by `session_replication_role = replica`).

### R2-6 (records): rollback points without order or compatibility floors
- Fix: CONTRACT 17 "Rollback floors": one row per deploy step that moves the other side's floor (3b, the 3b follow-up's
  step 3, 20261118_001, 3c steps 3 and 4, `fix-auth`'s verifier form, `fix-site`'s queues, the pre-Phase-1 builds, 3d),
  with the order of a rollback; the beta/live rule that the live site stays at or above every floor and a "push ke live"
  below one is not done. 8b "3c" points to it.

### R2-27 (records): no account-deletion procedure
- Fix: CONTRACT 10 "Account deletion": every store that names an account (edge_bff by owner key, user id or address,
  Orc's conversations, terminal's owner rows, Phase 5 payments), the step for each (delete, keep pseudonymous, or open),
  to build as a Phase 4 admin action (until then by hand with the user's go per account).
- Test: `tests/test_contract_records.py::test_the_deletion_procedure_names_every_store_that_names_an_account` walks every
  migration for a table with an owner key or a user id and fails on one section 10 does not name.

### R2-28 (records): the recipients of personal data recorded nowhere
- Fix: CONTRACT 18: Google Fonts (IP and user agent, every page before sign-in), Resend (addresses and bodies), the
  market-file bucket host (IP and object keys), Pwned Passwords (a 5-hex SHA-1 prefix, not personal), Railway,
  OpenRouter and its model providers (admin only, D1), the Phase 5 payment provider. Self-hosting Inter is listed as open.
- Test: `tests/test_contract_records.py::test_every_third_party_host_is_a_recorded_recipient_of_personal_data` collects
  every https host of edge-bff's server code (page policies, its own calls) and of the resources each page loads, and
  fails on one section 18 does not name.

### R2-40 (records): contract requirements no test held
- Tests (`apps/edge-bff/tests/test_contract_requirements.py`), each failing on the finder's mutation:
  1. `test_an_expired_session_answers_401_with_the_switch_off` (store.session `expires_at>now()`; mutation run: fails);
  2. `test_an_expired_session_answers_401_with_the_switch_on_although_it_was_used_a_moment_ago` (accounts.resolve);
  3. `test_the_mfa_tries_limit_answers_with_retry_after`, and the class: `test_every_429_an_answer_is_built_with_says_when_to_try_again`
     (an AST walk of `app/`: every Refusal/refusal/failure/error/JSONResponse/Response call with 429 passes Retry-After);
  4. `test_the_sign_in_and_the_registration_answers_carry_the_entitlements_version`;
  5. `test_refusals_name_the_catalogs_items_from_the_start_without_a_refusal_first`;
  6. no-store: in the two-user walk over every answer (the code refuter: the Screener already held part of it);
  7. `test_a_subscription_that_starts_tomorrow_gives_the_default_plan_today`;
  8. `test_an_email_send_records_the_client_address_count`;
  9. `test_a_session_waiting_for_mfa_can_sign_out`;
  10. `test_every_message_table_speaks_plain_words` (every code-to-sentence dict of `app/`, found by AST).
- Code fixed (what the tests found): `app/auth_flows.py register_verify` sets `request.state.principal`, so its
  signed-in answer carries `X-Edge-Entitlements` (item 4: it never did; mutation run: fails without it);
  `app/pages.py` `NOT_CONFIGURED` no longer names `EDGE_TERMINAL_URL` and `TERMINAL_PROXY_KEY` (item 10).
- Expected red on this branch alone: `test_every_429_an_answer_is_built_with_says_when_to_try_again` fails at
  `pages.py:178` (`self.failure('QUOTA', 429)` without Retry-After), which is R1-26, fixed on `fix-terminal` (its
  `pages.py` routes every terminal-api answer through `terminal_access.relayed`, whose 429 carries Retry-After; checked
  against that branch's `app/` here). Green after integration.

### R2-41 (records): CONTRACT.md clauses the code no longer follows
- Fix: one records pass of CONTRACT.md (section by section): item 1 (sign-in of a pending account: 401 and a restarted
  registration, `EMAIL_NOT_VERIFIED` unused) in 4; item 2 (`backtest.result:<section>` dropped) in 8; item 3 (per-file
  page capabilities not built) in 15; item 4 (Watchlist indicator keys checked for shape only, the flow keys open with
  R1-37) in 15; item 5 (`access:'admin'` marks, to build in 3f) in 8b 3f and 15; item 6 (a shape limit enters the
  Screener's result key) in 7; item 7 (examples per D4) in 8b 3e, 9 and 15; item 8 (email unique among non-pending
  accounts) in 1; item 9 (register/verify needs the registering browser's cookie; the admin's "resend a code" open for
  Phase 4) in 4 and 10; item 10 (`starts_at <= now()`) in 1, 2 and 8a; item 11 (the session answer's top-level
  `owner_key`) in 4; item 12 (the Screener star's `watchlist.view`) in 8b 3a; item 13 ("segera hadir" kept as the user's
  words beside the English "Coming soon") in 9.

## CONTRACT.md: the decisions of 2026-11-19 and the other tracks

Brought in as built (with the branch) or to build:
- the beta/live architecture as a new section 17 (EDGE_SITE, the live mask, two sites on one database, push to live,
  expand-then-contract, rollback floors) and the variables in 16;
- pre-launch mode on live (closed registration, sign-in for the admin and test accounts): to build (nothing exists);
- the guest (the `guest` plan, what a visitor sees on the Terminal, the sign-in box): to build in 3c/3e;
- the free plan's whole ticker list with the sign-in and upgrade boxes (decision 1): to build; it replaces
  `fix-terminal`'s R2-32 reading (reference copies naming BBCA only) for the ticker list the search reads;
- outbox and used codes and webhook events kept 30 days (decision 2): to build (one `store.PURGES` entry);
- "forgot password" kept as it is (3); one shared Terminal quota (4, as built); the gateway expiry to 2100-01-01 before
  switch-on (5, the main agent's data change); `public_data` on the relay's successful answers (6, M260): to build;
- the restricted-plan rule "2a" (`fix-plans` migration 030) in 8a;
- from `fix-auth`: verifier cost and form, sign-in limits per login and client, the per-account cap, MFA re-enrolment,
  the outbox purge, the password pool's 503, unexpected errors in the contract's shape;
- from `fix-plans`: LIMIT_REACHED for every plan limit, words from code and details, PLAN_EXPIRED for lists and limits,
  access.limits min(plan, HARD), preferences per tab, __Host- cookies, HSTS, no inline script, the password dialog,
  the landing, the name rule;
- from `fix-terminal`: one relay rule, the acknowledgement header, value domains, history 0, unknown datasets left out,
  reference copies, the gateway state on `/ready`, the page-file cache rule, what the Terminal data limits bind;
- the main agent's design values told to the user (admin on live with MFA, a recent MFA pass to start a new
  authenticator: to build, scrypt cost, no 100-failure cap on the beta).

## Records to write (for the main agent at integration)

- **ERRORS_AND_SOLUTIONS.md:** one entry (or sub-items) per finding above: symptom (the finding's failure scenario), the
  verified root cause and the fix as written here, status "fixed on fix-records, not deployed" (R1-2: "code side done;
  the variable on orc-test-runner waits for the user's go"; R1-6, R2-6, R2-27, R2-28, R2-41: "recorded in CONTRACT.md").
  Also: M473's sentence corrected (R1-44); M468-M481 one current status each (R1-45); M475/M477 status (R1-2); M481 "C3
  gaps" closed by R1-27 and R1-28; M260 "the user's go 2026-11-19, to build in 3c". Part D lessons: a registry
  membership never stands in for the behaviour it names (R1-15); a walk derives its scope from the whole route table and
  the schema, never a list of modules or kinds (R1-21, R1-27); a long-lived answer is tested on a live server (R1-28);
  a suite wired into no workflow is not a test (R1-39, R1-40); a generator outside a `scripts` folder is found by its
  `--check` (R1-44); a test reaching into a sibling service declares that service's requirements (R1-40); grant guards
  read column privileges too (R1-41); an audit or provenance id never carries a referential action (R1-42); a value
  that feeds a version needs a trigger, not a default (R1-43); a frozen live comment is reset by a forward migration
  (R1-45); a requirement is tested by itself, not through a neighbour (R2-40); a contract clause changes in the commit
  that changes the behaviour (R2-41).
- **DATABASE_SCHEMA.md / DATABASE_CHANGELOG.md:** migration `20261119_040_edge_bff_audit_ids_and_catalog_trace.sql`
  (written, not applied): the foreign keys of `admin_audit.actor_user_id`, `admin_audit.target_user_id` and
  `user_capability_overrides.created_by_user_id` dropped; `user_capability_overrides.updated_at`; triggers
  `plan_capabilities_trace` and `user_capability_overrides_trace` and their functions; the comment of
  `capabilities.kind` and the `means` of `terminal.history_days` reset; the column-privilege guard in its `$verify$`.
  Order at apply: after 20261118_002 and the other tracks' 20261119_0xx (it is numbered last of them). Dry-run and apply
  jobs: `verification/edge_multiuser/jobs/migration20261119_040.params.json`, `..._apply.params.json`; read-back:
  `column_grants_readback.params.json`. Small tables: not a large update (no Postgres restart).
- **RAILWAY_CHANGELOG.md:** nothing changed on Railway. At integration: the CI changes (backend-tests.yml jobs edge-bff
  and edge-bff-pages, the Orc job's Postgres; generated-files.yml job edge-bff) as CI records.
- **EXEC.md** (EXEC-MU-ACCOUNTS, the fix round): the records track's status (commits above); CONTRACT.md brought to the
  decisions of 2026-11-19; the open items below.

## Open (for the user; nothing guessed)

1. R1-2: delete `MARKET_AI_ORC_API_KEY` on orc-test-runner (a Railway change).
2. R2-28: self-host the Inter font (no visible change) or keep Google Fonts and state it in the Privacy text.
3. R2-27: on an account deletion, keep or delete the address's `email_suppression` row; how long Phase 5 payment
   records are kept (law).
4. R2-41 item 4 with R1-37: the Watchlist's Foreign-flow indicator keys (gate them by the Terminal's flow grants, or
   part of the Watchlist).

## Suites (this branch, local; PostgreSQL 16 on port 55565, Chromium /opt/pw-browsers/chromium)

See the final report of this track for the numbers of the last run (edge-bff pytest, market-ai-orc with Postgres,
scripts tests, the Terminal vitest).
