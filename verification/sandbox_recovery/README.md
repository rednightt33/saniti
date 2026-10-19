# Sandbox readiness recovery — 2026-10-19

User approval (2026-10-19, verbatim): "Kita itu saja ya, coba buat implementation ya. Boleh saya confirm bahwa masalah utama adalah ketika re deploy, Orc aktif dulu barubkemudian samdbox aktif. Tapi orc todak tahu kalau sandbox sudah aktif?"

Scope: lucid-patience / dev, market-ai-orc and edge-bff, Git main source. User decision and limitations:
the Orc/BFF READMEs. Execution approval was recorded in EXEC.md with source commit 5679bd5, then archived here after live verification. Root cause M187. No Railway configuration changes or production database mutation.

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

Source commit **5679bd505980787a6742d5bbdc4d252965e3d3bb** pushed to main and read back.

- Orc **4138d8bd-70e9-451d-9e77-faf91f6966c2**: SUCCESS, 19 October 2026 03:37:49 UTC (10:37:49 WIB).
- BFF **22c9671d-c117-4db6-9b6e-cd9e5a53f7d9**: SUCCESS, 03:37:34 UTC (10:37:34 WIB).
- Both serve one running replica. Sandbox remains Online on unchanged deployment **84fa7fa3-6bda-46af-8162-7d13d42fde7b**.
- Exact Orc deployment logs include `sandbox_runtime_initialized`, `mode4_active`, `ai_mode_selected` effective 4,
  `result_store_active` and GET /ready 200. BFF logs show normal startup. Readback: `live_readback.json`.
- No deliberate live outage or paid live-model calculation was performed. An authenticated localhost readiness
  probe over Railway SSH was unavailable because no SSH keys are configured; no keys/account permissions were
  created to work around this. Source, deployment state, initialization events and health are verified; the
  cold-start failure/recovery and UI flow are verified by the local integration tests described above.
- Disposable test Postgres was stopped and auto-removed after tests. Production data and sandbox service untouched.
Before rollout, Orc's active deployment logs for 03:15–03:35 UTC contained only periodic metadata/credit events,
no run-start event. The final 90-minute pre-push window contained only the previously completed 02:13 UTC request and periodic events, with no new active run. Source main was re-fetched and remained at the reviewed plan baseline.
