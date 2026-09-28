from __future__ import annotations

import hmac
import logging
import re
import sys
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, Response

from .config import Settings
from .ingest import OutboxConsumer
from .models import (API_VERSION, AccessGrant, AccessIn, ArtifactPrepare, ArtifactPrepared, ArtifactVerified,
                     EventBatch, EventBatchAck, ExecutionAck, ExecutionRecord, Finalize, HoldIn, LinkBatch,
                     LinkBatchAck, RunRef, RunRegistration)
from .service import AuditError, AuditService
from .storage import LocalStore, ObjectStore, build_store

ACCESSOR = re.compile(r"^[A-Za-z0-9._:@-]{1,128}$")
RUN_ID = r"^run_[0-9a-f]{32}$"
ARTIFACT_ID = r"^art_[0-9a-f]{32}$"
EXECUTION_ID = r"^exe_[0-9a-f]{24}$"
REQUEST_ID = r"^[A-Za-z0-9._:-]{1,200}$"
HOLD_ID = r"^hold_[0-9a-f]{32}$"


def _configure_logging() -> None:
    logger = logging.getLogger("market_audit_store")
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False


def create_app(settings: Settings | None = None, store: ObjectStore | None = None,
               start_consumer: bool = True) -> FastAPI:
    """market-audit-store. Producer endpoints (/v1/internal/...) take the Governor or sandbox key and record that
    producer as the source; query endpoints take the reader key. Object keys never appear in a response."""
    _configure_logging()
    settings = settings or Settings.from_env()
    store = store or build_store(settings)
    service = AuditService(settings, store)
    consumer = OutboxConsumer(service)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if start_consumer and settings.outbox_enabled:
            consumer.start()
        yield
        consumer.stop()

    app = FastAPI(title="Saniti Market Audit Store", version="1.0.0", lifespan=lifespan,
                  description=f"Contract {API_VERSION}. Durable, queryable audit of AI research runs.")
    app.state.service, app.state.consumer = service, consumer
    producers = {name: f"Bearer {key}" for name, key in (("market-sql-governor", settings.governor_key),
                                                         ("market-python-sandbox", settings.sandbox_key)) if key}
    reader = f"Bearer {settings.reader_key}" if settings.reader_key else None

    def producer(authorization: str | None = Header(default=None)) -> str:
        for name, expected in producers.items():
            if authorization and hmac.compare_digest(authorization, expected):
                return name
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    def operator(authorization: str | None = Header(default=None),
                 x_audit_accessor: str | None = Header(default=None)) -> str:
        if not (reader and authorization and hmac.compare_digest(authorization, reader)):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
        if x_audit_accessor is not None and not ACCESSOR.fullmatch(x_audit_accessor):
            raise HTTPException(status_code=422, detail="X-Audit-Accessor must match [A-Za-z0-9._:@-]{1,128}")
        return f"reader:{x_audit_accessor}" if x_audit_accessor else "reader"

    @app.exception_handler(AuditError)
    async def _audit_error(_: Request, exc: AuditError) -> JSONResponse:
        return JSONResponse(status_code=exc.status, content={"error": {"code": exc.code, "message": exc.message}})

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "market-audit-store", "contract": API_VERSION}

    @app.get("/ready")
    def ready() -> JSONResponse:
        try:
            service.ping()
        except Exception as exc:  # noqa: BLE001 - readiness reports, it does not raise
            return JSONResponse(status_code=503, content={"status": "unavailable", "reason": type(exc).__name__})
        return JSONResponse(content={"status": "ready"})

    # ------------------------------------------------------------------ producers (internal)

    @app.post("/v1/internal/runs", response_model=RunRef, tags=["producer"])
    def register_run(body: RunRegistration, source: str = Depends(producer)) -> dict[str, Any]:
        return service.register_run(source, body)

    @app.post("/v1/internal/runs/{run_id}/events", response_model=EventBatchAck, tags=["producer"])
    def append_events(body: EventBatch, run_id: str = _path(RUN_ID),
                      source: str = Depends(producer)) -> dict[str, Any]:
        return {"run_id": run_id, "appended": service.append_events(source, run_id, body.events)}

    @app.post("/v1/internal/artifacts", response_model=ArtifactPrepared, tags=["producer"])
    def prepare_artifact(body: ArtifactPrepare, source: str = Depends(producer)) -> dict[str, Any]:
        return service.prepare_artifact(source, body)

    @app.post("/v1/internal/artifacts/{artifact_id}/verify", response_model=ArtifactVerified, tags=["producer"])
    def verify_artifact(artifact_id: str = _path(ARTIFACT_ID), _: str = Depends(producer)) -> dict[str, Any]:
        return service.verify_artifact(artifact_id)

    @app.post("/v1/internal/runs/{run_id}/artifacts", response_model=LinkBatchAck, tags=["producer"])
    def link_artifacts(body: LinkBatch, run_id: str = _path(RUN_ID),
                       source: str = Depends(producer)) -> dict[str, Any]:
        return service.link(source, run_id, body.links)

    @app.post("/v1/internal/executions", response_model=ExecutionAck, tags=["producer"])
    def register_execution(body: ExecutionRecord, source: str = Depends(producer)) -> dict[str, Any]:
        return service.register_execution(source, body)

    @app.post("/v1/internal/runs/{run_id}/finalize", tags=["producer"])
    def finalize(body: Finalize, run_id: str = _path(RUN_ID), _: str = Depends(producer)) -> dict[str, Any]:
        # a producer adds expectations; only market-ai-orc's RUN_FINISHED (the outbox) marks a run finished
        return service.finalize(run_id, body.expected, finished=False)

    # ------------------------------------------------------------------ query and replay (reader)

    @app.get("/v1/runs/{run_id}", tags=["query"])
    def get_run(run_id: str = _path(RUN_ID), _: str = Depends(operator)) -> dict[str, Any]:
        return service.run_view(run_id)

    @app.get("/v1/requests/{request_id}/run", tags=["query"])
    def get_run_by_request(request_id: str = _path(REQUEST_ID), _: str = Depends(operator)) -> dict[str, Any]:
        return service.run_by_request(request_id)

    @app.get("/v1/runs/{run_id}/events", tags=["query"])
    def get_events(run_id: str = _path(RUN_ID), after_seq: int = Query(default=0, ge=0),
                   limit: int = Query(default=200, ge=1, le=500), _: str = Depends(operator)) -> dict[str, Any]:
        return service.events(run_id, after_seq, limit)

    @app.get("/v1/runs/{run_id}/artifacts", tags=["query"])
    def get_artifacts(run_id: str = _path(RUN_ID), _: str = Depends(operator)) -> dict[str, Any]:
        return {"run_id": run_id, "artifacts": service.run_artifacts(run_id)}

    @app.get("/v1/runs/{run_id}/replay-manifest", tags=["query"])
    def get_replay(run_id: str = _path(RUN_ID), _: str = Depends(operator)) -> dict[str, Any]:
        return service.replay_manifest(run_id)

    @app.get("/v1/conversations/{conversation_id}/runs", tags=["query"])
    def get_conversation(conversation_id: str = _path(REQUEST_ID), limit: int = Query(default=100, ge=1, le=500),
                         _: str = Depends(operator)) -> dict[str, Any]:
        return {"conversation_id": conversation_id, "runs": service.conversation_runs(conversation_id, limit)}

    @app.get("/v1/executions/{execution_id}/runtime", tags=["query"])
    def get_runtime(execution_id: str = _path(EXECUTION_ID), _: str = Depends(operator)) -> dict[str, Any]:
        return service.execution_runtime(execution_id)

    @app.post("/v1/artifacts/{artifact_id}/access", response_model=AccessGrant, tags=["query"])
    def access(body: AccessIn, artifact_id: str = _path(ARTIFACT_ID),
               accessor: str = Depends(operator)) -> dict[str, Any]:
        return service.grant_access(accessor, artifact_id, body.purpose, body.run_id)

    @app.post("/v1/retention-holds", tags=["retention"])
    def add_hold(body: HoldIn, actor: str = Depends(operator)) -> dict[str, Any]:
        return service.add_hold(actor, body.run_id, body.artifact_id, body.reason)

    @app.post("/v1/retention-holds/{hold_id}/release", tags=["retention"])
    def release_hold(hold_id: str = _path(HOLD_ID), actor: str = Depends(operator)) -> dict[str, Any]:
        return service.release_hold(actor, hold_id)

    @app.get("/v1/retention/report", tags=["retention"])
    def retention_report(_: str = Depends(operator)) -> dict[str, Any]:
        return service.retention_report()

    # ------------------------------------------------------------------ local development object endpoints

    if isinstance(store, LocalStore):
        local: LocalStore = store

        @app.put("/v1/local/objects/{token}", include_in_schema=False)
        async def local_put(token: str, request: Request) -> Response:
            claims = local.check(token, "PUT")
            if claims is None or not str(claims.get("k", "")).startswith("staging/"):
                return Response(status_code=403)
            body = await request.body()
            if len(body) > settings.max_artifact_bytes:
                return Response(status_code=413)
            local.put(claims["k"], body, request.headers.get("content-type") or "application/octet-stream")
            return Response(status_code=200)

        @app.get("/v1/local/objects/{token}", include_in_schema=False)
        def local_get(token: str) -> Response:
            claims = local.check(token, "GET")
            data = local.read(claims["k"]) if claims else None
            if data is None:
                return Response(status_code=403 if claims is None else 404)
            return Response(content=data, media_type="application/octet-stream")

    return app


def _path(pattern: str) -> Any:
    from fastapi import Path

    return Path(pattern=pattern)
