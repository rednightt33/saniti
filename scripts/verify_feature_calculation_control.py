#!/usr/bin/env python3
"""Read back Feature 01 control tables and rollback-only constraint smoke tests."""

from __future__ import annotations

import argparse
import os

import psycopg
from psycopg import sql


TABLES = (
    "Feature_Calculation_Queue",
    "Feature_Status",
    "Feature_Calculation_Log",
)


def expect_rejected(connection: psycopg.Connection, statement: str, params: tuple) -> None:
    connection.execute("SAVEPOINT validation_case")
    try:
        connection.execute(statement, params)
    except (
        psycopg.errors.CheckViolation,
        psycopg.errors.UniqueViolation,
        psycopg.errors.ForeignKeyViolation,
    ):
        connection.execute("ROLLBACK TO SAVEPOINT validation_case")
    else:
        raise AssertionError(f"Invalid statement unexpectedly succeeded: {statement}")
    finally:
        connection.execute("RELEASE SAVEPOINT validation_case")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", required=True, type=int)
    args = parser.parse_args()

    with psycopg.connect(
        host=args.host,
        port=args.port,
        dbname=os.environ["PGDATABASE"],
        user=os.environ["PGUSER"],
        password=os.environ["PGPASSWORD"],
        sslmode="require",
    ) as connection:
        assert connection.execute("SELECT current_database()").fetchone()[0] == "railway"
        for table in TABLES:
            assert connection.execute("SELECT to_regclass(%s)", (f'public."{table}"',)).fetchone()[0]
            count = connection.execute(
                sql.SQL("SELECT count(*) FROM public.{}").format(sql.Identifier(table))
            ).fetchone()[0]
            assert count == 0, (table, count)
            physical = connection.execute(
                "SELECT count(*) FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = %s", (table,)
            ).fetchone()[0]
            catalog = connection.execute(
                'SELECT count(*) FROM public."Column_Catalog" WHERE table_name = %s',
                (table,),
            ).fetchone()[0]
            assert physical == catalog and physical > 0, (table, physical, catalog)
            print(f"PASS {table}: rows={count}, columns={physical}, catalog={catalog}")

        table_count = connection.execute(
            'SELECT count(*) FROM public."Table_Catalog"'
        ).fetchone()[0]
        feature_count = connection.execute(
            'SELECT count(*) FROM public."Feature_01_Stock_Daily"'
        ).fetchone()[0]
        price_count = connection.execute(
            'SELECT count(*) FROM public."Price_Stock_Indonesia_IDX"'
        ).fetchone()[0]
        assert table_count == 14 and feature_count == price_count
        print(f"PASS catalog_tables={table_count}, feature_rows={feature_count}, price_rows={price_count}")

        ticker, price_date, version = connection.execute(
            'SELECT ticker, date, coalesce(ingestion_time, CURRENT_TIMESTAMP) '
            'FROM public."Price_Stock_Indonesia_IDX" LIMIT 1'
        ).fetchone()
        insert_queue = (
            'INSERT INTO public."Feature_Calculation_Queue" '
            '(ticker, price_date, source_ingestion_time) VALUES (%s, %s, %s)'
        )
        connection.execute(insert_queue, (ticker, price_date, version))
        expect_rejected(connection, insert_queue, (ticker, price_date, version))
        missing_ticker = "__MISSING_FEATURE_CONTROL_TEST__"
        assert connection.execute(
            'SELECT count(*) FROM public."Price_Stock_Indonesia_IDX" WHERE ticker = %s',
            (missing_ticker,),
        ).fetchone()[0] == 0
        expect_rejected(connection, insert_queue, (missing_ticker, price_date, version))
        expect_rejected(
            connection,
            'UPDATE public."Feature_Calculation_Queue" SET status = %s '
            'WHERE ticker = %s AND price_date = %s',
            ("INVALID", ticker, price_date),
        )
        connection.execute(
            'INSERT INTO public."Feature_Status" '
            '(ticker, latest_price_date, latest_source_ingestion_time) '
            'VALUES (%s, %s, %s)', (ticker, price_date, version)
        )
        expect_rejected(
            connection,
            'UPDATE public."Feature_Status" SET status = %s WHERE ticker = %s',
            ("SUCCESS", ticker),
        )
        insert_log = (
            'INSERT INTO public."Feature_Calculation_Log" '
            '(feature_table, ticker, price_date, source_ingestion_time, '
            'attempt_no, result, started_at) '
            'VALUES (%s, %s, %s, %s, 1, %s, CURRENT_TIMESTAMP)'
        )
        log_params = ("Feature_01_Stock_Daily", ticker, price_date, version, "SUPERSEDED")
        connection.execute(insert_log, log_params)
        expect_rejected(connection, insert_log, log_params)
        print("PASS rollback-only tests: queue FK/PK/status, status SUCCESS guard, log attempt key")
        connection.rollback()


if __name__ == "__main__":
    main()
