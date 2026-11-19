export const meta = {
  name: 'edge-beta-live-environment-design',
  description: 'Research best practice and Railway capabilities, map the current architecture, then three designs and two judges for separating the admin (beta) site from live production',
  phases: [
    { title: 'Understand', detail: 'architecture map from the repo, general best practice, Railway capabilities and prices' },
    { title: 'Design', detail: 'three designs from different angles' },
    { title: 'Judge', detail: 'two judges score the designs; one synthesis' },
  ],
}

const CONTEXT = `## The question (the user's words, 2026-11-19, translated)
"About the environment we discussed: is this best practice? Research first and propose to me how we should separate the admin environment and live production later, given the current architecture."

## What was discussed and decided today (to be re-examined, not taken as settled)
- The EDGE website (service edge-bff, FastAPI plus static pages Terminal, Backtest, Screener, Radar, Overview, Watchlist, Monitor/AI) runs in the only Railway environment, "dev", project 8aef1702-030b-49cb-9df7-5ac2e0a42691. Every other service runs there too, and AI agents apply code and database migrations there directly.
- Multi-user accounts (EXEC-MU-ACCOUNTS) are being built behind the switch EDGE_MULTIUSER (off). Launch = switch on, planned around 26 Nov - 3 Dec 2026, with the user's own domain and Resend for email.
- The user chose, after three options (full copy / light production / swap roles): one environment, two websites. The beta is the current Railway address (edge-bff, admin only = the user). The live site is a second edge-bff service (edge-bff-live) on the user's domain that moves to a tested version only on the user's "push ke live". Only the website is doubled. The database, terminal-api, backtest-worker, screener-worker, market-ai-orc and every data job are shared. The user then asked whether this is best practice.
- The user is not a developer. AI agents do all the building and operations under AGENTS.md rules. The user is cost-sensitive: Railway bills container memory including page cache; the main Postgres memory limit was cut to 2 GB (history in .railway/railway.ts comments). AI is admin-only at launch (decision D1); the free plan sees BBCA only (D2/D3).

## Repository
rednightt33/saniti, checked out in your working directory. Key files: .railway/railway.ts (every service, cron, volume, bucket, env names), PROJECT_CONTEXT.md, README.md, RAILWAY_CHANGELOG.md, DATABASE_CHANGELOG.md, DATABASE_SCHEMA.md, AGENTS.md, EXEC.md (section EXEC-MU-ACCOUNTS to the end, incl. "Production environment"), verification/edge_multiuser/access_tiers/CONTRACT.md, apps/*/README.md. Do not change files, deploy, call Railway or touch any database. Never print secrets.`

phase('Understand')
const [arch, practice, railway] = await parallel([
  () => agent(`${CONTEXT}

YOUR TASK: map the current architecture as it bears on separating a beta/admin site from live production. From the repository only, with file:line evidence. Cover:
1. Every service, cron, database, volume and bucket (.railway/railway.ts), grouped: user-facing request path; data production (crons, publisher, Stockbit, prices, Feature workers); AI (orc, governors, sandbox, audit store); operations (telegram, runners, restart cron, pgweb).
2. The user-facing request path in detail: what edge-bff, terminal-api, backtest-worker and screener-worker read and write (database schemas and logins, the terminal-display bucket, Orc), and where the user data of the multi-user work lives (edge_bff schema tables, terminal schema subscribers/access_log, Orc conversation tables). Which of these are shared by any two websites on one database.
3. What changes how often: from RAILWAY_CHANGELOG.md and DATABASE_CHANGELOG.md of the last 30 days, roughly count deploys per service and migrations per schema, and classify which kinds of change could break users (website code, worker code, terminal-api, migrations to edge_bff/terminal schemas, migrations to data tables, publisher output formats, AI).
4. How deploys happen today: GitHub-connected with checkSuites, CLI uploads, watchPatterns, the rollback points the records keep, and how migrations are applied (scripts, runners).
5. Sizes and costs you can find: Postgres size, memory limits, volumes, the number of always-on services.
6. Background loops inside edge-bff (backtest job loop, email sender, hourly purge, account seed, throttle) and anything that assumes one edge-bff instance.
Return a structured, dense report with evidence.`, { label: 'map:architecture', phase: 'Understand', effort: 'high' }),
  () => agent(`${CONTEXT}

YOUR TASK: research general best practice (web search and reading primary sources: cloud provider architecture guides, the Twelve-Factor App, Google SRE book, Martin Fowler's articles on blue-green deployment, feature toggles, ParallelChange/expand-contract, database refactoring, Heroku/Render/Fly/Railway guides, OWASP on admin interfaces, well-known engineering blogs). Questions:
1. Is "one environment, two website versions (beta and live) sharing one production database and back-end services" an accepted pattern? Under which names (e.g. canary, beta channel, blue-green with shared database, dark launch, ring deployment)? What are its known risks and when is it considered acceptable?
2. The standard alternatives: separate staging and production environments with separate databases; staging with a copy or anonymised snapshot of production data; read-only sharing of reference/market data between environments; feature flags in one deployment; preview environments per pull request. Pros, cons and typical cost for a small team.
3. How teams handle data that is produced once (here: market data produced by daily jobs) but must be available in both staging and production.
4. Separation of admin interfaces from the public site: same app with roles vs separate admin deployment/host; security recommendations.
5. Database migrations when two versions run at once (expand-contract), and rollback.
6. What a solo, non-developer owner with AI agents doing operations should prefer: simplicity vs isolation.
Cite every claim with the URL. Return a dense report.`, { label: 'research:best-practice', phase: 'Understand', effort: 'high' }),
  () => agent(`${CONTEXT}

YOUR TASK: research Railway's actual capabilities and prices from docs.railway.com, railway.com/pricing, the Railway changelog and blog, and Railway Help Station / community answers. Questions:
1. Environments: creating (duplicate vs empty), what a duplicate copies (services, variables, volumes and database data, domains, buckets), Sync between environments, PR/preview environments, restricting who can deploy to an environment, environment-specific deploy branches (can production follow one git branch and staging another?).
2. Networking: is the private network per environment? Can a service in one environment reach a database or service in another (private or via TCP proxy / public)? Shared variables across environments.
3. Databases: copying a Postgres to another environment, backups/restore into another service, read replicas or logical replication between two Railway Postgres services, and their costs.
4. Buckets: per environment, credentials, can one bucket be read from another environment, copying objects.
5. Prices: memory per GB-month, vCPU, volume per GB, egress, bucket storage and operations, plan limits (Hobby vs Pro), and what an idle small service costs. Give numbers with dates and sources.
6. Custom domains per service, several domains on one service, TLS, and how a domain moves between services or environments.
7. Deploy controls: deploy only on green GitHub checks, manual approval, rollback to a previous deployment, pinning a service to a commit.
Cite every claim with the URL. State clearly what the docs do not say. Return a dense report.`, { label: 'research:railway', phase: 'Understand', effort: 'high' }),
])

const FACTS = `## Findings of the understanding phase
### A. Current architecture (from the repository)
${arch || '(architecture mapper failed)'}

### B. General best practice (web research)
${practice || '(best-practice researcher failed)'}

### C. Railway capabilities and prices (web research)
${railway || '(Railway researcher failed)'}`

phase('Design')
const ANGLES = [
  { key: 'lean', text: 'ANGLE: LEAN AND FAST. Minimise cost and time to launch for a solo owner, while keeping live users safe from the changes the AI agents try every day. Prefer what reuses the current setup.' },
  { key: 'isolated', text: 'ANGLE: ISOLATION AND RISK FIRST. Assume that agents will make mistakes in migrations, data jobs and code. Design so that no mistake in the admin/beta side can reach live users or their data, and so that live user data is protected. Then price it honestly.' },
  { key: 'operable', text: 'ANGLE: OPERABILITY FOR A NON-DEVELOPER OWNER AND AI AGENTS. Optimise for what is simple to run every day: few moving parts, clear promote and rollback steps the owner can trigger in plain words, the rules in AGENTS.md (deploy checks, migrations, records), and the data jobs that already run in dev.' },
]
const designs = await parallel(ANGLES.map(a => () => agent(`${CONTEXT}

${FACTS}

YOU ARE A DESIGNER. ${a.text}

Propose ONE concrete architecture for separating the admin/beta site from live production for EDGE, given the facts above. It may confirm, adjust or replace the user's current choice. Include:
1. Topology: which Railway environments and services exist, which are shared, which domains point where.
2. Data: where live user data lives (accounts, sessions, subscriptions, saved items, backtest jobs, conversations, terminal access logs), where market data is produced and how it reaches live (and how a bad data job is kept from reaching live, if at all).
3. Change flow: how website code, worker code, terminal-api, AI, database migrations (user schemas and data tables) and publisher output move from beta to live; the promote step in the owner's words; rollback.
4. Admin: how the admin reaches admin-only features (AI Monitor, lab items, the Phase 4 dashboard) and how that is kept off the public site.
5. Cost: monthly estimate with the Railway prices found (state assumptions), compared with today.
6. Effort: what must be built or changed before launch and after, in days; what changes in AGENTS.md rules.
7. Risks and what it does not protect against; when to move to the next stage of separation (a growth path).
Be concrete and cite the facts (file:line or URL) you rely on.`, { label: `design:${a.key}`, phase: 'Design', effort: 'xhigh' })))

const DESIGNS = ANGLES.map((a, i) => `### Design ${i + 1} (${a.key})\n${designs[i] || '(designer failed)'}`).join('\n\n')

phase('Judge')
const SCORES = {
  type: 'object',
  properties: {
    scores: { type: 'array', items: { type: 'object', properties: {
      design: { type: 'integer' }, live_safety: { type: 'integer' }, user_data_protection: { type: 'integer' }, cost: { type: 'integer' },
      time_to_launch: { type: 'integer' }, operability: { type: 'integer' }, fit_current_architecture: { type: 'integer' }, total: { type: 'integer' },
      strengths: { type: 'string' }, weaknesses: { type: 'string' }, factual_errors: { type: 'string' } },
      required: ['design', 'live_safety', 'user_data_protection', 'cost', 'time_to_launch', 'operability', 'fit_current_architecture', 'total', 'strengths', 'weaknesses', 'factual_errors'] } },
    winner: { type: 'integer' },
    grafts: { type: 'array', items: { type: 'string' } },
    verdict_on_user_choice: { type: 'string' },
  },
  required: ['scores', 'winner', 'grafts', 'verdict_on_user_choice'],
}
const JUDGES = [
  'You weigh live safety and user data protection highest, then cost.',
  'You weigh cost, time to launch and operability for a solo non-developer owner highest, then safety.',
]
const judged = await parallel(JUDGES.map((j, i) => () => agent(`${CONTEXT}

${FACTS}

## Designs
${DESIGNS}

YOU ARE JUDGE ${i + 1}. ${j} Score each design 1-10 on each criterion (live_safety, user_data_protection, cost, time_to_launch, operability, fit_current_architecture) and give a total. Check each design's facts against the findings (wrong Railway capabilities, wrong prices, wrong claims about the code) and list factual errors. Name the winner, the ideas worth grafting from the others, and a verdict on the user's current choice (one environment, two websites, only the website doubled, shared database): is it acceptable as a first stage, and what must be added to make it safe?`, { label: `judge:${i + 1}`, phase: 'Judge', schema: SCORES, effort: 'xhigh' })))

const synthesis = await agent(`${CONTEXT}

${FACTS}

## Designs
${DESIGNS}

## Judges
${JSON.stringify(judged.filter(Boolean), null, 1)}

YOU ARE THE SYNTHESISER. Produce the final proposal for the user:
1. A direct answer: is the user's current choice best practice, acceptable as a first stage, or not; why, in plain words.
2. The recommended architecture (start from the judges' winner, graft the best ideas), with: topology, where each kind of data lives, the promote and rollback steps, how admin features stay off the public site, cost per month versus today (with assumptions), effort before launch in days, risks it does not cover.
3. One or two alternatives the user could reasonably prefer, with the trade-off in one line each.
4. A growth path: the trigger for each next step of separation (e.g. first paying users, AI opened to paid plans).
5. The decisions the user must take, as short options.
6. Every factual claim with its source (file:line or URL); drop claims the judges marked wrong.
Be dense and precise; the main agent will translate it for a non-developer.`, { label: 'synthesis', phase: 'Judge', effort: 'xhigh' })

return { synthesis, judged: judged.filter(Boolean), designs, arch, practice, railway }