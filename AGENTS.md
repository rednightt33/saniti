# Agent instructions

## Required reading

Before touching Railway or PostgreSQL, read `README.md`, `PROJECT_CONTEXT.md`, `DATABASE_SCHEMA.md`, `DATABASE_CATALOG.md`, `DATABASE_CHANGELOG.md`, `RAILWAY_CHANGELOG.md`, and `ERRORS_AND_SOLUTIONS.md` completely. Read the relevant files under `database/migrations/` before changing an existing table.

`ERRORS_AND_SOLUTIONS.md` lists every error found so far, with its root cause, solution and status. Check it before diagnosing a failure: the error may already be known. Its Part A is the data-format standard. Before adding a new data source or table (for example cross-asset or macro data), confirm that it meets every item of Part A, and settle any gap with the user before loading. To expose a table or Feature to the AI (onboarding), follow `NEW_TABLE_ONBOARDING_PLAN.md` end to end, Feature 04 being the benchmark; its index acceptance (section 3) is part of every onboarding.

To add an indicator (the Terminal, the Screener and the Backtest) on the beta only, or to release one to the live site,
follow `INDICATOR_BETA_TO_LIVE.md` literally (user 2026-11-23: "Ok untuk indicator beta to live MD, masukan ke agents md
beserta 2 docs sebelumnya agar AI bisa refer that"), with `SCREENER_ONBOARDING.md` §2.11 (the worked example of an
indicator end to end) and §3.2 (its one-page checklist) and `LIVE_PROMOTION.md` §3 (the lab, preview and released
switches) and §4 (the steps of a promotion). An item on the live site for the admin only follows its Part C (the
`preview` stage, user 2026-11-23).

Before changing the backtest (`apps/edge-bff/backtest`, `apps/backtest-worker`, `apps/edge-bff/app/backtest.py`, or the
publisher files and terminal-api routes it reads), read `BACKTEST_END_TO_END.md` (the flow from PostgreSQL to the page)
and `apps/edge-bff/backtest/CONTRACT.md` (its rules).

To update the broker tables after `IDX_Broker_Summary` changes (Feature 02, 03, 05, 06 and the `_INDEX` tables), follow `UPDATE_TABLE.md`: refresh order, checks, and the open gap that the loader in Git does not write `buy_freq`/`sell_freq`. To update the Stockbit corporate actions, insider movements and `idx_event_annotation` (ad hoc, with a token the user gives), follow `UPDATE_TABLE.md` part B. After a split, bonus share or rights issue (the daily Telegram "Basis harga lawan data broker" lists the ones that need it), follow `UPDATE_TABLE.md` part C: the price history is pulled again with the user's go, the broker data stays as it is, and the publisher measures the broker basis itself (EXEC-BACKTEST-REVAMP P9).

## Backtest look-ahead gate

User decision 2026-11-15 (EXEC-BACKTEST-REVAMP, decision 3: "uji look-ahead menjadi gerbang CI wajib"): a value the
Backtest reads on day t may use only data up to t. `.github/workflows/backtest-lookahead.yml` runs, on every push and pull
request, the worker suite (`apps/backtest-worker/tests/lookahead.test.ts`: every registry series, transform, pattern,
Flow FL01-FL52 with every option and the engine as a whole on data cut at t, with a self-test that a centred average is
caught; `pit.test.ts`, `flow-grammar.test.ts`, `grammar.test.ts`: the point-in-time indicators, the Flow indicators and
the grammar through the worker's own path) and the Screener and page suites. A new indicator, Flow indicator, transform,
pattern or condition kind enters the gate by the registries it is derived from; a test is never skipped to pass it
(edge-bff and screener-worker deployed only on green checks, K10 a, until the user turned Wait for CI off on 2026-11-23,
section "Deploys"; the gate still runs on every push and its red is reported). Before a release that changes what the Backtest
reads, run the real-data check too (`verification/backtest/lookahead/README.md`). The Terminal (`apps/edge-bff/terminal`)
keeps its own hindsight indicators (user: "Terminal jangan disentuh"); the Backtest reads their point-in-time versions
(`apps/backtest-worker/src/pit/`, worker-only, admins only).

## Plans

- `EXEC.md` holds every execution the user approved, one complete section per execution (user decision 2026-10-06).
  The pending-decisions register of EXEC-MU-ACCOUNTS (Findings and fixes, rule 6; user 2026-11-22) holds the open
  questions to the user of that execution.
  `PLAN.md` holds approved work that has no execution plan yet. `FUTURE_PLAN.md` holds proposals, future work and open
  user decisions. Do not create dated plan files (`PLAN_YYYY-MM-DD.md`, `ROUND_PLAN_*`); the old ones are discussion
  history (user decision 2026-10-06).
- Record an approval in `PLAN.md` or `EXEC.md` in the same task, with its date and the user's words, even when the user
  approves "in general"; keep only the open details as questions on that item (R34). Approval to plan is not a command to
  execute: an execution starts only after the user's go confirmation.
- When an item is done, record it in `ERRORS_AND_SOLUTIONS.md` and the changelogs and remove it from `PLAN.md` or
  `EXEC.md`.
- Before a golden test, compare `PLAN.md` and `EXEC.md` with the deployed behaviour and report any approved item not yet
  built.

## Judgement principle

User decision 2026-10-06, extended 2026-10-07 (verbatim text in `EXEC.md`, EXEC-D): the AI is dynamic but bounded.
Judgement (what the user means, the route, when to ask back, the question, design values) belongs to the model. Code
keeps only the guarantees: tools locked per step; data only after approval; every figure sourced; thresholds and
horizons locked to the user's words; each quick choice runs its route; a fixed question when the model fails; at most
two questions in a row. The model may always ask back when the user's intent is ambiguous, on any path; a rule that
forbids asking back is a defect unless a guarantee requires it. For every rule in code ask:

1. Does it protect data, cost or the correctness of figures? Then it is a guarantee and stays in code.
2. Does it guess the user's intent or force one kind of answer? Then it is judgement and moves to the model.
3. If the model judges wrongly, is there a way out by asking back? If not, add one.
4. Which test locks the rule, and must that test change?

## Gates and evidence

User decisions 2026-10-19 (verbatim in `EXEC.md`, EXEC-FASTLANE-LEN):

- Every refusal the AI meets is a failure of our guidance, not of the model. Every gate that can refuse a model reply
  must have (a) a rule the model sees before it writes, (b) how to pass it, (c) one right and one wrong example, and
  (d) a refusal message that names where the problem is and how to fix it. A new or changed gate does not ship
  without all four.
- Every code change that is executed and every claim about how the system behaves rests on inspecting the code, the
  logs and the live data at that moment, not on memory of the conversation; cite the file:line, log or run ID as
  evidence.

## Findings and fixes

User decisions 2026-11-22 (verbatim in `EXEC.md`, EXEC-MU-ACCOUNTS "The user's decisions of 2026-11-22"): "Perbaikan
proses di atas: setuju saya terapkan dan catat sebagai aturan kerja mulai sekarang? OK setuju" and "Setelah selesai bisa
assign 5 sub-agents Opus 5,5 medium untuk actually test out whether perbaikan bug sudah selesai." They answer the root
causes of ERRORS M544 (verified findings left unsolved between phases, workflow `wf_539660fc-8ff`).

1. **Done means every part.** A finding is closed only when every part of it is fixed, the other places with the same
   mechanism included. A part left open becomes an item in `PLAN.md` or `EXEC.md` with an owner and a trigger, never
   only a status word in `ERRORS_AND_SOLUTIONS.md`. A report counts parts, not ids.
2. **One owner per finding.** A fix round assigns findings, not files; a finding that crosses files stays with its owner.
3. **A deferral has a trigger.** "After X" names X and goes into the pending-decisions register; when X happens the
   register is read and the item is done or asked.
4. **The user's decisions are asked, not narrowed or taken.** When a finding or a design value needs the user, it is
   asked with context (Questions to the user) and entered in the register; the agent does not build an action the user
   did not ask for (ERRORS M535).
5. **Checker results are used as written.** A checker's output is read from its journal with unique ids (run plus
   finding id), never re-keyed by a bare id, and every verdict is read (the skeptics' notes too).
6. **Pending-decisions register.** `EXEC.md` EXEC-MU-ACCOUNTS "Pending decisions" lists every open question to the user:
   what it is, when it was asked, what it holds back, and by when it is needed. It is shown to the user at the end of
   every phase. A question asked only in chat is not asked.
7. **A latent gap is asked, not only held.** A gap kept closed by a guard test is also put in the plan or asked.
8. **Re-check after every fix round, only with the user's explicit approval** (user 2026-11-22: "Masukan ke memory:
   workflow ditambahkan 1 fase lagi which to test out perbaikan ya"; changed by the user 2026-11-24: "Aturan 8 harus
   dijalankan dengan approval saya explicit dengan pemilihan model dan tingkat berpikir yang I'll decide. Tapi purpose
   dari itu adalah pengecekan bug yang sudah di fix alhasil dari pengecekan dari subagents sebelumnya"). Two different
   steps:
   - The *initial check* is the one the user orders (for example "10 agent Sonnet high"): agents find the bugs, the
     agent fixes them.
   - The *re-check* tests out the fixes of the bugs that check found. It runs only after the user approves it
     explicitly, each time, and with the model and the thinking level (effort) the user chooses; the agent never starts
     one on its own, nor a second round. When the fixes are done, the agent asks with context: which findings were
     fixed, how many agents and areas it proposes, and that the user picks the model and the effort.
   In an approved re-check the agents receive the original findings, not the fix summary; each reproduces the original
   failure, looks for the same mechanism elsewhere, and returns a verdict per item (fixed, partly, not fixed, cannot
   tell) with its evidence (the test or probe run, file:line). An item found incomplete is fixed and, with the user's
   approval again, tested out alone; at most two rounds, then what remains goes into the register. CI is green as well.
   A fix that no agent other than its author tested out is not called done in a report: until the user approves a
   re-check, the report says the fix was tested by its author only.
   `RECHECK.md` is the list of those fixes across executions (user 2026-11-24, UD39, EXEC-RECHECK-LIST: "Recheck MD
   perlu dimention juga di AGENTS MD dan harus di update, jadi AI bisa refer ke recheck MD untuk cek item yang sudah
   diperbaiki tapi perbaikannya belum di QA"; "UD39 ok - masukan EXEC"). It is written by
   `python3 scripts/recheck_doc.py --write` from its one source, `verification/records/recheck_ledger.json` (one row per
   finding, keyed by run plus finding id; the step-8 ledger's rows moved into it on 2026-11-24):
   - A fix no agent other than its author tested out enters the ledger in the same commit as the fix: its key, the
     original finding as the checker wrote it (the ERRORS entry's symptom when no checker found it), its fix commits,
     where it runs, how its author tested it, status `waiting`; RECHECK.md is rewritten with it.
     `scripts/tests/test_recheck_ledger.py` fails when an ERRORS_AND_SOLUTIONS.md entry says its fix was tested by its
     author only and no row names it, when a status is unknown, a fix commit is not in Git, or where a fix runs differs
     from `verification/records/deployed_commits.json` (after a deploy, `python3 scripts/recheck_doc.py --sites`).
   - At the end of a fix round the agent asks for the re-check as above, with the count from RECHECK.md (the items
     waiting, per area).
   - An approved re-check takes its items from RECHECK.md and gives each agent the original findings from the ledger
     (`finding`; for a row moved from the step-8 ledger, its `title` and `recheck_action`), not the fix summary. Each
     agent also checks collateral damage: it runs the tests of the files the fix touched (the fix commits' files) and
     checks the pages and workers that use those files.
   - The results update the ledger in the same task: the round (run, round, verdict, date, evidence) under the row's
     `recheck`, its status, then RECHECK.md is rewritten; the ERRORS_AND_SOLUTIONS.md entries and the report follow it.
9. **Record statuses follow the deploys.** After a deploy the statuses of the entries it carries are updated in the same
   task, and `verification/records/deployed_commits.json` gets the commits the beta and the live site run. A test
   (`scripts/tests/test_record_status.py`, `.github/workflows/records-status.yml`, `scripts/record_status.py`) compares
   the headings that say "not deployed", "on the branch" or "on the beta" with those commits; an entry with such a
   heading cites its fix's commit.

## Questions to the user

User decision 2026-11-05: "Tolong update memori. Untuk setiap pertanyaan, harus dikasih konteksnya dulu." Every
question to the user, including an option list or a clarification, starts with its context, in plain language, before
the question itself:

1. What the thing is: name the table, feature, code group or step being asked about, and what it does, in words a
   non-developer understands (not only an internal label such as "Q-S2a" or "S1").
2. The facts: what the data or code shows now, with the numbers and examples (for example "3.058 kode di atas 4 huruf,
   seperti waran -W, data fitur sampai 31 Agustus 2026").
3. Why a decision is needed now and what each answer changes.
4. Then the options and the question.

A question that only makes sense to someone who has read the earlier turns or EXEC.md is incomplete.

## Mandatory workflow

1. Confirm the requested scope and exact target names with the user when ambiguous.
2. Inspect current Railway and database state before mutation. Use explicit project, environment, and service IDs from `PROJECT_CONTEXT.md`.
3. Preserve unrelated services, tables, rows, files, and user changes.
4. Apply the smallest safe change and verify it from the live system.
   - Tests (user decision 2026-11-23: "tes yang dijalankan bukan wajib full suite, tapi tes yg memang relevant
     (targeted) dan full suite wajib dijalankan apabila memang diperlukan"): run the tests relevant to the change; CI runs
     the full suites on every push. Run a full suite locally only when it is needed, for example a change to a test
     fixture or helper every test uses.
5. Record the change in GitHub during the same task:
   - Schema: add a forward SQL migration, refresh `DATABASE_SCHEMA.md`, and append `DATABASE_CHANGELOG.md`.
   - Metadata: update `Table_Catalog` for every new/changed public data table, `Column_Catalog` for every new/changed column in those tables, and `Feature_Catalog` for new/changed Feature definitions. Every active Feature definition must include a formula, plain-language analytical interpretation, recommended use, misuse warning, semantic review status, and validation-evidence paths; run `scripts/audit_feature_catalog_semantics.py` after a Feature change. Register safe Feature joins in `Feature_Relationship_Catalog` and generic AI tools/limits in `Tool_Catalog`. The only initial exclusions are `Database_Table_Status`, `Table_Catalog`, and `Column_Catalog` themselves. Register new/changed PostgreSQL routines in related `Table_Catalog.related_functions`; see `DATABASE_CATALOG.md`. Do not mark inferred meanings VERIFIED.
   - Performance: define high-frequency query patterns for each major Feature table and run bounded `EXPLAIN (ANALYZE, BUFFERS)` before adding a large index. A result limit does not prove scan efficiency. Record measured plan evidence and do not add speculative indexes. A table exposed to the AI passes `scripts/onboarding/measure_indexes.py` (the SQL Governor's scan, count and date-split rules; `NEW_TABLE_ONBOARDING_PLAN.md` section 3).
   - Data: append source metadata and verification results to `DATABASE_CHANGELOG.md`.
   - Railway infrastructure/config/deployment: update `.railway/railway.ts` if applicable and append `RAILWAY_CHANGELOG.md`.
   - Documentation/process: update the relevant Markdown file.
   - Generated files (user decision 2026-11-14, EXEC-GEN-CHECK, ERRORS M435): a file written by a script is rebuilt in
     the same commit as its source and has a test marked `generated_file` that compares it with what the script writes
     now. `.github/workflows/generated-files.yml` runs those tests on every push and pull request.
     `scripts/tests/test_generated_files.py` fails when a script in a `scripts` folder named build/generate/snapshot, or
     taking `--check`, has no such test and no reason in its `EXEMPT`. Fix a red run by running the generator its
     message names; never remove a mark to pass. When a generated file loses its last reader, remove the file, its
     generator and its test in the same commit.
   - Radar formulas (user decision 2026-11-15: "formula2 yang live saat ini di DEV harus selalu terupdate MDnya, at
     least untuk bagian radar dulu"): `RADAR_FORMULAS.md` explains every Radar formula in plain Indonesian with real
     examples. A change of a Radar function (`refresh_feature_07`, `refresh_feature_07_day`, the `feature_07_*`
     helpers) or of a row of `Feature_07_Radar_Rule`/`_Filter` updates it in the same task: apply on dev, run
     `python3 scripts/radar_formulas_doc.py --write` (the live thresholds and code fingerprints), rewrite the
     explanation and set its `explained-for` line to the new fingerprints. `scripts/tests/test_radar_formulas_doc.py`
     (every push) compares the document with the applied migrations; `.github/workflows/database-schema-docs.yml` (every
     day) rewrites the numbers from dev and turns red when the code changed but the explanation did not.
   - Overview formulas (EXEC-OVERVIEW, the same rule): `OVERVIEW_FORMULAS.md` explains every figure of the Market
     Overview page in plain Indonesian with real examples. A change of `apps/terminal-publisher/overview.py`,
     `apps/edge-bff/overview/src/model.ts` or `public.overview_stock_size` updates it in the same commit: run
     `python3 scripts/overview_formulas_doc.py --write` (constants and fingerprints, from the repository), rewrite the
     explanation and set its `explained-for` line to the new fingerprints. `scripts/tests/test_overview_formulas_doc.py`
     (every push) compares the document with the code; the daily workflow (`--check`) also compares the function on dev
     with its newest migration. After a publisher deploy, the last element of state.json `overview_stamp` (`CODE`)
     equals the document's `overview.py` fingerprint.
   - Watchlist formulas (EXEC-WATCHLIST, the same rule): `WATCHLIST_FORMULAS.md` explains every figure, badge and limit
     of the Watchlist page in plain Indonesian with real examples. A change of `apps/terminal-publisher/watchlist.py`
     (catalog, dates, badges) or `apps/edge-bff/app/watchlist.py` (limits) updates it in the same commit: run
     `python3 scripts/watchlist_formulas_doc.py --write`, rewrite the explanation and set its `explained-for` line to
     the new fingerprints. `scripts/tests/test_watchlist_formulas_doc.py` (every push) compares the document with the
     code. The page shows only the indicators of the file's catalog: a new indicator is a publisher change, never a
     list written into the page.
   - Sector formulas (EXEC-SECTOR-ANALYSIS, the same rule): `SECTOR_FORMULAS.md` explains every figure of the Sector
     Analysis page in plain Indonesian with real examples. A change of `apps/terminal-publisher/sector.py`,
     `public.refresh_feature_08_day` or `public.feature_08_weight` updates it in the same commit: run
     `python3 scripts/sector_formulas_doc.py --write`, rewrite the explanation and set its `explained-for` line to the new
     fingerprints. `scripts/tests/test_sector_formulas_doc.py` (every push) compares the document with the code; the daily
     workflow (`--check`) also compares both functions on dev with their newest migration. The page's weights come only
     from `feature_08_weight` (decision D1: market cap later is a new basis there, not a page change).
   - EDGE design system (user decision 2026-11-18, EXEC-DESIGN-SYSTEM): a new EDGE page, panel, chart or HTML mockup
     follows `.claude/skills/edge-design-system/` (spec v1.2, its canonical layer and components); a change to the
     system itself rebuilds its claude.ai copy as that folder's `README.md` says.
   - EDGE front-end: wording goes in `apps/edge-bff/static/edge-labels.js`, Orc's response shape only in `static/edge-view.js`, the look in `static/index.html`; an edited one-file preview returns with `preview/edge_preview.py import` (README, Front-end structure). Backend lines for the user go in `apps/market-ai-orc/app/user_texts.py` (plain Indonesian, no internal names; `tests/test_user_texts.py`). A new browser storage key (localStorage, sessionStorage or IndexedDB) in the shell or any page needs its entry, `browser` or `user`, in `apps/edge-bff/shared/edge-session.ts` (`STORAGE`); after editing that file run `node shared/build-shell.mjs` from `apps/edge-bff` and commit `static/edge-session.js` with it (`tests/test_storage_registry.py` fails otherwise; ERRORS M473).
   - EDGE Terminal look (user decision 2026-11-07, ERRORS M385): every change to the Terminal's look (`apps/edge-bff/terminal/src/styles/`, markup or layout in `src/app/`) runs `node verification/terminal_api/terminal_look/look_check11.mjs` on the build before it is committed. It reads the rendered pixels and fails when a text start is more than 1px off its column, a heading's text is more than 1px off the middle of its band, any visible switch's knob is more than 0.5px off the middle of its track, or a control row is not one line with its market choice at the right. A new heading, switch or control row is added to the check in the same task; a failure is fixed or reported to the user, never skipped.
   - AI tools: when a model tool, a sandbox session helper, a method guide, or the switch that turns one on is added, removed, renamed or changed, regenerate `AI_TOOLS.md` in the same task with `scripts/generate_ai_tools_doc.py` (from `apps/market-ai-orc`, its venv). When a dev `AI_ENABLE_*` switch changes, regenerate with `--flags` built from `railway variables --kv` (names and true/false only, never other values) so the dev snapshot is current. Every new name needs its plain-language sentence in the generator's `PLAIN`. `apps/market-ai-orc/tests/test_ai_tools_doc.py` fails when the file and the code drift apart.
   - AI models: when a model call is added, removed or changed (model, reasoning, output-token limit, tools, structured output, provider routing), when a model setting is added or renamed in a service's `config.py`, or when a model, reasoning, token, provider or slot variable changes on Railway, regenerate `AI_MODELS.md` in the same task with `scripts/generate_ai_models_doc.py` (from the repository root). For a Railway change pass `--dev-values` with the listed names and their values only (never secrets; the generator refuses secret-looking values). Every new call site needs its plain-language sentence in the generator's `PURPOSE`. `apps/market-ai-orc/tests/test_ai_models_doc.py` fails when the file and the code drift apart.
   - AI router: when the routing criteria change (classes, their descriptions, the action each class runs, the fallback, or which requests the router reads), update `AI_ROUTER.md` in the same task (it is generated from the router code with `scripts/generate_ai_router_doc.py` once the first-turn router lands) and re-run the router benchmark set before deploying.
   - System prompt: when the rendered orc system prompt or the final-response schema changes (any prompt text in `apps/market-ai-orc/app/orchestrator.py`, any field description in `app/schemas.py`, or a prompt switch of the dev profile), record a snapshot in the same task with `scripts/snapshot_system_prompt.py record <name> --decision "<user's words and date>" --change "<what changed>"` (repository root, the orc venv). `prompts/SYSTEM_PROMPT_HISTORY.md` lists every version and how to fall back (user decision 2026-10-08). `apps/market-ai-orc/tests/test_prompt_history.py` fails when the code renders a prompt or schema the newest snapshot does not hold.
   - Errors: record every new error, defect or data problem in `ERRORS_AND_SOLUTIONS.md`: symptom, verified root cause, solution, status and lesson for new data (Part D). When a fix lands, update the entry's status in place; never delete entries. If the lesson changes how data must be shaped, update Part A too.
   - After a direct Railway dashboard or CLI configuration change, run `railway config pull --force` and `railway config plan` so `.railway/railway.ts` matches the live project.
6. Run `git diff --check`, review the diff, commit and push the working branch. Push or fast-forward `main` only with
   the user's confirmation for that deploy (section "Deploys" below: a push to `main` deploys), then verify the branch
   matches `origin/main`.
7. If the GitHub push fails, report the task as incomplete and explain what remains unpushed.

## Model and provider

`AI_MODELS.md` lists every model call, its settings and the dev values; keep it current (Mandatory workflow, AI models).

The user decided on 2026-09-27 that `market-ai-orc` keeps the model `deepseek/deepseek-v4.1-flash` through OpenRouter's default provider routing. Do not set `AI_PROVIDER_SORT`, do not change `AI_MODEL`, and do not switch provider without the user's explicit approval.

On 2026-09-30 the user approved a model switcher: `AI_MODEL_SWITCH=1` (default) runs `AI_MODEL` (`deepseek/deepseek-v4.1-flash`), `AI_MODEL_SWITCH=2` runs `AI_MODEL_2` (`xiaomi/mimo-v2.6-pro`). Model 1 stays the default; leave `AI_MODEL_SWITCH` unset or `1` except for a test the user asked for, and do not change `AI_MODEL` or `AI_MODEL_2` without approval.

On 2026-10-04 the user approved (plan `PLAN_FINAL_2026-10-04.md`, decision K1) `AI_MODEL_2=xiaomi/mimo-v2.6-flash` with `AI_MODEL_SWITCH=2` on dev, measured first with a small golden test; `AI_MODEL` stays `deepseek/deepseek-v4.1-flash` as the way back (`AI_MODEL_SWITCH=1`). The same day the user approved routing away from providers that barely discount cache reads: `AI_PROVIDER_MAX_CACHE_PRICE_RATIO=0.25` on dev, a list derived from OpenRouter's endpoint pricing (`app/provider_policy.py`). `AI_PROVIDER_SORT` stays unset; any other provider change still needs approval. Later on 2026-10-04 the user switched dev back to DeepSeek (`AI_MODEL_SWITCH=1`) before the final golden test; `AI_MODEL_2` stays `xiaomi/mimo-v2.6-flash` for a later test. The provider rule applies to the model in use (DeepSeek: Relace, Wafer and InferenceNet skipped). Later on 2026-10-04 the user kept the provider routing as is (O1 not done) and kept `xiaomi/mimo-v2.5` (web-governor slot 2) for event classification, cross-checked by slot 1.

On 2026-10-05 the user approved a speed preference after the p1 analysis (M75 recurrence on Sail Research): `AI_PROVIDER_MIN_THROUGHPUT=50` on dev, sent as OpenRouter `provider.preferred_min_throughput` `{p50: 50}`. It is a preference, not a filter or a sort: slower endpoints are tried last and the price weighting stays on. `AI_PROVIDER_SORT` stays unset; changing the threshold or any other provider setting still needs approval.

On 2026-10-13 the user approved a model choice per message in EDGE (EXEC-MODELS: "kita akan menambahkan model2 ini
bisa di toggle model dan intellegence level di EDGE (Default router tetap low)", "Ok, go defaultnya adalah deepseek V4.1
flash HIGH ya"): the agent loop may run `deepseek/deepseek-v4.1-flash`, `z-ai/glm-5.3-flash`, `xiaomi/mimo-v2.6-flash` or
`qwen/qwen3.8-flash` (`apps/market-ai-orc/app/model_choices.py`; `xiaomi/mimo-v2.6-pro` removed on 2026-10-13, EXEC-LOGOS:
"Keluarin saja Mimo pro ya"); EDGE starts on DeepSeek
V4.1 Flash high, while a request without a choice keeps `AI_MODEL` and `AI_REASONING_EFFORT` (medium on dev). The
routers, follow-up suggestions and small checks stay on `AI_MODEL` with reasoning low; the web governor is unaffected.
Adding or removing an offered model, or changing EDGE's default, still needs the user's approval.

On 2026-10-06 the user decided "1 conversation ID = 1 session ID … RUN ID ya bisa berbeda" (EXEC-S): every model call
of a conversation (each turn, each mode 4 step, the routers) sends the conversation id as OpenRouter's `session_id`,
its sticky-routing key, so the calls stay with one provider endpoint and reuse its prompt cache; a request without a
conversation id keeps the run id. This changes no variable; `AI_PROVIDER_SORT` stays unset.

On 2026-09-30 the user approved mode 4 (`AI_ENABLE_MODE4`, `app/mode4.py`) and a mode switcher: `AI_MODE_SWITCH` sets the default mode (1 AUTO, 2 ANALYSIS, 3 RESEARCH, 4 MODE4) and `analysis_path` chooses per request. The user chose default 4 on dev; do not change `AI_MODE_SWITCH` without approval.

## Fast-lane defaults

On 2026-10-14 the user approved V4 (EXEC-FASTLANE): the fast lane takes fixed defaults instead of letting the model
weigh open parameters, and the user may tweak them. They live in one named table, `FASTLANE_DEFAULTS` in
`apps/market-ai-orc/app/fastlane_defaults.py`, active only with `AI_FASTLANE_DECISION_RULES=true` on `market-ai-orc`:

| Name | Meaning |
|---|---|
| `large_threshold_percentile` | a "large" or "high" value is at or above this percentile of the entity's own history |
| `rolling_window_days` | a rolling or "recent" window the user does not name, in trading days |
| `forward_horizon_days` | the horizon of a forward return the user does not name, in trading days |
| `history_years` | how far back a data need reaches when the user names no period |
| `span_week_trading_days` | "1 minggu terakhir": trading days back from the last available date (5) |
| `span_month_trading_days` | "1 bulan terakhir": trading days (21); "3 bulan" is three times this |
| `span_year_trading_days` | "1 tahun terakhir": trading days (252) |
| `feasibility_entity_years` | `check_data_feasibility` is called first only above this many entity-years |
| `largest_buying_measure` | reading of "pembelian tertinggi" / "beli terbesar": net value (buy minus sell), gross shown beside it |
| `foreign_party` | reading of "asing": the foreign investor type of the transactions, not the broker's own type |
| `event_date_meaning` | reading of a rebalancing or event date ("tanggal efektif"): the implementation close |

Entries with `unit` "reading" (O5, user 2026-10-15) are readings of words the user leaves open: the user's words and
the conversation's facts come first, and the model may still ask back.

To change a value: edit its `"value"` in that file (keep `unit` and `means` true), run
`pytest apps/market-ai-orc/tests/test_fastlane.py`, push `main` with the user's confirmation (orc redeploys itself;
claim it only at `SUCCESS`; section "Deploys"), and
record the old and new value with the user's words in `EXEC.md` (EXEC-FASTLANE). Adding or removing an entry also
changes the decisions note (`app/orchestrator.py`, `FASTLANE_DECISIONS_NOTE`) and its test. The standard lane never
reads this table.

## Security

Never commit secret values, database URLs, passwords, private keys, Railway tokens, Stockbit JWTs, or GitHub PATs. For a secret change, record only the variable name, Railway scope, action, and verification status. Redact secrets from logs and terminal output.

Railway resolves a reference variable (`${{service.NAME}}`) when the referencing service is deployed. After a secret or any referenced variable changes at its source, list its consumers with `python3 scripts/railway_reference_consumers.py <service>.<NAME>` and redeploy each of them (`--redeploy`, with the user's approval for the change); a consumer left undeployed keeps the old value (ERRORS M308: web search refused for 13 days on the OpenRouter key of an older deploy). The script reads the consumers from the live project and prints names and references only.

## Deploys

User decision 2026-11-22: "Tolong untuk selanjutnya, deploy workflow harus dengan konfirmasi saya. masukkan ke
memori." Every deploy waits for the user's confirmation, asked with context (what moves, which services and sites it
reaches, what the live site sees) and given for that deploy; an earlier go or an approved plan is not a confirmation.
A deploy is any action that starts a deployment of a Railway service:
- a push, merge or fast-forward of `main` (the beta's `edge-bff` and every GitHub-connected service whose watch paths
  it touches deploy from it: the shared workers, terminal-api, the publisher and market-ai-orc reach the live site
  too);
- moving `live` (the rules of "The live site" below hold as well);
- a CLI upload (`railway up`, `deploy.sh`, the backtest-worker's upload), `railway redeploy`, a Run Now that deploys,
  `railway config apply`, and a variable change that redeploys a service.
Before asking, read what is already waiting: a deployment of another session in WAITING or BUILDING deploys by itself
when its CI turns green (`railway deployment list`), and is named in the question. The session branch is pushed
freely: no service deploys from it. A scheduled cron run and the user's own Telegram buttons are not deploys.

Wait for CI (user decision 2026-11-23: "Untuk live dan beta matikan wait for CI. Kamu tetap lihat hasil CI dan lapor kalau
merah. Akan kita buat wait for CI ini aktif untuk live ketika dekat2 launch."): edge-bff, edge-bff-live and screener-worker
deploy without waiting for GitHub Actions (`.railway/railway.ts` `checkSuites: false`; the user switched it in the
dashboard, ERRORS M514). CI still runs on every push. After every push to `main` or `live` the agent reads that commit's
runs to their end and tells the user at once when one is red, with what failed and a proposal (a fix, or a rollback to
the deployment RAILWAY_CHANGELOG names). Wait for CI comes back on edge-bff-live near the launch (EXEC-MU-ACCOUNTS,
Carried open parts). A change of Wait for CI updates this paragraph, `LIVE_PROMOTION.md` and
`INDICATOR_BETA_TO_LIVE.md` (Part A step 11) in the same commit.

## The live site

User decisions 2026-11-19 and 2026-11-20 (EXEC.md option A): the beta (`edge-bff`, edge-bff-dev.up.railway.app, the
admin only, every feature first) and the live site (`edge-bff-live`, app.edgefinance.id).
- `edge-bff-live` deploys only from branch `live` (Wait for CI off since 2026-11-23, section "Deploys"). Never `railway up` to it: a CLI upload skips both
  `live` and CI, and the next push to `live` silently replaces it (live checker after the switch-on, F6).
- `live` moves only to a commit the beta already runs (its latest SUCCESS deployment), with the
  user's go; record it in RAILWAY_CHANGELOG.md. Rollback: EXEC.md option A.
- Beta work reaches the live site only on the user's request, never on a schedule (user, 2026-11-20: "Tidak bisa
  pengembangan di beta dibawa live on schedule basis. Semuanya harus on request basis."). Before moving `live`, read
  `LIVE_PROMOTION.md` and run `python3 scripts/live_diff.py --sites`, then tell the user everything that moves with
  the commit (whole commits move, not one feature).
- Every tab, page and catalog item has its stage in `apps/edge-bff/catalog/releases.json` (`tabs`, `items`; unlisted
  is lab). Lab stays off on the live site for everyone, the admin's `*` included, and stays on the beta. A catalog item
  at `preview` (user 2026-11-23: "promote ke live hanya admin saja yang bisa lihat, user paid tidak bisa lihat") is on
  both sites for the admin only; no plan holds it by stage, nor by `{"all": true}` (UD28, "Ok A"); its definition and
  formula are public (LIVE_PROMOTION.md §3 "Preview"; `INDICATOR_BETA_TO_LIVE.md` Part C). Which path a request takes
  (beta only, live for the admin only, released): LIVE_PROMOTION.md §4, its first table. A tab is lab or released only.
  Since 2026-11-23 (the user: "Cabut tes penjaga lab") a new catalog item may enter at `lab` (the beta only):
  indicators by `INDICATOR_BETA_TO_LIVE.md` (a Flow indicator by its section "A lab Flow indicator", since 2026-11-23);
  Screener metrics and presets as data. A candle pattern may not be lab yet (`tests/test_releases.py` `LAB_KIND_HELD`:
  not dry-run), nor a tab (`tests/test_live_switch.py` `LAB_TAB_HELD_UNTIL`: its rail entry is not served by the
  server yet); those enter as `released` only with the user's go, or stay off `main`. An item no worker gates by id, or one the shipped code names,
  is never lab. A new tab is its own `<tab>-app`.
  `tests/test_live_switch.py` fails when a capability tab or a page of the shell has no entry. Migrations stay
  expand-only while the live site runs older code on the shared database.
- Connecting a repository or changing a deploy trigger is an account action the session's project token may not do
  (ERRORS M514): ask the user, naming every field (repository, branch, root directory, Wait for CI), and read it back.

## Postgres memory after large updates

User decisions: 2026-11-01 (ERRORS M319): "Restart terencana Postgres sesudah setiap backfill besar. Memori langsung
bersih, dengan jeda sekitar satu menit." 2026-11-03 (EXEC-PG-MEMORY): "Jalankan 1 dan 2. No 1 harus well documented to
ensure bahwa ketika ada update besar yang sifatnya ad hoc, maka AI agent aware akan hal ini. Untuk nomor 2, kita coba
turunkan menjadi 1 giga." The same day, after the 1 GB test: "Pake 1 gb likely Setiap query akan timeout. Kembalikan ke
4GB ya sekarang tapi keep existing path in case kita mau adjust memory Postgres in the future supaya lebih gampang."

Why it matters:
- Railway bills the Postgres container's memory, and that includes the Linux page cache a large read or write leaves
  behind.
- The cache stays for hours after the work ends (it held 4 GB for 3 hours on 2026-11-02).
- The container limit is 2 GB since 2026-11-09 (user: "Naikkan limit sementara ke 2 GB"; "Limit ram keep 2gb dulu,
  nanti saya yg rubah"), after 1 GB from 2026-11-06 (user: "minta tolong untuk memory progress di cap jadi 1 GB..
  sekarang 4GB") stopped a rebuild for memory; `.railway/railway.ts`, `Postgres.deploy.limitOverride` (recorded from the
  live limit 2026-11-15, ERRORS M455). The 1 GB test of 2026-11-03 made year-wide queries take
  3–6 minutes (AI-shaped queries 0.1 s); 4 GB was used 2026-11-03 to 2026-11-06. Postgres itself uses about 0.1–0.3 GB at rest (`shared_buffers` 128 MB);
  the rest is cache.
- To change the limit, run `python3 scripts/set_postgres_memory.py --gb N` (check: guards, the `railway.ts` edit, the
  plan), then the same with `--apply` (Postgres restarts, about 12 seconds; the limit, start time and edge-bff `/ready`
  are read back). Only with the user's approval; record it in `RAILWAY_CHANGELOG.md` and `EXEC.md`.

Automatic restart (EXEC-PG-RESTART-CRON, user go 2026-11-03: "Go langkah 1–9, tafsiran toggle benar, setuju"):
- Service `postgres-memory-cron` runs `scripts/restart_postgres.py --cron` at the times in its variable
  `PG_RESTART_TIMES_WIB` (09:45 and 20:45 WIB); its cronSchedule is `cron_for` of those times (`45 2,13 * * *` UTC).
- A scheduled run restarts only when the automatic restart is ON and memory is at least 0.8 GB. Below that, or OFF, it
  does nothing and sends nothing.
- The user's Telegram bot (`/start`) has "🔄 Restart Postgres" (a manual restart now: Railway Run Now of the cron
  service) and "🧠 Postgres restart: status / auto ON-OFF". A manual run ignores the memory threshold and the switch.
- Every run keeps the guards: no cron of another service within 45 minutes, outside B6 (07:00-08:45 and 19:00-20:20
  WIB), no running statement and no active user run (M340); it waits up to 60 minutes for the last two.
- Telegram messages (telegram-monitor source `Postgres_Restart`): 🔔 manual request, ⏳ started, ✅ success, ❌ failed,
  ⚠️ refused with the reason, 🧪 check (mode check only).
- `PG_RESTART_MODE`: `check` decides and reports without restarting; `apply` restarts. `PG_RESTART_AUTO=false` turns
  the scheduled restart off whatever Telegram says.
- To change the times: `python3 scripts/set_postgres_restart_times.py --wib HH:MM,HH:MM` (check: refuses a time near
  another cron or in B6), then `--apply` with the user's approval. It sets the variable and the cronSchedule together
  and uploads a new deployment (ERRORS M229). Never edit only one of them.
- The code is uploaded with `apps/postgres-memory-cron/deploy.sh` (not GitHub-connected); its token is the variable
  `RAILWAY_RESTART_TOKEN` (a project token of its own; revoke it in Project Settings → Tokens to stop everything).
- The scheduled restart covers the daily crons. An **ad hoc** large update (below) still needs the steps below right
  after it: do not wait for the next scheduled time.
- Details: `apps/postgres-memory-cron/README.md`.

A large update is any one of these, scheduled or **ad hoc**. When in doubt, treat the work as one.
- a Stockbit broker or event round (`stockbit-updater`, `UPDATE_TABLE.md`);
- a backfill or a full recalculation of a Feature or `_INDEX` table;
- a Feature repair job (for example `verification/feature04_bonds/repair_job.py`);
- a price refill or a price correction (`idx-price-cron` manual, fixed-income correction);
- a manual or backfill run of `terminal-publisher`;
- a migration that rewrites or copies a large table, or builds an index on one;
- any job that reads or writes millions of rows;
- the schema document and `Database_Table_Status` refresh (`scripts/sync_database_schema.py`, e.g.
  `verification/database_table_status_20261025/refresh_job.py`): it reads `max(...)` of every table, a full read of the
  large Feature tables (`sync_database_schema.py:636-700`; 0.81 → 2.93 GB on 2026-11-05, ERRORS M350; user 2026-11-05:
  "Untuk point nomor 4 OK").

After a large update and its reader checks:
1. Run `python3 scripts/restart_postgres.py` (check), then the same command with `--apply` (or ask the user to press
   "🔄 Restart Postgres" in Telegram).
   - The script restarts only when all of these hold: Postgres memory is at least 0.8 GB, no cron is due within 45
     minutes, the time is outside the B6 windows, no client statement is running, and no user run is active (M340).
   - It waits for Postgres and every website's `/ready` (the beta's and the live site's, read from Railway:
     `site_ready_urls`, ERRORS M513 S7); Postgres is unavailable for about 12 seconds.
   - A refusal names its reason. Wait and run it again later; do not skip it.
2. A job started with `scripts/onboarding/run_job.sh` does step 1 itself when its `params.json` has
   `"large_write": true`. Every other job prints a `POSTGRES_MEMORY_CHECK` line at its end: when that line says
   `READY`, run step 1.
3. Record the restart in `RAILWAY_CHANGELOG.md`.
4. Market Overview (ERRORS M442): the publisher rechecks by content only the newest 3 market dates
   (`RECHECK_SESSIONS`). When the update rewrote older dates of the price table, the IHSG bars, Feature 01, 04 or 06,
   republish the Overview with the manual mode: `TERMINAL_PUBLISH_MODE=overview` on terminal-publisher, Run Now, then
   back to `daily` (with the user's approval; it reads about 1.2 GB of Feature 04, so step 1 follows it).

Before a deploy of `market-ai-orc` or a Postgres restart, check that no user run is active (`edge_bff.jobs` QUEUED,
RUNNING or RECOVERING; `AI_conversation_turn` RUNNING); wait until none is (ERRORS M340).

Heavy jobs raise `work_mem` to 64 MB and backfills raise `maintenance_work_mem` to 256 MB per connection. Run them one
at a time; below 4 GB this is required. If Postgres is killed for memory (a restart nobody started, `pg_postmaster_start_time`
newer than expected, connections dropped during a heavy job):
- stop the job;
- record it in `ERRORS_AND_SOLUTIONS.md`;
- ask the user before changing the limit (`scripts/set_postgres_memory.py`).

## History rules

- Never edit an old migration after it has been applied. Add a new migration.
- Do not use GitHub as a row-by-row database mirror. Record data-load metadata and keep operational row history in PostgreSQL load logs.
- Do not claim a Railway deployment succeeded until its exact deployment reaches `SUCCESS`.
- Do not claim a database change succeeded until the live schema/data has been read back and verified.
