# Fix round, track "plans": plans, refusals and the pages (EXEC-MU-ACCOUNTS re-check of Phases 0-3b)

Branch `fix-plans`, from `97b4ecb5` (the session's p3c-int plus the re-check's failing tests of rounds 1 and 2). Nothing
pushed, deployed or run against Railway or a remote database. The shared records (ERRORS_AND_SOLUTIONS.md, EXEC.md,
RAILWAY_CHANGELOG.md, DATABASE_CHANGELOG.md, DATABASE_SCHEMA.md, CONTRACT.md) are not edited here; what each must say
is under "Records" below, for the records track.

The findings and their three refuters' verdicts: `verification/edge_multiuser/access_tiers/recheck/r1_findings.json`,
`r1_verdicts.json` and round 2's `r2_result.json`.

## Findings fixed

### R1-23 PLAN_EXPIRED never answered for a list or limit restriction
- Root cause (verified): `Principal.refusal(capability)` judged PLAN_EXPIRED by `holds()`, which knows only `*`, flags
  and item families; a list or limit is never "held", so an ended plan that set no ticker list or history limit (it
  allowed every ticker and date) gave CAPABILITY_REQUIRED ("upgrade") instead of PLAN_EXPIRED ("renew").
- Fix: `app/principal.py` `refusal(capability, item=None, amount=None)` and `ended_allows()`: for a list or limit (its
  kind from the ended plan's row, else the current plan's), the ended plan allowed the request when it had no such row,
  its list holds `item`, or `amount` is within its limit. Flags and items as before.
- Hand-off (terminal track): the 3c call sites (`main.py` refuse_capability, `terminal_access.check`) should pass the
  ticker (`item`) or the window (`amount`) so an ended plan with its own narrower list or limit is judged too; the
  no-row case already works without them.
- Tests: `tests/test_c_p2_recheck.py::test_an_ended_plan_without_a_ticker_list_or_history_limit_gives_plan_expired`
  (green).

### R1-24 one RESTRICTIVE list object shared by every principal with a malformed list
- Root cause: `read_grants` stored the module-level `RESTRICTIVE['list']` object itself.
- Fix: `RESTRICTIVE` holds immutable values and `restrictive(kind)` returns a new list per read.
- Tests: `tests/test_c_p2_recheck.py::test_a_malformed_list_reads_as_a_new_empty_list_for_each_principal` (green).

### R1-25 the seed plan search counted a plan holding `'*' = false`
- Root cause: "which plan holds everything" was asked by row existence after M480 allowed a flag to be false.
- Fix: `accounts.py seed_subscription` reads `value = 'true'::jsonb`; the unapplied 3c migrations
  `20261118_001` and `20261118_002` verify blocks do too (also 002's join "the plan holding * holds a quota row");
  the applied 003/004 are not edited. The test helpers that find the admin plan (`make_user` and the lookups in
  test_principal, test_plan_catalog, test_phase2_fix_round, test_terminal_access, test_backtest, test_phase3a_gates,
  test_screener) read the same rule.
- Tests: `tests/test_c_p2_recheck.py::test_the_seed_plan_is_the_plan_whose_star_is_true` (green).

### R1-29 access.limits reported the raw plan value, not min(plan, HARD)
- Root cause: the ceiling HARD lives in each module's code; the session answer printed `Principal.limits` unchanged.
- Fix: each module declares its HARD where it registers its routes (`auth.ceiling(key, hard)`: layouts, presets,
  drawings, screener, watchlist, backtest queue); `Principal.access(ceilings=...)` reports `capped()` for those keys;
  `main.py` session answer passes `auth.ceilings` (HARD stays the code guarantee CONTRACT 8b names; no migration).
- Hand-off (terminal track): the 3c quota header clamps to 1e9 while access.limits shows the raw value (negligible;
  `auth.ceiling` covers it if wanted).
- Tests: `tests/test_c_p3a_probes.py::test_the_session_access_limits_are_the_numbers_the_routes_apply` (green).

### R2-15 every CAPABILITY_REQUIRED and LIMIT_REACHED had one fixed sentence; the auth throttles said "upgrade the plan"
- Root cause: `errors.refusal` set the message from the code alone (`message_of`), and every client shows the server's
  sentence first, so `details.display_name`, the limit, the account's number and the wait never reached the person.
- Fix: `errors.words(code, status, details)` is the one wording: CAPABILITY_REQUIRED names the item; PLAN_EXPIRED the
  item and the ended plan (the plans' display names are loaded with the capabilities' by `Auth.refresh_names`);
  LIMIT_REACHED of a plan limit (a capability key, `<tab>.<name>`) names it, the account's number and the wait (or, with
  no wait, "remove one ... or upgrade"); LIMIT_REACHED of anything else (`code_tries`, `mfa_tries`) names only the wait;
  MFA_REQUIRED with `details.mfa_enrolled` false says to set the authenticator up. `refusal()` uses it, so the 3c
  refusals built by `terminal_access` get it without a 3c change. The backtest loop's PLAN_EXPIRED/CAPABILITY_REQUIRED
  job end uses it too.
- Tests: `tests/test_c2web_browser.py::test_c2web_w2_*` (4, green); `test_backtest.py::test_queue_limit_one_running_and_three_queued`
  now asserts the worded sentence (it locked the fixed one).

### R1-34 the workers' CAPABILITY_REQUIRED message carried the internal capability key
- Root cause: backtest-worker `access.ts requireItem` and screener-worker `run.ts checkAllow` wrote the key in the
  message; edge-bff relayed it; the pages show the server's message.
- Fix (both layers, as the refuters split): the workers name the item without the key (the key stays in
  `details.capability`); edge-bff `allow.named` keeps a worker's own sentence (it names the condition) unless it carries
  the key or its family, and then words it by `errors.words` (one owner of the wording for people). The Screener
  `/counts` per-entry refusals (relayed as bytes) are covered by the worker side.
- Tests: `apps/backtest-worker/tests/c-p3b-recheck.test.ts`, `apps/screener-worker/tests/c-p3b-recheck.test.ts` (green);
  `access.test.ts:116` and the exact messages in `access.test.ts`/`server.test.ts` no longer contain the key (they
  locked it; the finding says so); new `tests/test_allow.py::test_a_relayed_message_that_carries_the_internal_key_is_worded_by_edge_bff`.

### R1-32 the Screener catalog listed presets the plan does not hold
- Root cause: two derivations of "which presets an account holds": `/api/v1/catalog/screener_preset` (`catalog.held`,
  the screener.preset family) and `Screeners.catalog_for` (items only, cache keyed by the allow only).
- Fix: `catalog.holds_entry(p, kind, id)` is the one rule (any family of the kind); `catalog.held` and
  `Screeners.catalog_for` both use it; the restricted catalog is kept per preset grant too (`catalog.grant_key`).
- Tests: `tests/test_c_p3b_recheck.py::test_f1_a_preset_the_plan_does_not_hold_is_not_listed_in_the_screener_catalog`
  (green). `test_screener.py::test_screener_rights_from_the_session_and_the_catalog_per_session` used the made-up
  preset ids `plain`/`admin`, which the release file does not list (a lab item, never held by a paid plan); it now uses
  two released ids (`brk52`, `golden`) with the same assertions.

### R1-18, R1-30 /api/v1/preferences served and stored a tab's saved items without that tab's capability (D5)
- Root cause: the generic preference store (CONTRACT 4b) predates D5; the routes needed only the principal.
- Fix: each `sync` entry of the storage registry names the view capability of its tab (`cap`; none for `ml.symbol`,
  which every tab reads); `shared/build-shell.mjs` writes them to `catalog/storage_sync.json` with the shell copy (and
  `--check` compares both); `app/preferences.py` leaves such a key out of GET and refuses its PUT (403
  CAPABILITY_REQUIRED, or PLAN_EXPIRED by `p.refusal`); rows are kept (D5: back on upgrade). The shared module stops
  writing a key refused that way (no retry loop).
- Reading of D5 taken here (the refuters asked the user): D5's "Reads need <tab>.view" covers the tab content held in
  the store (`ml.my` My conditions, `scr.last`, and every other tab key). If the user decides the store stays readable,
  revert by setting no `cap` (one line per key) and move the R1-18 test to `pending/`.
- Tests: `tests/test_c_p1s_preferences_plan.py` (green); new `tests/test_fix_plans.py` (catalog flags; served while the
  tab is held, refused and kept otherwise); `tests/test_storage_registry.py::test_the_server_reads_each_sync_key_with_the_capability_the_registry_names`.

### R2-14, R2-30 the Monitor showed refusal codes; every non-admin sign-in landed on the Monitor
- Root cause: `edge-client.js` ApiError's message was the code (`super(code)`), the words only on `error.text`, and
  the Monitor shows `e.message`; LoginForm, CodeForm and MfaForm all `go("/monitor")`.
- Fix: ApiError's message is the person's words (the server's message, else the access words), the code is `.code`
  (and `.info.code`); the export's busy check reads the code; `authText` reads `.code`. A sign-in lands on the
  Monitor only for an account whose access holds `*` or `monitor.view`, else on the Terminal (`landing()`); a reload on
  an account page shows the landing page.
- Tests: `test_c2web_browser.py::test_c2web_w1_*`, `test_c2_e2e_people.py::test_the_monitor_shows_a_plan_refusal_in_words_not_its_code` (green).
- Tests changed for the landing decision (the computed task: "land on the Terminal"): `test_c2web_browser.signed_in`
  and W1 (W1 now asserts the Terminal landing, then opens the Monitor from the rail), `e2e_people.register`
  (`signed_in_workspace`), `test_c2_e2e_people` (the Monitor test opens /monitor; it compares with words naming the
  Monitor instead of the single fixed sentence, which R2-15 replaced; the refuter's correction "words or no
  refusal"), `test_auth_pages_live.py` (three waits for a registered account).

### R2-16, R2-31 the shell's own session never followed a change of plan
- Root cause: two copies of the session; only the shared module read X-Edge-Entitlements, and only its own client
  was invalidated. Also the route-level MFA_REQUIRED carried no X-Edge-Entitlements (the principal was set on the
  request after the check).
- Fix: the shared module's `onVersion(fn)` (its own version change and a frame's broadcast); `edge-client.js` reads
  the header on its own answers and follows either: it reads the session again into `auth`, the model list and the
  preferences, and dispatches `edge-auth`; the App redraws on a new `access.version` (an account raised to a plan that
  needs the authenticator goes to /mfa, set-up offered). `principal.py` sets `request.state.principal` before the MFA
  check, and MFA_REQUIRED carries `details.mfa_enrolled` (route and admin).
- Tests: `test_c2web_browser.py::test_c2web_w3_*`, `test_c2_e2e_people.py::test_a_plan_raised_to_one_that_needs_mfa_asks_for_the_authenticator_without_a_reload` (green).

### R2-17 a session that ended under a frame left the shell signed in
- Fix: on a 401 of its own session the shared module posts `signed-out` on the channel and to its parent (same origin);
  the shell (`onSignedOut`) reads its session and a 401 there resets it to sign-in. Pending writes stay stamped as
  before.
- Tests: `test_c2web_browser.py::test_c2web_w4_*` (green).

### R1-17, R1-38 the Screener's cached paint ignored the plan
- Root cause: the boot pointer was validated by login and data versions only, and a refused catalog kept the drawn
  rows.
- Fix: the pointer's identity is the login with the session's `access.version` (`cacheId`; `live.ts` session carries
  it), so an answer of another plan, or the same plan narrowed, is never drawn; a catalog refused by the plan or the
  second factor (the shared module's kinds upgrade/mfa) drops the pointer and the rows and shows the refusal. No
  generic drop of every `cache` key on a version change: it would also drop pending drawings and the open layout.
- Other site closed: `edge.watchlist.logos` (a reference file's content) is now a user cache.
- Tests: `screener/tests/smoke/c_p1s_plan_refused_cache.mjs` (exit 0); new `screener/tests/page/page.test.ts` case
  "a pointer written under one plan is never read under another" (narrowed plan, same publication).

### R1-19 a drawings refusal was read as "account unreachable"
- Fix: `layoutsApi.ts` LayoutApiError carries `access` (kinds upgrade/mfa); `drawingsApi.ts` keeps the refusal in
  `listOf`, says its words once, keeps and merges no local copy (drops one), skips the pagehide copy. A cap
  (LIMIT_REACHED) does not lock the drawings.
- Tests: `terminal/tests/data/c_p1s_drawings_plan.test.ts` (green).
- Records: CONTRACT 8b 3e's lock-prompt list should name drawings and layouts.

### R1-20 browser-class keys named after tickers survived sign-out
- Fix: `ml.assets.flow.` is a user cache family; removing a series removes its two keys; the registry test refuses a
  browser-class key built from a ticker or symbol. `ml.winst.*` (a broker window's chosen period, fixed window ids)
  stays browser (borderline, noted).
- Tests: `terminal/tests/data/c_p1s_browser_keys.test.ts` (green); `tests/test_storage_registry.py::test_a_browser_key_family_never_names_a_ticker_or_symbol`.

### R2-39 plan caps answered 422 LIMIT_EXCEEDED, the queue cap 429 LIMIT_REACHED
- Fix: one code for every plan limit, LIMIT_REACHED, `details.limit` the capability key, `allowed`, `needed`, in the
  plan's words (`errors.plan_cap`). A cap answers 403 (waiting frees nothing); the backtest queue (frees itself) stays
  429 with Retry-After (the re-check's W2 test locks 429 for the queue). An empty indicator choice is INVALID_INPUT.
  The Watchlist page fixture mirrors it. WATCHLIST_FORMULAS.md explanation and fingerprint rewritten (AGENTS.md).
  The module headers of layouts, presets, drawings and screener.py, and the route table of `apps/edge-bff/README.md`,
  say 403 LIMIT_REACHED for the plan caps; 422 LIMIT_EXCEEDED stays only for the size limits of one item (bytes of
  state, config or drawings; a screen's request size), which are not plan limits.
- Tests changed with the finding (it names them): test_layouts, test_presets, test_drawings, test_watchlist,
  test_phase3a_gates, test_screener, test_c2_probe_phase3a.
- Records: CONTRACT 3 needs the sentence (proposed): "LIMIT_REACHED is every plan limit's code, details.limit the
  capability key, allowed and needed; 429 with Retry-After when waiting frees it (the backtest queue, the Terminal
  quotas), 403 when it does not (a saved-item cap: remove one or upgrade)."

### R2-18 names with markup, bidi, invisible or control characters
- Fix: `app/text_rules.py` is the one rule: NFC (not NFKC), single spaces, 1-100 characters; refused with a sentence:
  Cc, Cf except ZWJ/ZWNJ, Cs, Co, Cn, Zl/Zp (separators normalised to a space before), `<` `>`. Display: text nodes
  (the shell's element()); `export_cell` prefixes a leading = + - @ (tab, CR) with an apostrophe for any spreadsheet
  file (Phase 4 exports). `auth_flows.checked_name` uses it.
- Tests: `tests/test_fix_plans.py` (rule and registration route).
- Records: CONTRACT 1 (or 10) gets the rule; a user decision is not needed (refuse rather than strip: the person sees
  what to change).

### R2-19 the shell's CSP kept script-src 'unsafe-inline'; no form-action
- Fix: the head viewport script is `static/edge-boot.js`, the app `static/edge-app.js` (a mechanical move of the code,
  nothing else changed); the shell's policy is `script-src 'self'`; `form-action 'self'` in every page policy. The
  preview tool inlines the new files (round-trip test green). README "Front-end structure" says where the app is now.
- Tests: `tests/test_fix_plans.py::test_the_shell_has_no_inline_script_and_its_policy_no_unsafe_inline_script`;
  test_storage_registry, test_radar and test_watchlist_page read edge-app.js for the shell's code.
- Integration: another track's edit to the old inline app script of `static/index.html` must be re-applied to
  `static/edge-app.js` (same text; the file adds a 3-line header). `plans_move_scripts.py` beside this file does the
  move again on a merged `static/index.html` that still has the two inline scripts. AGENTS.md's "the look in
  static/index.html" stays true (CSS and markup); its line could name edge-app.js for the renderers (not edited here).

### R2-20 no page for the password change and sign-out everywhere
- Fix: with accounts on (GET /api/v1/auth/config), the account menu's "Password and sign-in" dialog: current, new and
  repeated password (the other sessions end; this one stays) and "Sign out everywhere" (every session, both websites,
  this one included; then sign-in). Words in `edge-labels.js` (`EdgeLabels.auth.account`); calls in `edge-client.js`.
  Checked at 1280 and 390 px.
- Tests: `tests/test_fix_plans.py::test_the_account_menu_changes_the_password_and_signs_out_everywhere` (browser).
- Records: CONTRACT 12's shell page list gets the dialog.

### R2-21 no Strict-Transport-Security
- Fix: an https origin sends `Strict-Transport-Security: max-age=31536000` on every answer (host only: no
  includeSubDomains, the domain's other hosts are not EDGE's; no preload).
- Tests: `tests/test_fix_plans.py::test_an_https_origin_sends_hsts_and_a_host_only_session_cookie`.

### R2-22 cookies without the __Host- prefix on the live domain
- Fix: on a Secure origin the cookies are `__Host-edge_session` and `__Host-edge_registration` (Path=/, no Domain;
  `security.cookie_name`, `registration_path`); local http keeps the plain names. One-time move: with the switch off,
  a session under the old name is read once and the answer sets it under the new name and deletes the old (the admin is
  not signed out); with the switch on the old name is never read. Sign-in and sign-out delete the old name.
- Tests: `tests/test_fix_plans.py` (name, attributes, the move, no legacy read with the switch on).
- Hand-off (terminal track): same-site GETs from a sibling host still carry the session; 3c's counted Terminal GETs
  could check `Sec-Fetch-Site` (the refuter's note), outside this track.

### R1-36 (the user's rule "2a"): a Terminal limit beside the Backtest's or the Screener's own data access
- Decision (the user, 2026-11-19, EXEC.md "Decisions from the fix round" item 1, the extra rule): "2a" (agreed;
  enforced by the catalog). A plan or an override that limits the Terminal's tickers, data sets or history may not also
  hold the Backtest's or the Screener's own data access, since those tabs read every stock; the free plan's example
  flags stay allowed.
- Root cause (verified, R1-36 and its refuters): the Terminal's data limits bind only the Terminal path (edge-bff's
  x-terminal-capabilities to terminal-api, `app/terminal_access.py`); the Backtest and Screener workers read every stock
  with their own terminal-api service keys (`.railway/railway.ts` TERMINAL_SERVICE_KEY_BACKTEST_WORKER/_SCREENER_WORKER,
  `apps/screener-worker/src/config.ts` TERMINAL_PROXY_KEY). Nothing in the catalog stopped an account from holding both
  (the free plan's `terminal.tickers ["BBCA"]` and 730 days with a Screener trial by an override), so it would see every
  ticker's prices and run any ticker over its whole history.
- Fix (the data model that owns it; no code reads it, no plan or capability key in code): migration
  `20261119_030_edge_bff_plan_data_scope.sql` (plans' number range):
  - `edge_bff.capabilities.data_scope`: `terminal_limit` (terminal.tickers, terminal.dataset, terminal.history_days: a
    list or limit narrows by being there, an item family unless `{"all": true}`) and `every_stock` (backtest.view,
    backtest.run, screener.view, screener.run). The rule reads the marks, never a list of keys: a later capability of
    either kind is marked in its own migration. The Terminal quotas (rate limits the paid plan holds beside the
    Backtest) and the example flags are not marked.
  - `data_scope_conflict(plan, user)` and `data_scope_conflicts(plan, user)`: what may apply at some time (an override
    with an end leaves the plan's value to come back; an account may always fall back to the default plan, so its
    overrides are judged on its live subscription's plan and on the default plan); `'*'` lifts every Terminal limit
    (terminal_access sends the admin header) only when it holds at every time.
  - `data_scope_guard()` AFTER ROW triggers on plan_capabilities and user_capability_overrides (insert, update,
    delete), subscriptions (an active one), plans (a new default plan) and capabilities (a changed mark). A clash is
    refused with SQLSTATE 23514 (check_violation), CONSTRAINT `terminal_limit_with_every_stock`, a message naming the
    plan or account and the keys ("user 7 on plan free would both limit the Terminal and open the Backtest or the
    Screener (terminal.dataset, terminal.history_days, terminal.tickers with screener.view)") and a hint with the way out
    and one right and one wrong example. One transaction-scoped advisory lock per check: two writes racing on one
    account are judged one after the other. Immediate (not deferred): within one transaction, take the Terminal limits
    away before adding the Backtest or Screener rows (or close the tabs before narrowing).
  - The two read functions are executable by edge_bff_runtime (it writes overrides and subscriptions; the trigger runs
    as the writer); the trigger function by nobody. The verify block checks the marks, the whole catalog (it names
    every clash and refuses), the five triggers, the privileges, and its own examples (rolled back).
- Tests: new `apps/edge-bff/tests/test_plan_data_scope.py` (the marks and the seed; each side refused on a plan, on an
  override, for the edge_bff_runtime role; the admin narrows a paid account only after closing its tabs; an override
  with an end; a subscription; `'*'`; a new default plan and a new mark; the race; the second run; the verify block on a
  catalog that clashes). Added to the harness in `tests/conftest.py`.
- Test changed (it contradicted the decision): `tests/test_terminal_access.py::test_a_paid_principal_gets_every_ticker_and_dataset`
  narrowed a paid account's data sets by an override while it kept the Backtest and the Screener; it now closes the
  capabilities marked `every_stock` first (read from the catalog), then narrows, with the same assertions.
- Not done here (outside the rule): the Overview, Radar and Watchlist files also carry every stock (R1-37, a decision);
  the Backtest page's chart reads count in the Terminal quota (decision 4 "a", the terminal track); the Phase 4 admin
  API maps the constraint's 23514 to a refusal for the admin page (its words: the message and hint above).
- Records: CONTRACT 8a gets the rule and the column (the sentence of the decision, the marks, the constraint name);
  CONTRACT 8b 3c records that the Terminal data limits bind the Terminal path only and that the catalog keeps the
  Backtest and Screener off a plan with them. DATABASE_SCHEMA.md: the column, the three functions and five triggers.
  DATABASE_CHANGELOG.md: the migration (not applied; at deploy, after 20261118_002, read back the marks and
  `SELECT * FROM edge_bff.data_scope_conflicts(NULL, NULL)` = no row). ERRORS_AND_SOLUTIONS.md: R1-36 fixed on
  fix-plans by the catalog rule, not deployed. EXEC.md: "2a" built.
- Integration: `tests/conftest.py` gets this migration after 20261118_002; the terminal track's 20261119_050 adds
  other columns to `edge_bff.capabilities` (value_min, value_max, item_pattern) and replaces capability_value_check;
  the two migrations touch nothing of each other (merge both conftest lines, in number order).

## Findings reported as decisions (not changed)

- R1-35 (O3b-2 variant): conditions on the attributes every result row and /universe show (last, chg_1d_pct,
  adv20_idr, bars, index_membership) are still gated by id, while the chips on the same values are not (O3b-2); the
  Screener's extra-columns anchor `bars gt 0` therefore needs screener.metric:bars. The user's O3b-2 reason ("values
  shown in every result row and in /universe, so gating them by id cannot hide them") fits the conditions too, but the
  decision named the chips only, and the three refuters asked for the user's word. Options in decisions_needed.
  No seeded plan reaches it (paid holds every released metric, free has no screener.view); only a Phase 4 override
  that narrows screener.metric does. The extra-columns anchor is left as it is until the answer: with option A it
  needs no item; with option B it moves to a test the worker does not gate (for example `price close gt 0`, checked
  through `tests/page/extra-columns-core.test.ts` for the edge case of a ticker without a finite last close), and
  `apps/screener-worker/tests/allow.test.ts:160` changes with it.
- R1-37: the Overview and Watchlist files carry every stock's foreign net (broker data), gated only by their view
  capability. Not changed (the user's rule: "the gate is the Terminal: flow menus closed"); options in decisions_needed.

## Records (for the records track)

- ERRORS_AND_SOLUTIONS.md: one entry per finding above (symptom = the finding's failure scenario; root cause and fix as
  written here; status "fixed on fix-plans, not deployed"); R1-35 and R1-37 "open: user decision".
- CONTRACT.md:
  - 3: the LIMIT_REACHED sentence of R2-39; messages are built from code and details (`errors.words`), a worker's
    message without an internal key is kept, one with it is reworded (R1-34, R2-15); the auth throttles' LIMIT_REACHED
    words name the wait, not a plan.
  - 4: MFA_REQUIRED carries `details.mfa_enrolled` on every route; the cookies' __Host- names on https (R2-22); HSTS
    (R2-21).
  - 4b: each sync key's `cap`, GET leaves out / PUT refuses a key of a tab the plan lacks, rows kept (R1-18).
  - 8a: PLAN_EXPIRED for a list or limit (`refusal(key, item, amount)`, R1-23); access.limits reports min(plan, HARD)
    (R1-29); the seed plan is the one whose `*` is true (R1-25).
  - 8b: 3b in detail: the Screener catalog lists only held presets (R1-32); 3e lock prompts add drawings and layouts
    (R1-19); 3c call sites pass item/amount (R1-23).
  - 1 or 10: the name rule and export rule (R2-18). 12: the shell follows X-Edge-Entitlements and a frame's
    `signed-out` (R2-16, R2-17); landing (R2-14); the Password and sign-in dialog (R2-20); no inline script (R2-19).
- EXEC.md: the fix round's track status; the D5 reading taken for the preference store (R1-18) and the landing on the
  Terminal (R2-14) as the computed task's decisions.
- DATABASE_CHANGELOG.md / DATABASE_SCHEMA.md: one new migration, `20261119_030_edge_bff_plan_data_scope.sql` (not
  applied; the column `edge_bff.capabilities.data_scope`, the functions `data_scope_conflict`, `data_scope_conflicts`,
  `data_scope_guard` and the five triggers; see R1-36 above for what to read back at deploy); the unapplied
  20261118_001 and _002 verify blocks changed (`'*' = true`).
- RAILWAY_CHANGELOG.md: nothing (no deploy). At deploy: the admin's session cookie moves to `__Host-edge_session` on
  its next request (switch off), no sign-out.

## Suites (last run on this branch, 2026-11-19)

- edge-bff pytest (Postgres fx_plans, port 55564, Chromium): 725 passed, 56 failed, 2 skipped. Every failure belongs to
  another track's finding: test_c2_ops_recheck (R2-33..37), test_c_p2_terminal_wire_domain (R1-22), test_c_p3a_probes
  (3: R1-26 twice, R1-27), test_cdb_ci_coverage (R1-39/40/44), test_cdb_grants_and_records (R1-41..43),
  test_cp0_reserved_owner (R1-3), test_cp0_terminal_relay (R1-1), test_cp1a_phase1_auth_check (R1-7..15), test_r2_life
  (R2-24, R2-25), test_r2_race (R2-9..12), test_r2_skew (R2-1..3); and two timing failures under load that pass alone
  (test_composer_layout mobile, the known flaky one; test_ui_1031 status dots: 3 runs alone and one with
  test_composer_layout, all green; green on the base too). This track's tests are all green (test_fix_plans,
  test_plan_data_scope, test_c_p2_recheck, test_c2web_browser, test_c2_e2e_people, test_c_p1s_preferences_plan,
  test_c_p3b_recheck, test_allow, test_storage_registry, the R1-29 probe).
- terminal-api pytest: 142 passed, 1 skipped (not changed by this track).
- backtest-worker npm test: 277 tests, 276 passed; the one failure (server.test.ts "a job over
  BACKTEST_TIMEOUT_SECONDS ends FAILED TIMEOUT") is timing under the edge-bff run and passes alone.
- screener-worker npm test: 127 passed.
- Page vitests: screener 1356 (1355 passed, 1 skipped, after `npm run build`: the bundle tests read dist/), terminal 968
  passed, watchlist 21 passed (1 skipped), backtest 91 passed (after `npm run build`), overview 21 passed (1 skipped),
  radar 7 passed (1 skipped). Typecheck (tsc --noEmit) clean for screener, backtest, terminal and watchlist.
- Screener smoke: `tests/smoke/c_p1s_plan_refused_cache.mjs` exit 0; `tests/smoke/smoke.mjs` 6 failures, the same 6 on
  the base 97b4ecb5 (Add a condition, Customize widths, Patterns columns, Flow P5c, long tasks).
- scripts pytest: 94 passed, 1 skipped. `node shared/build-shell.mjs --check`: the shell copy and
  catalog/storage_sync.json match.
