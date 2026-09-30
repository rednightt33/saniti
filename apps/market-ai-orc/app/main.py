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
from .conversation_plans import summary as plan_summary
from .conversations import (ConversationError, ConversationStore, UpkeepThread, fingerprint, owner_from_header,
                            reuse_key)
from .openrouter_client import OpenRouterClient
from .audit import RunAuditor
from .audit_outbox import AuditOutbox
from .mode4 import Mode4Orchestrator
from .modes import MODES, effective_default, path_for, resolve_mode
from .orchestrator import AgentOrchestrator, log_event
from .provider_log import ProviderLogger
from .research_plan_v2 import library_problem, negotiate
from .schemas import AgentRunRequest, AgentRunResponse, ModeExecution
from .tools import build_default_registry
from .tools.analysis import SandboxClient
from .tools.catalog import CatalogTools
from .tools.library import read_research_library
from .tools.registry import ToolError
from .tools.request_data import GovernorClient
from .tools.session import close_sessions

REUSE_VERSION = 1  # the conversation reuse contract both services must report
FEASIBILITY_VERSION = 1  # the Research Plan feasibility endpoints of the sandbox
POINT_IN_TIME_VERSION = 1
RESAMPLE_SEMANTICS_VERSION = 1  # market-python-sandbox runtime/saniti_session.py  # the sandbox's data_need_spec/v2 time_basis checks (IP1 Stage D)


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


def _with_research_library(multi_angle: dict, catalog: CatalogStore | None) -> tuple[dict | None, str | None]:
    if catalog is None:
        return None, "no catalog database (CATALOG_DATABASE_URL) to read the research library AI_research_library"
    try:
        rows = read_research_library(catalog)
    except ToolError as exc:
        return None, f"the research library AI_research_library could not be read: {exc}"
    problem = library_problem(rows)
    if problem is not None:
        return None, problem
    return {**multi_angle, "library": rows}, None


def create_app(
    settings: Settings | None = None,
    orchestrator: AgentOrchestrator | None = None,
    conversations: ConversationStore | None = None,
) -> FastAPI:
    """App factory; uvicorn runs it with --factory so config is validated at startup, not import."""
    _configure_logging()
    settings = settings or Settings.from_env()
    log_event("ai_model_selected", switch=settings.ai_model_switch, model=settings.ai_model,
              reasoning=settings.reasoning(settings.ai_reasoning_effort),
              max_output_tokens=settings.ai_max_output_tokens)
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
        # Research Plan feasibility needs both services' endpoints: the sandbox reports the capability (fail closed)
        feasibility = False
        if settings.ai_enable_plan_feasibility and settings.ai_require_research_plan_confirmation \
                and settings.ai_enable_dataneed and sandbox is not None and governor is not None:
            capability = (sandbox.runtime().get("plan_feasibility") or {})
            feasibility = capability.get("enabled") is True and capability.get("version") == FEASIBILITY_VERSION
            if not feasibility:
                log_event("plan_feasibility_inactive", reason="the sandbox does not report plan_feasibility "
                                                              f"version {FEASIBILITY_VERSION}")
        composite = False
        if settings.ai_enable_composite_keys and settings.ai_enable_dataneed and sandbox is not None:
            versions = sandbox.runtime().get("data_need_spec_versions") or []
            composite = "data_need_spec/v2" in versions
            if not composite:
                log_event("composite_keys_inactive", reason="the sandbox does not accept data_need_spec/v2")
        # IP1 Stage D: time_basis is a data_need_spec/v2 field, checked by the sandbox (fail closed)
        point_in_time = False
        if settings.ai_enable_point_in_time:
            capability = (sandbox.runtime().get("point_in_time") or {}) if composite and sandbox is not None else {}
            point_in_time = capability.get("enabled") is True and capability.get("version") == POINT_IN_TIME_VERSION
            if not point_in_time:
                log_event("point_in_time_inactive", reason="needs AI_ENABLE_COMPOSITE_KEYS (data_need_spec/v2) and a "
                                                           f"sandbox reporting point_in_time version "
                                                           f"{POINT_IN_TIME_VERSION}")
        # IP2 solution 1: weekly/monthly semantics live in the sandbox (resample semantics version 1)
        derived_frequency = False
        if settings.ai_enable_derived_frequency:
            capability = (sandbox.runtime().get("derived_frequency") or {}) if sandbox is not None else {}
            derived_frequency = capability.get("enabled") is True \
                and capability.get("version") == RESAMPLE_SEMANTICS_VERSION and settings.ai_enable_dataneed
            if not derived_frequency:
                log_event("derived_frequency_inactive", reason="needs AI_ENABLE_DATANEED and a sandbox reporting "
                                                               f"derived_frequency version {RESAMPLE_SEMANTICS_VERSION}")
        # research findings v1: the sandbox judges the sample and the verdict (needs the DataNeed flow and Research
        # Plan confirmation, whose plan declares the values)
        research_findings = False
        if settings.ai_enable_research_findings:
            capability = (sandbox.runtime().get("research_findings") or {}) if sandbox is not None else {}
            research_findings = capability.get("enabled") is True and capability.get("version") == 1 \
                and settings.ai_enable_dataneed and settings.ai_require_research_plan_confirmation
            if not research_findings:
                log_event("research_findings_inactive", reason="needs AI_ENABLE_DATANEED, "
                                                               "AI_REQUIRE_RESEARCH_PLAN_CONFIRMATION and a sandbox "
                                                               "reporting research_findings version 1")
        # Multi-Angle Research: both services must agree on the method registry and the grouped-execution contract
        multi_angle = None
        if settings.ai_enable_multi_angle_research:
            multi_angle, reason = negotiate(
                (sandbox.runtime().get("multi_angle_research") or {}) if sandbox is not None else None,
                min_angles=settings.ai_research_min_angles, max_angles=settings.ai_research_max_angles,
                max_groups=settings.ai_research_max_bundle_groups, feasibility=feasibility, composite=composite,
                min_families=settings.ai_research_min_families)
            if multi_angle is not None:
                # C07: the model reads the methods from AI_research_library; the table, the sandbox and this service
                # must carry the same research library, or multi-angle research stays inactive (fail closed)
                multi_angle, reason = _with_research_library(multi_angle, catalog)
            if multi_angle is not None:
                multi_angle = {**multi_angle, "max_session_restarts": settings.ai_research_max_session_restarts}
            if multi_angle is None:
                if "library" in (reason or ""):
                    log_event("research_library_mismatch", reason=reason)
                log_event("multi_angle_research_inactive", reason=reason)
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
            plan_feasibility=feasibility,
            composite_keys=composite,
            point_in_time=point_in_time,
            research_findings=research_findings,
            preflight_parts=settings.ai_enable_preflight_parts,
            multi_angle=multi_angle,
        )
        auditor = RunAuditor(sandbox, settings.research_audit_database_url) \
            if sandbox is not None or settings.research_audit_database_url else None
        # IP2: AI_research_run_audit stays the summary; the outbox hands the full run to market-audit-store
        audit_outbox = AuditOutbox(settings.audit_outbox_database_url) \
            if settings.ai_audit_store_enabled and settings.audit_outbox_database_url else None
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
        resources = None
        if settings.ai_enable_conversation_reuse and sandbox is not None and settings.ai_enable_dataneed:
            # both services must have reuse on, at the same version; otherwise reuse stays off (fail closed)
            capability = (sandbox.runtime().get("conversation_reuse") or {})
            if capability.get("enabled") is True and capability.get("version") == REUSE_VERSION:
                resources = sandbox.conversation_resources
            else:
                log_event("conversation_reuse_inactive", reason="the sandbox does not report conversation_reuse "
                                                                f"version {REUSE_VERSION}")
        orchestrator = AgentOrchestrator(settings, owned_client, registry, auditor=auditor,
                                         catalog_summary=summary, provider_logger=provider_logger,
                                         session_closer=closer, conversation_resources=resources,
                                         draft_reader=sandbox.get_draft if feasibility else None,
                                         derived_frequency=derived_frequency, audit_outbox=audit_outbox)
    if settings.ai_enable_mode4 and isinstance(orchestrator, AgentOrchestrator):
        # mode 4 builds on the caller-chosen paths and on Multi-Angle Research (its plans are research_plan/v2)
        if orchestrator.analysis_path and orchestrator.multi_angle:
            orchestrator = Mode4Orchestrator(orchestrator)
            log_event("mode4_active", max_seconds=settings.ai_mode4_max_seconds,
                      sandbox_min_angles=orchestrator.sandbox_min)
        else:
            log_event("mode4_inactive", reason="needs AI_ENABLE_ANALYSIS_PATH and an active Multi-Angle Research")
    # mode switcher (app/modes.py): AI_MODE_SWITCH, or AUTO when this deployment cannot run that mode
    default_mode = effective_default(settings.ai_mode_switch, orchestrator)
    log_event("ai_mode_selected", switch=settings.ai_mode_switch, name=MODES[settings.ai_mode_switch],
              effective=default_mode, effective_name=MODES[default_mode])
    if default_mode != settings.ai_mode_switch:
        log_event("mode_switch_fallback", switch=settings.ai_mode_switch, effective=default_mode,
                  reason="the mode is not active on this deployment (see analysis_path_inactive / mode4_inactive)")
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

    def routed(request: AgentRunRequest, continuation: object) -> tuple[AgentRunRequest, ModeExecution]:
        """The request with the analysis_path of its mode (AUTO: none) and the mode record for execution.mode."""
        number, source = resolve_mode(request.analysis_path, continuation, default_mode)
        if source == "SWITCH" and default_mode != settings.ai_mode_switch:
            source = "FALLBACK"
        if number == 4 and not getattr(orchestrator, "mode4", False):  # a mode 4 plan after mode 4 was turned off
            number, source = 1, "FALLBACK"
        return (request.model_copy(update={"analysis_path": path_for(number)}),
                ModeExecution(mode=number, name=MODES[number], source=source))

    def with_mode(result: AgentRunResponse, mode: ModeExecution) -> AgentRunResponse:
        return result.model_copy(update={"execution": result.execution.model_copy(update={"mode": mode})})

    @app.post("/v1/agent/run", response_model=AgentRunResponse, dependencies=[Depends(authorize)])
    def run_agent(payload: AgentRunRequest,
                  x_saniti_owner: str | None = Header(default=None)) -> AgentRunResponse | JSONResponse:
        if payload.analysis_path not in (None, "AUTO"):
            if not getattr(orchestrator, "analysis_path", False):
                return refuse(ConversationError("ANALYSIS_PATH_UNAVAILABLE", "analysis_path needs "
                                                "AI_ENABLE_ANALYSIS_PATH (with the DataNeed flow and Research Plan "
                                                "confirmation); send it as null.", 400))
            if payload.analysis_path == "MODE4" and not getattr(orchestrator, "mode4", False):
                return refuse(ConversationError("MODE4_UNAVAILABLE", "analysis_path MODE4 needs AI_ENABLE_MODE4 (with "
                                                "the caller-chosen paths and Multi-Angle Research); send it as "
                                                "null.", 400))
            if payload.analysis_path == "ANALYSIS" and (payload.continuation is not None
                                                        or payload.plan_reply is not None):
                return refuse(ConversationError("ANALYSIS_PATH_CONFLICT", "analysis_path ANALYSIS cannot reply to a "
                                                "Research Plan; send the reply without it.", 400))
        if payload.history_mode == "CLIENT":
            if payload.plan_reply is not None:
                return refuse(ConversationError("PLAN_REPLY_NEEDS_SERVER_MODE", "plan_reply is for history_mode "
                                                "SERVER; with CLIENT send the continuation of the plan.", 400))
            request, mode = routed(payload, payload.continuation)
            return with_mode(orchestrator.run(request), mode)
        try:
            if conversations is None:
                raise ConversationError("HISTORY_MODE_UNAVAILABLE", "history_mode SERVER needs "
                                        "AI_ENABLE_CONVERSATION_STORE; send the history with history_mode CLIENT.", 400)
            if payload.history:
                raise ConversationError("HISTORY_SOURCE_CONFLICT", "history_mode SERVER keeps the history itself; "
                                        "send only the new message.", 400)
            if payload.continuation is not None:
                raise ConversationError("CONTINUATION_SOURCE_CONFLICT", "history_mode SERVER keeps the Research "
                                        "Plan itself; reply with the message, or with plan_reply for an explicit "
                                        "APPROVE, REVISE or CANCEL.", 400)
            owner = owner_from_header(x_saniti_owner)
            start = conversations.begin(owner, payload, fingerprint(payload))
        except ConversationError as error:
            return refuse(error)
        if start.replay is not None:
            return JSONResponse(content={**start.replay, "conversation": {
                "conversation_id": start.conversation_id, "turn_index": start.turn_index, "persistence": "SAVED",
                "replayed": True, "research_plan": plan_summary(start.state)}})
        request, mode = routed(payload.model_copy(update={"conversation_id": start.conversation_id,
                                                          "history": start.history,
                                                          "continuation": start.continuation}), start.continuation)
        try:
            if getattr(orchestrator, "conversation_reuse", False):
                result = orchestrator.run(request, conversation_key=reuse_key(owner, start.conversation_id))
            else:
                result = orchestrator.run(request)
        except Exception:
            conversations.abandon(start, payload.request_id, "INTERNAL_ERROR")
            raise
        result = with_mode(result, mode)
        saved = conversations.finish(start, payload.request_id, result)
        return JSONResponse(content={**result.model_dump(mode="json"), "conversation": {
            "conversation_id": start.conversation_id, "turn_index": start.turn_index,
            "persistence": "SAVED" if saved else "NOT_SAVED", "replayed": False,
            "research_plan": plan_summary(start.state)}})

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
