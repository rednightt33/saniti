from __future__ import annotations

import hmac
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Response, status

from .config import Settings
from .db import Database
from .orchestrator import AnalysisOrchestrator, AnalysisWorker
from .analytics_store import AnalyticsSnapshotStore
from .compaction import dumps
from .schemas import (
    AnalysisAccepted, AnalysisCreate, AnalysisStatus, AnalyticsWorkerClaim,
    AnalyticsWorkerCompletion, AnalyticsWorkerFailure,
)


settings = Settings.from_env()
database = Database(settings.database_url, settings.query_timeout_seconds)
orchestrator = AnalysisOrchestrator(database, settings)
worker = AnalysisWorker(database, settings, orchestrator)
snapshot_store = AnalyticsSnapshotStore(settings) if settings.analytics_enabled else None


@asynccontextmanager
async def lifespan(_: FastAPI):
    database.open()
    worker.start()
    yield
    worker.stop()
    orchestrator.close()
    database.close()


app = FastAPI(title="Saniti Market AI", version="1.0.0", docs_url=None, redoc_url=None, lifespan=lifespan)


def authorize(authorization: str | None = Header(default=None)) -> None:
    expected = f"Bearer {settings.internal_api_key}"
    if not authorization or not hmac.compare_digest(authorization, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


def authorize_analytics_worker(authorization: str | None = Header(default=None)) -> None:
    expected = f"Bearer {settings.analytics_worker_api_key}"
    if not settings.analytics_enabled or not authorization or not hmac.compare_digest(authorization, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict[str, str]:
    try:
        with database.query_transaction() as connection:
            connection.execute("SELECT 1").fetchone()
        return {"status": "ready"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc


@app.post("/v1/analyses", response_model=AnalysisAccepted, status_code=202, dependencies=[Depends(authorize)])
def create_analysis(payload: AnalysisCreate) -> AnalysisAccepted:
    with database.connection() as connection, connection.transaction():
        row = connection.execute(
            '''INSERT INTO public."Analysis_Request" (question,user_reference)
               VALUES (%s,%s) RETURNING request_id''',
            (payload.question, payload.user_reference),
        ).fetchone()
    return AnalysisAccepted(request_id=str(row["request_id"]))


@app.get("/v1/analyses/{request_id}", response_model=AnalysisStatus, dependencies=[Depends(authorize)])
def get_analysis(request_id: str) -> AnalysisStatus:
    with database.query_transaction() as connection:
        row = connection.execute(
            '''SELECT request_id,status,current_stage,analysis_ready_date,answer,
                      recommended_next_analysis,error_message,input_tokens,output_tokens,
                      total_tokens,tool_call_count,tool_iteration_count,current_context_tokens,
                      peak_context_tokens,context_compaction_count
               FROM public."Analysis_Request" WHERE request_id=%s''',
            (request_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return AnalysisStatus(
        request_id=str(row["request_id"]), status=row["status"], current_stage=row["current_stage"],
        analysis_ready_date=row["analysis_ready_date"].isoformat() if row["analysis_ready_date"] else None,
        answer=row["answer"], recommended_next_analysis=row["recommended_next_analysis"], error_message=row["error_message"],
        usage={key: row[key] for key in ("input_tokens", "output_tokens", "total_tokens", "tool_call_count", "tool_iteration_count", "current_context_tokens", "peak_context_tokens", "context_compaction_count")},
    )


@app.post("/internal/analytics/jobs/claim", dependencies=[Depends(authorize_analytics_worker)])
def claim_analytics_job(payload: AnalyticsWorkerClaim, response: Response) -> dict:
    assert snapshot_store is not None
    with database.connection() as connection, connection.transaction():
        connection.execute(
            '''UPDATE public."Analytics_Job"
               SET status='FAILED',error_class='LEASE_EXHAUSTED',
                   error_message='Maximum worker attempts exhausted',
                   completed_at=clock_timestamp(),updated_at=clock_timestamp()
               WHERE status='PROCESSING' AND lease_expires_at < clock_timestamp()
                 AND attempt_count >= max_attempts'''
        )
        row = connection.execute(
            '''WITH candidate AS (
                   SELECT job_id FROM public."Analytics_Job"
                   WHERE status='PENDING'
                      OR (status='PROCESSING' AND lease_expires_at < clock_timestamp()
                          AND attempt_count < max_attempts)
                   ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1
               )
               UPDATE public."Analytics_Job" j
               SET status='PROCESSING',worker_id=%s,lease_token=gen_random_uuid(),
                   lease_expires_at=clock_timestamp()+make_interval(secs=>%s),
                   attempt_count=attempt_count+1,
                   started_at=COALESCE(started_at,clock_timestamp()),updated_at=clock_timestamp()
               FROM candidate WHERE j.job_id=candidate.job_id
               RETURNING j.job_id,j.snapshot_id,j.lease_token,j.analysis_spec_json,
                         j.max_runtime_seconds,j.max_memory_mb,j.max_result_rows,
                         j.max_result_bytes''',
            (payload.worker_id, settings.worker_lease_seconds),
        ).fetchone()
        if row:
            snapshot = connection.execute(
                '''SELECT object_key,content_sha256,compressed_byte_count
                   FROM public."Analytics_Dataset_Snapshot" WHERE snapshot_id=%s''',
                (row["snapshot_id"],),
            ).fetchone()
    if not row:
        response.status_code = 204
        return {}
    return {
        "job_id": str(row["job_id"]), "lease_token": str(row["lease_token"]),
        "snapshot_url": snapshot_store.presigned_download(snapshot["object_key"]),
        "snapshot_sha256": snapshot["content_sha256"],
        "snapshot_compressed_bytes": snapshot["compressed_byte_count"],
        "analysis_spec": row["analysis_spec_json"],
        "limits": {
            "runtime_seconds": row["max_runtime_seconds"],
            "memory_mb": row["max_memory_mb"],
            "result_rows": row["max_result_rows"],
            "result_bytes": row["max_result_bytes"],
        },
    }


@app.post("/internal/analytics/jobs/{job_id}/complete", dependencies=[Depends(authorize_analytics_worker)])
def complete_analytics_job(job_id: str, payload: AnalyticsWorkerCompletion) -> dict[str, bool]:
    encoded = dumps(payload.result).encode("utf-8")
    rows = payload.result.get("rows") or []
    with database.connection() as connection, connection.transaction():
        job = connection.execute(
            '''SELECT max_result_rows,max_result_bytes FROM public."Analytics_Job"
               WHERE job_id=%s AND status='PROCESSING' AND lease_token=%s
                 AND lease_expires_at >= clock_timestamp() FOR UPDATE''',
            (job_id, payload.lease_token),
        ).fetchone()
        if not job:
            raise HTTPException(status_code=409, detail="Invalid or expired analytics lease")
        if not isinstance(rows, list) or len(rows) > job["max_result_rows"] or len(encoded) > job["max_result_bytes"]:
            raise HTTPException(status_code=413, detail="Analytics result exceeds job limits")
        connection.execute(
            '''UPDATE public."Analytics_Job" SET status='SUCCESS',result_json=%s,
                 completed_at=clock_timestamp(),updated_at=clock_timestamp(),
                 lease_token=NULL,lease_expires_at=NULL WHERE job_id=%s''',
            (dumps(payload.result), job_id),
        )
    return {"accepted": True}


@app.post("/internal/analytics/jobs/{job_id}/fail", dependencies=[Depends(authorize_analytics_worker)])
def fail_analytics_job(job_id: str, payload: AnalyticsWorkerFailure) -> dict[str, bool]:
    with database.connection() as connection, connection.transaction():
        row = connection.execute(
            '''UPDATE public."Analytics_Job" SET status='FAILED',error_class=%s,
                 error_message=%s,completed_at=clock_timestamp(),updated_at=clock_timestamp(),
                 lease_token=NULL,lease_expires_at=NULL
               WHERE job_id=%s AND status='PROCESSING' AND lease_token=%s
                 AND lease_expires_at >= clock_timestamp() RETURNING job_id''',
            (payload.error_class, payload.error_message, job_id, payload.lease_token),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=409, detail="Invalid or expired analytics lease")
    return {"accepted": True}
