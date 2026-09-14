# Market query sandbox

This isolated Railway service performs bounded custom joins, windows, and descriptive
transformations over immutable snapshots prepared by `market-ai-backend`. It has no
PostgreSQL credentials. Its dedicated token can claim only `QUERY_SANDBOX` jobs.

Only one `SELECT`/`WITH` DuckDB statement is accepted. External access, file readers,
DDL, DML, extensions, and attachments are denied. The backend independently enforces
source-table allowlists, estimated scans, snapshot rows/bytes, runtime, memory, and
compact result limits.
