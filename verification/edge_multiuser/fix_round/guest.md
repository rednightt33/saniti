# Track guest: the free ticker list, guests and the pre-launch mode (EXEC-MU-ACCOUNTS, decisions of 2026-11-19)

Branch `dec-guest` from `fix-int` (`9a22ee75`). Nothing pushed, deployed or applied to a remote database; no Railway
call. The two new migrations ran only on the disposable cluster `dec_guest` (port 55573). The shared records
(ERRORS_AND_SOLUTIONS.md, EXEC.md, CONTRACT.md, DATABASE_SCHEMA.md, DATABASE_CHANGELOG.md, RAILWAY_CHANGELOG.md) are not
edited here; what each must say is under "Records" below.

The user's words (EXEC.md EXEC-MU-ACCOUNTS, "Testing on the live site" and "Decisions from the fix round" item 1, on the
main checkout's EXEC.md; not yet on `fix-int`'s):
- "tidak, user tetap bisa search ticker, tapi ketika dia klik ticker selain bbca maka akan keluar pop up box to login
  (jika belum login) dan jika sudah login maka akan keluar pop up box (to upgrade plan)";
- "1a - bukan hanya chart, nanti ada indikator dll yg juga mungkin di show ke user. jadi design harus plug and play dan
  fluid, karna ticker dan indikatornya bisa berubah";
- the live site before the launch: "Terbuka, tapi belum bisa mendaftar", "Dan hanya admin yang bisa login (saya)", then
  "A" (the admin plus accounts marked as test accounts);
- the extra rule of item 4 ("2a", a restricted plan never holds the Backtest's or the Screener's data access): it holds
  for the guest plan as for every plan (the guest plan holds Terminal rows only; the migration's verify block runs
  `data_scope_conflicts('guest', NULL)`).
- D7 = A (the upgrade contact before the launch) and "segera hadir" (Coming soon).

## Commits

| Commit | What |
|---|---|
| `7d793ad2` | terminal-api: the whole ticker list for every plan (`refcut.names_only`, from each file's own columns); `x-terminal-client` counts a guest owner's quotas per visitor (migration `20261119_170`, not applied) |
| `101e9291` | edge-bff: the guest principal from the catalog's guest plan; `auth.need(..., guests=True)`, `auth.visitor`; `GET /api/v1/auth/guest`; the pre-launch mode; `users.test_account` with its audited trigger; `scripts/edge_test_account.py` (migration `20261119_070`, not applied) |
| `4c7dad6d` | front-end: the shared module's guest session, the Terminal's locks and box requests, the shell's guest Terminal, `LockedDialog`, the closed register page; browser tests |
| `2ad40fcb` | docs: edge-bff README, terminal-api README, the edge-bff-live comment in `.railway/railway.ts` |
| `d47eefbe` | `SCREENER_ONBOARDING.md` pointers moved with the lines of both `main.py` files |

## 1. The whole ticker list (terminal-api `app/refcut.py`)

- **Before (fix-terminal R2-32, option a):** a plan without the dataset `reference` got its own copy of every reference
  file; a file with a `ticker` column kept the plan's tickers, so the free plan's ticker list named BBCA alone.
- **Now:** the ticker list is whole for every owner edge-bff forwards (every route of `/api/terminal/v1` needs
  `terminal.view`, so every such owner holds it; the guest too). The other reference lists keep the plan's filter.
- **Derived, not listed:** `names_only(doc, columns, datasets)` reads the file itself. A file keyed by `ticker` is
  names-only when every other column holds text or null (a number or a list is data), no column is named
  `<dataset>_...` after a dataset terminal-api serves (`main.py DATASETS`), and no column holds only 64-hex digests (an
  index of published objects). On the publisher's real columns (`tests/test_guest_tickers.py` reads `publisher.py`):
  tickers (`ticker, name, type, sector, industry, instrument`) whole; logos (`sha256` digests: the image index, and
  edge-bff refuses another ticker's logo image) and fixed_income (`yield_first` ... `price_last`: the datasets' dates)
  keep the plan's tickers; brokers by the `broker` dataset (`BY_DATASET`, unchanged); stock_lists no rows (unchanged).
  A new column of a figure, a list, a dataset or a digest turns a list back to filtered (fail closed).
- **The page:** `live.ts` lists every ticker in the search; the plan's tickers open, the others carry a lock and open
  the box (section 3). A remembered ticker the plan does not hold never locks the page: the plan's first ticker opens.
- Tests: `apps/terminal-api/tests/test_guest_tickers.py` (the publisher's columns, the derivation, the fixtures);
  `test_terminal_fix_round.py` changed (below).

## 2. Guests

- **The guest plan is a plan** (migration `20261119_070`): `edge_bff.plans.for_guests` (one plan, never the default:
  `plans_one_guest`, `plans_guest_not_default`); seed `guest` ("Guest") with the free plan's Terminal grants:
  `terminal.view` true, `terminal.tickers` `["BBCA"]`, `terminal.dataset` `{"ids": ["price"]}`, `terminal.history_days`
  730, `terminal.indicator` `{"ids": []}`. No Terminal quota row (see quotas below).
- **Read like every plan** (`accounts.py guest_plan`, `principal.py guest_principal`): one statement on every guest
  request gives the plan's rows with their kinds and versions; `read_grants` checks each value's shape, `can()` decides
  flags and items, `version_of` makes `X-Edge-Entitlements`. A change of the plan's rows applies on the next request
  (tested: `test_a_change_of_the_guest_plans_rows_changes_what_a_visitor_sees_without_code` widens the tickers and adds
  `I01`; the header, the terminal-api capabilities and the catalog answer follow). No plan key in code: the plan is
  found by `for_guests`; `tests/test_plan_catalog.py` now reads every plan seed of every migration.
- **Fail closed whatever the rows say:** a visitor never holds `*`, `admin.access`, an admin right of `rights.py` or a
  beta-only key (dropped and logged `guest_capability_dropped`); `live` is set, so no lab item is held either.
- **Where it exists:** only on routes that ask for it, `auth.need(capability, guests=True)` and `auth.visitor`:
  `GET|POST /api/terminal/v1/{path}` (`terminal.view`), `GET /api/v1/catalog/{kind}` (the Terminal's indicator items)
  and `GET /api/v1/auth/guest` (the guest plan's access in the session answer's shape, `visitor` true, no login, owner
  key or CSRF token). Every other route keeps answering 401 `UNAUTHENTICATED` (tested over eleven routes), so the shell
  shows the sign-in page there. The route walk (`tests/test_route_table.py`) lists them in `GUEST_OPEN` with their reason
  and fails on any other route that admits visitors, or a stale entry.
- **Who is a visitor:** a request whose session cookie resolves to no session (none, expired, revoked). A session that
  resolves keeps its own principal on the guest routes (and its CSRF on writes); a session waiting for the second
  factor still gets `MFA_REQUIRED`. A guest writes without CSRF: it has no session a cross-site page could ride, and the
  Origin check of every write still holds (tested: another origin is `ORIGIN_REJECTED`).
- **On / off:** `EDGE_GUESTS` (true/false; unset = the live site on, the beta off). With `EDGE_MULTIUSER` off (the beta)
  there is no guest, and `EDGE_GUESTS=true` stops the start (`config.validate`). The Terminal relay of the beta answers
  401 to a visitor as before.
- **The guest owner:** every visitor reaches terminal-api as owner `edge-guest` (`accounts.GUEST_OWNER`; never issued to
  an account, refused for `EDGE_OWNER` and `EDGE_ADMIN_OWNERS`), with the guest plan's capabilities header.

### The client address on Railway, and quotas per visitor

- **How it is read** (`principal.py client_of`): Railway's edge forwards every request from the internet and adds the
  client's address to `X-Forwarded-For` (the service's own `uvicorn --no-proxy-headers` keeps the socket peer as the
  edge, so the header is the only place the visitor's address is). The right-most entry is the hop the edge added; any
  entry a client wrote itself stays to its left, so the right-most is the one a client cannot choose. It counts only
  when it parses as an IP address.
- **When it is missing (fail closed):** no `X-Forwarded-For`, or a right-most hop that is not an address: no guest
  principal, 401 `UNAUTHENTICATED` (the page shows sign-in). A request without the header did not pass the edge (on
  Railway every public request does). The socket peer is taken only with `EDGE_ENVIRONMENT=local` (a developer
  machine, the browser tests); on Railway the environment is `dev` and it never applies.
- **Not yet proved on Railway:** the Phase 0 probe of what Railway's edge really sends (CONTRACT section 4 "Client IP")
  has not run. If the edge sent one address for everyone, all visitors would share one quota (stricter). Corrected by
  the 3c check (C3-5): if the edge passed a line or an entry the client wrote as the right-most hop, a script could
  choose a new visitor key per request and get fresh quotas each time (wider), so the earlier "never wider" was wrong.
  edge-bff now reads the right-most hop over every header line and keys IPv6 by its /64 (throttle.forwarded_hop,
  address_key). The user chose "1a" (2026-11-20): the probe runs on Railway before the live site opens to visitors,
  and sends a client-written X-Forwarded-For once as one line and once as two.
- **Per visitor at terminal-api** (migration `20261119_170`): edge-bff sends `x-terminal-client`, 32 hex of an HMAC of
  the address under `EDGE_SESSION_SECRET` with its own label (`guest_client`), never the address. Beside both owner
  headers of an owner that does not hold `*`, terminal-api counts that owner's quotas per visitor: `Store.usage`,
  `frees_in` and the audit rows (`terminal.access_log.client_key`), and the quota check's advisory lock per visitor, so
  visitors do not wait for each other. Without the header the owner's row counts as a whole (stricter). terminal-api
  refuses the header without owner headers, with an admin owner, with a service key or a cookie, or when it is not 32
  lower-case hex (400 naming the header, with a right example; never echoing the value).
- **The numbers:** the guest plan sets no Terminal quota, so each visitor gets terminal-api's `terminal.quota` defaults
  (60 files and 30 tickers an hour, 150 tickers and 300 MB a day, 20 history reads an hour). A quota row added to the
  guest plan later overlays them, as for any plan (data).
- **The 90-day audit:** each guest grant writes one audit row with the visitor key, as every owner's grant does.

### EXPLAIN evidence (the index `access_log_client_at`)

Disposable database `terminal_test` of `dec_guest` (PG 16.15, defaults), terminal migrations 20261025_100 to
20261119_170 applied; one guest owner with 300 000 rows of the last day from 3 000 visitors, 2 000 other owners with
200 000 rows; `ANALYZE`; the usage statement of `Store.usage` for one visitor (the scratch script
`explain_guest.sql`, not committed; rolled back):

| Statement | Without the index | With it |
|---|---|---|
| a visitor's usage (`subscriber_id`, `client_key`, the last day) | 151.4 ms, 300 665 buffers, `Index Scan using terminal_access_log_subscriber_at` reading every visitor's rows | 0.26 ms, 107 buffers, `Index Scan using access_log_client_at` |
| a signed-in owner's usage (no visitor key) | 0.18 ms, 106 buffers, `terminal_access_log_subscriber_at` | unchanged (partial index: no other row is in it) |

The index is partial (`WHERE client_key IS NOT NULL`): its build reads `terminal.access_log` once and writes only the
rows of guests (none yet). That read of a large table makes the migration a large update in the sense of AGENTS.md
("Postgres memory after large updates"): restart Postgres after it as that section says.

## 3. The boxes

- **What is locked** comes from what the server says the principal holds, never from a list in the page
  (`terminal/src/data/live.ts lockRules`): a ticker outside `access.limits['terminal.tickers']` (no list: none locked),
  an indicator or Flow indicator `GET /api/v1/catalog/indicator|flow_indicator` does not list (`*` reads no catalog;
  a catalog that cannot be read locks its kind), a feature flag it lacks (`edge.can`). An answer without `access` (an
  older server) locks nothing, as before.
- **Where:** the search lists every ticker with a lock on the locked ones (`app/search.ts`, `.gp-lock`); choosing one
  asks for the box. The indicator menu marks a locked indicator (`.im-row.locked`, `.im-lock`) and its Add asks for the
  box (`app/indMenu.ts`). The layouts button asks for the box without `terminal.layouts` (`app/layouts.ts`). Presets are
  not offered without `terminal.presets` (`app/presets.ts`). A visitor's drawings last as long as the page (nothing
  written to the browser or the account: `app/drawings.ts`).
- **The box is EDGE's** (`app/locked.ts` posts `{source: "terminal", type: "locked", kind, id, name}` to the shell, this
  origin only; the shell's `LockedDialog` in `static/edge-app.js`), because the shell knows whether someone is signed in:
  - a visitor: "Sign in to open {name}", "Sign in" (to `/login`) and, while registration is open, "Create account";
  - an account: "{name} is not in your plan", "Coming soon" and "Contact us to upgrade: <EDGE_UPGRADE_CONTACT>", or,
    while it is unset, "How to contact us about upgrading will be shown here soon".
  - Words: `static/edge-labels.js` `EdgeLabels.locked` (and `access.comingSoon`); the lock mark's word is read from the
    shell's labels (same-origin frame), "Locked" when the Terminal is opened alone, where the box request opens EDGE's
    Terminal page instead.
- **Look:** the design system's dialog (`DialogShell`: head with title and line, body, actions at the right, the main
  action ink, focus on it, Escape and Tab inside). Checked at 1440 and 390 px, light and dark (screenshots in the
  session's scratchpad). The Terminal's own look changes only by the 12 px lock mark (`terminal.css .gp-lock, .im-lock,
  .im-row.locked`); `look_check11.mjs` PASS on the build (the look server sends no `access`, so nothing is locked there;
  no new heading, switch or control row).
- **`EDGE_UPGRADE_CONTACT`:** one line of plain text, at most 200 characters, no `<` `>` or control characters (refused at
  start otherwise); shown as text. Unset: the "comes soon" sentence.
- **The shell for a visitor:** `/terminal` without a session opens the Terminal where the site has guests
  (`GET /api/v1/auth/config` `guests`); the account button is a "Sign in" button; every other page shows sign-in. The
  sign-in page offers "Open the Terminal without an account". After a sign-in the shell lands as before (`landing()`).
- **The shared module** (`shared/edge-session.ts`, rebuilt to `static/edge-session.js`): `allowGuest()` (the Terminal
  calls it) makes a 401 of the session route read `GET /api/v1/auth/guest`; `access()`, `can()`, `limit()` and
  `catalog()` read it like an account's. A visitor holds nothing of the browser's storage (no last-login mark, nothing
  cleared); a visitor who signs in, or an account whose session ends under the page, reloads the page as the other.

## 4. The pre-launch mode

- **`EDGE_PRELAUNCH`** (true/false; unset = the live site on, the beta off; `EDGE_PRELAUNCH=true` with the switch off
  stops the start). At the launch the main agent sets it to `false` on edge-bff-live.
- **Registration closed:** `POST /api/v1/auth/register`, `/register/verify` and `/code/resend` with purpose `register`
  answer 403 `REGISTRATION_CLOSED` ("Registration opens soon. EDGE is not taking new accounts yet; you can still open
  the Terminal without an account."), the same for every address. `/password/forgot` and `/password/reset` stay open.
  The register and verify pages show "Registration opens soon" with the way to the Terminal and back to sign-in.
- **Sign-in:** only the admin (an account whose resolved grants hold `*` or `admin.access`, the catalog's rule that also
  decides the second factor) and accounts marked `edge_bff.users.test_account` sign in. Any other account gets 403
  `SIGN_IN_CLOSED` ("EDGE opens to accounts soon. Until then only test accounts can sign in; ...") after its password was
  checked like any other (a wrong password is still 401 `INVALID_CREDENTIALS`), and no session is made. A pending
  registration with the right password is not restarted (registration is closed).
- **The test-account mark** (migration `20261119_070`): `users.test_account` boolean, false. Two deferred constraint
  triggers (`users_test_account_audited` on an insert that marks, `users_test_account_audited_change` on a change)
  refuse at commit any change without an `admin_audit` row of the same transaction (action `account.test_mark`, the
  account as target, `after.test_account` the new value), SQLSTATE 23514, a hint with a right and a wrong example. The
  migration's verify block proves both cases on a probe account, rolled back.
- **`scripts/edge_test_account.py`** (as a job: `scripts/onboarding/edge_test_account_job.py`, params `{"email",
  "plan", "reason", "off"}`): for one of the user's addresses and a plan key it makes an active account (username from
  the address or given, names "Test Account" unless given, the address marked verified) with a password identity no
  password opens (a random verifier), marks it with its audit row (actor `operator`), and subscribes it to the plan
  (`provider` `test`) unless the plan is the default; an existing account is marked (and subscribed when it has no live
  subscription). Refused (exit 1): an unknown plan, a plan holding `*`/`admin.access`, the guest plan, an account not
  active, an account already on another plan. `--off` removes the mark. It prints the user id, username, plan and
  outcome only (never the address, a verifier or the URL; a driver error only by class and SQLSTATE). The person then
  sets the password with "Forgot password" (needs Resend).
- **Visitors still open the Terminal** in the pre-launch mode (tested).
- **`GET /api/v1/auth/config`** with the switch on: `{"multiuser": true, "registration", "prelaunch", "guests",
  "upgrade_contact"}`; with it off `{"multiuser": false}` as before.

## Tests

New:
- `apps/edge-bff/tests/test_guest.py` (16): BBCA and the whole list for a visitor, the guest owner and visitor key sent,
  another ticker refused before terminal-api; 401 on eleven other routes; a change of the guest plan's rows; `*` and
  `admin.access` never held; no client address, no guest (and `client_of`'s rules); no guests with the switch off or by
  default on the beta, configurable on live; a signed-in account keeps its principal and its CSRF; a page-sent visitor
  key refused; the guest owner reserved; pre-launch registration closed; pre-launch sign-in (paula refused, the admin
  to MFA, a marked test account in, everyone with the mode off); the settings; the mark and its audit; the script; the
  migration's second run.
- `apps/edge-bff/tests/test_guest_browser.py` (4, Chromium, the built Terminal): a visitor sees BBCA, every ticker with
  locks, and the sign-in box (which leads to `/login`); a free account gets the upgrade box with the contact; a locked
  indicator opens the box; pre-launch pages.
- `apps/terminal-api/tests/test_guest_tickers.py` (10): the derivation on the publisher's columns, its fail-closed
  rules, the fixtures' columns; visitors counted apart and the owner's row as a whole without the key; the header's
  refusals; the store per visitor on PostgreSQL (usage, `frees_in`, the audit column, its CHECK).
- `apps/edge-bff/terminal/tests/data/guest_session.test.ts` (5): the shared module's guest session.

Changed (each held a rule a decision of 2026-11-19 replaced; no expectation weakened):
- `apps/terminal-api/tests/test_terminal_fix_round.py`: `test_the_free_plan_gets_reference_lists_that_name_its_own_
  tickers_only` became `..._gets_the_whole_ticker_list_and_its_own_rows_of_every_other_reference_file` (it held the
  BBCA-alone list of the R2-32 reading that decision 1 replaces; every other file still names no other ticker);
  `test_the_broker_list_follows_...` expects the whole list and checks the logos still follow the tickers; the
  `fixed_income` fixture carries the publisher's `FI_COLUMNS` (it had three of them).
- `apps/edge-bff/tests/test_c2_e2e_people.py`: the free-plan reload test asked for the BBCA-alone copy of the ticker
  list to be downloaded; the whole copy now equals the list the browser kept from the first load (its cache by sha256),
  so the test checks that the list is announced and that a file with data per ticker (brokers) comes as the plan's copy.
  The other free-plan test's docstring follows the decision (its assertions are unchanged).
- `apps/edge-bff/tests/test_route_table.py`: the walk admits `GUEST_OPEN` routes on the visitor dependency (decision
  "1a"), names them with their reason, and fails on any other or a stale entry; `PRINCIPAL_ONLY` names
  `GET /api/v1/auth/guest`.
- `apps/edge-bff/tests/test_plan_catalog.py`: the plan-key grep reads every plan seed of every migration (the guest plan
  added) and its expected set gains `guest`.
- `apps/edge-bff/tests/test_auth_flows.py`: `test_config_with_the_switch_on` expects the new keys.
- `apps/edge-bff/tests/e2e_people.py`: its fake terminal-api passes the dataset ids to `refcut.build`, as terminal-api.

## Records (for the main agent and the records track)

- **CONTRACT.md:**
  - Section 1 `plans`: `for_guests` (one, never the default), the `guest` seed; `users`: `test_account` and its audited
    triggers. Section 2: the guest principal (who, where, what it never holds, `client_of`, fail closed), `auth.visitor`,
    `need(..., guests=True)`, CSRF for guests. Section 3: `REGISTRATION_CLOSED` (403) and `SIGN_IN_CLOSED` (403) in the
    table. Section 4: `GET /api/v1/auth/guest`, the config keys, the pre-launch rules ("to build" marks become built).
    Section 7 / 8b 3c: `x-terminal-client`, per-visitor quotas, the `reference` rule now derived (`names_only`), the free
    plan's whole list (replace "the ticker list ... to build"). Section 9: the guest plan as built (no quota rows: the
    defaults per visitor). Section 12: the boxes, the closed register page, the guest Terminal in the shell. Section 16:
    `EDGE_GUESTS`, `EDGE_PRELAUNCH`, `EDGE_UPGRADE_CONTACT`. Section 17: the pre-launch mode built; rollback floor below.
    Section 18: no new recipient (the visitor key never leaves EDGE and terminal-api; terminal-api keeps it 90 days in
    the audit rows as a pseudonymous key, which the Privacy text may state).
- **ERRORS_AND_SOLUTIONS.md:** no defect of the deployed system was found by this track. If the records track keeps an
  entry per decision built, the lesson for Part D: "what a visitor without an account may see is a plan in the catalog,
  read through the same code as every plan; the routes that admit it are named in one table the route walk holds".
- **DATABASE_SCHEMA.md / DATABASE_CHANGELOG.md:** `20261119_070_edge_bff_guest_plan_and_test_accounts.sql` (the column
  `plans.for_guests`, index `plans_one_guest`, CHECK `plans_guest_not_default`, the `guest` plan and its five rows, the
  column `users.test_account`, function `edge_bff.test_account_audited()` (no EXECUTE for PUBLIC), the two deferred
  constraint triggers); `20261119_170_terminal_access_log_client.sql` (the column `terminal.access_log.client_key`, its
  CHECK NOT VALID, the partial index `access_log_client_at`) with the EXPLAIN evidence above. Neither applied. At deploy,
  read back: `SELECT plan_key, is_default, for_guests FROM edge_bff.plans`; the guest plan's five rows; `SELECT * FROM
  edge_bff.data_scope_conflicts('guest', NULL)` empty; no account marked; the two triggers; the terminal column, CHECK
  and index; `edge_bff` and `terminal` are operational schemas (no catalog rows).
- **EXEC.md:** the track's status and the readings below; `railway.ts` already names the three variables.
- **RAILWAY_CHANGELOG.md:** nothing changed on Railway.

## Deploy order and rollback floors

1. Both migrations (they add only; the running services read none of the new columns).
2. terminal-api (it reads `client_key` in `/ready`; it accepts `x-terminal-client` and serves the whole ticker list).
   Floor: while guests are on anywhere, terminal-api is never rolled back below this build (an older one refuses the
   header 400 for every guest call: fails closed, guests see nothing).
3. edge-bff (beta first: with the switch off nothing changes there; `/ready` reads `plans.for_guests` and
   `users.test_account` only with the switch on). Then edge-bff-live, where `EDGE_GUESTS` and `EDGE_PRELAUNCH` default on.
4. Before the guest plan is offered on live: the client-address probe (decision 1 below).

## Readings taken here (for the main agent to confirm or change)

- "Plan that holds terminal.view" is read at terminal-api as "every owner edge-bff forwards" (edge-bff's Terminal routes
  need `terminal.view`).
- Names-only lists: derived from the columns; today only the ticker list. The bonds' list stays filtered (its columns
  carry the datasets' dates), so the free plan and guests do not see the bonds in the search; the logos stay filtered
  (edge-bff refuses another ticker's logo image, which 3c decided), so the search shows monograms for the locked tickers.
- The guest plan has no Terminal quota rows (the task listed the four grants, not the quotas); visitors get
  terminal-api's defaults each. The free plan keeps D6's numbers.
- The layouts button and presets follow the same lock rule (the free plan lacks both, 8a); a visitor's drawings are kept
  nowhere (as R1-19 for a refused plan).
- The admin of the pre-launch rule is read from the catalog (`*` or `admin.access`), as the second factor is, not from
  the role.

## Decisions needed (only the user can take them)

1. **The client-address probe before guests go live.** The guest quotas count per address read from Railway's
   `X-Forwarded-For`; the probe that proves what Railway's edge sends (CONTRACT section 4) has not run. Options: (a) run
   the probe before the live site opens to visitors (a Railway call with the user's go); (b) open guests without it
   (worst case, corrected by the 3c check C3-5: if the edge kept a client-written hop right-most, quotas per visitor
   could be widened at will). The user chose (b) on 2026-11-19 on the earlier, wrong worst case, then "1a" on
   2026-11-20 once it was corrected.
2. **A ceiling for all visitors together.** Per-address quotas do not bound a visitor who changes address. Options:
   (a) none for now; (b) a total per hour for the guest owner (a new terminal-api quota, data).
3. **Bonds and logos for the free plan and guests.** Today they stay filtered (above). Options: (a) keep; (b) treat the
   bonds' list as names (search shows bonds, locked) and/or open the logo images to every plan.

## Suites (this branch, local, PostgreSQL 16 on port 55573, Chromium /opt/pw-browsers/chromium, every page built)

| Suite | Result |
|---|---|
| edge-bff pytest, the whole `tests/` (Postgres, Chromium, every page built) | 900 passed, 3 failed: `test_backtest.py::test_a_queued_job_reads_its_owners_rights_when_it_is_dispatched`, `test_composer_layout.py::test_submit_history_and_fixed_headers[mobile]` (the known flaky one) and `[mobile-small]`. Run again alone, all three pass (mobile-small 3 of 3 on this branch, and on the base's `app`/`static`); the first two failed only while the page vitests and the workers' suites ran beside it. The pytest process printed its result and then did not exit (a thread still polling the test database); it was stopped and its database dropped |
| terminal-api pytest (`TERMINAL_TEST_POSTGRES_URL`: the terminal migrations 20261025_100 to 20261119_170 on `terminal_test`) | 170 passed |
| market-ai-orc pytest (`ORC_TEST_POSTGRES_URL`) | 2204 passed |
| backtest-worker `npm test` | 277 passed (run alone; beside the edge-bff suite the known timing test "a job over BACKTEST_TIMEOUT_SECONDS ends FAILED TIMEOUT" failed once); `npm run registry:check` current |
| screener-worker `npm test` | 127 passed (`onboarding_pointers` after `d47eefbe`) |
| Page vitests | terminal 973 (38 files), backtest 91, screener 1355 passed and 1 skipped, radar 8, overview 22, watchlist 22; every page built (`npm run build`) |
| scripts pytest (`scripts/tests`, the generated-file tests included) | 94 passed, 1 skipped |
| `node shared/build-shell.mjs --check` (apps/edge-bff) | `static/edge-session.js` and `catalog/storage_sync.json` match |
| `look_check11.mjs` on the built Terminal | PASS |
