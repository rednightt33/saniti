# Fix round of the EDGE multi-user re-check: track "terminal" (Terminal path, Phase 3c builds on it)

EXEC-MU-ACCOUNTS, re-check of Phases 0-3b (user 2026-11-18: "Cek juga fase sebelumnya"), fix round. Branch
`fix-terminal` from `97b4ecb5` (p3c-int plus the re-check's failing tests). Nothing deployed, no migration applied, no
Railway call, no remote database. The findings and the three refuters' verdicts:
`verification/edge_multiuser/access_tiers/recheck/r1_findings.json`, `r1_verdicts.json` and round 2's `r2_result.json`.

Findings of this track: R1-1, R1-26, R1-22, R2-4, R2-5, R2-32, R1-4, R1-5, R1-31, R1-36.

## Commits

| Commit | What |
|---|---|
| `88d75b8e` | terminal-api: every 429 names its quota, limit, window and wait (`retry_after_s`, `Retry-After`) |
| `e5f0c181` | terminal-api: unknown dataset ids left out (R2-5), `history_days` 0 taken (R1-22), the applied-header echo (R2-4) |
| `d959a594` | terminal-api: reference files filtered to the plan (R2-32), the gateway account on `/ready` (R1-4) |
| `570e607c` | edge-bff: one relay rule for every terminal-api answer; the header mapping; PageFiles headers before the caches |
| `0713d505` | edge-bff: tests of the relay rule, the acknowledgement, history 0, the caches, the reference relay |
| `eaa7bc28` | migration `20261119_050` (not applied): a value domain per capability, read by the value trigger (R1-22) |
| `9b83ea19` | the free plan's Terminal draws BBCA (R2-32): e2e fake answers with terminal-api's own code; `live.ts` words |
| `f82419c0` | `SCREENER_ONBOARDING.md` pointers moved with the lines of both `main.py` files |
| `34edaafa` | `apps/edge-bff/README.md` follows the changes |

## Per finding

### R1-1 (blocks-3c): terminal-api's 401 and 429 reached the page as they were

- **Root cause (verified):** `forward_terminal` ended with `JSONResponse(status_code=answer.status_code, content=data)`
  (base `apps/edge-bff/app/main.py:588`) and `relay_cut` did the same for a non-200 (base `:613`). Only terminal-api's
  `capability_required` was mapped (`terminal_access.answered_capability`). terminal-api's 401 (`session_ended` when the
  gateway or owner row is unusable, `proxy_key_rejected` on a rotated key) is about its own account, never the EDGE
  session, yet the page's shared module reads any 401 as a sign-out (`shared/edge-session.ts` `readError`). Its 429 had
  no `Retry-After`, no `LIMIT_REACHED` and no structured quota name (base terminal-api `main.py:529-531`, `quota.py`
  `Refusal.message()` text only).
- **Fix (the general class, one helper):** `apps/edge-bff/app/terminal_access.py` `relayed(p, status, data, headers,
  where)` (`:303`) is the one rule of `forward_terminal`, `relay_cut` and `PageFiles` (`main.py:562`, `:611`;
  `pages.py` `index`, `page_file`). A 401, or a 403 other than `capability_required`, is 503 `TERMINAL_UNAVAILABLE`
  logged (`terminal_refused`, status and code); a 400 about the owner headers edge-bff built (`OWN_HEADER_CODES`) and
  every 5xx too; a 429 is 429 `LIMIT_REACHED` with `details.limit` `terminal.<quota>`, `details.allowed`,
  `details.retry_after_s` and `Retry-After`; a 400 about the request is 400 `INVALID_INPUT` and a 404 404 `NOT_FOUND`,
  each with terminal-api's code as `details.reason`; `capability_required` stays 403 `CAPABILITY_REQUIRED` with its
  display name. terminal-api's prose never reaches the page. terminal-api's side: `main.py` `take()` (`:555`) raises
  `quota_exceeded` with `quota`, `limit`, `window`, `retry_after_s` and the header (`wait_error`, `:213`); the wait is
  `store.frees_in` (when the rolling window lets the refused request fit, read only on a refusal; at most the window).
  The service ceiling (`seconds_left`) and the sign-in throttle (900 s) send `Retry-After` too.
- **Page:** `terminal/src/data/live.ts` `api()` shows the contract's words of a relayed refusal instead of its code.
- **M260 (public_data):** not applied. By construction no terminal-api refusal text reaches the page any more (every
  refusal is rebuilt by edge-bff); `public_data` on the 2xx bodies needs the user's go (ERRORS M260 "needs the user's
  go"; spec refuter of R1-1). Listed under decisions.
- **Tests:** `tests/test_cp0_terminal_relay.py` (the re-check's, 2 now pass); `tests/test_terminal_fix_round.py`
  `test_every_terminal_api_answer_maps_onto_the_contract` (16 cases), `test_a_relayed_refusal_reaches_the_page_and_the_
  session_stays`; terminal-api `tests/test_terminal_fix_round.py` (the 429 fields, `frees_in` on PostgreSQL 16).
- **Tests changed (they locked the pass-through CONTRACT section 3 forbids; the refuters named them):**
  `tests/test_terminal.py` `test_gateway_needs_the_edge_session_and_csrf_for_writes` (`:84`, now `LIMIT_REACHED` with
  `Retry-After`), `test_gateway_leaves_the_reference_names_to_terminal_api` (404 in the contract shape, the code as
  `details.reason`); `tests/test_terminal_access.py` `test_a_cut_terminal_api_refuses_passes_through` renamed
  `..._reaches_the_page_in_the_contract_shape`.

### R1-26 (blocks-3c): two 429s without Retry-After (page files and the gateway relay)

- **Root cause (verified):** `PageFiles` answered a grant's 429 `failure('QUOTA', 429)` with no header and a family
  code outside the section 3 table (base `pages.py:175-176`); `forward_terminal` dropped every terminal-api header; and
  terminal-api sent none.
- **Fix:** the same helper: a page-file grant's 429 is `LIMIT_REACHED` with `Retry-After` (`pages.py page_file`); the
  `QUOTA` message is gone. terminal-api sends the header and the fields (R1-1).
- **Tests:** `tests/test_c_p3a_probes.py -k retry_after` (the re-check's, 2 now pass). **Changed:** `tests/test_radar.py`
  `test_refusals_name_the_cause_and_the_way_out` (`:123-125`, now `LIMIT_REACHED` with its details and `Retry-After`),
  named by the refuters; its `FakeHttp` answers the 429 with terminal-api's new fields.

### R1-22 (blocks-3c): values the catalog accepts broke the 3c header

- **Root cause (verified):** the catalog held one domain per kind (`20261117_003` `capability_value_check`,
  `principal.valid_value`), the read side maps an unreadable limit to 0 (`principal.RESTRICTIVE`), and
  `terminal_access.capabilities` copied `history_days` and the tickers into the header with a type check only, while
  terminal-api takes `history_days` 1-36600 and tickers `^[A-Z0-9]{1,12}$` (base `entitlements.py`) and answered every
  call of such an account 400 `invalid_owner_headers`.
- **Fix, read side (needed whatever the catalog holds):** `capabilities` (`terminal_access.py:128`) maps every value
  onto the wire: `history_days` above `MAX_HISTORY_DAYS` is the bound; 0 is sent as 0, which terminal-api now takes as
  the empty window (`entitlements.MIN_HISTORY_DAYS`), and `check` (`:230`) refuses every dated path (`files`, `bundle`,
  `cut`, `history`) first with 403 `CAPABILITY_REQUIRED` `terminal.history_days`, so the page files, which carry no
  history window, keep working (the code refuter's correction); a ticker outside the rule is left out and logged
  (`terminal_tickers_dropped`, the count only). The same class (refuters' other sites): a quota of 0 is now 403
  `CAPABILITY_REQUIRED` naming the limit, not 429 with `Retry-After` 3600 (waiting would not help).
- **Fix, catalog (data model):** migration `database/migrations/20261119_050_edge_bff_capability_domains.sql` (not
  applied; in the test harness, `tests/conftest.py`): `edge_bff.capabilities` gains `value_min`, `value_max` and
  `item_pattern`; `capability_value_check` (replaced, the shape checks and their hint unchanged) refuses a value outside
  them with a hint that names the domain and an example; `capability_domain_holds` refuses a domain a stored value would
  no longer fit; `$verify$` checks the six domains, every stored value, the triggers and the privileges. Domains:
  `terminal.history_days` 1-36600, `terminal.tickers` 0-500 items of `^[A-Z0-9]{1,12}$` (500 names of 12 characters fit
  the 8 KiB header, so the "list of about 900 tickers gives 503 for every call" site is closed at write time), the four
  Terminal quotas 1-10^9. Every other capability keeps no domain (R1-29 may set `value_max` = HARD in its own migration).
- **Tests:** `tests/test_c_p2_terminal_wire_domain.py` (the re-check's, 6 now pass); `tests/test_terminal_fix_round.py`
  (history 0 on every path, dropped tickers, the domains at write time for plans and overrides, the domain change, the
  domains equal to terminal-api's bounds and the widest value fits the header, the migration's second run and verify).
  **Changed:** `tests/test_phase2_fix_round.py` `test_a_value_of_the_right_shape_is_written`: `('terminal.history_days',
  '0')` is now `'1'` (the spec refuter: "Update test_phase2_fix_round.py's 'history_days 0 is right' case if (2) refuses
  0"); `tests/test_terminal_access.py` `test_quota_bounds_and_the_owner_key_rule` (quota 0 is 403); terminal-api
  `tests/test_phase3c.py` `BAD`: `history_days` 0 (now accepted) became -1 and 36601.

### R2-4 (blocks-switch-on): no acknowledgement of the applied header

- **Root cause (verified):** the deployed terminal-api ignores the owner headers; edge-bff relayed whatever came back
  and refused first only a request whose tickers or every dataset were locked, so a terminal-api below 3c would serve a
  capped principal in full.
- **Fix:** terminal-api's middleware (`main.py:255`) sets `x-terminal-capabilities-applied: 1 <version>` on every
  answer to an owner call, refusals included (`entitlements.APPLIED_HEADER`, `applied()`); `terminal_access.relayed`
  refuses an answer for a principal without `*` that lacks it (or names another version) with 503
  `TERMINAL_UNAVAILABLE`, logged `terminal_capabilities_not_applied`, on the JSON relay, the byte relay, the logo and the
  page files. The switch-off owner holds `*` and needs none, so deploy steps 1-5 of 3c do not change.
- **Tests:** terminal-api `test_every_answer_to_an_owner_call_carries_the_applied_version`; edge-bff
  `test_a_terminal_api_that_ignores_the_header_never_serves_a_capped_principal` (a fake pre-3c terminal-api),
  `test_the_switch_off_owner_needs_no_acknowledgement`, `test_the_acknowledgement_is_the_version_of_this_principal`.
  The fakes that stand in for terminal-api (`tests/test_radar.py` `acknowledge`, `tests/test_terminal_access.py`
  `FakeApi`, `tests/e2e_people.py`) now acknowledge as terminal-api does.

### R2-5 (non-blocking): one unknown dataset id failed every call

- **Root cause (verified):** `parse_capabilities` refused a `datasets` entry this terminal-api did not know (base
  `entitlements.py` `ids(... known=...)`), and edge-bff expands `{all: true}` over its compiled `DATASET_IDS`.
- **Fix:** the unknown id is left out (`Capabilities.ignored`) and logged (`owner_datasets_ignored`); it is not served
  anyway, so this fails closed. Unknown fields, quota names and `v` are still refused.
- **Tests:** terminal-api `test_an_unknown_dataset_id_is_left_out_and_logged`. **Changed:** `tests/test_phase3c.py`
  `BAD` `['price', 'options']` (now left out) became `['price', 'Options']` (breaks the id rule, still refused).

### R2-32 (blocks-3c per the finder; switch-on per the refuters): the free plan's Terminal drew nothing

- **Root cause (verified):** `live.ts liveData` awaits the ticker list before it draws, and 3c refused every reference
  file to a plan without `terminal.dataset:reference` (base `terminal_access.check` `head == 'reference'`).
- **Fix (option a, the task's reading of D3 = B, "tanpa daftar ticker": no list of other tickers):** terminal-api
  answers an owner whose plan lacks the dataset `reference` with its own copy of each reference file
  (`apps/terminal-api/app/refcut.py`, derived from each file's columns: a `ticker` column keeps the plan's tickers; the
  broker list keeps every row only with `broker`, `BY_DATASET`; any other file, the stock lists today, has no rows),
  announced in the shape of a cut (`/api/terminal/v1/reference/<name>/cut?sha256=<hex>`, `expires_in_seconds` 0) and
  served by `GET /reference/{name}/cut` (`main.py:777`), counted when served (one file, one audit row `refcut/<name>/
  <sha256>`), built from the published file checked against its sha256, deterministic gzip, cached per (name, source,
  plan filter). A file that cannot be filtered is 503 `reference_unavailable`, never served whole. With `reference` the
  plan gets the published file as before (the full lists). edge-bff forwards `reference/*` (no refusal) and relays the
  copy byte for byte (`main.py` `TERMINAL_BYTES`). `ROUTE_ACCESS` marks both reference routes `filtered`. The page draws
  as it does today; `live.ts` only names a plan whose list holds no published ticker instead of failing on `tickers[0]`.
- **Tests:** `tests/test_c2_e2e_people.py::test_the_free_plans_terminal_draws_bbca_with_the_answers_phase_3c_gives_it`
  (the re-check's) now passes; its answer set changed as the test itself says ("A fix on the 3c side changes the answers
  set below to the ones 3c then gives this principal; the assertion stays"): the e2e fake now answers the header
  edge-bff really sends with terminal-api's own code (`e2e_people.py` `terminal_api()`: `entitlements`, `refcut`,
  `cut`), and the test also checks that the copies and the cut came through edge-bff and no full list was downloaded.
  New: `test_the_free_plans_terminal_opens_on_bbca_with_nothing_remembered` (the task's "add a test that the free plan
  draws BBCA": no stored ticker, the default MAPI refused, BBCA drawn, no other ticker shown). terminal-api
  `test_the_free_plan_gets_reference_lists_that_name_its_own_tickers_only`, `test_the_broker_list_follows_the_broker_
  dataset_and_the_full_lists_follow_reference`, `test_a_reference_file_that_cannot_be_filtered_is_refused_not_served_
  whole`, `test_every_reference_file_the_publisher_writes_has_its_rule_here` (walks `publisher.py REF_NAMES`); edge-bff
  `test_the_plans_copy_of_a_reference_file_is_relayed_byte_for_byte`. **Changed (3c's own tests, the design changed):**
  `tests/test_terminal_access.py` `FREE_REFUSED` lost `reference/tickers` and `reference/logos`, now in `FREE_FORWARDED`
  with `reference/tickers/cut`; terminal-api `tests/test_phase3c.py` `SECOND_PATHS` lost `/reference/{name}`.

### R1-4 (non-blocking): the gateway's own account expires 2027-10-25 and nothing tracks it

- **Root cause (verified in the records and the code; the live row not read):** the gateway subscriber was made
  "through 2027-10-25" (`DATABASE_CHANGELOG.md:3587`); `store.account` takes only `active AND expires_at > now()`, and
  on 3c `lookup()` reads that row before any owner's row, so at expiry every owner fails.
- **Fix:** `/ready` reports `gateway_account` {`state` ok, expiring (within 30 days), expired, inactive or missing,
  `days_left`} and logs `gateway_account_<state>` unless ok, without making the service unready (`main.py:630`,
  `store.gateway_state`); with R1-1 an expired gateway is now 503 `TERMINAL_UNAVAILABLE` logged `terminal_refused` in
  edge-bff, never a sign-out. Owner rows already end 2100-01-01 (`store.OWNER_EXPIRES`).
- **Not done (the user's go):** setting the live gateway row's `expires_at` to 2100-01-01 through the audited admin API
  (decision below). Nothing reads `/ready`'s new field on a schedule; the warning shows in the logs at each healthcheck.
- **Tests:** terminal-api `test_ready_reports_the_gateway_account_and_stays_ready`, `test_the_gateway_state_reads_the_
  row_on_a_real_server`.

### R1-5, R1-31, R1-36: shared page-file caches; Terminal limits that bind only the Terminal path

- **Decided by the code and the contract (R1-5, R1-31 part 2):** the page files stay in process caches shared by every
  user (CONTRACT section 15; QA 2026-11-14), so terminal-api grants, counts and audits a page file for the principal
  whose request missed the caches, once per edge-bff process and sha256; a read from the caches counts against no one's
  quota and leaves no terminal-api audit row. Lenient, never wider. Recorded in `pages.py` (docstring), the edge-bff
  README and terminal-api's README (whose "headers are accepted for the per-owner audit and quota" overstated it).
- **Fixed for 3c's acceptance (R1-31, the code refuter's other site):** `PageFiles` builds the principal's headers on
  every request before the caches (`pages.py` `page_index`, `page_file`), so edge-bff's own refusal for that principal
  (a quota of 0, an invalid owner key, a header terminal-api cannot take) holds whether the caches are warm or cold.
  Test: `test_a_page_file_refusal_of_the_principal_holds_when_another_account_warmed_the_cache`.
- **Recorded, not changed (R1-31 part 1, R1-36):** `terminal.tickers`, `terminal.dataset` and `terminal.history_days`
  bind the `/api/terminal/v1` path and terminal-api only. The Backtest and Screener workers read with their own service
  accounts (no owner header), the Overview and Watchlist page files are gated by `<tab>.view` alone. The Backtest page's
  `/bundle` reads and the Watchlist page's logo list go through `/api/terminal/v1`, so with 3c they get the cut, the
  plan's reference copies and count in the per-owner D6 Terminal quota (60 tickers per hour shared with the Terminal).
  No seeded plan combines a data restriction with those tabs (free holds none of them; paid has no restriction). Which
  rule should hold is the user's (decision below).

## What the shared records must say (for the records track)

- **CONTRACT.md** section 3: the relayed terminal-api refusals as listed under R1-1 (the table rows `TERMINAL_UNAVAILABLE`
  503 for an upstream 401/403/5xx, `LIMIT_REACHED` with `details.limit` `terminal.<quota>`, `allowed`, `retry_after_s`);
  name the tests that locked the old shape and changed (`test_terminal.py:84`, `test_radar.py:123-125`) as the spec
  refuter of R1-26 asked. Section 8b "3c in detail":
  - Headers: `history_days` null or 0-36600 (0 = no dated row), unknown dataset ids left out, the acknowledgement
    `x-terminal-capabilities-applied: 1 <version>` on every owner answer and edge-bff's 503 without it (R2-4, R2-5).
  - "edge-bff refuses first": a reference file is no longer refused; with `history_days` 0 every dated path is refused;
    a quota of 0 is 403 `CAPABILITY_REQUIRED` naming the limit (was 429).
  - "Every path filters", `/reference`: the plan's own copy without the dataset `reference` (R2-32, `refcut.py`), with
    the reading of D3 = B ("no list of other tickers") and the user's words that chose it (the relayed request "A").
  - "Tests per stage": the free principal is refused `/files`, `/bundle` packs, `/history`, the manifest of another
    ticker, and gets the references as its own copies (no longer "refused the references").
  - 3e Terminal: "search marks locked tickers" holds only for a plan with the dataset `reference`; for the free plan the
    search lists its own tickers (R2-32's refuters).
  - Deploy order: a rollback floor, "while EDGE_MULTIUSER is on, terminal-api is never rolled back below 3c" (R2-4; the
    acknowledgement makes a mistake fail closed); the order rule "add a dataset on terminal-api first, remove it on
    edge-bff first" (R2-5). terminal-api must be deployed before (or with) this edge-bff: edge-bff refuses capped
    principals' answers without the acknowledgement, which only matters with the switch on.
  - The page-file cache rule and the Terminal-path scope of the data limits (R1-5, R1-31, R1-36).
- **ERRORS_AND_SOLUTIONS.md:** new entries (symptom, verified cause, solution, status FIXED on the branch, lesson):
  the relay pass-through (R1-1, R1-26; lesson: one relay rule for every upstream answer, upstream account problems are
  never the user's session); the wire domain (R1-22; lesson: a value domain per capability in the catalog, and every
  consumer maps the whole domain); the missing acknowledgement (R2-4; lesson: an entitlement sent to a separately
  deployed service needs proof it was applied); the strict vocabulary (R2-5); the free Terminal (R2-32); the gateway
  account's expiry (R1-4, OPEN for the data change). M260: status unchanged (OPEN), with the note that refusals no longer
  carry terminal-api text.
- **DATABASE_SCHEMA.md / DATABASE_CHANGELOG.md:** migration `20261119_050_edge_bff_capability_domains.sql` (not
  applied): the three columns, the two helper functions, the replaced `capability_value_check`, the trigger
  `capabilities_domain_holds`, the six domains, `GRANT EXECUTE` of the two pure helpers to `edge_bff_runtime`. When it
  is applied: its order after `20261118_002`, and a read-back of the six domains. `edge_bff` is an operational schema
  (no Table_Catalog or Column_Catalog rows).
- **EXEC.md:** the reading of D3 (option a, reference copies) with the user's words; the decisions below as open.
- **RAILWAY_CHANGELOG.md:** nothing (no Railway change).

## Decisions needed (only the user can take them)

1. **M260, `public_data` on the Terminal relay's 2xx bodies.** Refusals no longer carry terminal-api text; the 2xx
   bodies are relayed as they are. ERRORS M260 says the filter needs the user's go.
2. **R1-4, the gateway row's end date.** Read the live row (`SELECT subscriber_id, active, expires_at FROM
   terminal.subscriber WHERE email = 'edge-owner@terminal.local'`), then set `expires_at` 2100-01-01 through the audited
   admin API (`POST /api/terminal/v1/admin/subscribers/<id>`), as the service accounts have.
3. **R1-36 / R1-31 part 1, what the Terminal data limits bind.** Options: (a) record that they bind the Terminal path
   only (today's code); (b) a catalog rule that a plan or override restricting tickers, datasets or history cannot hold
   `backtest.*`, `screener.*`, `overview.view` or `watchlist.view`; (c) pass the restrictions to the workers and page
   files (large). Also: whether the Backtest page's `/bundle` reads and the Watchlist logos count in the D6 Terminal
   quota (they do with 3c).
4. **R1-5, per-reader page-file counting.** Recorded as "once per process and sha256" (lenient). If Phase 4's usage
   counters need each reader, edge-bff records page-file reads itself.
5. **R2-32's reading of D3.** The fix follows the task's reading ("no list of other tickers": the free plan gets lists
   naming BBCA alone). The relayed user request is "A"; EXEC.md should carry the user's words for it.

## Suites (this branch, local, PostgreSQL 16 on port 55561, Chromium /opt/pw-browsers/chromium, Terminal page built)

| Suite | Result |
|---|---|
| edge-bff pytest (full) | 735 passed, 60 failed, 1 skipped. Against the base run (71 failed): every test of this track's findings now passes (`test_cp0_terminal_relay.py` 2, `test_c_p2_terminal_wire_domain.py` 6, `test_c_p3a_probes.py -k retry_after` 2, `test_c2_e2e_people.py` free-plan test). Two new failures: `test_c2_phase2_isolation.py::test_the_terminal_proxy_answer_carries_the_entitlements_version` (its fake terminal-api did not acknowledge; fixed in `bd1d5065`, passes) and the known flaky `test_composer_layout.py::test_submit_history_and_fixed_headers[mobile]` (passes alone). The other 58 are other tracks' re-check tests, failing at the base too: `test_c2_e2e_people.py` 2 (Monitor words, MFA after a plan change), `test_c2_ops_recheck.py` 8, `test_c2web_browser.py` 6, `test_c_p1s_preferences_plan.py` 1, `test_c_p2_recheck.py` 3, `test_c_p3a_probes.py` 2 (route walks, access.limits), `test_c_p3b_recheck.py` 1, `test_cdb_ci_coverage.py` 3, `test_cdb_grants_and_records.py` 5, `test_cp0_reserved_owner.py` 4, `test_cp1a_phase1_auth_check.py` 10, `test_r2_life.py` 2, `test_r2_race.py` 7, `test_r2_skew.py` 4 |
| terminal-api pytest (with `TERMINAL_TEST_POSTGRES_URL`, terminal schema migrations applied) | 160 passed |
| Terminal page vitest (`apps/edge-bff/terminal`) | 965 passed, 3 failed: `tests/data/c_p1s_browser_keys.test.ts` 2 and `tests/data/c_p1s_drawings_plan.test.ts` 1 (re-check C-P1S, another track; they test `shared/edge-session.ts` and `drawingsApi.ts`, untouched here) |
| screener-worker npm test | 126 passed, 1 failed: `tests/c-p3b-recheck.test.ts` F-msg (another track); `onboarding_pointers.test.ts` passes after `f82419c0` |
| backtest-worker npm test | 276 passed, 1 failed: `c-p3b-recheck` F-msg (another track) |
| scripts tests | 94 passed, 1 skipped |
