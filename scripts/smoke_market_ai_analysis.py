#!/usr/bin/env python3
"""Insert one bounded smoke request and wait for the Railway worker result."""

from __future__ import annotations

import json
import os
import time

import psycopg
from psycopg.rows import dict_row


def main() -> None:
    url = os.environ.get("APP_DATABASE_URL", "")
    if not url:
        raise RuntimeError("APP_DATABASE_URL is required")
    with psycopg.connect(url, row_factory=dict_row, autocommit=True) as connection:
        request_id = connection.execute(
            '''INSERT INTO public."Analysis_Request" (question,user_reference)
               VALUES (%s,'release-1b-smoke') RETURNING request_id''',
            (
                "Find the common safe data date for Feature 1, Feature 2, and Feature 3, "
                "then report BBCA close and 20-trading-day return on that date. Check "
                "quality, load every relevant Feature definition before data retrieval, "
                "and answer concisely with recorded evidence.",
            ),
        ).fetchone()["request_id"]
        deadline = time.monotonic() + 240
        row = None
        while time.monotonic() < deadline:
            row = connection.execute(
                '''SELECT status,current_stage,analysis_ready_date,answer,error_message,
                          input_tokens,output_tokens,total_tokens,tool_call_count,
                          tool_iteration_count,peak_context_tokens,version_snapshot,
                          methodology_metadata
                   FROM public."Analysis_Request" WHERE request_id=%s''',
                (request_id,),
            ).fetchone()
            if row["status"] in {"SUCCESS", "FAILED", "CANCELLED"}:
                break
            time.sleep(3)
        if not row or row["status"] not in {"SUCCESS", "FAILED", "CANCELLED"}:
            raise RuntimeError("Smoke analysis did not reach terminal state in 240 seconds")
        output = {
            "request_id": str(request_id), "status": row["status"], "stage": row["current_stage"],
            "analysis_ready_date": row["analysis_ready_date"].isoformat() if row["analysis_ready_date"] else None,
            "input_tokens": row["input_tokens"], "output_tokens": row["output_tokens"],
            "total_tokens": row["total_tokens"], "tool_calls": row["tool_call_count"],
            "iterations": row["tool_iteration_count"], "peak_context_tokens": row["peak_context_tokens"],
            "has_answer": bool(row["answer"]), "has_version_snapshot": bool(row["version_snapshot"]),
            "has_methodology_metadata": bool(row["methodology_metadata"]),
            "error": row["error_message"],
        }
        print(json.dumps(output))
        if row["status"] != "SUCCESS":
            raise SystemExit(1)


if __name__ == "__main__":
    main()
