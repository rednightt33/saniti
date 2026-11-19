# Fix round of the ultracode re-check, track auth (authentication and account security)

Branch `fix-auth` from `97b4ecb5` (rel-base: p3c-int plus the re-check's failing tests of rounds 1 and 2). Nothing is
pushed, deployed or applied: the three migrations below are new and unapplied, and no Railway call was made.

Findings: round 1 `verification/edge_multiuser/access_tiers/recheck/r1_findings.json` with the refuters' verdicts in
`r1_verdicts.json`; round 2 `r2_result.json` (the session's copy; the refuters' summaries in it). Each fix follows the
refuters' corrections where they corrected the finder (R1-3, R1-10, R1-11, R2-24).

This file holds what the shared records must say (ERRORS_AND_SOLUTIONS.md, EXEC.md, CONTRACT.md, DATABASE_SCHEMA.md,
DATABASE_CHANGELOG.md); this track edits none of them (the records track does).

## Migrations (unapplied; forward-only; each refuses a second run and has a `$verify$` block)

| File | What | Why |
|---|---|---|
| `20261119_010_edge_bff_password_identity.sql` | `identities_password` CHECK accepts both verifier forms (`scrypt$<salt>$<hash>` and `scrypt$n=..,r=..,p=..$<salt>$<hash>`); `identities.sign_in_failures` (int, 0) and `identities.sign_in_locked_until` (timestamptz) | R2-29, R1-16 |
| `20261119_011_edge_bff_mfa_pending_enrolment.sql` | `mfa_totp.pending_nonce` (bytea 16), `mfa_totp.pending_created_at`, CHECK `mfa_totp_pending` (both or neither; only beside a confirmed enrolment; never the confirmed nonce); `mfa_recovery_codes.pending` (bool, false) | R1-7 |
| `20261119_012_edge_bff_email_outbox_purge.sql` | indexes `email_outbox_to_email_created (to_email, created_at)` and `email_outbox_unsent (next_at) WHERE status IN ('pending','sending')`; function `edge_bff.purge_email_outbox()` (SECURITY DEFINER, fixed search_path, EXECUTE for edge_bff_runtime only) | R2-35, R2-24 |

All three are in `apps/edge-bff/tests/conftest.py` (after `20261118_002`). `store.ready()` reads their columns and the
function, so an edge-bff of this version is not ready (503 `NOT_READY`) until they are applied: apply them before the
deploy (the house rule of every edge_bff migration). No grant changes: edge_bff_runtime still holds no DELETE on
`email_outbox` (so `20261116_003`'s `$verify$` block and `tests/test_principal.py:210` stay true, and
`scripts/provision_edge_bff_login.py` EXACT_GRANTS needs no change); the purge function is the only delete it can make.

Rollback floor (beta/live, CONTRACT "Production environment" consequences): once an account has signed in with the
switch on under this version, its verifier is of the new form, which an edge-bff before this branch cannot read (it
answers a wrong password). Ship this version to every website that has the switch on before any of them rehashes, and
do not roll back below it afterwards without replacing those verifiers (the rollback comment of `_010` says so).

## Findings, root cause, fix, tests

| Id | Root cause (verified) | Fix | Tests |
|---|---|---|---|
| R1-3 | `config.validate` checked EDGE_OWNER and EDGE_ADMIN_OWNERS only for shape; Orc's test-key owner rule (`market-ai-orc app/conversations.py TEST_OWNER_RE`) was nowhere in edge-bff's start checks | `accounts.ORC_TEST_OWNER` (Orc's pattern, one copy compared with Orc's text by a test) and `orc_reserved_owner` (that rule plus `default`); `validate` refuses it for EDGE_OWNER and every EDGE_ADMIN_OWNERS entry, naming the forms and `edge-private` as the example. Not `reserved_owner` (refuters: it reserves `edge-private`, the live owner) | `test_cp0_reserved_owner.py` (4 re-check cases; added: `edge-private` and four other keys validate, an admin owner is refused, the pattern equals Orc's). Placeholders `'someone-else'` in `admin_owners` of `test_principal.py`, `test_manual_routes.py`, `test_releases.py` renamed `'another-owner'` (they meant "another owner", which Orc reserves) |
| R1-7 | one `mfa_totp` row overwritten in place by any re-enrolment (`confirmed_at` NULL, codes deleted) before the new factor was proved; the permission check was read outside the write | `FlowStore.enroll` decides under the row lock: no confirmed enrolment, the one candidate is replaced (first enrolment, CONTRACT 4); a confirmed one, only an MFA-passed session may start a new one, written to `pending_nonce` and pending recovery codes beside it; `use_step` swaps it in only on a code of the new secret (old recovery codes deleted then). Recovery codes of a waiting enrolment are never accepted | `test_cp1a_phase1_auth_check.py::..f3..`; `test_fix_auth.py::test_the_confirmed_authenticator_works_until_the_new_one_is_proved` |
| R1-8 | the reset's failed codes were counted only under an existing account's user id | new counter `CODE_ADDRESS` (key the address, 20 a day) read and raised for every reset try, account or not; `CODE_USER` kept for accounts | `..f2..` |
| R1-9 | `SIGNIN_LOGIN` keyed by the typed login alone, cleared only by a success; the message said "a minute" | key (normalised login, client address); a reset proved by the email code clears the account's username and email keys of the resetting client and (with R1-16) the account's cap; `SIGN_IN_RATE_LIMIT`'s message carries `{wait}`, filled from `details.retry_after_s` (`errors.message_of`); page fallbacks say "a few minutes" | `..f8..`; `test_fix_auth.py::test_tries_from_another_address_do_not_keep_the_owner_out`, `::test_a_sign_in_limit_says_its_own_wait`; `test_auth_throttle.py` keys moved to the new hash |
| R1-10 | `key_hash` separated keys by scope only, prefixes in a shared scope | `Limit` has a `counter` label inside the HMAC (`scope`, `counter`, key; a tuple key as a JSON list); REGISTER_HOUR and REGISTER_DAY share `register` (refuter: one label per counter); the password change has its own `PASSWORD_CHANGE`; MFA_USER keyed by the user id under its own label. No migration (the scope CHECK is unchanged); existing counts restart once at deploy | `..f1..` (both) |
| R1-11 | the register route always set a fresh registration cookie | `FlowStore.register` returns `keep_held`: nothing made and the browser's own cookie names a pending row of the same address (refuter's qualifier kept, so no other address is revealed) | `..f4..` |
| R1-12 | a `taken` answer after a proved code used no try | both `taken` returns (pre-check and UniqueViolation) raise the code's attempts (consumed at 5) | `..f5..` |
| R1-13 | resends and sign-in restarts of a registration were bounded only by the address's shared budget | `REGISTRATION_MAIL`: one pending registration is mailed at most 3 times a day (its code, resends, restarts), key its user id, in `_issue_code` | `..f6..`; `test_auth_flows.py::test_resend_waits_60_seconds_and_sends_at_most_10_a_day` changed (one registration stops at 3; the address's 10 a day now shown through an account's reset codes) |
| R1-14 | `Login.login` max 200, registration emails up to 254 | `accounts.EMAIL_MAX = 254`, used by `checked_email`, `seed_identity` and `Login` | `..f7..` |
| R1-16 | no per-account consecutive-failure count for the password | `AccountStore.sign_in_try`: one UPDATE decides and counts before the check (the R2-12 lesson); at 100 a 24 h lock, answered as a wrong password (OWASP: same answer); after the lock the count restarts at 90 (as MFA, N2); cleared by a success (in `create_session`), a reset or a change (`_set_password`) and by `scripts/edge_mfa_unlock.py` (now also clears the password count of the account it unlocks). The same statement runs for a login that names no account. Switch on only (see decisions) | `test_fix_auth.py::test_the_100th_..`, `::test_after_the_lock_ends_..` |
| R2-9 | credential writes and session inserts checked no proof in their own transaction and took no common lock | the account's users row is the lock (`AccountStore.lock_account`): `create_session` takes it and checks `proved` (the sign-in's verifier, compare-and-set, also clears the cap and stores `rehash`) or `replaces` (the MFA verify's pending session, revoked in the same transaction); `FlowStore.change` takes it and checks the keep session is live (else 401 `UNAUTHENTICATED`) and the proved verifier (else 400 `CURRENT_PASSWORD_INVALID`); `revoke_all` takes it; reset already did | `test_r2_race.py::test_a_password_change_in_flight..`, `::test_a_sign_in_in_flight..` |
| R2-10 | `_may_send`'s 60 s gap counted every outbox row, notifications included | the gap reads only code purposes (`CODE_PURPOSES`, the purposes of `email_codes`) | `test_r2_race.py::..hold_back..` (both) |
| R2-11 | `use_step` confirmed by user id only | `use_step(user_id, CheckedStep(nonce, step))`: confirms only the enrolment (confirmed, candidate or waiting) whose nonce was checked; else the try counts as a failure | `test_r2_race.py::test_an_mfa_code_confirms_only..` |
| R2-12 | the MFA cap was read in one transaction, restarted in a second, counted in a third | `FlowStore.mfa_try`: decide (and restart after a lock), check, count in one transaction under `SELECT ... FOR UPDATE` of the enrolment; the recovery-code use happens inside it | `test_r2_race.py::test_a_burst_at_the_mfa_cap..` (both cases) |
| R2-24 | the pending purge left every outbox row naming the address; no delete of the outbox existed | `purge_email_outbox()` (rows sent, failed, expired or suppressed, older than 24 h, of addresses with no row in `users`; 10 000 per call) called by `Store.cleanup_sessions` in a transaction of its own after the pending purge | `test_r2_life.py::test_l1..`; `test_fix_auth.py::test_the_outbox_purge_keeps_..` |
| R2-25 | Starlette's ServerErrorMiddleware re-raises after the handler, uvicorn logs the text | `errors.UnexpectedErrors`, the outermost middleware: answers 503 in the contract's shape, logs `request_failed` with method, path, class and SQLSTATE only, never re-raises | `test_r2_life.py::test_l2..` |
| R2-29 | verifiers at N=2^14 r=8 p=1, below OWASP; no recorded cost | `security.COST = (16384, 8, 5)` (OWASP's equivalent at 16 MiB); verifier `scrypt$n=16384,r=8,p=5$<salt>$<hash>`; only the costs in `COSTS` are read; an old verifier is checked at p=1 and padded with p=4, so a check costs the same whatever the verifier's age (M478 N1 kept); a switch-on sign-in with an old verifier stores a new one in its `create_session` transaction; EDGE_PASSWORD_VERIFIER may be of either form. Measured here: p=1 52 ms, p=5 235 ms per derivation (a switch-on sign-in derives 4 times: about 0.9 s of CPU) | `test_fix_auth.py::test_new_verifiers_..`, `::test_a_check_costs_the_same..`, `::test_a_sign_in_replaces_..`, `::test_the_configured_verifier_..` |
| R2-35 | no index for the outbox's hot reads; no purge | the two indexes and the purge (above) | `test_c2_ops_recheck.py::test_the_outbox_reads_..` |
| R2-37 | every derivation ran on the default executor that the database calls use | `passwords.PasswordWork`: 4 threads of its own; at most 16 requests in password work at once (sign-in, register, reset, change), the next one 503 `SERVICE_UNAVAILABLE` with `Retry-After: 5` before any try is counted; the Pwned Passwords call runs there too | `test_c2_ops_recheck.py::test_a_burst_of_sign_ins..`; `test_fix_auth.py::test_a_request_over_the_password_pools_limit..` |

Not fixed here (see decisions and the list at the end): the per-client bound of R2-37 (SIGNIN_IP) and the
auth_throttle growth; R1-9 item 3 (a forgot within a live code's life); the step-up of R1-7.

## What the shared records must say

### ERRORS_AND_SOLUTIONS.md

One entry per finding above (or one entry with sub-items R1-3 ... R2-37), each: symptom (the finding's failure
scenario), verified root cause (column 2), solution (column 3, commit on `fix-auth`), status "fixed on branch fix-auth,
not deployed; migrations 20261119_010/011/012 not applied", tests (column 4). Also:
- M478 N4 corrected: "registrations by others use at most 3 of the address's 10 daily emails" was false (R1-13). Now: a
  new registration of an address mails it at most once an hour and 3 times a day, and one registration is mailed at
  most 3 times a day, so the registrations of others use at most 6 of the 10 once the owner has registered.
- Part D lessons (new data and new limits):
  - a limit keyed by a public identifier needs a proof-based way out and should be keyed with the client too (R1-9);
  - every counter gets its own label inside the key hash, never a text prefix in a shared scope (R1-10);
  - a cap on a value anyone may type must count alike whether or not an account exists (R1-8);
  - a security setting is replaced only once its replacement is proved (R1-7);
  - a write authorised by an earlier proof checks the proof under a lock in its own transaction (R2-9, R2-11);
  - a cap is decided and counted under one lock (R2-12, R1-16);
  - a send gate counts only the sends it exists for (R2-10);
  - rows naming a person by value need their own purge (R2-24);
  - framework logging of unexpected exceptions bypasses an app's redaction (R2-25);
  - CPU-heavy unauthenticated work gets its own bounded pool (R2-37);
  - a verifier names its cost so the cost can change (R2-29).

### CONTRACT.md

- Section 1: `identities` (both verifier forms, `sign_in_failures`, `sign_in_locked_until`); `auth_throttle`
  (`key_hash` = HMAC of scope, counter label and key); `mfa_totp` (`pending_nonce`, `pending_created_at`);
  `mfa_recovery_codes` (`pending`); `email_outbox` (the two indexes; rows of an address with no account deleted 24 h
  after they were made by `purge_email_outbox()`; the runtime holds no DELETE).
- Section 3: `SIGN_IN_RATE_LIMIT`'s message says the wait; a request over the password pool's limit is 503
  `SERVICE_UNAVAILABLE` with `Retry-After` (details `retry_after_s`).
- Section 4 "Throttle": sign-in 10 failures per login and client address per 15 min (enforced; was per login); per
  account at most 100 consecutive failed passwords, a 24 h lock answered as a wrong password, restart at 90, cleared
  by success, reset by email code (which also clears the resetting client's per-login counts) or change; per-IP still
  recorded only until the probe. "Codes": the 20-a-day cap also per address for resets; `USERNAME_TAKEN` uses one of the
  code's 5 tries; one registration mailed at most 3 times a day; the 60 s gap is between code emails only.
  "Registration rules": "stored with scrypt as today" becomes "scrypt N=2^14, r=8, p=5 (OWASP's minimum equivalent;
  the fix round's brief, R2-29; decision 5 below asks the user to confirm the CPU cost), the verifier naming its cost;
  an old verifier (p=1) is replaced at the next sign-in". "Sessions": a reset, a change, a sign-out everywhere, a sign-in and an MFA verify serialise on the
  account's users row; a sign-in or verify whose proof no longer holds is refused. "Admin MFA": a confirmed enrolment
  is replaced only by an MFA-passed session and only once a code of the new authenticator proves it.
- Section 5: outbox retention as above (and the open decision for addresses with an account).

### DATABASE_SCHEMA.md and DATABASE_CHANGELOG.md

The three migrations as "written, not applied" (columns, CHECKs, indexes, function and its grant as in the table
above). After they are applied on dev: the read-back (columns present, `identities_password` validated,
`purge_email_outbox` SECURITY DEFINER with `search_path=pg_catalog, edge_bff`, EXECUTE for edge_bff_runtime only, no
DELETE on `email_outbox` for edge_bff_runtime) and the plan evidence below. Not a large update (empty or tiny tables
on dev with the switch off): no Postgres restart.

### EXEC.md

The fix round's status for this track (the commit, the unapplied migrations, the decisions below asked of the user).

## Plan evidence (R2-35, AGENTS.md "Performance")

`tests/test_c2_ops_recheck.py::test_the_outbox_reads_of_every_send_and_every_sender_turn_use_an_index` EXPLAINs the
real SQL of `OutboxStore.claim` (two UPDATEs and the SELECT ... FOR UPDATE SKIP LOCKED) and `FlowStore._may_send` at
20 000 sent rows: no Seq Scan on `email_outbox` with migration `_012` (it failed on all four before). The finder's
measurement at 500 000 rows without the indexes: 30-54 ms and 8 367 buffers per statement.

## Decisions for the user (asked with context; nothing was guessed)

1. Retention of the outbox rows of addresses that have an account (and of consumed email codes and webhook events).
2. The password cap on the beta website (switch off), where there is no reset.
3. A "Forgot password?" asked again while a code is live (R1-9 item 3) and the shared daily email budget.
4. Re-authentication before an admin starts setting up a new authenticator (R1-7 step-up).
5. Confirm the scrypt cost (R2-29): built at OWASP's minimum equivalent, about 0.9 s of CPU per switch-on sign-in.

The facts and options of each are in the final report of this track (decisions_needed).

## Not fixed in this track, and why

- R2-37, the per-client bound: enforcing SIGNIN_IP (30 failed sign-ins per client address per 15 min) needs the
  Railway client-address probe (CONTRACT 4 "Client IP", a Phase 0 runbook step) first: if Railway's edge does not set
  the right-most X-Forwarded-For hop, every client shares one address and an enforced per-address limit becomes a
  lock-out of everyone. The probe is a Railway call, outside this track. The refuters rejected a global cap meanwhile
  (anyone could drive it). The bounded password pool already keeps a flood from stalling the signed-in users.
- R2-37, the auth_throttle growth (one row per made-up login) and its hourly purge as a full scan: the batched purge
  in its own transaction belongs with R2-33 (the cleanup that stops the run queue), another track's finding; a
  window_start index waits for that design and its measurement.
- R2-25 in terminal-api (no Exception handler; 3c's per-owner writes): the same middleware is needed there; terminal
  track (apps/terminal-api is not this track's code).
- R1-9 item 3 and R1-13's remaining shared budget: decision 3.
- R1-7's step-up: decision 4. The re-check's own test (`..f3..`) starts a re-enrolment with no body from an MFA-passed
  session and expects 200, so a code in the body would contradict it; the waiting enrolment (built) closes the
  finding's take-over path.
- R2-10's side note: a `password_changed` email is not counted in SEND_EMAIL (a session holder can mail the owner once
  per change); not changed (no finding asks it; decision 3 covers the budget).
