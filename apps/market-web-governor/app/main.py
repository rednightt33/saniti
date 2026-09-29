from __future__ import annotations

import hmac
import json
import logging
import sys
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import JSONResponse

from .ask import AskRequest, AskService, AskStore, PostgresAskStore
from .config import Settings
from .event_store import EventStore
from .fetcher import DocumentFetcher
from .governor import GovernorValidationError, WebGovernor
from .models import CreateWebNeedRequest, ExecuteWebNeedRequest, FastSearchRequest, FetchRequest
from .provider import OpenRouterProvider
from .store import EvidenceJanitor, IdempotencyConflict, SqliteStore, StoreUnavailable


def _configure_logging() -> logging.Logger:
    logger = logging.getLogger("market_web_governor")
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


def create_app(
    settings: Settings | None = None,
    store: SqliteStore | None = None,
    provider: OpenRouterProvider | None = None,
    fetcher: DocumentFetcher | None = None,
    event_store: EventStore | None = None,
    ask_service: AskService | None = None,
    ask_store: AskStore | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    store = store or SqliteStore(settings.store_path, settings.stale_running_seconds)
    provider = provider or OpenRouterProvider(settings)
    fetcher = fetcher or DocumentFetcher(settings)
    governor = WebGovernor(settings, store, provider, fetcher, event_store)
    if ask_store is None and settings.event_store_url:
        ask_store = PostgresAskStore(settings.event_store_url)
    ask_service = ask_service or AskService(settings, provider, ask_store)
    logger = _configure_logging()
    expected = f"Bearer {settings.api_key}"

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        janitor = EvidenceJanitor(store, settings.retention_hours, settings.cleanup_interval_seconds)
        janitor.start()
        yield
        janitor.stop()
        for resource in (provider, fetcher, ask_service):
            close = getattr(resource, "close", None)
            if callable(close):
                close()

    app = FastAPI(
        title="Saniti Market Web Governor",
        version="1.0.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )

    def authorize(authorization: str | None = Header(default=None)) -> None:
        if not authorization or not hmac.compare_digest(authorization, expected):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    @app.exception_handler(IdempotencyConflict)
    async def idempotency_conflict(_: Any, exc: IdempotencyConflict) -> JSONResponse:
        return JSONResponse(status_code=409, content={"code": "IDEMPOTENCY_CONFLICT", "detail": str(exc)})

    @app.exception_handler(StoreUnavailable)
    async def store_unavailable(_: Any, exc: StoreUnavailable) -> JSONResponse:
        return JSONResponse(status_code=503, content={"code": "STORE_UNAVAILABLE", "detail": str(exc)})

    @app.exception_handler(GovernorValidationError)
    async def validation_error(_: Any, exc: GovernorValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"code": exc.code, "detail": str(exc)})

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    def ready() -> dict[str, str]:
        try:
            store.ping()
        except StoreUnavailable:
            raise HTTPException(status_code=503, detail="Evidence store unavailable")
        return {"status": "ready"}

    @app.get("/v1/capabilities", dependencies=[Depends(authorize)])
    def capabilities() -> dict[str, Any]:
        return governor.capabilities()

    @app.post("/v1/web-needs", dependencies=[Depends(authorize)])
    def create_web_need(body: CreateWebNeedRequest) -> dict[str, Any]:
        result = governor.create_need(body)
        event = "web_need_created" if result["status"] == "APPROVED" else "web_need_replayed"
        logger.info(json.dumps({"event": event, "request_id": body.request_id,
                                "web_need_id": result["web_need_id"], "status": result["status"]}))
        return result

    @app.post("/v1/web-needs/{web_need_id}/execute", dependencies=[Depends(authorize)])
    def execute_web_need(web_need_id: str, body: ExecuteWebNeedRequest) -> dict[str, Any]:
        try:
            result = governor.execute_need(web_need_id, body.request_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Web need not found")
        except RuntimeError as exc:
            if str(exc) == "WEB_NEED_ALREADY_RUNNING":
                raise HTTPException(status_code=409, detail="Web need is already running")
            raise
        logger.info(json.dumps({"event": "web_need_completed", "request_id": body.request_id,
                                "web_need_id": web_need_id, "status": result["status"],
                                "evidence_count": len(result.get("evidence", [])),
                                "event_store": result.get("event_store"),
                                "warning_codes": sorted({w.get("code") for w in result.get("warnings", [])})}))
        return result

    @app.get("/v1/web-needs/{web_need_id}", dependencies=[Depends(authorize)])
    def get_web_need(web_need_id: str) -> dict[str, Any]:
        result = governor.get_need(web_need_id)
        if not result:
            raise HTTPException(status_code=404, detail="Web need not found")
        return result

    @app.get("/v1/evidence/{evidence_id}", dependencies=[Depends(authorize)])
    def get_evidence(evidence_id: str) -> dict[str, Any]:
        result = store.get_evidence(evidence_id)
        if not result:
            raise HTTPException(status_code=404, detail="Evidence not found")
        return result

    @app.get("/v1/documents/{document_id}", dependencies=[Depends(authorize)])
    def get_document(document_id: str) -> dict[str, Any]:
        result = store.get_document(document_id)
        if not result:
            raise HTTPException(status_code=404, detail="Document not found")
        return result

    @app.post("/v1/search", dependencies=[Depends(authorize)])
    def search(body: FastSearchRequest) -> dict[str, Any]:
        result = governor.fast_search(body)
        _log_result("web_search_returned", body.request_id, result)
        return result

    @app.post("/v1/fetch", dependencies=[Depends(authorize)])
    def fetch(body: FetchRequest) -> dict[str, Any]:
        result = governor.fetch(body)
        _log_result("web_fetch_returned", body.request_id, result)
        return result

    @app.post("/v1/ask", dependencies=[Depends(authorize)])
    def ask(body: AskRequest) -> dict[str, Any]:
        result = ask_service.ask(body)
        logger.info(json.dumps({
            "event": "web_ask_answered", "request_id": body.request_id, "ask_id": result.get("ask_id"),
            "status": result.get("status"), "sources": len(result.get("sources") or []),
            "citations": len(result.get("citations") or []), "seconds": result.get("seconds"),
            "replayed": bool(result.get("replayed")), "stored": result.get("stored"),
            "warning_codes": sorted({warning.get("code") for warning in result.get("warnings") or []}),
        }))
        return result

    def _log_result(event: str, request_id: str, result: dict[str, Any]) -> None:
        logger.info(json.dumps({
            "event": event, "request_id": request_id, "web_need_id": result.get("web_need_id"),
            "status": result.get("status"), "evidence_count": len(result.get("evidence", [])),
            "provider_call_count": (result.get("execution") or {}).get("provider_call_count"),
            "model_slot": (result.get("execution") or {}).get("model_slot"),
            "warning_codes": sorted({warning.get("code") for warning in result.get("warnings", [])}),
        }))

    return app
