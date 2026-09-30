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
- `suite.json` items may carry an `expect` note for the reviewer; the runner ignores it. Current suite:
  `ma-suite20-20260930c` (after S16/M39/P10, backend-rendered findings and value references); earlier
  `ma-suite20-20260929b` (12 multi-angle research questions, 4 edge cases, 4 ANALYSIS questions with ground truth;
  the same questions as `ma-suite20-20260929a`, rerun after the fixes of `MULTI_ANGLE_FIX_PLAN.md`).
- Run: set a new `prefix` in `suite.json` (request ids are idempotency keys), then
  `railway up apps/orc-test-runner --path-as-root --service orc-test-runner --environment dev --detach`.

The code of the earlier suites (suite1–suite9, 2026-09-27/28) was not kept in the repository; this version was
written for the Multi-Angle Research golden questions (2026-09-29).
