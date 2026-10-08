# EDGE reconciliation — dev rollout verified, 2026-10-08

User go: "Ok, do it" for Railway deployment from `codex/edge-bff`, without merging main.
Implementation baseline `242e282`; main's later documentation-only `93efb9f` was preserved before branch publication.

## Live database evidence

Market Postgres `bb21a9f4-a9d3-4a51-945f-fa86b63f4b86`, database railway, PostgreSQL 18.6.
Pgweb host/port/database matched this service. Admin preflight at 10:10:09 UTC read actual
`public."AI_conversation"` and `public."AI_conversation_turn"`: 24 columns, five indexes,
33 PostgreSQL-18 constraints, full conversation grants/membership. EDGE schema/roles absent;
zero active Orc requests and no PUBLIC-executable non-system SECURITY DEFINER routines.

After approved migration, readback at 10:13:24 UTC verified `edge_bff.sessions`, `edge_bff.jobs`,
and `edge_bff.conversation_ui`: 28 columns, 40 constraints, six indexes, runtime DML on exactly
those three relations. Restricted login connected successfully; direct canonical-table read was denied.
No original table, data, catalog, routine, retention, or web Postgres change. Only the EDGE section
of DATABASE_SCHEMA.md was refreshed; earlier global snapshots retain their original dates.
Detailed SQL/result evidence: `verification/edge/admin_preflight_20261008.json` and
`verification/edge/schema_readback_20261008.json`.

## Live deployments and probes

- Orc SUCCESS `24461464-9154-4789-bb5f-8ccbcc54204b`, code `b12153a`, branch codex/edge-bff.
  One additive owner-checked request-read endpoint; existing runner/model/provider/mode/flags preserved.
- BFF SUCCESS `e49f4a1c-a8ee-4733-a7d0-78370d7d52d5`, code `304600a`, branch codex/edge-bff.
  Service `c3656044-2817-44a7-9b55-54910bab416f`; HTTPS https://edge-bff-dev.up.railway.app.
- Seventeen real public HTTPS/auth checks passed, including password login, Secure/HttpOnly cookie,
  BFF-to-Orc history, refresh recovery read, CSRF/input rejection and logout/session revocation.
- Private Orc read probes verified 401 without auth and structured REQUEST_NOT_FOUND with the BFF owner/key.
- No agent POST or paid AI calls; active AI streaming/real answer/bookmark/pin/export not tested live.
  Earlier deterministic local coverage remains 1,533 Orc tests and 23 BFF tests; new manifest checks: two passed.
- Native config pull and plan completed: up to date/NOOP. No whole-project IaC apply.
- Three temporary private-network sandboxes are verified DESTROYED; temporary SSH registration/agent/key cleaned up.

Password handoff is the secret EDGE_INITIAL_PASSWORD in Railway Variables, unused by the application.
The owner can retrieve it securely and then remove that handoff variable; verifier-based login remains valid.
No credentials in Git, output or chat. Detailed rollout proof: `verification/edge/rollout_20261008.json`.

## Remaining limits

Direct TCP/SSH DNS and direct cloud proxy access to the newly allocated hostname are unavailable
from this cloud machine. Public HTTPS was exercised from Railway through its public ingress.
No fresh cloud snapshot restoration or live browser rendering was verified; the earlier local browser
tests exercised the unchanged UI against a deterministic Orc. Main merge and paid AI tests remain separate decisions.
