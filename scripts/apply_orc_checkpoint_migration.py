#!/usr/bin/env python3
"""Apply/verify the approved additive checkpoint migration. DATABASE_URL is supplied at runtime, never printed.

Default is verification only. --apply is idempotent only after verifying an existing column, constraint and catalog
entry; a partial/mismatched state fails for inspection. No Railway config, role grant or market-data row is changed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

MIGRATION = Path(__file__).resolve().parents[1] / "database/migrations/20261019_001_orc_execution_checkpoint.sql"


def inspect(connection) -> dict:
    column = connection.execute('''SELECT data_type,is_nullable FROM information_schema.columns
        WHERE table_schema='public' AND table_name='AI_conversation_turn'
          AND column_name='execution_checkpoint' ''').fetchone()
    constraint = connection.execute('''SELECT pg_get_constraintdef(oid) AS definition FROM pg_constraint
        WHERE conrelid='public."AI_conversation_turn"'::regclass
          AND conname='ai_conversation_checkpoint_check' AND contype='c' AND convalidated''').fetchone()
    catalog = connection.execute('''SELECT documentation_status,definition FROM public."Column_Catalog"
        WHERE table_schema='public' AND table_name='AI_conversation_turn'
          AND column_name='execution_checkpoint' ''').fetchall()
    return {"column_present":column is not None,
            "nullable_jsonb":bool(column and column["data_type"] == "jsonb" and column["is_nullable"] == "YES"),
            "bounded_constraint":bool(constraint and "262144" in constraint["definition"]
                                      and "version" in constraint["definition"] and "steps" in constraint["definition"]),
            "catalog_verified":len(catalog) == 1 and catalog[0]["documentation_status"] == "VERIFIED"
                               and bool(catalog[0]["definition"])}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    sql = MIGRATION.read_text()
    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True, row_factory=dict_row,
                         connect_timeout=10) as connection:
        before = inspect(connection)
        if before["column_present"]:
            if not all(before.values()):
                raise RuntimeError("Checkpoint schema/catalog mismatch; inspect before any mutation")
            action = "ALREADY_APPLIED"
        elif args.apply:
            if before["catalog_verified"] or before["bounded_constraint"]:
                raise RuntimeError("Partial checkpoint migration; inspect before any mutation")
            connection.execute(sql)
            action = "APPLIED"
        else:
            action = "NOT_APPLIED"
        after = inspect(connection)
        if args.apply and not all(after.values()):
            raise RuntimeError("Checkpoint verification failed")
    print(json.dumps({"action":action, "migration":MIGRATION.name,
                      "migration_sha256":hashlib.sha256(sql.encode()).hexdigest(), "verification":after}))


if __name__ == "__main__":
    try:
        main()
    except psycopg.Error as exc:
        # Connection exceptions may include credential-bearing addresses. Report only the type and SQLSTATE.
        print(json.dumps({"error":type(exc).__name__, "sqlstate":exc.sqlstate}))
        raise SystemExit(1)
