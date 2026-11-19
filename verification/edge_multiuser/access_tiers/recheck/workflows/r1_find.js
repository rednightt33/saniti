export const meta = {
  name: 'mu-recheck-phases-0-3b-find',
  description: 'Ultracode re-check of EDGE multi-user Phases 0-3b (deployed, switch off): 7 lens finders at xhigh, round 1',
  phases: [{ title: 'Find', detail: '7 independent finders, one lens each, over Phases 0-3b as deployed on main' }],
}

const COMMON = `You are an independent checker of the EDGE multi-user work (EXEC-MU-ACCOUNTS) in the repository rednightt33/saniti. You work in your own git worktree. Its HEAD is the session's integrated branch, code identical to main 93c9f645, as deployed on Railway dev with the switch EDGE_MULTIUSER off.

Phases 0, 1, 2, 3a and 3b are built, checked once by three checkers each, and deployed with the switch off. Phase 3c (Terminal data per plan) is being built on top of them right now. The user's worry, in their words: "Jangan sampai fase 3C di bangun dari broken block fase2 sebelumnya." Your job is to find defects the earlier checkers missed, especially any that Phase 3c would build on.

## Ground truth to read
- verification/edge_multiuser/access_tiers/CONTRACT.md: the whole specification, sections 0-16, including 8a and 8b, the user decisions D1-D8 and O3b-1/O3b-2.
- EXEC.md, the section "EXEC-MU-ACCOUNTS" to the end of the file: the user's words, the runbooks and the run logs.
- ERRORS_AND_SOLUTIONS.md M468-M482: the defects already found and fixed. Do not report one of them again unless its fix is missing, wrong or incomplete, and then say which entry.
- The code, the tests and the migrations named in your lens.

## How to work
- Verify every claim yourself in the code, with file:line evidence (AGENTS.md "Gates and evidence"). When you can, prove it with a failing test or a probe that runs. Separate VERIFIED from SUSPECTED, and for SUSPECTED name the check that would confirm it.
- For each finding, give the general class: which mechanism, and which other routes, tables, services or tabs could hit the same mechanism. That includes Phase 3c's Terminal data paths and later tabs.
- Write probe tests in your worktree (the tests folder of the app concerned). Commit only the tests of VERIFIED findings: they are failing tests the fix round will make pass. Commit messages end with exactly these two lines:
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_015yBxadqbqnpdpSwmfCDQca
- Do not push, deploy, call Railway, or touch any remote database. Never print secrets.
- edge-bff pytest needs a Postgres cluster of your own. Make it with:
  su pgtest -c "/usr/lib/postgresql/16/bin/initdb -D /home/pgtest/<NAME> -E UTF8 -U postgres --auth=trust"
  then:
  su pgtest -c "/usr/lib/postgresql/16/bin/pg_ctl -D /home/pgtest/<NAME> -o '-p <PORT> -k /tmp' -l /home/pgtest/<NAME>.log start"
  Run with EDGE_TEST_POSTGRES_URL=postgresql://postgres@127.0.0.1:<PORT>/postgres and EDGE_TEST_CHROMIUM=/opt/pw-browsers/chromium.
  Run one pytest process at a time on your cluster (concurrent runs collide on cluster-wide roles). Stop your cluster when done.
- The machine is shared with other agents. Timing tests may flake under load: rerun alone before calling one a failure, and compare with the base when unsure.
- Severity:
  - blocks-3c: Phase 3c builds on it, so it must be fixed before or with 3c;
  - blocks-switch-on: must be fixed before EDGE_MULTIUSER goes on;
  - non-blocking;
  - records: a document, test or record gap only.

Return findings only when you have evidence. An empty list with a thorough "checked" list is a valid answer.`;

const LENSES = [
  { key: 'p0-runtime', name: 'C-P0', db: ['r0', 55511], text: `LENS: Phase 0 runtime and downstream identity (CONTRACT section 7, section 16, ERRORS M470, M477).
- terminal-api (apps/terminal-api/app/*.py): the private-host key rules, identify, every key kind, OWNER_HEADER handling, the gateway subscriber, service accounts, quotas and audit;
- market-ai-orc: the owner on every request, conversations, progress, stop and manual_agent, under (owner, request id);
- orc-test-runner (apps/orc-test-runner/run.py);
- edge-bff's calls to orc and terminal-api (what owner they send, whether any path can name another owner).
Ask: could any caller reach another owner's data, or a key work off the private host? What will Phase 3c's per-owner Terminal rows inherit from here?` },
  { key: 'p1-auth', name: 'C-P1A', db: ['r1a', 55512], text: `LENS: Phase 1 authentication flows (CONTRACT sections 3, 4, 5, 6).
- registration, email codes, resend, sign-in, sessions, CSRF, sign-out-all, MFA enroll and verify, password forgot, reset and change;
- the throttle (app/throttle.py), the mailer, the hooks exemption, the session cookie and its rotation;
- the switch-off paths: everything must be 404 or exactly as before.
Code: apps/edge-bff/app/auth_flows.py, accounts.py, security.py, passwords.py, throttle.py, mailer.py, hooks.py, main.py, config.py; migrations 20261116_002, 20261116_003, 20261117_001, 20261117_002. Check them against OWASP and NIST rules as CONTRACT 4 states them.` },
  { key: 'p1-state', name: 'C-P1S', db: ['r1s', 55513], text: `LENS: Phase 1 per-user state and isolation (CONTRACT sections 2, 4b, 12, 14).
- owner_key on every stored row and every query: layouts, drawings, presets, watchlist lists, preferences, the Monitor's conversations, backtest jobs, results and trials, screener saved items;
- the browser side: shared/edge-session.ts (STORAGE, noteIdentity, seedKeeps, migrateBare, checkUser, the cleared broadcast), each page's api client (backtest, screener, radar, overview, watchlist, terminal data/*Api.ts).
Ask: can one user ever see, write or keep in the browser another user's state, including after sign-out, a user switch in the same browser, or a second tab?` },
  { key: 'p2-entitlements', name: 'C-P2', db: ['r2', 55514], text: `LENS: Phase 2 entitlements, the foundation Phase 3c builds on (CONTRACT sections 2, 8, 8a).
- app/principal.py: can, capped, refusal, access, version_of, read_grants, valid_value, RESTRICTIVE fail-closed, seed, expired_plan, switch_off_principal, account_principal, admin_owners;
- app/accounts.py: GRANTS, the lapsed CTE, seed_subscription;
- app/releases.py and catalog/releases.json; app/catalog.py; app/rights.py; app/errors.py display names;
- migrations 20261117_003 and 004: the triggers capability_value_check and capabilities_kind_fixed, the plan rows, the grants.
Phase 3c will read terminal.tickers (list), terminal.history_days (limit), terminal.dataset (items) and new limit rows through these functions. Check every kind (flag, limit, list, items), a missing row, a malformed value, overrides, an expired or cancelled subscription, two subscriptions, and the version changing when anything that changes access changes. Does "no row" ever mean "everything" where it must not?` },
  { key: 'p3a-gates', name: 'C-P3A', db: ['r3a', 55515], text: `LENS: Phase 3a route gates and caps (CONTRACT section 8b "3a in detail", decisions D1-D8).
- every edge-bff route: walk FastAPI's routes yourself, do not trust the existing route-walk scope; every second path to the same content; caps min(plan, HARD); LIMIT_REACHED and Retry-After;
- D5 (a lowered plan cannot read old items), PLAN_EXPIRED, the Monitor gates (D1), the page files (no-cache, <family>.view), the X-Edge-Entitlements header, refresh_names;
- the SSE re-check gap and other known OPEN rows of M481: confirm whether each is real.
Code: app/main.py, backtest.py, screener.py, watchlist.py, layouts.py, presets.py, drawings.py, pages.py, monitor.py, rights.py.` },
  { key: 'p3b-workers', name: 'C-P3B', db: ['r3b', 55516], text: `LENS: Phase 3b worker item gates (CONTRACT section 8b "3b in detail", "Found by the 3b checkers", ERRORS M482).
- the context wire {rights, allow, limits} from app/allow.py to apps/backtest-worker/src (access.ts, validate.ts, grammar.ts, server.ts, run.ts, compute.ts) and apps/screener-worker/src (run.ts, server.ts, pool.ts, errors.ts);
- every place an item can be named or computed; the caches (worker and edge-bff, keyed by allow digest); the job re-check; the preset items and the review per plan;
- the backtest-worker deployed by CLI from 3698a8a4: is the deployed worker the code in the repository? Compare engine_version logic only; do not call Railway.
The two checkers' known open items (O3b-1, O3b-2, step 3) are decided and being built now: do not report them again, unless a variant of the same class is not covered by "3b follow-up".` },
  { key: 'db-records-ci', name: 'C-DB', db: ['rdb', 55517], text: `LENS: migrations, database grants, records and CI.
- the migrations 20261116_001 to 20261117_004 against database/migrations/APPLIED.sha256, DATABASE_SCHEMA.md and DATABASE_CHANGELOG.md (what was applied, with which sha256, and read back);
- scripts/provision_edge_bff_login.py (the runtime role's grants: least privilege, nothing missing); the $verify$ blocks; the rollback comments;
- whether any table holds data whose change is not caught;
- CI: .github/workflows/backend-tests.yml, backtest-lookahead.yml, generated-files.yml and edge-bff-image.yml. Do they run every multi-user test? Are any tests skipped, marked, or unable to fail (a test that passes with the guarded code removed)? Try removing a guard and see whether a test fails, for the 10 most important guards.
- the records: CONTRACT, EXEC, ERRORS, RAILWAY_CHANGELOG. Is any status claimed without evidence?
You may run apply-and-verify of all edge_bff migrations on your own local cluster.` },
];

const SCHEMA = {
  type: 'object',
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          title: { type: 'string' },
          phase: { type: 'string', enum: ['0', '1', '2', '3a', '3b', 'cross'] },
          severity: { type: 'string', enum: ['blocks-3c', 'blocks-switch-on', 'non-blocking', 'records'] },
          status: { type: 'string', enum: ['VERIFIED', 'SUSPECTED'] },
          files: { type: 'array', items: { type: 'string' } },
          root_cause: { type: 'string' },
          evidence: { type: 'string' },
          failure_scenario: { type: 'string' },
          general_class: { type: 'string' },
          affects_3c: { type: 'boolean' },
          affects_3c_why: { type: 'string' },
          test_path: { type: ['string', 'null'] },
          test_commit: { type: ['string', 'null'] },
          fix: { type: 'string' },
          confirm_check: { type: 'string' },
        },
        required: ['title', 'phase', 'severity', 'status', 'files', 'root_cause', 'evidence', 'failure_scenario', 'general_class', 'affects_3c', 'fix'],
      },
    },
    checked: { type: 'array', items: { type: 'string' } },
    worktree_head: { type: ['string', 'null'] },
  },
  required: ['findings', 'checked'],
}

phase('Find')
const results = await parallel(LENSES.map(l => () =>
  agent(`${COMMON}\n\nYour checker name: ${l.name}. Your Postgres cluster: name ${l.db[0]}, port ${l.db[1]}.\n\n${l.text}`, {
    label: `find:${l.key}`, phase: 'Find', schema: SCHEMA, effort: 'xhigh', isolation: 'worktree',
  }).then(r => r ? { lens: l.key, name: l.name, ...r } : { lens: l.key, name: l.name, findings: [], checked: [], failed: true })))

let n = 0
const findings = []
for (const r of results.filter(Boolean)) for (const f of r.findings || []) findings.push({ id: `R1-${++n}`, lens: r.lens, checker: r.name, ...f })
log(`${findings.length} findings from ${results.filter(Boolean).length} finders`)
return {
  findings,
  checked: results.filter(Boolean).map(r => ({ lens: r.lens, failed: !!r.failed, worktree_head: r.worktree_head || null, checked: r.checked })),
}
