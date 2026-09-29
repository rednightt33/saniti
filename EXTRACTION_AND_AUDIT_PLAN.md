# Extraction cost and analysis audit plan

Status: **planned, not executed** (user, 2026-09-29: "Jangan eksekusi dulu"). Each item runs only after the user says so.
Origin: the broker screening runs of 2026-09-28 (`b01_broker_screen`, `b02_broker_screen_analysis`) and errors G10 and
M23 in `ERRORS_AND_SOLUTIONS.md`.

## Evidence that motivates the plan

- `b01` (model chose the path): 27.4 minutes. The data phase took about 14 minutes because 7 of 8 extractions were
  refused with `REJECTED_JOIN_COST` (`COST_LIMIT`, plan cost 604,535 to 827,899 against `SQL_MAX_PLAN_COST` 600,000).
  Every refused request joined the raw `IDX_Broker_Summary` (43.7 million rows) with `IDX_Stock_Universe` (bank
  filter, `Ticker` = `Symbol`), in five of them also with `Price_Stock_Indonesia_IDX` (`ticker, date` = `Symbol, Date`).
  One earlier spec was refused by the validator with `RELATIONSHIP_KEY_MISMATCH`.
- `check_data_feasibility` answered FEASIBLE twice for the same kind of request (G10).
- Each refused attempt had already extracted 9 to 43 parts: 1,936,119 rows extracted and discarded.
- `b02` (`analysis_path` ANALYSIS): used the pre-aggregated `Feature_02_Broker_Rolling`; 67 extractions, no refusal.
- No request was refused for the number of joins (`TOO_MANY_JOINS` / `TOO_MANY_TABLES` never occurred); no request
  used more than 3 tables.

## Approved scope (not executed)

### A0. Number of parts from a per-part estimate (market-sql-governor) — approved

Today `extract.partitioning` sets `parts = ceil(estimate / (0.8 × limit))` for the most violated limit, which assumes
the cost falls in proportion to the window. For the broker × universe join a one-day part can still cost more than
600,000.

Change: after a split, estimate the most expensive part (EXPLAIN only, no data read); while it exceeds a limit, split
further (DATE, then ENTITY where it applies) up to `SQL_EXTRACT_MAX_PARTS`. When even the smallest part exceeds the
limit, stop with the part's window, its estimate and the limit in the refusal. The same function serves the
feasibility estimate, so `check_data_feasibility` no longer reports FEASIBLE for a plan a part will refuse (G10).

### A2. Estimate every part before the first extraction (market-sql-governor) — approved

Before part 1 is extracted, estimate all planned parts; if any part fails, refuse the whole extraction before any
data is read. No partial extraction is discarded any more.

Cost: one EXPLAIN per part (about 50–100 ms each; 28 parts ≈ 2–3 s), bounded by `SQL_EXTRACT_MAX_PARTS`.

### J. Raise the join limit to 6 (market-sql-governor) — requested

- `SQL_MAX_JOINS` applies to `POST /v1/query` (the direct query path of `request_data`, not used in the DataNeed
  flow). The DataNeed path (`POST /v1/extract`) has no join-count limit; it allows up to 8 restrictions (semi-joins)
  per extraction (`restrictions: max_length=8`). Raising `SQL_MAX_JOINS` would not have changed the broker runs.
- The code caps `SQL_MAX_JOINS` at 4 and `SQL_MAX_TABLES` at 5 and requires `max_joins < max_tables`. Six joins
  therefore needs a code change: maxima to at least 6 joins and 7 tables, then `SQL_MAX_JOINS=6` and
  `SQL_MAX_TABLES=7` on market-sql-governor (dev), with `railway config pull --force` / `plan` afterwards.
- More joins per query raise plan cost; the cost, scan and time limits stay as they are and still refuse an expensive
  query.
- Open question for the user: should the extraction path also get an explicit join/restriction limit (for example 6
  instead of the current 8), or is `/v1/query` alone meant?

### C. Record the modules each execution imports (market-python-sandbox) — approved for the plan

Parse the code before it runs (AST, no execution) and record the top-level module names on each execution
(`session_execution` log and the execution record) and `modules_used` in the completion's final status. Modules the
session pre-loads (pandas, numpy, saniti) are listed from the code's import statements, not from `sys.modules`, so
they are not missed.

Open decision: also store the code text (size-limited, kept like other execution records, 30 days), which would let
a run's full process be read back, or only the module names.

## Proposed, not approved yet

- **A1** Feasibility check estimates every part (largely delivered by A0, which shares the function).
- **A3** A refusal names the failing part, its cost and the limit, and a catalog alternative (for broker flows:
  `Feature_02_Broker_Rolling`).
- **A4** Bounded `EXPLAIN (ANALYZE, BUFFERS)` on dev of a one-day broker × universe extraction, to find why a
  one-day part costs over 600,000; no speculative index (AGENTS.md).
- **D** Shorter tables in final answers (top rows plus a summary) to cut the final-answer writing time.

## Verification when executed

- Governor unit tests for A0/A2/J (a part that stays too expensive is refused before any extraction; FEASIBLE agrees
  with extraction); sandbox tests for C (modules listed, flag-off shape unchanged).
- Dev rollout one service at a time, deployment `SUCCESS` read back, then the `b01` question again with the model
  choosing the path; compare time, refusals and discarded rows with the 2026-09-28 run.
- Record in `RAILWAY_CHANGELOG.md`, update G10 in `ERRORS_AND_SOLUTIONS.md`, `.railway/railway.ts` after variable
  changes.
