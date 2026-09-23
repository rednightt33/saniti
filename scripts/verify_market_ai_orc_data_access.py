#!/usr/bin/env python3
"""Read-only live verification of market-ai-orc catalog and preview tools.

Runs the service's own tool code as the market_ai_orc login (CATALOG_DATABASE_URL):
- traverses every AI catalog to the end with read_catalog_rows and checks completeness;
- calls preview_table_rows once per approved market-data table.
It prints counts, column names, ordering, and byte sizes only, never row values.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/market-ai-orc"))

from app.catalog_store import CatalogStore  # noqa: E402
from app.compaction import dumps  # noqa: E402
from app.tools import build_default_registry  # noqa: E402
from app.tools.catalog_rows import CATALOG_TABLES  # noqa: E402
from app.tools.preview import ORDERING  # noqa: E402


def call(registry, name: str, arguments: dict) -> dict:
    outcome = registry.execute("verify", name, json.dumps(arguments))
    if not outcome.ok:
        raise RuntimeError(f"{name} {arguments.get('catalog_name') or arguments.get('table_name')}: {outcome.output['error']}")
    return outcome.output["result"]


def main() -> None:
    url = os.environ.get("CATALOG_DATABASE_URL", "")
    if not url:
        raise RuntimeError("CATALOG_DATABASE_URL (market_ai_orc login) is required")
    registry = build_default_registry(
        CatalogStore(url, connect_timeout_seconds=5, statement_timeout_ms=5000), cursor_secret=os.urandom(32)
    )
    report: dict[str, object] = {"catalogs": {}, "previews": {}}
    for catalog in CATALOG_TABLES:
        cursor, pages, rows, keys = None, 0, 0, set()
        while True:
            page = call(registry, "read_catalog_rows", {"catalog_name": catalog, "page_size": None, "cursor": cursor})
            pages += 1
            names = [column["name"] for column in page["columns"]]
            positions = [names.index(key) for key in page["order_by"]]
            for row in page["rows"]:
                keys.add(tuple(row[i] for i in positions))
            rows += page["returned_rows"]
            if not page["has_more"]:
                break
            cursor = page["next_cursor"]
        report["catalogs"][catalog] = {
            "total_rows": page["total_rows"], "rows_read": rows, "distinct_keys": len(keys),
            "complete": rows == len(keys) == page["total_rows"], "pages": pages,
            "order_by": page["order_by"], "columns": [f"{c['name']} {c['type']}" for c in page["columns"]],
        }
    for table in ORDERING:
        result = call(registry, "preview_table_rows", {"table_name": table})
        report["previews"][table] = {
            "returned_rows": result["returned_rows"], "row_limit": result["row_limit"],
            "columns": len(result["columns"]), "order_by": result["ordering"]["order_by"],
            "bytes": len(dumps(result).encode("utf-8")),
        }
    print(json.dumps(report, indent=2))
    if not all(entry["complete"] for entry in report["catalogs"].values()):
        raise SystemExit("catalog traversal incomplete")


if __name__ == "__main__":
    main()
