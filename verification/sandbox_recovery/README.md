# Sandbox readiness recovery — 2026-10-19

Scope: lucid-patience / dev, market-ai-orc and edge-bff, Git main source. User decision and limitations:
EXEC-SANDBOX-RECOVERY. Root cause M187. No Railway configuration changes or production database mutation.

## Behaviour covered

- HTTP remains available when sandbox missed startup; no AI call or partial tool registry is admitted.
- A later incoming readiness/run request initializes the complete runtime once, without restarting Orc.
- Authentication, readiness and runtime metadata precede capability negotiation; invalid/unisolated runtime
  is rejected. All negotiation reads use one successful snapshot. Five-second cooldown, no idle thread.
- Concurrent callers cannot start a second factory or observe an incomplete runtime.
- Existing BFF queue waits beyond three dependency probes without spending dispatch attempts; once ready it
  dispatches the original request ID once. Stop during handshake prevents dispatch; the existing deadline applies.
- The real shared session-opening path emits `Initiating sandbox session.` with owner-scoped progress.
- An HTTP Chromium test against the real BFF worker and disposable Postgres observes
  `Waiting for services to be ready.`, then `Initiating sandbox session.`, then one saved result. Its upstream
  is deterministic; this is not a live-model calculation test.

## Validation

- Orc full suite: **1618 passed, 272 skipped** (conditional integration/resource gates).
- Orc conversation/retry/reuse/result-store/session subset with disposable Postgres: **74 passed**.
- BFF queue/API/client/readiness subset with disposable Postgres: **35 passed**.
- Canonical real-Orc response + frontend contract run: **11 passed, 4 blocked**. The four existing mobile
  preview cases navigate `file://`; managed Chromium rejects them with `ERR_BLOCKED_BY_ADMINISTRATOR`.
  No security/browser policy was changed. The HTTP recovery browser test passes separately.
- HTTP recovery/session progress browser case: **1 passed**.
- Additional malformed-runtime/snapshot cases were added after the full suite; their focused result is recorded
  below: **11 passed**. AI_TOOLS generator ran without a generated diff. JavaScript syntax and git diff whitespace checks pass.
- No OpenRouter inference or Telegram message was sent by these tests. Local test databases create/drop only
  inside disposable loopback Docker Postgres, never Railway.

## Rollout/readback

Pending source push and exact deployment verification. No deliberate live outage will be induced.
Before rollout, Orc's active deployment logs for 03:15–03:35 UTC contained only periodic metadata/credit events,
no run-start event. Source main was re-fetched and remained at the reviewed plan baseline.
