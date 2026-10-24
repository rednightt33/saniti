# Restore reference — not executed

Snapshot UUID is recorded in APPLY/README and the job log. Every original shared feature row is in
migration_archive.index_feature_rows (private schema), with source_table, row_hash and typed JSONB.
The initialization verifies md5(row_data::text), full JSON equality to each original row and row count
before deleting any legacy row. No raw prices or universe rows are deleted.

For an explicitly approved restore, first inspect snapshot counts and any newly created legacy rows.
Use a single transaction and typed jsonb_populate_record for the exact allowlisted source table, e.g.:

```sql
BEGIN;
-- Replace UUID with the recorded snapshot and review collisions first.
INSERT INTO public."Feature_01_Stock_Daily"
SELECT (jsonb_populate_record(NULL::public."Feature_01_Stock_Daily", row_data)).*
FROM migration_archive.index_feature_rows
WHERE snapshot_id = '293f4c52-0fd2-4d43-b02e-e0c6dba94f30'::uuid
  AND source_table = 'Feature_01_Stock_Daily';
-- Reconcile exact payload/count, then COMMIT only after approval and verification.
ROLLBACK;
```

Repeat with the other five exact source tables as authorized, never arbitrary caller-provided table
names. Do not overwrite new legacy rows or delete INDEX outputs merely to resolve a collision.
The archive has no automatic expiry during this audit/validation phase.
