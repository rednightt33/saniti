# Database migrations

`20261012_001_finalize_fixed_income_markets.sql` adds data-driven fixed-income market
clocks and universe source mappings, final-candle evidence, market-specific monitoring,
and the `is_final` gate used by Feature04. It was rehearsed with a full rollback before
being applied to `lucid-patience/dev`.

`20261012_002_configure_fixed_income_source_dates.sql` records each market's TradingView
daily-bar label convention in `Fixed_Income_Market_Schedule.source_date_mapping`. It was
rehearsed with rollback deployment `70bbf1e9-5d9d-4f79-a232-33e9b53adb9e` and applied by
deployment `32f7d785-2b8c-4aa8-997d-1f873d0a9850`.

Each applied schema change must have one forward-only SQL file named:

```text
YYYYMMDD_NNN_short_description.sql
```

Rules:

- Review the live schema before writing a migration.
- Make the change transactional when PostgreSQL supports it.
- Make reruns safe or fail with a clear state check.
- Never place credentials or user data in a migration.
- Never rewrite an applied migration; add another file. `APPLIED.sha256` lists the hash of every applied migration and `apps/market-ai-orc/tests/test_migrations_frozen.py` fails when one changes: add the new file's line after it is applied (`sha256sum <file>`). A generated migration's drift test checks only the newest registration of each object; the earlier files stay frozen.
- After applying, verify the live result, refresh `DATABASE_SCHEMA.md`, append `DATABASE_CHANGELOG.md`, commit, and push.
- For an approved new/changed table or column, update `Table_Catalog` and `Column_Catalog` in a forward migration. For Feature columns or formulas, also version `Feature_Catalog`; register safe joins in `Feature_Relationship_Catalog`. Register generic AI tool schemas, activation, and advertised limits in `Tool_Catalog`. For PostgreSQL routines, update the affected table's `related_functions` and document the signature and behavior. Run `scripts/sync_database_catalog.py` before `scripts/sync_database_schema.py`, verify coverage, and run bounded query-plan acceptance before adding a large index. See `DATABASE_CATALOG.md` for exact procedure and confidence rules.
