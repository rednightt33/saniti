# orc-test-runner

Live test runner for `market-ai-orc` on the Railway private network (`dev`). The orchestrator has no public domain
and the agent container cannot reach Railway SSH, so questions are sent from this one-off service.

- Railway service `orc-test-runner` (`09358b92-09d4-4da2-b547-bf8f621e226c`), restart policy `NEVER`, no domain.
  One variable: `MARKET_AI_ORC_API_KEY` (a reference to market-ai-orc's key); it is never printed.
- `run.py` (standard library only) sends every item of `suite.json` as a new `history_mode` SERVER conversation
  (owner `golden-multi-angle`), with the item's `analysis_path`, and approves a `RESEARCH_PLAN_CONFIRMATION` once with
  `plan_reply` APPROVE. Two workers by default.
- Output: one `OTR {json}` line per turn (status, plan version, angles, research run, per-angle statuses, gate,
  cost), followed at once by that turn's full response as `OTRDUMP <item>:<turn> i/n` gzip+base64 chunks (Railway
  drops long lines; a crash later loses nothing). Reassemble each tag's chunks in order, base64-decode, gunzip. Fetch
  the log with `railway logs <deployment> --deployment --lines 5000` (a larger limit is refused).
- Audit readback (2026-09-30): when `AUDIT_STORE_READER_KEY` is set (a reference to market-audit-store's reader
  key, added only for the suite and removed after it), the runner waits 60 s after the last turn, then reads each
  turn's run from market-audit-store (`GET /v1/requests/{request_id}/run`, polled up to `audit_wait_seconds` until
  `COMPLETE`) and prints `OTR {"event": "audit", ...}` with the run status, counts, event types and the refused
  finals (gate stage, detail, draft size). The refused drafts themselves (`final.rejected`, `final.forced`,
  `final.unrendered`) are read in full from the run's TOOL_TRACE artifact through a short-lived access grant and
  printed as `OTRDUMP audit:<item>:<turn>` chunks. `"audit_only": true` in `suite.json` skips the questions and only
  reads the audit of the suite's request ids.
- Mode 4 (2026-09-30): an item with `"turns": [message, ...]` is one SERVER conversation of plain messages (no
  `analysis_path`, no `plan_reply`; market-ai-orc's reply classifier reads each reply). The request timeout is 3900 s
  (`AI_MODE4_MAX_SECONDS` 3600 plus margin), and the `OTR` line lists the mode 4 steps (step, status, turn, angles,
  cost, duration).
- `suite.json` items may carry `model` and `reasoning_level` (EXEC-MODELS), sent with each of the item's messages, and
  an `expect` note for the reviewer; the runner ignores the note. Current suite:
  `ma-models-20261013a` (EXEC-MODELS live check: ab6 without a choice and with each offered model;
  `suites/models_20261013a.json`); earlier `ma-ab-table-20261013j` (A/B 4 OFF; ON is `i`; `suites/ab_table_20261013i.json` and `j`); earlier
  `ma-prose-20261013h` (EXEC-PROSE quick check, ab5 and ab6, tables on; `suites/prose_20261013h.json`); earlier
  `ma-ab-table-20261013g` (A/B 3, table ON; OFF is `suites/ab_table_20261013f.json`, ON `g`); earlier
  `ma-m147-20261013a` (M147 live check, ab5; `suites/m147_20261013a.json`); earlier quick table A/B `ma-ab-table-20261013d`/`e`; earlier `ma-m143-20261013a` (EXEC-M143 live check, one question; `suites/m143_20261013a.json`); earlier `ma-ab-table-20261013c` (EXEC-TABLE A/B: the ab5 rerun with `audit_request_ids` and `audit_full_trace`; the OFF and ON
  runs are `suites/ab_table_20261013a.json` and `b`); earlier `ma-ab-style-20261012a` (EXEC-IMPL-1012 A/B: four questions, a chat and a fact question through AUTO and two ANALYSIS
  questions; kept as `suites/ab_style_20261012a.json`); earlier `ma-m43g13-20260930a` (the broker question over three turns in mode 4 after the M43 fix, and e02 through
  the RESEARCH path after the G13 scope check); earlier `ma-modeswitch-20260930a` (one AUTO question while `AI_MODE_SWITCH=4`; the `OTR` line shows `execution.mode`);
  earlier `ma-mode4-20260930a` (the broker question over three turns and a price question followed by a new question);
  earlier `ma-suite20-20260930c` (after S16/M39/P10, backend-rendered findings and value references); earlier
  `ma-suite20-20260929b` (12 multi-angle research questions, 4 edge cases, 4 ANALYSIS questions with ground truth;
  the same questions as `ma-suite20-20260929a`, rerun after the fixes of `MULTI_ANGLE_FIX_PLAN.md`).
- Run: set a new `prefix` in `suite.json` (request ids are idempotency keys), then
  `railway up apps/orc-test-runner --path-as-root --service orc-test-runner --environment dev --detach`.

The code of the earlier suites (suite1–suite9, 2026-09-27/28) was not kept in the repository; this version was
written for the Multi-Angle Research golden questions (2026-09-29).
