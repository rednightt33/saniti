from __future__ import annotations

import hashlib
import hmac
import logging
import sys
import threading
import time
from contextlib import asynccontextmanager
from functools import partial

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import JSONResponse

from .catalog_store import CatalogStore
from .catalog_summary import CatalogSummary
from .config import Settings
from .conversations import ConversationError, ConversationStore, UpkeepThread, fingerprint, owner_from_header
from .openrouter_client import OpenRouterClient
from .audit import RunAuditor
from .orchestrator import AgentOrchestrator, log_event
from .provider_log import ProviderLogger
from .schemas import AgentRunRequest, AgentRunResponse
from .tools import build_default_registry
from .tools.analysis import SandboxClient
from .tools.catalog import CatalogTools
from .tools.request_data import GovernorClient
from .tools.session import close_sessions


def _configure_logging() -> None:
    logger = logging.getLogger("market_ai_orc")
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False


def _sandbox_ready(sandbox: SandboxClient, attempts: int = 3, delay_seconds: float = 2.0) -> bool:
    for attempt in range(attempts):
        if sandbox.ready():
            return True
        if attempt + 1 < attempts:
            time.sleep(delay_seconds)
    return False


def create_app(
    settings: Settings | None = None,
    orchestrator: AgentOrchestrator | None = None,
    conversations: ConversationStore | None = None,
) -> FastAPI:
    """App factory; uvicorn runs it with --factory so config is validated at startup, not import."""
    _configure_logging()
    settings = settings or Settings.from_env()
    if conversations is None and settings.ai_enable_conversation_store and settings.conversation_database_url:
        conversations = ConversationStore(settings.conversation_database_url,
                                          retention_days=settings.ai_conversation_retention_days,
                                          lease_seconds=settings.conversation_lease_seconds)
    upkeep = UpkeepThread(conversations, settings.ai_conversation_upkeep_seconds) if conversations else None
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
        governor = None
        if settings.sql_governor_url:
            governor = GovernorClient(settings.sql_governor_url, settings.sql_governor_api_key or "",
                                      settings.sql_governor_timeout_seconds)
        sandbox = None
        if settings.py_sandbox_url:
            sandbox = SandboxClient(settings.py_sandbox_url, settings.py_sandbox_api_key or "",
                                    settings.py_sandbox_request_timeout_seconds, settings.py_sandbox_poll_wait_seconds)
            if not _sandbox_ready(sandbox):
                # Intentionally disabled: python_analysis stays false until the sandbox is ready at startup.
                logging.getLogger("market_ai_orc").warning(
                    '{"event":"python_sandbox_not_ready","python_analysis":false}')
                sandbox.close()
                sandbox = None
        registry = build_default_registry(
            catalog,
            catalog_timeout_seconds=(
                settings.catalog_connect_timeout_seconds
                + 4 * settings.catalog_statement_timeout_ms / 1000
                + 2
            ),
            cursor_secret=hashlib.sha256(
                b"market-ai-orc catalog cursor:" + settings.internal_api_key.encode()
            ).digest(),
            page_size_default=settings.catalog_page_size_default,
            page_size_max=settings.catalog_page_size_max,
            page_max_bytes=settings.catalog_page_max_bytes,
            preview_enabled=settings.market_data_preview_enabled,
            governor_client=governor,
            governor_timeout_seconds=settings.sql_governor_timeout_seconds + 5,
            request_data_max_bytes=settings.request_data_max_result_bytes,
            sandbox_client=sandbox,
            sandbox_timeout_seconds=settings.py_sandbox_request_timeout_seconds + 5,
            python_analysis_max_bytes=settings.python_analysis_max_result_bytes,
            lookup_fact_enabled=settings.ai_enable_lookup_fact,
            request_data_enabled=settings.ai_enable_request_data,
            dataneed_enabled=settings.ai_enable_dataneed,
            session_timeout_seconds=settings.py_sandbox_session_timeout_seconds,
            standard_period_return=settings.ai_enable_standard_period_return,
            catalog_discovery_v2=settings.ai_enable_catalog_discovery_v2,
        )
        auditor = RunAuditor(sandbox, settings.research_audit_database_url) \
            if sandbox is not None or settings.research_audit_database_url else None
        summary = None
        if settings.ai_catalog_summary_in_prompt and catalog is not None:
            summary = CatalogSummary(
                CatalogTools(catalog), registry.names, settings.ai_catalog_summary_ttl_seconds,
                on_refresh=lambda **fields: log_event("ai_catalog_summary_refreshed", **fields))
            # built in the background at startup; a request arriving before it is ready runs without a summary
            threading.Thread(target=summary.text, name="catalog-summary", daemon=True).start()
        provider_logger = ProviderLogger(owned_client) if settings.ai_log_provider else None
        # (request_id, session_ids): the sessions a run leaves open are closed when it ends (S05)
        closer = partial(close_sessions, sandbox) if sandbox is not None and settings.ai_enable_dataneed else None
        orchestrator = AgentOrchestrator(settings, owned_client, registry, auditor=auditor,
                                         catalog_summary=summary, provider_logger=provider_logger,
                                         session_closer=closer)
    ready = {"value": False}

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if upkeep is not None:
            upkeep.start()  # releases lapsed leases and deletes expired conversations, then hourly
        ready["value"] = True
        yield
        ready["value"] = False
        if upkeep is not None:
            upkeep.stop()
        close = getattr(orchestrator, "close", None)
        if callable(close):
            close()
        orchestrator.registry.close()
        if owned_client is not None:
            owned_client.close()

    app = FastAPI(
        title="Saniti Market AI Orchestrator", version="0.2.0",
        docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan,
    )
    app.state.orchestrator = orchestrator
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

    def refuse(error: ConversationError) -> JSONResponse:
        return JSONResponse(status_code=error.http_status,
                            content={"detail": {"code": error.code, "message": error.message}})

    @app.post("/v1/agent/run", response_model=AgentRunResponse, dependencies=[Depends(authorize)])
    def run_agent(payload: AgentRunRequest,
                  x_saniti_owner: str | None = Header(default=None)) -> AgentRunResponse | JSONResponse:
        if payload.history_mode == "CLIENT":
            return orchestrator.run(payload)
        try:
            if conversations is None:
                raise ConversationError("HISTORY_MODE_UNAVAILABLE", "history_mode SERVER needs "
                                        "AI_ENABLE_CONVERSATION_STORE; send the history with history_mode CLIENT.", 400)
            if payload.history:
                raise ConversationError("HISTORY_SOURCE_CONFLICT", "history_mode SERVER keeps the history itself; "
                                        "send only the new message.", 400)
            owner = owner_from_header(x_saniti_owner)
            start = conversations.begin(owner, payload, fingerprint(payload))
        except ConversationError as error:
            return refuse(error)
        if start.replay is not None:
            return JSONResponse(content={**start.replay, "conversation": {
                "conversation_id": start.conversation_id, "turn_index": start.turn_index, "persistence": "SAVED",
                "replayed": True}})
        request = payload.model_copy(update={"conversation_id": start.conversation_id, "history": start.history})
        try:
            result = orchestrator.run(request)
        except Exception:
            conversations.abandon(start, payload.request_id, "INTERNAL_ERROR")
            raise
        saved = conversations.finish(start, payload.request_id, result)
        return JSONResponse(content={**result.model_dump(mode="json"), "conversation": {
            "conversation_id": start.conversation_id, "turn_index": start.turn_index,
            "persistence": "SAVED" if saved else "NOT_SAVED", "replayed": False}})

    @app.get("/v1/conversations/{conversation_id}/messages", dependencies=[Depends(authorize)])
    def conversation_messages(conversation_id: str, after: int | None = None, limit: int | None = None,
                              x_saniti_owner: str | None = Header(default=None)) -> JSONResponse:
        try:
            if conversations is None:
                raise ConversationError("HISTORY_MODE_UNAVAILABLE", "The conversation store is not enabled.", 404)
            return JSONResponse(content=conversations.messages(owner_from_header(x_saniti_owner), conversation_id,
                                                               after, limit))
        except ConversationError as error:
            return refuse(error)

    return app
