# EDGE reconciliation

VERIFIED FACTS: repository baseline 242e282; active Orc deployment 6a0ebf8f, commit 92884b6; market Postgres and separate web Postgres unchanged; no edge-bff service. Native CLI read-only inspection confirms DeepSeek slot 1, mode switch 4, server history/run memory. No secrets printed. HTML SHA256: 3ad20976de979ca6c854571e9558cf6530c684365236e70295ffd7139421b4a8

Repository update during execution: origin/main advanced to 93efb9f (EXEC/ERROR documentation only); preserve and rebase those changes before publishing this review branch.

CONFLICTS WITH PLAN: no known behavioral/topology conflict. Current main is newer than the attachment's b673611 baseline. Local Chromium is now available. Live database reconciliation is blocked, so migration cannot be marked live-ready.

UNKNOWN: live schema/grants/migration state; secret bootstrap and final origin. Existing pgweb/TCP cannot be reached from this execution environment. No read-only job/service was created to work around this because live service mutation is not authorized.

FILE-LEVEL INVENTORY: EXEC.md; new apps/edge-bff source/static/tests/README/Dockerfile; additive Orc store/route/read tests/README; new migration and schema/changelogs; separate provisioning utility; proposed .railway definition; reconciliation/rollout report. No runner/model/router/prompt changes.

TEST MATRIX: disposable PostgreSQL for migration/grants/jobs/leases/sessions; deterministic Orc route and full regressions; BFF HTTP/SSE with fake Orc, all statuses and recovery; Chromium through actual BFF/worker/local Postgres with deterministic Orc, XSS-safe response and continuations; IaC static validation and secret review. Paid tests are excluded.
