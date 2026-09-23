from __future__ import annotations

import hmac
import logging
import re
import sys
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Body, Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import JSONResponse

from .config import Settings
from .decisions import GovernorResponse
from .governor import Database, Governor, GovernorUnavailable
from .janitor import DatasetJanitor
from .store import build_store

REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def _configure_logging() -> None:
    logger = logging.getLogger("market_sql_governor")
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False


def create_app(settings: Settings | None = None, governor: Governor | None = None) -> FastAPI:
    """App factory. The only data endpoint accepts a structured Data Request Spec, never SQL."""
    _configure_logging()
    settings = settings or Settings.from_env()
    database = Database(settings)
    governor = governor or Governor(settings, database, build_store(settings))
    store = getattr(governor, "store", None)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        janitor = None
        if store is not None and settings.dataset_cleanup_interval_seconds > 0:
            janitor = DatasetJanitor(store, interval_seconds=settings.dataset_cleanup_interval_seconds,
                                     retention_hours=settings.dataset_retention_hours)
            janitor.start()
        yield
        if janitor is not None:
            janitor.stop()

    app = FastAPI(title="Saniti Market SQL Governor", version="1.0.0",
                  docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    expected = f"Bearer {settings.api_key}"

    def authorize(authorization: str | None = Header(default=None)) -> None:
        if not authorization or not hmac.compare_digest(authorization, expected):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    def ready() -> dict[str, str]:
        try:
            governor.database.ping()
        except GovernorUnavailable:
            raise HTTPException(status_code=503, detail="Database unavailable")
        return {"status": "ready"}

    @app.post("/v1/query", response_model=GovernorResponse, dependencies=[Depends(authorize)])
    def query(body: Any = Body(...)) -> Any:
        if not isinstance(body, dict) or set(body) != {"request_id", "spec"}:
            raise HTTPException(status_code=422, detail="Body must be exactly {request_id, spec}")
        request_id = body["request_id"]
        if not isinstance(request_id, str) or not REQUEST_ID.fullmatch(request_id):
            raise HTTPException(status_code=422, detail="request_id must match ^[A-Za-z0-9._:-]{1,128}$")
        try:
            return governor.handle(request_id, body["spec"])
        except GovernorUnavailable:
            return JSONResponse(status_code=503, content={"detail": "Governed database unavailable"})

    return app
