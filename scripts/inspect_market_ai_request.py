#!/usr/bin/env python3
"""Print a bounded, secret-free audit summary for one market-AI request."""

from __future__ import annotations

import json
import os
import sys
from urllib.parse import urlsplit, urlunsplit

import psycopg
from psycopg.rows import dict_row


def use_public_proxy(app_url: str, proxy_url: str) -> str:
    app = urlsplit(app_url)
    proxy = urlsplit(proxy_url)
    if not app.username or app.password is None or not proxy.hostname or proxy.port is None:
        raise RuntimeError("Application or proxy database URL is incomplete")
    netloc = f"{app.username}:{app.password}@{proxy.hostname}:{proxy.port}"
    return urlunsplit((app.scheme, netloc, app.path, app.query, app.fragment))


def main() -> None:
    url = os.environ.get("APP_DATABASE_URL", "") or os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError("APP_DATABASE_URL or DATABASE_URL is required")
    if proxy := os.environ.get("POSTGRES_PUBLIC_URL", ""):
        url = use_public_proxy(url, proxy)
    requested_id = sys.argv[1] if len(sys.argv) > 1 else None
    with psycopg.connect(url, row_factory=dict_row) as connection:
        recent = connection.execute(
            '''SELECT request_id,status,current_stage,attempt_count,input_tokens,
                      output_tokens,tool_call_count,tool_iteration_count,
                      created_at,started_at,completed_at,updated_at
               FROM public."Analysis_Request"
               WHERE user_reference='release-1b-smoke'
               ORDER BY created_at DESC LIMIT 10'''
        ).fetchall()
        if requested_id:
            request = connection.execute(
                '''SELECT request_id,status,current_stage,attempt_count,input_tokens,
                          output_tokens,total_tokens,tool_call_count,tool_iteration_count,
                          context_compaction_count,error_message,created_at,started_at,
                          completed_at,updated_at
                   FROM public."Analysis_Request" WHERE request_id=%s''',
                (requested_id,),
            ).fetchone()
        else:
            request = connection.execute(
                '''SELECT request_id,status,current_stage,attempt_count,input_tokens,
                          output_tokens,total_tokens,tool_call_count,tool_iteration_count,
                          context_compaction_count,error_message,created_at,started_at,
                          completed_at,updated_at
                   FROM public."Analysis_Request"
                   WHERE user_reference='release-1b-smoke'
                   ORDER BY created_at DESC LIMIT 1'''
            ).fetchone()
        if not request:
            raise RuntimeError("Analysis request was not found")
        request_id = request["request_id"]
        calls = connection.execute(
            '''SELECT attempt_number,iteration_number,stage,input_tokens,output_tokens,
                      reasoning_tokens,active_context_tokens,decision_summary_source,
                      left(coalesce(decision_summary,''),300) AS decision_summary,
                      created_at
               FROM public."Analysis_Model_Call" WHERE request_id=%s
               ORDER BY attempt_number,iteration_number''',
            (request_id,),
        ).fetchall()
        steps = connection.execute(
            '''SELECT step_number,stage,tool_name,status,estimated_rows,processed_rows,
                      returned_rows,duration_ms,left(coalesce(error_message,''),300) AS error_message,
                      created_at
               FROM public."Analysis_Step_Log" WHERE request_id=%s
               ORDER BY step_number''',
            (request_id,),
        ).fetchall()
        jobs = connection.execute(
            '''SELECT job_id,execution_class,method,status,attempt_count,error_class,
                      left(coalesce(error_message,''),300) AS error_message,
                      created_at,started_at,completed_at
               FROM public."Analytics_Job" WHERE request_id=%s ORDER BY created_at''',
            (request_id,),
        ).fetchall()
        evidence_count = connection.execute(
            'SELECT count(*) AS n FROM public."Analysis_Evidence" WHERE request_id=%s',
            (request_id,),
        ).fetchone()["n"]
    print(json.dumps(
        {
            "request": request,
            "recent_smoke_requests": recent,
            "model_calls": calls,
            "steps": steps,
            "jobs": jobs,
            "evidence_count": evidence_count,
        },
        default=str,
    ))


if __name__ == "__main__":
    main()
