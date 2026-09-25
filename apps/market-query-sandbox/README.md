# Market query sandbox

> **Status: deactivated on `dev` since 2026-09-25**, together with `market-ai-backend`, the only
> service it works for. The active deployment was removed and the GitHub source disconnected; the service
> and its variables are kept. See `RAILWAY_CHANGELOG.md`.

This isolated Railway service performs bounded custom joins, windows, and descriptive
transformations over immutable snapshots prepared by `market-ai-backend`. It has no
PostgreSQL credentials. Its dedicated token can claim only `QUERY_SANDBOX` jobs.

Only one `SELECT`/`WITH` DuckDB statement is accepted. External access, file readers,
DDL, DML, extensions, and attachments are denied. The backend independently enforces
source-table allowlists, estimated scans, snapshot rows/bytes, runtime, memory, and
compact result limits.
