#!/usr/bin/env python3
"""Apply one forward-only SQL migration using Railway-injected DB credentials."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import psycopg


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("migration", type=Path)
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    args = parser.parse_args()

    connection_args = {}
    if args.host:
        connection_args = {
            "host": args.host,
            "port": args.port or 5432,
            "dbname": os.environ["PGDATABASE"],
            "user": os.environ["PGUSER"],
            "password": os.environ["PGPASSWORD"],
            "sslmode": "require",
        }
    else:
        connection_args = {"conninfo": os.environ["DATABASE_URL"]}

    sql = args.migration.read_text(encoding="utf-8")
    with psycopg.connect(**connection_args) as connection:
        connection.execute(sql)
        connection.commit()
    print(f"Applied {args.migration.name}")


if __name__ == "__main__":
    main()
