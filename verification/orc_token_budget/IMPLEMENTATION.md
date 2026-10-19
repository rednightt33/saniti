# ORC executor budget and presentation recovery

Status, 2026-10-19: **implemented and validated locally; live rollout pending network access**.
User authorized implementation and then the shared 96k alternative. Approval and the complete plan are in
`EXEC.md` / `EXEC-ORC-BUDGET`. Existing live deployment/configuration remain unchanged.

## Result in source

- One immutable budget per executor sub-run. All executor models share the configured total output limit; the MiMo
  12k exception and all executor Low/Off downgrade paths are removed. Work, final, repair and timeout keep the
  requested choice. Router/classifier/follow-up/Web models retain their independent contracts.
- Approved target is 96,000 combined tokens. DeepSeek/GLM accept effort and MiMo accepts on/off; no fixed 48k/48k
  split is promised. Qwen sends a configurable numeric reasoning cap, with 48,000 acceptance still to be tested.
  `AI_MAX_PRESENTATION_TOKENS=48000` is a target, not an enforceable provider answer cap. Source defaults preserve
  8k total / 8k numeric and dev remains at its old explicit settings until rollout.
- No fastlane 90-second call cap. The existing general 600-second dev provider cap, inner 1800, Mode4 3600 and BFF
  3900 are retained. Provider operations include backoff/retry inside their remaining inner/root deadline. Async
  cancellation closes a read stalled before or after keep-alive bytes; no inference thread continues in the client.
  A fresh HTTP client is used per POST; provider prompt-cache stickiness still uses the same conversation session id.
- At most one explicit transient-HTTP retry; no transport replay after ambiguous timeout/network loss/malformed 2xx.
  Helper wrappers do not add another retry after transport failure. Stop prevents the next dispatch. Unknown usage
  after interruption is recorded as unknown billing, not a refund or zero.
- Provider incomplete flags and usage are checked before accepting JSON or executing tool arguments. Reasoning-only
  exhaustion stops. A nonempty truncated presentation gets one repair with tools locked; truncated tool arguments
  may be regenerated once and are never executed as received. All choices stay fixed.
- Existing sandbox/R-STORE persistence is reused before final generation. A nullable bounded checkpoint column holds
  per-sub-run WORK/READY metadata, saved checksums, completion contract, sources and a bounded visible draft. No raw
  dataset, provider reasoning or private model memo is checkpointed. Writes use owner/conversation/generation/lease
  fencing and short transactions. READY also reserves the conversation's result aliases/scalar counters, preventing
  reuse after process loss. It never writes a terminal answer or prematurely inserts terminal run memory.
- A new computation invalidates READY before starting. Incomplete storage or an oversized contract disables recovery.
  READY means the saved computation passed existing completion/coverage gates; it is not a proof of every possible
  natural-language deliverable. Existing provenance/statistical gates and table/export limits remain.
- `presentation_retry_of`/`presentation_retry_step` creates a new normal SERVER-mode queued request with an explicit
  model/level in the same owned conversation. It skips routing/planning, locks tools, checks artifacts before a paid
  call and presents the saved question/sources/coverage/date. It never queries current prices or recalculates. The
  latest conversation data record survives. Source checkpoints stay separated per Mode4 step.
- BFF exposes safe recovery choices and collapsed call settings; the retry button names the model/level and warns of
  AI usage costs. Full-request retry fills the composer and restores its original supported model/level. EdgeView is
  version 2. Pin/history/resize/panel behavior and the worker/SSE/lease protocol are preserved.

## Local evidence

`LOCAL_VALIDATION.json` records test totals, changed-code hashes and screenshot hashes.

| Validation | Result |
|---|---|
| ORC full suite with disposable PostgreSQL 17 | 1,933 passed |
| BFF complete suite | 131 passed |
| BFF affected checks after full-retry choice preservation | 18 passed |
| Migration operator smoke test | NOT_APPLIED → APPLIED → ALREADY_APPLIED → ALREADY_APPLIED |
| Audit Store v1 event contract | Safe call settings accepted; no forbidden reasoning key |
| Prompt history | Render unchanged, v014 remains current; record command correctly refused a duplicate snapshot |

Tests cover all offered executor levels on both lanes, Mode4 inheritance, incomplete-but-valid JSON, truncated tool
arguments, reasoning exhaustion, silence/keep-alive cancellation, root time remaining, >90-second completion without
replay, ownership/old-generation refusal, restart/reference reservation, missing results before inference, and
presentation without data/computation tools. No live inference or live data mutation was performed.

UI uses real local BFF authentication, queue, SSE and disposable PostgreSQL with an upstream fixture, at 1920×1080,
1280×800, 390×844 and 360×740. Mouse/touch, reload without dispatch, budget disclosure and sent settings pass; zero
page JavaScript errors. Mobile is Chromium touch emulation, not a physical iOS/Android device. Screenshots were
visually inspected; two review examples are included:

- [Mobile recovery](UI_MOBILE_RECOVERY.png)
- [Desktop budget/settings](UI_DESKTOP_BUDGET.png)

## Remaining rollout

1. Workspace network policy currently omits HTTPS `openrouter.ai` / `edge-bff-dev.up.railway.app` and TCP
   `shuttle.proxy.rlwy.net:40042`. This blocks direct live migration and capability/golden validation. Existing
   credentials are available and never printed. No new service/domain/replica or bypass is proposed.
2. Inspect live schema, run the tracked `scripts/apply_orc_checkpoint_migration.py --apply` with runtime-supplied
   administrative `DATABASE_URL`, and read back the column/constraint/catalog/grants. Apply before main auto-deploy.
3. Deploy ORC/BFF from Git main and wait for exact Railway deployments to reach SUCCESS. Keep all other services,
   provider routing, helper budgets and market-data permissions unchanged.
4. Use bounded live provider probes to verify eligible 96k acceptance and Qwen numeric 48k before activation. A small
   successful probe proves acceptance, not that a model was driven all the way to its 48k boundary. Record the result;
   never silently substitute a smaller numeric cap, Off/Low, another model or another routing policy.
5. Activate only supported settings through the tracked configuration workflow: approved combined 96000,
   presentation target 48000, and Qwen numeric 48000 after G0. Pull/plan IaC and regenerate AI_MODELS with safe live
   values. Run golden/readback and complete deployment/schema changelogs. Until then this work is not live.

The general 600 seconds may end a slow call before 96k tokens are produced. A larger cap is capacity, not promised
usage or completion, and no timeout/session/CPU/SQL limit is raised automatically. Existing 40k-character history
pointer, legacy audit-summary caps, full result persistence and backend table/export behavior are retained.
