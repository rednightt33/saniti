from __future__ import annotations

import hmac
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, status

from .config import Settings
from .db import Database
from .orchestrator import AnalysisOrchestrator, AnalysisWorker
from .schemas import AnalysisAccepted, AnalysisCreate, AnalysisStatus


settings = Settings.from_env()
database = Database(settings.database_url, settings.query_timeout_seconds)
orchestrator = AnalysisOrchestrator(database, settings)
worker = AnalysisWorker(database, settings, orchestrator)


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
