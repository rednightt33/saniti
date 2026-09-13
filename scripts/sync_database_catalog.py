#!/usr/bin/env python3
"""Reconcile approved table/column catalog rows with live PostgreSQL metadata.

New tables and columns must first be registered by a forward-only migration.
This script updates physical facts and never overwrites a manually reviewed
non-Feature definition. It rejects unregistered physical objects.
"""

from __future__ import annotations

import argparse
import os
from typing import Any

import psycopg

from sync_database_schema import COLUMN_DESCRIPTIONS


def connection_args(args: argparse.Namespace) -> dict[str, Any]:
    if args.host:
        return {
            "host": args.host,
            "port": args.port or 5432,
            "dbname": os.environ["PGDATABASE"],
            "user": os.environ["PGUSER"],
            "password": os.environ["PGPASSWORD"],
            "sslmode": "require",
        }
    return {"conninfo": os.environ["DATABASE_URL"]}


def latest_feature_definitions(connection: psycopg.Connection[Any]) -> dict[tuple[str, str], tuple[str, str, str]]:
    rows = connection.execute(
        """
        SELECT feature_table, feature_column, definition, unit, null_rule, version
        FROM public."Feature_Catalog"
        WHERE is_active
        ORDER BY feature_table, feature_column, substring(version FROM 2)::integer DESC
        """
    ).fetchall()
    result: dict[tuple[str, str], tuple[str, str, str]] = {}
    for table_name, column_name, definition, unit, null_rule, _version in rows:
        result.setdefault((table_name, column_name), (definition, unit, null_rule))
    return result


def physical_columns(connection: psycopg.Connection[Any]) -> list[tuple[Any, ...]]:
    return connection.execute(
        """
        SELECT
            columns.table_schema,
            columns.table_name,
            columns.column_name,
            columns.ordinal_position,
            columns.data_type,
            columns.is_nullable = 'YES',
            columns.column_default,
            EXISTS (
                SELECT 1
                FROM information_schema.table_constraints AS constraint_definition
                JOIN information_schema.key_column_usage AS key_column
                  ON key_column.constraint_catalog = constraint_definition.constraint_catalog
                 AND key_column.constraint_schema = constraint_definition.constraint_schema
                 AND key_column.constraint_name = constraint_definition.constraint_name
                 AND key_column.table_schema = constraint_definition.table_schema
                 AND key_column.table_name = constraint_definition.table_name
                WHERE constraint_definition.constraint_type = 'PRIMARY KEY'
                  AND constraint_definition.table_schema = columns.table_schema
                  AND constraint_definition.table_name = columns.table_name
                  AND key_column.column_name = columns.column_name
            ) AS is_primary_key,
            pg_catalog.col_description(class.oid, attributes.attnum) AS column_comment,
            catalog.source_code_paths
        FROM public."Table_Catalog" AS catalog
        JOIN information_schema.columns AS columns
          ON columns.table_schema = catalog.table_schema
         AND columns.table_name = catalog.table_name
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.nspname = columns.table_schema
        JOIN pg_catalog.pg_class AS class
          ON class.relnamespace = namespace.oid
         AND class.relname = columns.table_name
        JOIN pg_catalog.pg_attribute AS attributes
          ON attributes.attrelid = class.oid
         AND attributes.attname = columns.column_name
        ORDER BY columns.table_name, columns.ordinal_position
        """
    ).fetchall()


def reconcile(connection: psycopg.Connection[Any]) -> tuple[int, int]:
    unregistered_tables = connection.execute(
        """
        SELECT physical.table_name
        FROM information_schema.tables AS physical
        WHERE physical.table_schema = 'public'
          AND physical.table_type = 'BASE TABLE'
          AND physical.table_name NOT IN (
              'Database_Table_Status', 'Table_Catalog', 'Column_Catalog'
          )
          AND NOT EXISTS (
              SELECT 1
              FROM public."Table_Catalog" AS catalog
              WHERE catalog.table_schema = physical.table_schema
                AND catalog.table_name = physical.table_name
          )
        ORDER BY physical.table_name
        """
    ).fetchall()
    if unregistered_tables:
        raise RuntimeError(
            f"Public tables need Table_Catalog entries: {[row[0] for row in unregistered_tables]}"
        )

    missing_tables = connection.execute(
        """
        SELECT table_name
        FROM public."Table_Catalog" AS catalog
        WHERE to_regclass(format('%I.%I', catalog.table_schema, catalog.table_name)) IS NULL
        ORDER BY table_name
        """
    ).fetchall()
    if missing_tables:
        raise RuntimeError(f"Catalog targets missing physical tables: {[row[0] for row in missing_tables]}")

    feature_definitions = latest_feature_definitions(connection)
    feature_tables = {
        row[0]
        for row in connection.execute(
            "SELECT table_name FROM public.\"Table_Catalog\" WHERE category = 'Feature'"
        ).fetchall()
    }
    columns = physical_columns(connection)
    missing_feature_definitions = [
        (row[1], row[2])
        for row in columns
        if row[1] in feature_tables
        and (row[1], row[2]) not in feature_definitions
    ]
    if missing_feature_definitions:
        raise RuntimeError(
            f"Feature columns need active Feature_Catalog entries: {missing_feature_definitions}"
        )
    existing_rows = {
        (row[0], row[1], row[2]): row[3:]
        for row in connection.execute(
            """
            SELECT table_schema, table_name, column_name, ordinal_position,
                   data_type, is_nullable, default_expression, is_primary_key,
                   definition, source_column_or_expression, unit, null_rule,
                   documentation_status, source_code_paths
            FROM public."Column_Catalog"
            """
        ).fetchall()
    }
    updated = 0

    for (
        table_schema, table_name, column_name, position, data_type, nullable,
        default_expression, is_primary_key, column_comment, source_code_paths,
    ) in columns:
        key = (table_name, column_name)
        feature = feature_definitions.get(key)
        if feature:
            definition, unit, null_rule = feature
            source_reference = "Feature_Catalog active semantic version"
            documentation_status = "VERIFIED"
        else:
            definition = column_comment or COLUMN_DESCRIPTIONS.get(table_name, {}).get(column_name)
            unit = None
            null_rule = None
            source_reference = None
            documentation_status = "PARTIAL" if definition else "NEEDS_REVIEW"
            if key == ("IDX_Broker_Profile", "broker_classification"):
                documentation_status = "VERIFIED"
                source_reference = "User-confirmed meaning; live values checked"
            elif key == ("Price_Stock_Indonesia_IDX", "ingestion_time"):
                documentation_status = "VERIFIED"
                source_reference = "database/migrations/20260913_002_add_price_ingestion_time.sql"

        existing = existing_rows.get((table_schema, table_name, column_name))

        if existing is None:
            raise RuntimeError(
                f"Column_Catalog entry is required by migration: "
                f"{table_schema}.{table_name}.{column_name}"
            )

        (
            old_position, old_type, old_nullable, old_default, old_primary,
            old_definition, old_source, old_unit, old_null_rule, old_status, old_paths,
        ) = existing
        physical_changed = (
            (old_position, old_type, old_nullable, old_default, old_primary, old_paths)
            != (position, data_type, nullable, default_expression, is_primary_key, source_code_paths)
        )
        semantic_changed = (
            (feature is not None and
             (old_definition, old_source, old_unit, old_null_rule, old_status)
             != (definition, source_reference, unit, null_rule, documentation_status))
            or (old_definition is None and definition is not None)
        )
        if not physical_changed and not semantic_changed:
            continue

        if feature is not None or old_definition is None:
            new_semantics = (definition, source_reference, unit, null_rule, documentation_status)
        else:
            new_semantics = (old_definition, old_source, old_unit, old_null_rule, old_status)
        connection.execute(
            """
            UPDATE public."Column_Catalog"
            SET ordinal_position = %s,
                data_type = %s,
                is_nullable = %s,
                default_expression = %s,
                is_primary_key = %s,
                source_code_paths = %s,
                definition = %s,
                source_column_or_expression = %s,
                unit = %s,
                null_rule = %s,
                documentation_status = %s
            WHERE table_schema = %s AND table_name = %s AND column_name = %s
            """,
            (
                position, data_type, nullable, default_expression, is_primary_key,
                source_code_paths, *new_semantics, table_schema, table_name, column_name,
            ),
        )
        updated += 1

    catalog_columns = connection.execute(
        """
        SELECT table_schema, table_name, column_name
        FROM public."Column_Catalog"
        """
    ).fetchall()
    physical_keys = {(row[0], row[1], row[2]) for row in columns}
    stale = set(catalog_columns) - physical_keys
    if stale:
        raise RuntimeError(f"Catalog has stale columns: {sorted(stale)}")
    if len(catalog_columns) != len(columns):
        raise RuntimeError(
            f"Column coverage mismatch: physical={len(columns)}, catalog={len(catalog_columns)}"
        )
    return len(columns), updated


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    args = parser.parse_args()
    with psycopg.connect(**connection_args(args)) as connection:
        physical_count, updated = reconcile(connection)
    print(
        f"Catalog reconciled: {physical_count} physical columns, "
        f"{updated} updated"
    )


if __name__ == "__main__":
    main()
