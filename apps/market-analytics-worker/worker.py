from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import duckdb
import httpx
import pandas as pd


BACKEND_URL = os.environ["MARKET_AI_BACKEND_URL"].rstrip("/")
WORKER_API_KEY = os.environ["ANALYTICS_WORKER_API_KEY"]
POLL_SECONDS = max(1, int(os.getenv("ANALYTICS_WORKER_POLL_SECONDS", "2")))
PORT = int(os.getenv("PORT", "8080"))
WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"
HEADERS = {"Authorization": f"Bearer {WORKER_API_KEY}"}


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/health":
            self.send_response(404); self.end_headers(); return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

    def log_message(self, *_: Any) -> None:
        return


def validate_sql(statement: str, dataset_names: set[str]) -> str:
    sql = statement.strip().rstrip(";").strip()
    if not re.match(r"^(select|with)\b", sql, re.IGNORECASE):
        raise ValueError("Only SELECT/WITH analytics are allowed")
    if ";" in sql:
        raise ValueError("Only one analytics statement is allowed")
    forbidden = re.compile(
        r"\b(attach|detach|copy|export|import|install|load|pragma|call|create|alter|drop|"
        r"insert|update|delete|merge|vacuum|checkpoint|secret|read_csv|read_json|"
        r"read_parquet|httpfs|sqlite_scan|postgres_scan)\b",
        re.IGNORECASE,
    )
    match = forbidden.search(sql)
    if match:
        raise ValueError(f"Forbidden analytics operation: {match.group(1)}")
    if not dataset_names:
        raise ValueError("Snapshot contains no datasets")
    return sql


def execute_job(claim: dict[str, Any], compressed: bytes) -> dict[str, Any]:
    expected = claim["snapshot_sha256"]
    if hashlib.sha256(compressed).hexdigest() != expected:
        raise ValueError("Snapshot checksum mismatch")
    if len(compressed) != int(claim["snapshot_compressed_bytes"]):
        raise ValueError("Snapshot byte count mismatch")
    package = json.loads(gzip.decompress(compressed))
    datasets = package.get("datasets") or []
    names = {item["name"] for item in datasets}
    specification = claim["analysis_spec"]
    statement = validate_sql(specification["sql"], names)
    limits = claim["limits"]
    started = time.monotonic()
    connection = duckdb.connect(":memory:")
    timeout = threading.Timer(float(limits["runtime_seconds"]), connection.interrupt)
    try:
        connection.execute(f"SET memory_limit='{int(limits['memory_mb'])}MB'")
        connection.execute("SET threads=1")
        connection.execute("SET enable_external_access=false")
        for item in datasets:
            frame = pd.DataFrame(item["rows"], columns=item["columns"])
            connection.register(f"frame_{item['name']}", frame)
            connection.execute(
                f'CREATE TEMP TABLE "{item["name"]}" AS SELECT * FROM "frame_{item["name"]}"'
            )
            connection.unregister(f"frame_{item['name']}")
        timeout.start()
        cursor = connection.execute(statement)
        columns = [item[0] for item in cursor.description]
        max_rows = int(limits["result_rows"])
        fetched = cursor.fetchmany(max_rows + 1)
        if len(fetched) > max_rows:
            raise ValueError(f"Analytics output exceeds result row limit {max_rows}")
        rows = [dict(zip(columns, row)) for row in fetched]
        result = {
            "method": "SAFE_DUCKDB_SQL",
            "method_version": "v1",
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "input_row_count": sum(int(item["row_count"]) for item in datasets),
            "dataset_row_counts": {item["name"]: int(item["row_count"]) for item in datasets},
            "sql_sha256": hashlib.sha256(statement.encode("utf-8")).hexdigest(),
            "runtime_ms": round((time.monotonic() - started) * 1000),
        }
        encoded = json.dumps(result, default=str, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(encoded) > int(limits["result_bytes"]):
            raise ValueError("Analytics output exceeds result byte limit")
        return json.loads(encoded)
    finally:
        timeout.cancel()
        connection.close()


def run() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", PORT), HealthHandler)
    threading.Thread(target=server.serve_forever, name="health", daemon=True).start()
    with httpx.Client(timeout=30) as client:
        while True:
            try:
                response = client.post(
                    f"{BACKEND_URL}/internal/analytics/jobs/claim",
                    headers=HEADERS, json={"worker_id": WORKER_ID},
                )
                if response.status_code == 204:
                    time.sleep(POLL_SECONDS); continue
                response.raise_for_status()
                claim = response.json()
                job_id, lease_token = claim["job_id"], claim["lease_token"]
                try:
                    snapshot = client.get(claim["snapshot_url"], timeout=60)
                    snapshot.raise_for_status()
                    result = execute_job(claim, snapshot.content)
                    completed = client.post(
                        f"{BACKEND_URL}/internal/analytics/jobs/{job_id}/complete",
                        headers=HEADERS,
                        json={"lease_token": lease_token, "result": result},
                    )
                    completed.raise_for_status()
                except Exception as exc:
                    failed = client.post(
                        f"{BACKEND_URL}/internal/analytics/jobs/{job_id}/fail",
                        headers=HEADERS,
                        json={
                            "lease_token": lease_token,
                            "error_class": type(exc).__name__,
                            "error_message": str(exc)[:2000],
                        },
                    )
                    if failed.status_code not in {200, 409}:
                        failed.raise_for_status()
            except Exception as exc:
                print(json.dumps({"event": "analytics_worker_error", "error": str(exc)[:1000]}), flush=True)
                time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    run()

