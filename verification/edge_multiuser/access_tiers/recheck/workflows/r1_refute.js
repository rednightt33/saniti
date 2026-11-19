export const meta = {
  name: 'mu-recheck-phases-0-3b-refute-r1',
  description: 'Ultracode re-check of EDGE multi-user Phases 0-3b, round 1 cross-check: 3 lens refuters x 3 batches judge the 46 findings at xhigh',
  phases: [{ title: 'Refute', detail: '3 lenses (reproduce, code path, spec and decisions) over 3 batches of findings' }],
}

const DIR = '/tmp/claude-0/-home-user-saniti/f3bec3b8-f6e3-5a54-b257-4a56b384bdc8/scratchpad/recheck'

const COMMON = `You are an independent SKEPTIC of findings from a re-check of the EDGE multi-user work (EXEC-MU-ACCOUNTS) in the repository rednightt33/saniti. Seven finders reviewed Phases 0, 1, 2, 3a and 3b, which are deployed on Railway dev with the switch EDGE_MULTIUSER off. They returned 46 findings. Your job is to try to REFUTE each finding of your batch from one lens, and to judge its severity, so that only real defects reach the fix round. Default to refuted=true only when you have evidence that the claim is wrong; when the claim holds, say so plainly. Do not invent new findings here, except as "notes" when you meet one by chance.

## Code to judge
You work in your own git worktree. Before anything else run:
  git checkout --detach ae9a1d8f
Commit ae9a1d8f is main bf273f52 (the deployed Phases 0-3b plus records) plus every failing test the finders committed (9 commits on top of bf273f52). Phase 3c and the 3b follow-up are built on branch p3c-int, commit 41067e7d, not deployed. For every finding, also check whether p3c-int already fixes it or changes it (read it with "git show 41067e7d:<path>" or "git diff bf273f52 41067e7d -- <path>"); report that in fixed_on_p3c_int.

## Ground truth
- verification/edge_multiuser/access_tiers/CONTRACT.md: the specification, sections 0-16, 8a and 8b; the user decisions D1-D8, O3b-1, O3b-2.
- EXEC.md, section "EXEC-MU-ACCOUNTS" to the end: the user's words, runbooks and run logs.
- ERRORS_AND_SOLUTIONS.md M468-M482: known defects, their fixes and open rows.
- The user's rules for fixes: verified root cause first; name the general class; no instance-specific patches (a fix naming one table, route or item is a patch unless that object is the root cause); fix at the layer that owns the mechanism (data model, backend validation, service contracts, prompts last); derive, do not enumerate.

## Findings
Your batch is the JSON file named below. Each finding has an id, title, severity (blocks-3c / blocks-switch-on / non-blocking / records), status, root_cause, evidence, failure_scenario, general_class, affects_3c, fix, test_path and test_commit. Judge every finding of your batch; return one verdict per id.

## Rules
- Verify every claim yourself with file:line evidence (AGENTS.md "Gates and evidence").
- Do not push, deploy, call Railway, or touch any remote database. Never print secrets. Do not commit anything.
- edge-bff pytest needs a Postgres cluster of your own:
  su pgtest -c "/usr/lib/postgresql/16/bin/initdb -D /home/pgtest/<NAME> -E UTF8 -U postgres --auth=trust"
  su pgtest -c "/usr/lib/postgresql/16/bin/pg_ctl -D /home/pgtest/<NAME> -o '-p <PORT> -k /tmp' -l /home/pgtest/<NAME>.log start"
  Run with EDGE_TEST_POSTGRES_URL=postgresql://postgres@127.0.0.1:<PORT>/postgres and EDGE_TEST_CHROMIUM=/opt/pw-browsers/chromium. One pytest process at a time on your cluster. Stop your cluster when done. If initdb says the folder exists, remove /home/pgtest/<NAME> first (it is yours).
- Node suites: run "npm ci" in the app folder only if node_modules is missing; the Terminal, Backtest and Screener pages are under apps/edge-bff/<page>.
- The machine is shared with other agents. Timing tests may flake under load: rerun alone before calling a failure.
- Severity meanings: blocks-3c = Phase 3c (Terminal data per plan: per-owner terminal-api rows, the x-terminal-capabilities header, the 730-day cut, per-owner quotas) builds on it, so it must be fixed before or with 3c; blocks-switch-on = must be fixed before EDGE_MULTIUSER goes on; non-blocking; records = a document, test or record gap only.

Return a verdict for every finding of your batch.`

const LENSES = [
  { key: 'repro', text: `LENS: REPRODUCE. For each finding with a committed test: run that test at ae9a1d8f and confirm it fails at the asserted line for the stated reason (not an import error, a fixture problem, the wrong base, or a flake; rerun once). Then judge the test itself: would a correct GENERAL fix make it pass, or does it lock one instance, an implementation detail, or a behaviour that contradicts a user decision? For a finding without a test, build the smallest probe that shows the failure (run it, do not commit it), or say why it cannot be shown locally. Also check that the failure scenario's precondition is reachable in the real deployment (switch on, real config, real callers), not only in a test double.` },
  { key: 'code', text: `LENS: CODE PATH AND DEFENCE IN DEPTH. For each finding: trace the whole path from the caller to the data, both sides (the page's code under apps/edge-bff/<page>/src and shared/, edge-bff app/, the workers, terminal-api, market-ai-orc, the database constraints, triggers and grants). Look for another layer that already prevents the failure. Check that the stated root cause is the real mechanism and is precise; if not, give the better root cause. Check that the general class is complete: list other sites of the same mechanism with file:line, and say whether the proposed fix covers them.` },
  { key: 'spec', text: `LENS: SPECIFICATION, DECISIONS AND RECORDS. For each finding: compare the claimed defect with CONTRACT.md, the user decisions (D1-D8, O3b-1, O3b-2 and the words in EXEC.md) and ERRORS M468-M482. Is the behaviour actually required, or did the user decide otherwise or accept it? Is it already recorded as OPEN, deferred or decided (give the entry)? Is the severity right: does Phase 3c really build on it (read the 3c design in CONTRACT 8b "3c in detail" and the code on p3c-int 41067e7d), and does it really have to be fixed before the switch goes on? Is the proposed fix general and at the right layer per the user's rules, and does it need the user's approval (Railway variables, cost, a decision change)? Name the approval needed.` },
]

const BATCHES = [
  { key: 'A', ids: 'R1-1 to R1-16 (lenses p0-runtime and p1-auth)' },
  { key: 'B', ids: 'R1-17 to R1-31 (lenses p1-state, p2-entitlements and p3a-gates)' },
  { key: 'C', ids: 'R1-32 to R1-46 (lenses p3b-workers and db-records-ci)' },
]

const VERDICTS = {
  type: 'object',
  properties: {
    verdicts: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          id: { type: 'string' },
          refuted: { type: 'boolean' },
          verdict: { type: 'string', enum: ['REAL', 'REAL-SEVERITY-CHANGE', 'PARTLY-REAL', 'DUPLICATE-KNOWN', 'REFUTED', 'UNCERTAIN'] },
          proposed_severity: { type: 'string', enum: ['blocks-3c', 'blocks-switch-on', 'non-blocking', 'records', 'none'] },
          reason: { type: 'string' },
          evidence: { type: 'string' },
          test_valid: { type: ['boolean', 'null'] },
          test_note: { type: 'string' },
          root_cause_correct: { type: 'boolean' },
          better_root_cause: { type: 'string' },
          fix_assessment: { type: 'string' },
          other_sites: { type: 'array', items: { type: 'string' } },
          fixed_on_p3c_int: { type: ['boolean', 'null'] },
          p3c_int_note: { type: 'string' },
          duplicate_of: { type: ['string', 'null'] },
          approval_needed: { type: ['string', 'null'] },
        },
        required: ['id', 'refuted', 'verdict', 'proposed_severity', 'reason', 'evidence', 'root_cause_correct', 'fixed_on_p3c_int'],
      },
    },
    notes: { type: 'array', items: { type: 'string' } },
  },
  required: ['verdicts'],
}

phase('Refute')
const jobs = []
let port = 55521
for (const b of BATCHES) for (const l of LENSES) {
  const p = port++
  jobs.push({ b, l, p })
}
const results = await parallel(jobs.map(j => () =>
  agent(`${COMMON}\n\nYour batch: ${j.b.ids}, in the file ${DIR}/r1_batch_${j.b.key}.json. The finders' "checked" lists are in ${DIR}/r1_checked.json if you need them.\nYour Postgres cluster: name ref_${j.b.key}_${j.l.key}, port ${j.p}.\n\n${j.l.text}`, {
    label: `refute:${j.b.key}:${j.l.key}`, phase: 'Refute', schema: VERDICTS, effort: 'xhigh', isolation: 'worktree',
  }).then(r => ({ batch: j.b.key, lens: j.l.key, failed: !r, verdicts: r ? r.verdicts : [], notes: r ? (r.notes || []) : [] }))))

const byId = {}
for (const r of results.filter(Boolean)) for (const v of r.verdicts) (byId[v.id] = byId[v.id] || []).push({ lens: r.lens, ...v })
const summary = Object.keys(byId).sort((a, b) => Number(a.split('-')[1]) - Number(b.split('-')[1])).map(id => {
  const vs = byId[id]
  const notRefuted = vs.filter(v => !v.refuted).length
  return { id, survives: notRefuted >= 2, not_refuted: notRefuted, judged_by: vs.length, severities: vs.map(v => `${v.lens}:${v.proposed_severity}`), verdicts: vs }
})
log(`${summary.filter(s => s.survives).length}/${summary.length} findings survive; ${results.filter(r => r && r.failed).length} refuters failed`)
return { summary, failed: results.filter(r => r && r.failed).map(r => `${r.batch}:${r.lens}`), notes: results.filter(Boolean).flatMap(r => r.notes.map(n => `${r.batch}:${r.lens}: ${n}`)) }