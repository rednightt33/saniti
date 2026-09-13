#!/usr/bin/env python3
"""Verify the application login can read Features and cannot read raw sources."""

from __future__ import annotations

import json
import os

import psycopg
from psycopg.errors import InsufficientPrivilege


def main() -> None:
    url = os.environ.get("APP_DATABASE_URL", "")
    if not url:
        raise RuntimeError("APP_DATABASE_URL is required")
    with psycopg.connect(url) as connection:
        user = connection.execute("SELECT current_user").fetchone()[0]
        feature_count = connection.execute(
            'SELECT count(*) FROM public."Feature_01_Stock_Daily" WHERE ticker=%s AND date=%s',
            ("BBCA", "2026-08-31"),
        ).fetchone()[0]
        raw_denied = False
        try:
            connection.execute('SELECT 1 FROM public."Price_Stock_Indonesia_IDX" LIMIT 1')
        except InsufficientPrivilege:
            raw_denied = True
            connection.rollback()
    if user != "market_ai_app" or feature_count != 1 or not raw_denied:
        raise RuntimeError("market_ai_app least-privilege verification failed")
    print(json.dumps({"login": user, "feature_read": True, "raw_read_denied": True}))


if __name__ == "__main__":
    main()
