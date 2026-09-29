# Multi-Angle Research: fix plan after suite20

Status (2026-09-29): **approved scope, not started.** The user approved the items below and asked not to execute yet.
Evidence: suite20 (`RAILWAY_CHANGELOG.md` 2026-09-29, `ERRORS_AND_SOLUTIONS.md`). Nothing here changes Railway,
the database or code until the user gives the go-ahead.

## Approved items

| # | Item | Entry | Services | Summary |
|---|---|---|---|---|
| 1 | Outcome must be the approved quantity | S15 | sandbox, orc | r09 reported three SUPPORTED angles on the closing price level instead of the forward return |
| 2 | `AI_research_library`: the eight methods as a governed table | C07 | database, orc, sandbox | The model chooses methods from the table instead of the method list in the system prompt |
| 3 | Janitor must not delete open session workspaces | S14 | sandbox | r04 lost its input files mid-run |
| 4 | No finalize before every angle is attempted | M36 | orc, sandbox | 6 of 42 angles NOT_RUN in runs whose executions all succeeded |
| 5 | Method rules checked at feasibility, not at the final plan | M38 | orc (sandbox rules) | 4 of 16 research questions got no plan after a FEASIBLE check |
| 6 | Negation-aware agreement check | P09 | orc | r08 forced to LIMITATION by "tidak mengizinkan … saling mendukung" |

Suggested order: 3 and 1 first (a wrong or lost result), then 4, 5 and 6 (orc gates and feasibility), then 2 (a new
table plus a migration). Items 2 and 5 share the method requirements and are designed together.

### 1. Outcome must be the approved quantity (S15)

- The declarative form accepts a forward-return outcome whose price column is in another request of the angle's
  contract, joined on entity and date by the catalog relationship, so a condition in Feature_03 and a return from
  Feature_01 no longer force the frame form.
- Frame form: an outcome whose values are implausible for the approved `outcome_unit` (for example a median above 100
  for PERCENT, or values equal to a price column of the contract) makes the angle INVALID with `OUTCOME_NOT_APPROVED`.
- Answer gate: an interpretation that names an outcome other than the plan's (for example "harga penutupan" for a
  return) is refused.
- Tests: the r09 shape (condition and price in separate requests) records declaratively; a price-level frame outcome
  is INVALID; the gate refuses the r09 wording.

### 2. `AI_research_library` (C07)

Decision (2026-09-29): a new table holds the eight Multi-Angle Research methods; the model refers to it instead of the
method list in the system prompt. `AI_research_catalog` stays unchanged (the earlier decision).

- Forward migration: `public."AI_research_library"`, one row per method and engine version. Proposed columns:
  `method_id`, `method_family`, `engine_version`, `status`, `question_shape` (the question it answers),
  `input_roles` (jsonb: role, type, required), `required_parameters` / `optional_parameters` (jsonb with ranges),
  `data_requirements` (jsonb: entity required, label constant per date or per entity, one request per declaration,
  forward return needs a price column and a future buffer, minimum entities per date), `sample_unit`,
  `secondary_checks`, `decision_rules_ref`, `interpretation`, `misuse_warning`, `example_question`,
  `registry_sha256`, `is_active`, timestamps. Read-only grant to `market_ai_catalog_reader` only.
- Source of truth stays the code registry (the engines are code). The migration is generated from it; market-ai-orc
  reads the table at start-up and activates multi-angle research only when the rows' `registry_sha256` equals the
  registry negotiated with the sandbox (a drift test fails otherwise).
- Model access: the plan turn reads the library through the catalog tools (a RESEARCH_LIBRARY section of
  `get_catalog_details`, or a small dedicated read tool); the prompt keeps only the rule "choose methods from the
  research library". Item 5 validates plans against the same requirements.
- Documentation required by `AGENTS.md`: `Table_Catalog`, `Column_Catalog`, `DATABASE_SCHEMA.md`,
  `DATABASE_CATALOG.md`, `DATABASE_CHANGELOG.md`; Tool_Catalog if a tool schema changes. Apply by the temporary-job
  pattern (inspect, dry run, apply, read back) with approval.
- Open decision for the user when this starts: whether a changed tool schema (for example `check_research_feasibility`
  v2 in item 5) ships in the same migration.

### 3. Janitor and open sessions (S14)

- `cleanup_workspaces` skips the workspace of every open session (the session service registers its directories, or
  the cleanup reads the open sessions from the store). Test: an open session survives a cleanup; a closed one is
  removed.

### 4. Finalize only after every angle is attempted (M36)

- The RESEARCH_RUN_INCOMPLETE reminder asks for `complete_research_run` with `finalize` false first (it lists the
  missing angles) and to record them.
- The executor refuses the first `finalize` true while an approved angle is unrecorded and tool calls remain; it is
  accepted afterwards (a genuinely failing angle still becomes NOT_RUN).

### 5. Method rules at feasibility (M38)

- `check_research_feasibility` receives each angle's design (method, parameters, horizon, unit, holdout) with its data
  and checks the parameter rules, holdout ranges, entity and label requirements and the role-to-column mapping
  (items 1 and 2) before a plan is written; REVISION_REQUIRED names the angle and the fix.
- The final plan is compared with the checked design by hash; no new rule appears at the end. The plan gate gets a
  second repair like FINDINGS_2.
- The tool input schema changes, so a new Tool_Catalog version is needed.

### 6. Negation-aware agreement check (P09)

- Agreement phrases governed by a negation (tidak, bukan, belum, tanpa, not, no) in the same clause are ignored, as
  the causal-claim check already does. Regression test on the r08 sentence.

## Not approved yet (open decisions)

- M37: the final-turn output budget (`AI_MAX_OUTPUT_TOKENS` or a reasoning cap): a configuration change.
- G12 remainder: the example call uses a price column of the angle's contract (partly covered by item 1).
- Expression functions for new questions: `ema(x, n)` with automatic warm-up, and a threshold on forward-return
  outcomes (for "return at least X%").
- Data: an IHSG daily table and its catalog relationship; interest rates when the table exists.

## Verification when executed

Each service: local tests, push `main`, deploy one service at a time to `SUCCESS`, then rerun suite20
(`apps/orc-test-runner`) and compare with 2026-09-29: research answered 9 of 15, NOT_RUN 6, plan failures 4,
S15-type findings 3.
