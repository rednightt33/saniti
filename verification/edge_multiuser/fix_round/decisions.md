# Fix round of the ultracode re-check: track `decisions` (the small decisions of 2026-11-19)

Branch `dec-small` from `fix-int` (`9a22ee75`). Nothing was pushed, deployed or applied to a remote database, and no
Railway call was made; migration `20261119_012` (unapplied) ran only on the disposable cluster `dec_small` (port 55572).
The user's words are in EXEC.md EXEC-MU-ACCOUNTS ("Decisions from the fix round" item 2, "Decisions after the fix
round" items 1-7 and the design values the main agent took; on the session branch `claude/pensive-feynman-4ahfe3`,
`f2562fbf`; `fix-int`'s own EXEC.md predates that section, so this track did not edit EXEC.md). The user's message that
started this run: "1a 2a 3a 4 leave as is, ini setau saya untuk ai bisa lihat log untuk proses enhancement di belakang
5a pakai inter 6 ok rekomendasi 7 ok".

## Commits

| Commit | What |
|---|---|
| `a3eaaae4` | email retention 30 days (migration `20261119_012`, `store.PURGES`); a recent MFA pass for a new authenticator; `public_data` on the Terminal relay (M260) with its route walk |
| `36dbe227` | the `/mfa` page test of the ten-minute re-check |
| `389673d3` | R1-35 ("1a"): the Screener attributes every answer shows are not gated by id; one definition in the Screener catalog |
| `09d7fc42` | R2-28 ("5a pakai inter"): Inter served by EDGE itself; no Google Fonts; CSP `font-src 'self'` |
| `e58d1578` | CONTRACT.md records of R1-37/R2-41 item 4, R1-18, R1-2, R2-27, R2-41 item 9 and of what this track built |

## 1. Email retention, 30 days ("Decisions from the fix round" item 2: "a")

- Root cause of the gap: the auth track's purge (R2-24) deleted only the rows of an address with no account; no rule
  bounded the rows of an account's address, the used email codes or the webhook deliveries (`email_hook_events`, where
  `edge_bff_runtime` holds SELECT and INSERT only).
- Fix, at the layer that owns each table:
  - `database/migrations/20261119_012_edge_bff_email_outbox_purge.sql` (unapplied, so changed in place; its two indexes
    and the EXECUTE grant kept): `purge_email_outbox(max_rows)` also deletes every sent, failed, expired or suppressed
    row made more than 30 days ago, whatever the address; a pending or sending row is never deleted. New
    `purge_email_hook_events(max_rows)` (SECURITY DEFINER, `search_path=pg_catalog, edge_bff`, EXECUTE for
    `edge_bff_runtime` only, at most 10 000 per call) deletes deliveries received more than 30 days ago (Svix retries
    for days; the signature tolerance is 5 minutes). The `$verify$` block checks both functions and that the runtime
    holds no DELETE or TRUNCATE on the outbox or the deliveries.
  - `app/accounts.py` `purge_codes` (`EMAIL_RETENTION_DAYS = 30`): a code no longer usable, used (`consumed_at`) or
    expired unused (`expires_at`), 30 days after it ended; a live code is never deleted, so the one-live-code index
    and the five tries are unchanged. The runtime already holds DELETE on `email_codes` (20261116_003).
  - `store.PURGES` gains `codes` and `hook_events` after `outbox`, each a housekeeping batch in its own transaction
    with the try-lock of the other website; `store.ready()` checks the new function.
  - `email_suppression` is never purged (decision R2-27 below).
- Reading recorded: "used codes" taken as codes that can no longer be used (used or expired); an expired, never used
  code is not personal beyond its user id and was otherwise kept until the next code of its purpose.
- Tests: `apps/edge-bff/tests/test_decisions_small.py` (31 and 29 days on each side of each rule, run as a login with
  `edge_bff_runtime`'s grants only; the batch bound of each new purge; the grants and the function attributes).
  `tests/test_beta_live_site.py` changed with the decision: the set of purges is six, not four.
- Records: CONTRACT sections 1 (the `email_codes`, `email_outbox`, `email_suppression` rows and a new
  `email_hook_events` row) and 5; `apps/edge-bff/README.md` (account flows).
- For the records track / main agent: DATABASE_SCHEMA.md and DATABASE_CHANGELOG.md list `20261119_012` with the second
  function; its read-back after APPLY adds `purge_email_hook_events` (SECURITY DEFINER, fixed search_path, EXECUTE for
  `edge_bff_runtime` only) and `has_table_privilege('edge_bff_runtime', 'edge_bff.email_hook_events', 'DELETE')` false.
  The edge-bff of this branch is not ready (`store.ready`) until `_012` is applied, as before.

## 2. A new authenticator needs an MFA pass within the last 10 minutes (the main agent's design value)

- Root cause: R1-7's fix let any session that had ever passed MFA start a re-enrolment (`principal.mfa_ok`), so a
  session hours old (an unlocked computer) could start replacing the second factor.
- Fix: `FlowStore.enroll(user_id, nonce, hashes, session_hash)` decides under the enrolment's row lock (the R2-9 rule:
  the permission is part of the write): beside a confirmed authenticator the request's own session must be live and
  have `mfa_passed_at > now() - MFA_RECENT_SECONDS` (600, the database's clock). Otherwise 403 `MFA_REQUIRED` with
  `details` `{mfa_enrolled: true, recent_s: 600}`; `errors.words` gives the sentence ("Setting up a new authenticator
  needs a code from your current one entered in the last 10 minutes. Enter the code ..., then start the set-up
  again."). `POST /api/v1/auth/mfa/verify` already makes a session passed now. The first enrolment is unchanged.
- Page (`static/edge-app.js` `MfaForm`): after that refusal the code form's success starts the set-up again instead of
  leaving `/mfa`. The words come from the server (the shell shows the server's sentence first); no label changed.
- Tests: `test_decisions_small.py` (within, past and after a fresh code; the first enrolment; the page in Chromium). The
  re-check's own `test_cp1a_phase1_auth_check.py::test_cp1a_f3...` (a re-enrolment right after a verify) and
  `test_fix_auth.py::test_the_confirmed_authenticator_works_until_the_new_one_is_proved` pass unchanged.
- Records: CONTRACT section 4 "Admin MFA"; README (MFA paragraph). EXEC.md already records the value (session branch).

## 3. `public_data` on the Terminal relay's successful JSON answers (ERRORS M260, "a")

- Root cause (M260): `forward_terminal` and the page index relayed terminal-api's JSON as received; only the Orc and
  worker relays passed theirs through `client.public_data`.
- Check first (M260's condition): no page module and no forwarded terminal-api route reads or answers a key of
  `PRIVATE_KEYS` (scan of `apps/edge-bff/{terminal,backtest,watchlist,overview,radar}/src`, `apps/terminal-api/app`
  and `apps/terminal-publisher`: only terminal-api's admin and sign-in routes name `password`, and neither is
  forwarded); presigned URLs are on the public bucket host, never `*.railway.internal`.
- Fix, in the one rule: `terminal_access.relayed` returns `(refusal, data)`: `(None, public_data(data))` for an
  acknowledged 2xx (None stays None: a cut's bytes and a logo are relayed as they are), `(Refusal, None)` otherwise.
  Callers: `main.py` `forward_terminal` and `relay_cut`, `pages.py` `index` (filtered) and the file grant (its
  presigned URL is read by edge-bff only, so the unfiltered answer is used; the page gets the checked bytes).
- Tests: `test_decisions_small.py` walks every route holding `terminal_access.guard` (derived from the app) with one
  sample per alternative of `main.TERMINAL_ROUTES` (derived, so a new kind of path fails until it has one), a stand-in
  terminal-api planting private keys and an internal address in every answer; none reaches a page, the public fields
  stay; a self-test finds the plants once the filter is taken out. `tests/test_terminal_fix_round.py` changed with the
  decision: `relayed` returns the pair, so its two direct calls unpack it (the refusals asserted are unchanged).
- Records: CONTRACT decision 6 of 2026-11-19; README (terminal-api's answers). For the records track: ERRORS M260 to
  "fixed on branch dec-small, not deployed".

## 4. R1-35: Screener conditions on the attributes every result row and `/universe` show ("1a")

- Root cause: O3b-2 exempted the universe chips only; `run.ts` `definitionItems` still gated `{kind: 'universe', attr}`
  by id, while `/universe` sends `last`, `chg_1d_pct`, `adv20_idr`, `bars` and the index memberships of every listed
  stock and every result row repeats `last`, `chg_1d_pct`, `adv20_idr`; the page's extra-column anchor `bars gt 0`
  needed `screener.metric:bars`.
- One definition, derived from the catalog: each universe entry of `screener-metrics.json` whose value a `/universe`
  row carries names that row field (`"row"`: `last`, `chg_1d_pct`, `adv20_idr`, `bars`, and `index_membership` ->
  `indices`). Core `catalog.ts` `SHOWN_ATTRIBUTES` reads it (and `catalogProblems` checks it); edge-bff reads the same
  file (`app/catalog.py` `shown_attributes`; the Dockerfile copies `screener/src/core/screener-metrics.json` beside
  `app/`, and `test_backtest.py`'s image COPY list gains it).
- Consumers: screener-worker `definitionItems` skips them; edge-bff `catalog.ungated` is the one rule of
  `allow.allow_of` (every principal's `screener_metric` list holds them) and `catalog.holds_entry` (the catalogs list
  them; a lab-stage one is still not held on the live site).
- Tests: `apps/screener-worker/tests/shown.test.ts` holds the definition to the rows the worker answers, both ways (every
  `/universe` row carries each named field, with the stock-lists file; no `/universe` or result row carries a universe
  attribute the catalog does not name), and screens on each with `screener_metric: []` (`index_membership` is
  REQUIRES_DATA, never refused by the plan). `tests/allow.test.ts` changed with the decision: `FULL`'s first metric
  filter (`chg_1d_pct`) is no longer an item, so an indicator filter (`I07` `adx`) covers that place; the `adv20_idr`
  My metric passes without a grant and a `return_rank` one is refused; the extra-column anchor passes with
  `screener_metric: []`. edge-bff `test_decisions_small.py` (the set, the allow and the catalog). SCREENER_ONBOARDING.md
  pointers moved with the edited lines; the `row` field is listed there.
- Not changed, noted: the four transform metrics (`hi52`, `lo52`, `rs`, `vol_ratio`) are not gated by the worker (no id
  on the wire) but edge-bff's catalog still lists them by grant; a menu built from `/api/v1/catalog` (3e) would hide
  them for a plan without them. Outside this decision; for 3e.

## 5. R2-28: Inter served by EDGE itself ("5a pakai inter")

- `apps/edge-bff/static/fonts/`: Inter 4.001 (`Copyright 2016 The Inter Project Authors`, read from the files' name
  table; Google Fonts v18, the files Google served) from `@fontsource-variable/inter` 5.2.5 (npm), the variable weight
  axis, normal style, in Google's seven subsets (the browser loads only what a page's text needs; the Terminal loads
  the latin file alone), `OFL.txt` (SIL Open Font License 1.1 with the Inter copyright line). Two sheets, one per
  weight range the pages asked Google for: `inter-400-700.css` (shell, Backtest, Screener, Radar, Overview,
  Watchlist) and `inter-400-600.css` (the Terminal: its 700 text drew at 600 before, and still does).
- `app/main.py`: `GET /fonts/{name}` (a name pattern inside `fonts/`, `font/woff2`, `text/css`, `text/plain`, a day's
  public cache); every CSP is `style-src 'self' 'unsafe-inline'; font-src 'self'`.
- Every page's `index.html` and the shell's `@import` name the sheet; no page, stylesheet or module names a Google host
  (three CSS comments of the mockup head were reworded). The pages' browser scripts (smoke, visual) stub or serve
  `/fonts/` as they did Google Fonts; the Terminal visual compare serves EDGE's own files to the built page.
- The Terminal look check: `verification/terminal_api/terminal_look/serve.mjs` (the EDGE stand-in) serves `/fonts/` as
  edge-bff does; `node verification/terminal_api/terminal_look/look_check11.mjs` on the rebuilt Terminal: **PASS**,
  `errs []`, with Inter loaded from `/fonts/inter-400-600.css` and `inter-latin-wght-normal.woff2` (checked in the
  browser: `document.fonts.check('600 12px Inter')` true).
- Tests: `test_decisions_small.py` (no Google host anywhere, each page's sheet, every policy, the files, the licence,
  refused names). `tests/test_contract_records.py` changed with the decision: the walk must no longer find
  `fonts.googleapis.com` (it asserted it was there).
- Records: CONTRACT section 18 (Google Fonts no longer a recipient); README (front-end layers, the Backtest CSP).
- Left for the main agent: `.claude/skills/edge-design-system/assets/spec-v1.2.css` still `@import`s Google Fonts; a
  new page built from it would fail the test above. Changing the design system rebuilds its claude.ai copy (a remote
  publish, outside this track).

## 6. CONTRACT.md records

- R1-37 and R2-41 item 4 ("2a"): 8b "What the Terminal data limits bind" and section 15 (the Watchlist's flow keys):
  the flow rule does not cover the Overview and Watchlist foreign-net columns; nothing changes until a plan closes flow.
- R1-18 ("3a"): section 4b, the user's decision replaces the computed task's reading.
- R1-2 ("leave as is"): sections 7 and 16: the key stays for the agents' improvement jobs; section 18 names that reach
  (with the switch on, every user's conversations); `pending/README.md` gives the reason the test stays there.
- R2-27 ("ok rekomendasi"): section 10's deletion table: `email_suppression` keeps the address and reason; Phase 5
  payment records kept pseudonymised for the legal period.
- R2-41 item 9 ("ok"): section 10: a person on another browser registers again.
- A block "Decisions after the fix round" beside the decisions of 2026-11-19 lists all seven with where each is.

## Later commits

| Commit | What |
|---|---|
| `98534d22` | CONTRACT section 4's enrol route row marks the ten-minute pass built |
| `f56fb659` | SCREENER_ONBOARDING.md pointers into edge-bff `main.py` moved with the font lines |
| `d5229ebf` | `test_backtest.py`: a queued job's allow at dispatch holds the shown attributes (the expectation changes with "1a") |

## Suites (cluster `dec_small`, port 55572; Chromium `/opt/pw-browsers/chromium`)

| Suite | Result |
|---|---|
| edge-bff pytest, full `tests/`, with Postgres and Chromium (app code of the final head) | 900 passed, 3 failed: `test_backtest.py::test_a_queued_job_reads_its_owners_rights_when_it_is_dispatched` (its expectation changed with "1a", `d5229ebf`; passes alone since), `test_composer_layout.py::test_submit_history_and_fixed_headers[mobile]` and `[mobile-small]` (the known flaky test; alone they pass 1 of 3 and 1 of 2; with the shell's old Google Fonts import restored for the comparison, `[mobile]` alone fails 2 of 4 as well, so the self-hosted font does not cause it: "element is not visible" on the history drawer after a reload) |
| terminal-api pytest (`TERMINAL_TEST_POSTGRES_URL` a database with the terminal migrations `20261025_100`, `20261026_100`, `20261028_100`, `20261118_100` and stand-in market tables) | 160 passed |
| backtest-worker `npm test` | 277 passed (a first run beside the edge-bff suite: 276, the timing test "a job over BACKTEST_TIMEOUT_SECONDS ends FAILED TIMEOUT" failed under load and passes alone and in the rerun) |
| screener-worker `npm test` | 131 passed (with `tests/shown.test.ts`; the first run found the SCREENER_ONBOARDING pointers into `main.py`, fixed in `f56fb659`) |
| market-ai-orc pytest with `ORC_TEST_POSTGRES_URL` | 2202 passed |
| page vitests: terminal / backtest / screener / radar / overview / watchlist | 968 / 91 / 1355 + 1 skipped / 8 / 22 / 22 passed (the screener's golden grammar test timed out at 5 s once under load; alone 1.3 s, and the full rerun passed) |
| page builds (all six, `npm run build`) | OK; Vite notes `/fonts/inter-*.css` stays to be resolved at run time (edge-bff serves it) |
| `scripts/tests` pytest (the generated-file tests included) | 94 passed, 1 skipped (`test_sync_database_schema_status.py`: `SCHEMA_TEST_POSTGRES_URL` not set) |
| `node shared/build-shell.mjs --check` (apps/edge-bff) | OK |
| `node verification/terminal_api/terminal_look/look_check11.mjs` on the rebuilt Terminal | PASS, `errs []`, Inter loaded from `/fonts/` |

Not run: the page smoke and visual scripts whose font stub changed (backtest `npm run smoke`, `tests/visual/*`, the
screener smoke scripts); `node --check` passes on each, and their stub regex matches the `/fonts/` sheet and Google's
hosts. `apps/market-python-sandbox` generated-file tests cannot collect here (`duckdb` is not installed); the track
does not touch it.
