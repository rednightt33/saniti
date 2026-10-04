from __future__ import annotations

import hashlib
import hmac
import logging
import re
import sys
import threading
import time
from contextlib import asynccontextmanager
from functools import partial

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import JSONResponse, StreamingResponse

from .catalog_store import CatalogStore
from .catalog_summary import CatalogSummary
from .config import Settings
from .conversation_plans import DATA_RECORD_KEY
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
from .provider_policy import CachePricePolicy
from .research_plan_v2 import library_problem, negotiate
from .schemas import AgentRunRequest, AgentRunResponse, ModeExecution
from .tools import build_default_registry
from .tools.analysis import SandboxClient
from .tools.catalog import CatalogTools
from .tools.library import read_research_library
from .tools.method_guides import active_guides, guides_problem, menu as guide_menu, read_method_guides
from .tools.registry import ToolError
from .tools.request_data import GovernorClient
from .result_store import ResultBucket, ResultStore
from .tools.session import (EVENT_STUDY_VERSION, RESULT_STORE_VERSION, SESSION_RELEASE_VERSION, close_sessions,
                            output_file, release_request, restore_carried)
from .tools.artifacts import STORED_TABLES_VERSION, read_output_any
from .tools.lineage import BUNDLE_LINEAGE_VERSION
from .tools.metric import read_metrics

REUSE_VERSION = 1  # the conversation reuse contract both services must report
EXPORT_ID_RE = re.compile(r"^exp_[0-9a-f]{24}$")
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


def _method_guides(sandbox: SandboxClient | None, catalog: CatalogStore | None, *, dataneed: bool,
                   event_study: bool, hypothesis_plan: bool, multi_angle: bool,
                   period_return: bool) -> tuple[dict | None, str | None]:
    """4b: the guides of the methods this deployment offers, when AI_method_guide, the sandbox and this service carry
    the same guides (fail closed)."""
    if catalog is None or sandbox is None:
        return None, "needs the catalog database and the sandbox"
    try:
        rows = read_method_guides(catalog)
    except ToolError as exc:
        return None, f"AI_method_guide could not be read: {exc}"
    problem = guides_problem(rows, sandbox.runtime().get("method_guides"))
    if problem is not None:
        return None, problem
    names = active_guides(dataneed=dataneed, event_study=event_study, hypothesis_plan=hypothesis_plan,
                          multi_angle=multi_angle, period_return=period_return)
    return ({"names": names, "menu": guide_menu(names)} if names else None), "no method is offered"


def _bundle_limits(sandbox: SandboxClient) -> dict | None:
    """G14: bundle_max_rows / bundle_max_bytes / bundle_max_parts from the sandbox's runtime limits (older sandboxes
    report them only under multi_angle_research); None leaves the size check to the sandbox."""
    runtime = sandbox.runtime()
    keys = ("bundle_max_rows", "bundle_max_bytes", "bundle_max_parts")
    for source in (runtime.get("limits") or {}, (runtime.get("multi_angle_research") or {}).get("limits") or {}):
        limits = {k: source[k] for k in keys if isinstance(source.get(k), int)}
        if limits.get("bundle_max_rows"):
            return limits
    log_event("bundle_limits_unknown", reason="the sandbox runtime reports no bundle_max_rows")
    return None


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
              max_output_tokens=settings.ai_max_output_tokens, capture_reasoning=settings.ai_capture_reasoning,
              event_study=settings.ai_enable_event_study, hypothesis_plan=settings.ai_enable_hypothesis_plan)
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
        # G14: the sandbox's bundle limits, so the planners check a bundle's size before extracting it
        bundle_limits = _bundle_limits(sandbox) if sandbox is not None and settings.ai_enable_dataneed else None
        # G2: the event study is described only when the sandbox runs it (fail closed)
        event_study = False
        if settings.ai_enable_event_study:
            capability = (sandbox.runtime().get("event_study") or {}) if sandbox is not None else {}
            event_study = capability.get("enabled") is True and capability.get("version") == EVENT_STUDY_VERSION \
                and settings.ai_enable_dataneed
            if not event_study:
                log_event("event_study_inactive", reason="needs AI_ENABLE_DATANEED and a sandbox reporting "
                                                         f"event_study version {EVENT_STUDY_VERSION}")
        multi_angle_active = multi_angle is not None and feasibility and composite
        hypothesis_plan = settings.ai_enable_hypothesis_plan and research_findings
        method_guides = None
        if settings.ai_enable_method_guides:
            method_guides, reason = _method_guides(
                sandbox, catalog, dataneed=settings.ai_enable_dataneed, event_study=event_study,
                hypothesis_plan=(hypothesis_plan if multi_angle_active else research_findings),
                multi_angle=multi_angle_active, period_return=settings.ai_enable_standard_period_return)
            if method_guides is None:
                log_event("method_guides_inactive", reason=reason)
        metrics = None
        if settings.ai_enable_query_metric:
            # D5: the active metrics of AI_metric_catalog, read once; none (or no Governor): off (fail closed)
            try:
                metrics = read_metrics(catalog) if catalog is not None and governor is not None else None
            except Exception as exc:  # noqa: BLE001 - the tool stays off; the reason is logged
                log_event("query_metric_inactive", reason=f"AI_metric_catalog unreadable ({type(exc).__name__})")
                metrics = None
            if metrics:
                log_event("query_metric_active", metrics=[m["metric_id"] for m in metrics])
            else:
                log_event("query_metric_inactive", reason="needs the catalog, the Governor and an active metric")
        export = False
        if settings.ai_enable_export:
            # D4: the sandbox writes the file (stored_tables v1); the result store is checked below
            capability = (sandbox.runtime().get("stored_tables") or {}) if sandbox is not None else {}
            export = settings.ai_enable_dataneed and capability.get("enabled") is True \
                and capability.get("version") == STORED_TABLES_VERSION
            if not export:
                log_event("export_inactive", reason="needs AI_ENABLE_DATANEED and a sandbox reporting stored_tables "
                                                    f"version {STORED_TABLES_VERSION}")
        evidence = False
        if settings.ai_enable_evidence:
            # D6: tier 2 recounts a released table in the sandbox (stored_tables v1); the result store is checked below
            capability = (sandbox.runtime().get("stored_tables") or {}) if sandbox is not None else {}
            evidence = settings.ai_enable_dataneed and governor is not None and capability.get("enabled") is True \
                and capability.get("version") == STORED_TABLES_VERSION
            if not evidence:
                log_event("evidence_inactive", reason="needs AI_ENABLE_DATANEED, the Governor and a sandbox reporting "
                                                      f"stored_tables version {STORED_TABLES_VERSION}")
        lineage_tool = False
        if settings.ai_enable_lineage_tool:
            # D3: the sandbox must serve GET /v1/bundles/{id}/lineage (bundle_lineage v1); otherwise off (fail closed)
            capability = (sandbox.runtime().get("bundle_lineage") or {}) if sandbox is not None else {}
            lineage_tool = settings.ai_enable_dataneed and capability.get("enabled") is True \
                and capability.get("version") == BUNDLE_LINEAGE_VERSION
            if not lineage_tool:
                log_event("lineage_tool_inactive", reason="needs AI_ENABLE_DATANEED and a sandbox reporting "
                                                          f"bundle_lineage version {BUNDLE_LINEAGE_VERSION}")
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
            event_study=event_study,
            hypothesis_plan=hypothesis_plan,
            method_guides=method_guides,
            catalog_discovery_v2=settings.ai_enable_catalog_discovery_v2,
            plan_feasibility=feasibility,
            composite_keys=composite,
            point_in_time=point_in_time,
            research_findings=research_findings,
            preflight_parts=settings.ai_enable_preflight_parts,
            planner_parallel_parts=settings.ai_planner_parallel_parts,
            multi_angle=multi_angle,
            bundle_limits=bundle_limits,
            lineage_tool=lineage_tool,
            export=export,
            metrics=metrics or None,
            evidence=evidence,
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
        provider_policy = None
        if settings.ai_provider_max_cache_price_ratio is not None:
            provider_policy = CachePricePolicy(owned_client, settings.ai_model,
                                               settings.ai_provider_max_cache_price_ratio,
                                               ttl_seconds=settings.ai_provider_policy_ttl_seconds, log=log_event)
            provider_policy.start()
        # (request_id, session_ids): the sessions a run leaves open are closed when it ends (S05)
        closer = partial(close_sessions, sandbox) if sandbox is not None and settings.ai_enable_dataneed else None
        # S28: (request_id) -> the answer's end releases every session of the request; fail closed to the closer
        releaser = None
        if closer is not None:
            capability = sandbox.runtime().get("session_release") or {}
            if capability.get("enabled") is True and capability.get("version") == SESSION_RELEASE_VERSION:
                releaser = partial(release_request, sandbox)
                sandbox.open_wait_seconds = int(capability.get("open_wait_seconds") or 0)
            else:
                log_event("session_release_inactive", reason="the sandbox does not report session_release "
                                                             f"version {SESSION_RELEASE_VERSION}")
        # (session_id, output_id, request_id, offset, limit): rows of a released output an answer references (M44)
        # D2: the sandbox's copy, else the conversation's stored copy (when the run has a results context)
        row_reader = partial(read_output_any, sandbox) if sandbox is not None and settings.ai_enable_dataneed else None
        resources = None
        if settings.ai_enable_conversation_reuse and sandbox is not None and settings.ai_enable_dataneed:
            # both services must have reuse on, at the same version; otherwise reuse stays off (fail closed)
            capability = (sandbox.runtime().get("conversation_reuse") or {})
            if capability.get("enabled") is True and capability.get("version") == REUSE_VERSION:
                resources = sandbox.conversation_resources
            else:
                log_event("conversation_reuse_inactive", reason="the sandbox does not report conversation_reuse "
                                                                f"version {REUSE_VERSION}")
        # R-STORE (round 2026-10-03 C2): the conversation keeps its results when the sandbox can copy a released file
        # out and take a stored table back (result_store v1) and conversation reuse is on; otherwise off (fail closed)
        result_store, fetcher, uploader = None, None, None
        if settings.ai_enable_result_store and resources is not None and conversations is not None:
            capability = sandbox.runtime().get("result_store") or {}
            if capability.get("enabled") is True and capability.get("version") == RESULT_STORE_VERSION:
                bucket = ResultBucket(**settings.result_bucket) if settings.result_bucket else None
                result_store = ResultStore(settings.conversation_database_url, bucket)
                fetcher = lambda sid, oid, rid: output_file(sandbox, sid, oid, rid)  # noqa: E731
                uploader = lambda sid, rid, meta, data: restore_carried(sandbox, sid, rid, meta, data)  # noqa: E731
                if bucket is not None:
                    conversations.before_delete = lambda ids: bucket.delete(result_store.object_keys(ids))
                log_event("result_store_active", bucket=bucket is not None)
            else:
                log_event("result_store_inactive", reason="the sandbox does not report result_store version "
                                                          f"{RESULT_STORE_VERSION}")
        elif settings.ai_enable_result_store:
            log_event("result_store_inactive", reason="needs conversation reuse, the conversation store and the sandbox")
        if result_store is None and registry.disable("export_result"):
            log_event("export_inactive", reason="exports are kept with the conversation: the result store is inactive")
        if result_store is None and registry.disable("get_evidence"):
            log_event("evidence_inactive", reason="evidence is kept with the conversation: the result store is inactive")
        orchestrator = AgentOrchestrator(settings, owned_client, registry, auditor=auditor,
                                         catalog_summary=summary, provider_logger=provider_logger,
                                         provider_policy=provider_policy,
                                         session_closer=closer, session_releaser=releaser,
                                         result_store=result_store, output_fetcher=fetcher,
                                         carried_uploader=uploader,
                                         conversation_resources=resources,
                                         draft_reader=sandbox.get_draft if feasibility else None,
                                         derived_frequency=derived_frequency, audit_outbox=audit_outbox,
                                         row_reader=row_reader)
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
            # M47: the conversation's data record from earlier turns (AI_conversation.state)
            record = (start.state or {}).get(DATA_RECORD_KEY)
            extra = {"data_record": record} if record else {}
            if getattr(orchestrator, "conversation_reuse", False):
                result = orchestrator.run(request, conversation_key=reuse_key(owner, start.conversation_id), **extra)
            else:
                result = orchestrator.run(request, **extra)
        except Exception:
            conversations.abandon(start, payload.request_id, "INTERNAL_ERROR")
            raise
        result = with_mode(result, mode)
        saved = conversations.finish(start, payload.request_id, result)
        return JSONResponse(content={**result.model_dump(mode="json"), "conversation": {
            "conversation_id": start.conversation_id, "turn_index": start.turn_index,
            "persistence": "SAVED" if saved else "NOT_SAVED", "replayed": False,
            "research_plan": plan_summary(start.state)}})

    @app.get("/v1/exports/{export_id}/download", dependencies=[Depends(authorize)])
    def download_export(export_id: str, x_saniti_owner: str | None = Header(default=None)) -> Any:
        """D4: an exported file of one of the owner's conversations, streamed from Postgres in 1 MB chunks."""
        store = getattr(orchestrator, "result_store", None)
        try:
            owner = owner_from_header(x_saniti_owner)
        except ConversationError as error:
            return refuse(error)
        found = store.owned_export(owner, export_id) \
            if store is not None and EXPORT_ID_RE.fullmatch(export_id) else None
        if found is None:
            return JSONResponse(status_code=404, content={"detail": {"code": "EXPORT_NOT_FOUND",
                                                                     "message": "No such export for this owner."}})
        return StreamingResponse(store.export_chunks(found["conversation_id"], export_id),
                                 media_type=found["mime_type"], headers={
                                     "Content-Disposition": f'attachment; filename="{found["file_name"]}"',
                                     "Content-Length": str(found["size_bytes"]),
                                     "X-Saniti-Sha256": found["sha256"]})

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
