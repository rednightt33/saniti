export const meta = {
  name: 'mu-recheck-phases-0-3b-find-r2',
  description: 'Ultracode re-check of EDGE multi-user Phases 0-3b, round 2: 7 finders from new angles at xhigh, told the 46 round-1 findings',
  phases: [{ title: 'Find', detail: '7 new angles: version skew, races, browser attacker, data lifecycle, switch-on end to end, operations, contract trace' }],
}

const DIR = '/tmp/claude-0/-home-user-saniti/f3bec3b8-f6e3-5a54-b257-4a56b384bdc8/scratchpad/recheck'

const COMMON = `You are an independent checker of the EDGE multi-user work (EXEC-MU-ACCOUNTS) in the repository rednightt33/saniti. This is ROUND 2 of an ultracode re-check of Phases 0, 1, 2, 3a and 3b, which are deployed on Railway dev with the switch EDGE_MULTIUSER off. Phase 3c (Terminal data per plan) is built on branch p3c-int (commit 41067e7d) and waits on this re-check. The user's worry: "Jangan sampai fase 3C di bangun dari broken block fase2 sebelumnya."

## Code
You work in your own git worktree. Before anything else run:
  git checkout -B r2-<your lens key> ae9a1d8f
Commit ae9a1d8f is main bf273f52 (deployed Phases 0-3b plus records) plus the round-1 finders' failing tests. 24 tests in the files test_cp0_*, test_cp1a_*, test_c_p1s_*, test_c_p2_*, test_c_p3a_*, test_c_p3b_*, test_cdb_* and the c-p3b-recheck worker tests fail there on purpose: they belong to round 1. Read p3c-int with "git show 41067e7d:<path>" when a finding concerns what 3c builds on.

## Already found: do not report again
Round 1 found 46 defects, all confirmed by three refuters. They are listed, with their general class, in ${DIR}/r1_seen.json, together with the refuters' side notes. Read it first. Report a finding only if it is NEW: a different mechanism, or a site of a known class that the round-1 entry and its proposed fix do not cover (then say which entry and why its fix misses it). Your angle is new on purpose; use it.

## Ground truth
- verification/edge_multiuser/access_tiers/CONTRACT.md (sections 0-16, 8a, 8b; decisions D1-D8, O3b-1, O3b-2).
- EXEC.md, section "EXEC-MU-ACCOUNTS" to the end, including "Production environment": the user plans two websites in the same Railway environment, a beta at the Railway address (the service edge-bff, following main) and a live site at the user's domain (a second edge-bff service, moved to a tested version only on the user's "push ke live"), sharing one database and every other service. Not built and its details are open; where a finding would get worse, or appear, with two edge-bff versions on one database, say so in affects_beta_live.
- ERRORS_AND_SOLUTIONS.md M468-M482.

## How to work
- Verify every claim in the code with file:line evidence. Prove it with a failing test or a probe that runs whenever you can. VERIFIED needs evidence; SUSPECTED names the check that would confirm it.
- For each finding give the general class: the mechanism and the other routes, tables, services or tabs that can hit it, including 3c's paths and later tabs (3e page locks, Phase 4 admin, Phase 5 payments).
- Commit only the failing tests of VERIFIED findings on your branch (they are what the fix round makes pass). Commit messages end with exactly:
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_015yBxadqbqnpdpSwmfCDQca
- Do not push, deploy, call Railway, or touch any remote database. Never print secrets.
- edge-bff pytest needs your own Postgres cluster:
  su pgtest -c "/usr/lib/postgresql/16/bin/initdb -D /home/pgtest/<NAME> -E UTF8 -U postgres --auth=trust"   (remove /home/pgtest/<NAME> first if it exists; it is yours)
  su pgtest -c "/usr/lib/postgresql/16/bin/pg_ctl -D /home/pgtest/<NAME> -o '-p <PORT> -k /tmp' -l /home/pgtest/<NAME>.log start"
  EDGE_TEST_POSTGRES_URL=postgresql://postgres@127.0.0.1:<PORT>/postgres EDGE_TEST_CHROMIUM=/opt/pw-browsers/chromium. One pytest process at a time on your cluster. Stop it when done.
- Node: run "npm ci" in a page folder only if node_modules is missing; playwright for node scripts resolves with NODE_PATH=/opt/node-tools/node_modules.
- The machine is shared: rerun a timing failure alone before calling it real.
- Severity: blocks-3c (3c builds on it); blocks-switch-on (fix before EDGE_MULTIUSER goes on); non-blocking; records (document, test or record gap only).

Return findings only with evidence. An empty list with a thorough "checked" list is a valid answer.`

const LENSES = [
  { key: 'skew', name: 'C2-SKEW', port: 55531, text: `LENS: VERSION SKEW AND DEPLOY ORDER. Services deploy separately (edge-bff from main after checks; terminal-api, the workers and Orc by CLI upload) and migrations are applied before or after code. Check every pair: edge-bff with terminal-api, with each worker, with Orc, and each with the database schema, across the recorded deploy orders of Phases 0-3b (EXEC.md run logs, RAILWAY_CHANGELOG.md) and the planned 3c order. Ask: during the window between two deploys, or after a rollback to a recorded rollback point, does any request fail, any check open, or any row get written that the other version misreads? Are the wire formats versioned, and does an unknown field or value fail closed? Then the beta/live plan: two edge-bff versions on one database and shared workers. Which tables, background loops (backtest job loop, email sender, hourly purge, the account seed, the throttle) and caches would two versions fight over?` },
  { key: 'race', name: 'C2-RACE', port: 55532, text: `LENS: CONCURRENCY AND RACES. Two requests at once from one user, two tabs, two users, two edge-bff replicas or processes, the background loops beside the routes. Check: session rotation and sign-out-all against requests in flight; the throttle counters under parallel tries (can 20 parallel wrong codes all pass the check before any is counted?); registration and username races; MFA enrolment and verify races; subscription or override changes while a job or SSE stream runs (time of check versus time of use, the grants version); job leases and the job re-check; idempotency keys and client_request_id replays; the email outbox claim and lease. Prove races with tests that run the requests concurrently (threads against the real Postgres cluster), not by reading alone.` },
  { key: 'browser', name: 'C2-WEB', port: 55533, text: `LENS: THE BROWSER AS AN ATTACKER AND AS A USER. Every page of EDGE (the shell static/, and the pages terminal, backtest, screener, radar, overview, watchlist, account pages /register /verify /forgot /reset /mfa). Check: CSRF on every state-changing route (method, origin and token rules, including the hooks exemption and GET routes that change state); the CSP and every inline script or style; cookie flags and scope; cache headers on every authenticated or per-plan answer (a shared or browser cache serving one user's answer to another, or an old plan's answer); clickjacking; open redirects (next= or return parameters); HTML injection through user-chosen names (username, first and last name, saved item names, layout names) in every place they are shown, including emails and the admin views planned for Phase 4. Then the user's side: every refusal code a page can receive (CONTRACT section 3) and whether each page shows its words and its way out (AGENTS.md Gates (d)), with the session module shared/edge-session.ts.` },
  { key: 'life', name: 'C2-LIFE', port: 55534, text: `LENS: DATA LIFECYCLE, PRIVACY AND LOGS. Follow each personal datum (email, phone, name, IP, user agent, codes, password verifiers, TOTP secrets and recovery codes, session ids) from where it enters to every place it is stored or written: tables, logs (edge-bff, terminal-api, Orc: what does each log line contain?), the email outbox and its payload nulling, Telegram notifications, the audit tables, exports, error answers, the browser storage. Check retention and deletion: what the hourly purge removes, what a user deletion cascades or leaves (subscriptions ON DELETE CASCADE was noted in round 1), whether codes and secrets are stored hashed or encrypted as CONTRACT says, and whether any log or answer leaks one user's datum to another or to the page. Check that masking is applied everywhere CONTRACT asks (email and phone masked in lists).` },
  { key: 'e2e', name: 'C2-E2E', port: 55535, text: `LENS: SWITCH ON, END TO END, AS THREE PEOPLE. Run edge-bff locally with EDGE_MULTIUSER on against your cluster (read conftest.py and the existing browser tests for how the suite starts the app with fakes for Orc, terminal-api and the workers; reuse that harness, the fixture data of M469 and EDGE_EMAIL_MODE=log). Then act as three people in a real browser (playwright, chromium at /opt/pw-browsers/chromium): the admin (user #1, with MFA), a paid user and a free user. Register, verify, sign in, use every tab, save items, lower a plan (D5), expire a plan, sign out, switch user in the same browser, open two tabs. Look for anything that breaks, leaks, shows the wrong words, or contradicts CONTRACT or D1-D8. Commit each reproducible failure as a test (a pytest browser test or a node smoke script beside the existing ones).` },
  { key: 'ops', name: 'C2-OPS', port: 55536, text: `LENS: OPERATIONS, FAILURE MODES AND PERFORMANCE. Check: start-up validation (config.validate) for every switch and secret combination, and what /ready says in each; behaviour when Postgres restarts mid-request (the planned 09:45 and 20:45 WIB restarts, AGENTS.md), when terminal-api, a worker, Orc or the email provider is down or slow; the M340 user-run check (scripts/restart_postgres.py and the deploy rule) against the new tables that hold user runs (do the guards still see every running job?); the growth of the new tables (auth_throttle, sessions, email_codes, email_outbox, admin_audit, terminal access_log) and whether each has a purge and an index for its hot query. AGENTS.md "Performance": for the high-frequency queries of the principal (session resolve, read_grants, the throttle), run bounded EXPLAIN (ANALYZE, BUFFERS) on your cluster with realistic row counts (insert e.g. 100k sessions and throttle rows) and report a missing index or a full scan with the plan as evidence.` },
  { key: 'trace', name: 'C2-TRACE', port: 55537, text: `LENS: CONTRACT TRACEABILITY. Make a matrix of every requirement (each MUST, each rule, each table column, each route, each refusal code, each acceptance test of section 13) in CONTRACT.md sections 0-8b that belongs to Phases 0-3b, and for each one find the code that builds it and the test that locks it (file:line both). Report every requirement with no code, code that differs from it, or no test (a test that cannot fail counts as none: check by breaking the code where cheap). Also check the reverse: code paths in apps/edge-bff/app that implement behaviour the CONTRACT does not describe. Skip requirements already in r1_seen.json.` },
]

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
          related_r1: { type: ['string', 'null'] },
          affects_3c: { type: 'boolean' },
          affects_3c_why: { type: 'string' },
          affects_beta_live: { type: 'string' },
          test_path: { type: ['string', 'null'] },
          test_commit: { type: ['string', 'null'] },
          fix: { type: 'string' },
          confirm_check: { type: 'string' },
        },
        required: ['title', 'phase', 'severity', 'status', 'files', 'root_cause', 'evidence', 'failure_scenario', 'general_class', 'affects_3c', 'fix'],
      },
    },
    checked: { type: 'array', items: { type: 'string' } },
    worktree_branch: { type: ['string', 'null'] },
    worktree_head: { type: ['string', 'null'] },
  },
  required: ['findings', 'checked'],
}

phase('Find')
const results = await parallel(LENSES.map(l => () =>
  agent(`${COMMON}\n\nYour checker name: ${l.name}; your lens key: ${l.key}. Your Postgres cluster: name r2_${l.key}, port ${l.port}.\n\n${l.text}`, {
    label: `find2:${l.key}`, phase: 'Find', schema: SCHEMA, effort: 'xhigh', isolation: 'worktree',
  }).then(r => r ? { lens: l.key, name: l.name, ...r } : { lens: l.key, name: l.name, findings: [], checked: [], failed: true })))

let n = 0
const findings = []
for (const r of results.filter(Boolean)) for (const f of r.findings || []) findings.push({ id: `R2-${++n}`, lens: r.lens, checker: r.name, ...f })
log(`${findings.length} new findings from ${results.filter(r => r && !r.failed).length} finders (${results.filter(r => r && r.failed).length} failed)`)
return {
  findings,
  checked: results.filter(Boolean).map(r => ({ lens: r.lens, failed: !!r.failed, branch: r.worktree_branch || null, head: r.worktree_head || null, checked: r.checked })),
}