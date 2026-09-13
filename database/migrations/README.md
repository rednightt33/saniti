# Database migrations

Each applied schema change must have one forward-only SQL file named:

```text
YYYYMMDD_NNN_short_description.sql
```

Rules:

- Review the live schema before writing a migration.
- Make the change transactional when PostgreSQL supports it.
- Make reruns safe or fail with a clear state check.
- Never place credentials or user data in a migration.
- Never rewrite an applied migration; add another file.
- After applying, verify the live result, refresh `DATABASE_SCHEMA.md`, append `DATABASE_CHANGELOG.md`, commit, and push.
- For an approved new/changed table or column, update `Table_Catalog` and `Column_Catalog` in a forward migration. For Feature columns or formulas, also version `Feature_Catalog`. For PostgreSQL routines, update the affected table's `related_functions` and document the signature and behavior. Run `scripts/sync_database_catalog.py` before `scripts/sync_database_schema.py` and verify coverage. See `DATABASE_CATALOG.md` for exact procedure and confidence rules.
