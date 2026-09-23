from __future__ import annotations

import hmac
import logging
import sys
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, status

from .catalog_store import CatalogStore
from .config import Settings
from .openrouter_client import OpenRouterClient
from .orchestrator import AgentOrchestrator
from .schemas import AgentRunRequest, AgentRunResponse
from .tools import build_default_registry


def _configure_logging() -> None:
    logger = logging.getLogger("market_ai_orc")
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False


def create_app(
    settings: Settings | None = None,
    orchestrator: AgentOrchestrator | None = None,
) -> FastAPI:
    """App factory; uvicorn runs it with --factory so config is validated at startup, not import."""
    _configure_logging()
    settings = settings or Settings.from_env()
    owned_client: OpenRouterClient | None = None
    if orchestrator is None:
        owned_client = OpenRouterClient(
            settings.openrouter_api_key,
            settings.ai_request_timeout_seconds,
            x_title=settings.openrouter_x_title,
            http_referer=settings.openrouter_http_referer,
        )
        catalog = None
        if settings.catalog_database_url:
            catalog = CatalogStore(
                settings.catalog_database_url,
                connect_timeout_seconds=settings.catalog_connect_timeout_seconds,
                statement_timeout_ms=settings.catalog_statement_timeout_ms,
            )
        registry = build_default_registry(
            catalog,
            catalog_timeout_seconds=(
                settings.catalog_connect_timeout_seconds
                + 2 * settings.catalog_statement_timeout_ms / 1000
                + 2
            ),
        )
        orchestrator = AgentOrchestrator(settings, owned_client, registry)
    ready = {"value": False}

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        ready["value"] = True
        yield
        ready["value"] = False
        orchestrator.registry.close()
        if owned_client is not None:
            owned_client.close()

    app = FastAPI(
        title="Saniti Market AI Orchestrator", version="0.1.0",
        docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan,
    )
    expected = f"Bearer {settings.internal_api_key}"

    def authorize(authorization: str | None = Header(default=None)) -> None:
        if not authorization or not hmac.compare_digest(authorization, expected):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    def readiness() -> dict[str, str]:
        if not ready["value"]:
            raise HTTPException(status_code=503, detail="Not ready")
        return {"status": "ready"}

    @app.post("/v1/agent/run", response_model=AgentRunResponse, dependencies=[Depends(authorize)])
    def run_agent(payload: AgentRunRequest) -> AgentRunResponse:
        return orchestrator.run(payload)

    return app
