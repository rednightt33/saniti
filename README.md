# saniti

## Database schema documentation

[`DATABASE_SCHEMA.md`](DATABASE_SCHEMA.md) is generated from the live Railway PostgreSQL schema. It documents tables, columns, constraints, indexes, and known logical relationships.

The `Database_Table_Status` table separates three different concepts:

- `Latest Data Date`: latest business date represented by the table, such as the newest broker-summary trading date.
- `Last Changed At`: latest completed load or automatically tracked data change.
- `Last Checked At`: time the schema catalog last inspected the table.

Reference tables are tracked from their recorded baseline forward. Transactional tables derive freshness from their dated records and load log.

The `Update database schema documentation` GitHub Action refreshes the catalog daily at 01:17 Asia/Jakarta and can also be started manually. Configure a repository Actions secret named `RAILWAY_TOKEN` with access to the Railway project before enabling the workflow.

To refresh it locally:

```bash
python -m pip install -r requirements-schema.txt
DATABASE_URL="postgresql://..." python scripts/sync_database_schema.py
```
