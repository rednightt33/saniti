from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import logging
import re
import sys
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import ValidationError

from .config import Settings
from .bundles import BUNDLE_ID
from .dataneed_service import DataNeedError, DataNeedService
from .backtest_validation import BACKTEST_VERSION
from .event_study_validation import EVENT_STUDY_VERSION
from .method_guides import GUIDES_SHA256, GUIDES_VERSION
from .data_need import SPEC_VERSIONS
from .sessions import RESTORE_VERSION, SESSION_RELEASE_VERSION, SessionError
from . import stored_tables
from .dataneed_store import DataNeedStore
from .models import ANALYSIS_ID, REQUEST_ID, AnalysisRequest, RunReport
from .outputs import CONTENT_TYPES
from .service import AnalysisService, ServiceUnavailable
from .spec import SPEC_ID
from .spec_v2 import SpecRequestAny

FILE_ID = re.compile(r"^(res|art)_[0-9a-f]{24}$")
NEED_ID = re.compile(r"^need_[0-9a-f]{24}$")
DRAFT_ID = re.compile(r"^draft_[0-9a-f]{24}$")
FEASIBILITY_VERSION = 1
# IP1 Stage D: data_need_spec/v2 time_basis (HISTORICAL_DESCRIPTIVE / POINT_IN_TIME) and its refusals
POINT_IN_TIME_VERSION = 1
RESAMPLE_SEMANTICS_VERSION = 1  # runtime/saniti_session.py; app/data_need.py
RESEARCH_FINDINGS_VERSION = 1  # runtime/research_stats.py VERSION; app/research_findings.py
MULTI_ANGLE_VERSION = 2  # research_plan/v2, research_governance/v2, research_findings/v2 (MULTI_ANGLE_RESEARCH.md)
RESEARCH_RUN_ID = re.compile(r"^rrun_[0-9a-f]{24}$")
GROUP_ID = re.compile(r"^g[1-9][0-9]?$")
SESSION_ID = re.compile(r"^sess_[0-9a-f]{24}$")
OUTPUT_ID = re.compile(r"^out_[0-9a-f]{24}$")
def as_of_date(body: dict) -> Any:
    """R-STORE (round 2026-10-03 C2e): the conversation's data date; a range ending LATEST is bound to it when it is
    earlier than the reference date. None when absent, False when malformed."""
    value = body.get("as_of_date")
    if value is None:
        return None
    try:
        return date.fromisoformat(value) if isinstance(value, str) and len(value) == 10 else False
    except ValueError:
        return False


DATA_NEED_KEYS = {"request_id", "reference_time", "timezone", "spec", "research_governance", "as_of_date"}
# Conversation reuse (S1/S2): market-ai-orc derives the key from the conversation and its owner and sends it as a
# header, never from the model. Ignored while PY_SANDBOX_ENABLE_CONVERSATION_REUSE is off.
CONVERSATION_HEADER = "X-Saniti-Conversation-Key"
CONVERSATION_KEY = re.compile(r"^ck_[0-9a-f]{32}$")
REUSE_VERSION = 1
PAGE_MAX = 500


def _configure_logging() -> None:
    logger = logging.getLogger("market_python_sandbox")
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False


def create_app(settings: Settings | None = None, service: AnalysisService | None = None,
               run_workers: bool = True, dataneed: DataNeedService | None = None) -> FastAPI:
    """Private analysis service for market-ai-orc. No public domain, no docs routes."""
    _configure_logging()
    settings = settings or Settings.from_env()
    service = service or AnalysisService(settings)
    if dataneed is None and settings.dataneed_enabled:
        # created only when the flow is enabled: with the flag off the service has no DataNeed state at all
        dataneed = DataNeedService(service, DataNeedStore(Path(settings.data_dir) / "dataneed.sqlite3"))

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        service.start(run_workers=run_workers)
        if dataneed is not None:
            dataneed.start(run_janitor=run_workers)
        yield
        if dataneed is not None:
            dataneed.stop()
        service.stop()

    app = FastAPI(title="Saniti Market Python Sandbox", version="2.0.0", docs_url=None, redoc_url=None,
                  openapi_url=None, lifespan=lifespan)
    app.state.service = service
    app.state.dataneed = dataneed
    expected = f"Bearer {settings.api_key}"

    def authorize(authorization: str | None = Header(default=None)) -> None:
        if not authorization or not hmac.compare_digest(authorization, expected):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    def unavailable(exc: ServiceUnavailable) -> JSONResponse:
        headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after else None
        return JSONResponse(status_code=exc.http_status, headers=headers, content={
            "status": "REJECTED", "error": {"code": exc.code, "message": exc.message},
            "retry_after_seconds": exc.retry_after})

    def analysis_id_or_404(analysis_id: str) -> str:
        if not re.fullmatch(ANALYSIS_ID, analysis_id):
            raise HTTPException(status_code=404, detail="Unknown analysis_id")
        return analysis_id

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    def ready() -> Any:
        if not service.isolation.ok:
            return JSONResponse(status_code=503, content={"status": "not_ready",
                                                          "reason": "isolation self-test failed"})
        return {"status": "ready"}

    @app.get("/v1/runtime", dependencies=[Depends(authorize)])
    def runtime() -> dict[str, Any]:
        return {"isolation": service.isolation.public(), "versions": service.isolation.versions,
                "network_isolation": "seccomp: socket creation denied in analysis processes (not a network namespace)",
                "duckdb": "locked connection: files only inside the job's input/ and intermediate/ directories, "
                          "no extensions or attachments, configuration locked",
                "conversation_reuse": {"enabled": settings.conversation_reuse and dataneed is not None,
                                       "version": REUSE_VERSION},
                # R-STORE: GET .../outputs/{output_id}/file and POST /v1/sessions/{id}/carried
                "result_store": {"enabled": dataneed is not None and settings.conversation_reuse,
                                 "version": RESTORE_VERSION, "restore_max_bytes": settings.restore_max_bytes},
                # D3 (round 2026-10-03): GET /v1/bundles/{id}/lineage, Governor query ids in new bundle manifests
                "bundle_lineage": {"enabled": dataneed is not None, "version": 1},
                # D0 (round 2026-10-03): POST /v1/stored-tables/{op} on a stored table uploaded by market-ai-orc
                "stored_tables": {"enabled": dataneed is not None, "version": stored_tables.STORED_TABLES_VERSION,
                                  "ops": list(stored_tables.OPS), "max_bytes": settings.restore_max_bytes,
                                  "export_formats": list(stored_tables.EXPORT_FORMATS),
                                  "export_max_bytes": stored_tables.EXPORT_MAX_BYTES},
                # S28: POST /v1/requests/{request_id}/release, and how long opening a session waits for a slot
                "session_release": {"enabled": dataneed is not None, "version": SESSION_RELEASE_VERSION,
                                    "open_wait_seconds": settings.open_wait_seconds},
                # POST /v1/data-needs/check and GET /v1/data-need-drafts/{draft_id} (Research Plan feasibility)
                "plan_feasibility": {"enabled": dataneed is not None, "version": FEASIBILITY_VERSION},
                # IP1 Stage B: data_need_spec/v2 names every key pair of a composite relationship
                "data_need_spec_versions": list(SPEC_VERSIONS) if dataneed is not None else [],
                "point_in_time": {"enabled": dataneed is not None, "version": POINT_IN_TIME_VERSION},
                # IP2 solution 1: weekly/monthly derived from daily rows (resample semantics version)
                "derived_frequency": {"enabled": dataneed is not None and settings.derived_frequency_enabled,
                                      "version": RESAMPLE_SEMANTICS_VERSION},
                # research findings: saniti.event_summary, backend sample category and verdict
                "research_findings": {"enabled": dataneed is not None and settings.research_findings_enabled,
                                      "version": RESEARCH_FINDINGS_VERSION},
                # Multi-Angle Research: 3-6 angles, promoted drafts per bundle group, backend findings per angle
                "multi_angle_research": multi_angle_capability(),
                # G2: saniti.event_study, recomputed by the harness at complete_analysis
                "event_study": {"enabled": dataneed is not None, "version": EVENT_STUDY_VERSION},
                # P32 layer 3: saniti.backtest, re-run by the harness at complete_analysis
                "backtest": {"enabled": dataneed is not None, "version": BACKTEST_VERSION},
                # 4b: the method guides (menu and manual), hash-bound with market-ai-orc and AI_method_guide
                "method_guides": {"enabled": dataneed is not None, "version": GUIDES_VERSION,
                                  "sha256": GUIDES_SHA256},
                "limits": {**settings.child_limits(), "max_runtime_seconds": settings.max_runtime_seconds,
                           "max_memory_mb": settings.max_memory_mb, "duckdb_memory_mb": settings.duckdb_memory_mb,
                           "max_logical_datasets": settings.max_logical_datasets,
                           "max_input_files": settings.max_input_files, "max_input_rows": settings.max_input_rows,
                           "max_input_bytes": settings.max_input_bytes,
                           # G14: the bundle limits every caller checks before extracting (not only multi-angle)
                           "bundle_max_rows": settings.bundle_max_rows, "bundle_max_bytes": settings.bundle_max_bytes,
                           "bundle_max_parts": settings.bundle_max_parts,
                           "max_intermediate_bytes": settings.max_intermediate_bytes,
                           "max_output_dir_bytes": settings.max_output_dir_bytes,
                           "max_code_chars": settings.max_code_chars, "max_output_bytes": settings.max_output_bytes,
                           "result_retention_hours": settings.result_retention_hours,
                           "failed_workspace_ttl_hours": settings.failed_workspace_ttl_hours,
                           "concurrency": settings.concurrency, "max_queued": settings.max_queued,
                           "per_request": {"analyses": settings.max_analyses_per_request,
                                           "cpu_seconds": settings.max_cpu_seconds_per_request,
                                           "input_bytes": settings.max_input_bytes_per_request,
                                           "specs": settings.max_specs_per_request},
                           "validator": {"runtime_seconds": settings.validator_runtime_seconds,
                                         "memory_mb": settings.validator_memory_mb}}}

    def multi_angle_capability() -> dict[str, Any]:
        from .research_library import LIBRARY_SHA256
        from .research_methods import registry

        enabled = dataneed is not None and settings.dataneed_enabled and settings.multi_angle_research_enabled
        policy = settings.multi_angle_policy()
        reg = registry()
        return {"enabled": enabled, "version": MULTI_ANGLE_VERSION, "min_angles": policy.min_angles,
                "max_angles": policy.max_angles_per_plan, "supports_grouped_execution": enabled,
                "findings_version": "research_findings/v2", "governance_version": "research_governance/v2",
                "method_ids": [m["method_id"] for m in reg["methods"]], "method_registry_sha256": reg["sha256"],
                "library_sha256": LIBRARY_SHA256,
                "policy": policy.public(),
                "limits": {"bundle_max_rows": settings.bundle_max_rows, "bundle_max_bytes": settings.bundle_max_bytes,
                           "bundle_max_parts": settings.bundle_max_parts, "max_requests_per_spec": 8,
                           "max_sessions": settings.max_sessions}}

    def invalid(exc: ValidationError, what: str) -> JSONResponse:
        errors = [{"loc": ".".join(str(p) for p in e["loc"]), "msg": e["msg"]} for e in exc.errors()[:15]]
        return JSONResponse(status_code=422, content={"status": "REJECTED", "error": {
            "code": "INVALID_REQUEST", "message": f"The {what} is invalid.", "details": errors}})

    @app.post("/v1/specs", dependencies=[Depends(authorize)])
    def create_spec(body: Any = Body(...)) -> Any:
        """Review a proposed Analysis Spec against the user's messages; an approved spec becomes immutable."""
        try:
            request = SpecRequestAny.model_validate(body)
        except ValidationError as exc:
            return invalid(exc, "analysis spec")
        return service.create_spec(request)

    def dataneed_error(exc: DataNeedError) -> JSONResponse:
        return JSONResponse(status_code=exc.http_status, content=exc.body())

    def dataneed_enabled() -> None:
        # the DataNeed flow ships dark: its routes do not exist until PY_SANDBOX_DATANEED_ENABLED is set
        if not settings.dataneed_enabled or dataneed is None:
            raise HTTPException(status_code=404, detail="Not Found")

    dataneed_routes = [Depends(dataneed_enabled), Depends(authorize)]

    def conversation_key(x_saniti_conversation_key: str | None = Header(default=None)) -> str | None:
        """The caller's conversation key, or None: absent, malformed, or reuse disabled."""
        if not settings.conversation_reuse or not x_saniti_conversation_key:
            return None
        return x_saniti_conversation_key if CONVERSATION_KEY.fullmatch(x_saniti_conversation_key) else None

    @app.post("/v1/data-needs", dependencies=dataneed_routes)
    def submit_data_need(body: Any = Body(...), key: str | None = Depends(conversation_key)) -> Any:
        """Validate a DataNeedSpec revision (and its ResearchGovernanceRequest in mode RESEARCH)."""
        if not isinstance(body, dict) or not {"request_id", "reference_time", "spec"} <= set(body) <= DATA_NEED_KEYS \
                or not isinstance(body["request_id"], str) or not re.fullmatch(REQUEST_ID, body["request_id"]):
            return JSONResponse(status_code=422, content={"status": "REJECTED", "error": {
                "code": "INVALID_REQUEST", "message": "Body must be {request_id, reference_time, timezone, spec, "
                                                      "research_governance}."}})
        try:
            reference_time = datetime.fromisoformat(str(body["reference_time"]))
        except ValueError:
            return JSONResponse(status_code=422, content={"status": "REJECTED", "error": {
                "code": "INVALID_REQUEST", "message": "reference_time must be an ISO timestamp."}})
        timezone = body.get("timezone") if isinstance(body.get("timezone"), str) else "Asia/Jakarta"
        as_of = as_of_date(body)
        if as_of is False:
            return JSONResponse(status_code=422, content={"status": "REJECTED", "error": {
                "code": "INVALID_REQUEST", "message": "as_of_date must be YYYY-MM-DD or null."}})
        try:
            return dataneed.submit(body["request_id"], reference_time, timezone[:64], body["spec"],
                                   body.get("research_governance"), conversation_key=key, as_of=as_of)
        except DataNeedError as exc:
            return dataneed_error(exc)

    @app.post("/v1/data-needs/check", dependencies=dataneed_routes)
    def check_data_need(body: Any = Body(...)) -> Any:
        """Research Plan feasibility: validate a DataNeedSpec into a never-extracted draft (no revision, no review)."""
        if not isinstance(body, dict) or not {"request_id", "reference_time", "spec"} <= set(body) \
                <= {"request_id", "reference_time", "timezone", "spec", "as_of_date"} \
                or not isinstance(body["request_id"], str) or not re.fullmatch(REQUEST_ID, body["request_id"]):
            return JSONResponse(status_code=422, content={"status": "REJECTED", "error": {
                "code": "INVALID_REQUEST", "message": "Body must be {request_id, reference_time, timezone, spec}."}})
        try:
            reference_time = datetime.fromisoformat(str(body["reference_time"]))
        except ValueError:
            return JSONResponse(status_code=422, content={"status": "REJECTED", "error": {
                "code": "INVALID_REQUEST", "message": "reference_time must be an ISO timestamp."}})
        timezone = body.get("timezone") if isinstance(body.get("timezone"), str) else "Asia/Jakarta"
        as_of = as_of_date(body)
        if as_of is False:
            return JSONResponse(status_code=422, content={"status": "REJECTED", "error": {
                "code": "INVALID_REQUEST", "message": "as_of_date must be YYYY-MM-DD or null."}})
        try:
            return dataneed.check(body["request_id"], reference_time, timezone[:64], body["spec"], as_of=as_of)
        except DataNeedError as exc:
            return dataneed_error(exc)

    @app.get("/v1/data-need-drafts/{draft_id}", dependencies=dataneed_routes)
    def get_data_need_draft(draft_id: str) -> Any:
        if not DRAFT_ID.fullmatch(draft_id):
            raise HTTPException(status_code=404, detail="Unknown draft_id")
        draft = dataneed.get_draft(draft_id)
        if draft is None:
            raise HTTPException(status_code=404, detail="Unknown draft_id")
        return draft

    @app.get("/v1/data-needs/{need_id}", dependencies=dataneed_routes)
    def get_data_need(need_id: str) -> Any:
        if not NEED_ID.fullmatch(need_id):
            raise HTTPException(status_code=404, detail="Unknown need_id")
        need = dataneed.get_need(need_id)
        if need is None:
            raise HTTPException(status_code=404, detail="Unknown need_id")
        return need

    @app.post("/v1/bundles", dependencies=dataneed_routes)
    def build_bundle(body: Any = Body(...)) -> Any:
        """Verify, store, profile and cover the extracted parts of an approved need as one governed bundle."""
        if not isinstance(body, dict) or set(body) != {"request_id", "need_id", "plan"} \
                or not isinstance(body["request_id"], str) or not re.fullmatch(REQUEST_ID, body["request_id"]) \
                or not isinstance(body["need_id"], str) or not NEED_ID.fullmatch(body["need_id"]):
            return JSONResponse(status_code=422, content={"status": "REJECTED", "error": {
                "code": "INVALID_REQUEST", "message": "Body must be {request_id, need_id, plan}."}})
        try:
            return dataneed.build_bundle(body["request_id"], body["need_id"], body["plan"])
        except DataNeedError as exc:
            return dataneed_error(exc)

    @app.post("/v1/bundles/reuse", dependencies=dataneed_routes)
    def reuse_bundle(body: Any = Body(...), key: str | None = Depends(conversation_key)) -> Any:
        """Conversation reuse (S1): bind an approved need to an earlier bundle of the conversation with exactly the
        same data contract, or NO_MATCH."""
        if not isinstance(body, dict) or set(body) != {"request_id", "need_id"} \
                or not isinstance(body["request_id"], str) or not re.fullmatch(REQUEST_ID, body["request_id"]) \
                or not isinstance(body["need_id"], str) or not NEED_ID.fullmatch(body["need_id"]):
            return JSONResponse(status_code=422, content={"status": "REJECTED", "error": {
                "code": "INVALID_REQUEST", "message": "Body must be {request_id, need_id}."}})
        try:
            return dataneed.reuse_bundle(body["request_id"], body["need_id"], key)
        except DataNeedError as exc:
            return dataneed_error(exc)

    @app.get("/v1/conversations/{key}/resources", dependencies=dataneed_routes)
    def conversation_resources(key: str) -> Any:
        """What earlier messages of the conversation left for reuse (ids and summaries, no data)."""
        if not CONVERSATION_KEY.fullmatch(key):
            raise HTTPException(status_code=404, detail="Unknown conversation")
        try:
            return dataneed.resources(key)
        except DataNeedError as exc:
            return dataneed_error(exc)

    @app.get("/v1/bundles/{bundle_id}/lineage", dependencies=dataneed_routes)
    def bundle_lineage(bundle_id: str, request_id: str = Query(..., max_length=128),
                       key: str | None = Depends(conversation_key)) -> Any:
        """D3: how the bundle was made (source tables, row filters, ranges, Governor queries); no rows."""
        if not BUNDLE_ID.fullmatch(bundle_id):
            raise HTTPException(status_code=404, detail="Unknown bundle_id")
        try:
            return dataneed.bundle_lineage(bundle_id, request_id, key)
        except DataNeedError as exc:
            return dataneed_error(exc)

    @app.get("/v1/bundles/{bundle_id}", dependencies=dataneed_routes)
    def get_bundle(bundle_id: str) -> Any:
        """The complete bundle manifest with its Data Quality Manifests and delivery coverage (backend and audit)."""
        if not BUNDLE_ID.fullmatch(bundle_id):
            raise HTTPException(status_code=404, detail="Unknown bundle_id")
        bundle = dataneed.get_bundle(bundle_id)
        if bundle is None:
            raise HTTPException(status_code=404, detail="Unknown bundle_id")
        return bundle

    def session_error(exc: SessionError) -> JSONResponse:
        body: dict[str, Any] = {"status": "REJECTED", "error": {"code": exc.code, "message": exc.message,
                                                                 **exc.details}}
        if exc.next_action:
            body["next_action"] = exc.next_action
        headers = {"Retry-After": str(exc.details["retry_after_seconds"])} \
            if exc.details.get("retry_after_seconds") else None
        return JSONResponse(status_code=exc.http_status, content=body, headers=headers)

    def session_body(body: Any, required: set[str], optional: set[str] = frozenset()) -> dict[str, Any] | None:
        if not isinstance(body, dict) or not required <= set(body) <= required | optional \
                or not isinstance(body.get("request_id"), str) or not re.fullmatch(REQUEST_ID, body["request_id"]):
            return None
        return body

    def invalid_body(shape: str) -> JSONResponse:
        return JSONResponse(status_code=422, content={"status": "REJECTED", "error": {
            "code": "INVALID_REQUEST", "message": f"Body must be {shape}."}})

    def session_id_or_404(session_id: str) -> str:
        if not SESSION_ID.fullmatch(session_id):
            raise HTTPException(status_code=404, detail="Unknown session_id")
        return session_id

    @app.post("/v1/sessions", dependencies=dataneed_routes)
    def open_session(body: Any = Body(...), key: str | None = Depends(conversation_key)) -> Any:
        """A persistent analysis session on a READY bundle of the same request."""
        body = session_body(body, {"request_id", "bundle_id"}, {"carried_outputs"})
        if body is None or not isinstance(body["bundle_id"], str) or not BUNDLE_ID.fullmatch(body["bundle_id"]):
            return invalid_body("{request_id, bundle_id, carried_outputs?}")
        carried = body.get("carried_outputs")
        if carried is not None and not (isinstance(carried, list) and len(carried) <= 40
                                        and all(isinstance(o, str) and len(o) <= 64 for o in carried)):
            return invalid_body("{request_id, bundle_id, carried_outputs: [output_id, ...] (at most 40)}")
        try:
            return dataneed.open_session(body["request_id"], body["bundle_id"], conversation_key=key,
                                         carried_outputs=carried)
        except SessionError as exc:
            return session_error(exc)

    @app.post("/v1/sessions/{session_id}/execute", dependencies=dataneed_routes)
    def execute(session_id: str, body: Any = Body(...)) -> Any:
        """Run code in the session's persistent namespace (one execution at a time)."""
        body = session_body(body, {"request_id", "code"})
        if body is None:
            return invalid_body("{request_id, code}")
        try:
            return dataneed.sessions.execute(session_id_or_404(session_id), body["request_id"], body["code"])
        except SessionError as exc:
            return session_error(exc)

    @app.post("/v1/sessions/{session_id}/inspect", dependencies=dataneed_routes)
    def inspect(session_id: str, body: Any = Body(...)) -> Any:
        """Describe session variables (all names, or up to 20 with a bounded preview)."""
        body = session_body(body, {"request_id"}, {"names", "max_rows", "dataset"})
        if body is None:
            return invalid_body("{request_id, names?, max_rows?, dataset?}")
        rows = body.get("max_rows", 5)
        if isinstance(rows, bool) or not isinstance(rows, int):
            return invalid_body("{request_id, names?, max_rows: integer}")
        if body.get("dataset") is not None:
            # D1: the profiler's full column statistics of one dataset of the session's bundle (no rows)
            if not isinstance(body["dataset"], str) or not 0 < len(body["dataset"]) <= 120:
                return invalid_body("{request_id, dataset: a logical name or data_request_id}")
            try:
                return dataneed.sessions.inspect_dataset(session_id_or_404(session_id), body["request_id"],
                                                         body["dataset"])
            except SessionError as exc:
                return session_error(exc)
        try:
            return dataneed.sessions.inspect(session_id_or_404(session_id), body["request_id"], body.get("names"),
                                             rows)
        except SessionError as exc:
            return session_error(exc)

    @app.get("/v1/sessions/{session_id}", dependencies=dataneed_routes)
    def session_state(session_id: str, request_id: str = Query(..., max_length=128)) -> Any:
        try:
            return dataneed.sessions.state(session_id_or_404(session_id), request_id)
        except SessionError as exc:
            return session_error(exc)

    @app.get("/v1/sessions/{session_id}/outputs/{output_id}/file", dependencies=dataneed_routes)
    def session_output_file(session_id: str, output_id: str, request_id: str = Query(..., max_length=128),
                            key: str | None = Depends(conversation_key)) -> Any:
        """R-STORE: the stored file of a released output, for the orchestrator's durable copy."""
        if not OUTPUT_ID.fullmatch(output_id):
            raise HTTPException(status_code=404, detail="Unknown output_id")
        try:
            path, output = dataneed.sessions.output_file(session_id_or_404(session_id), request_id, output_id,
                                                         conversation_key=key)
        except SessionError as exc:
            return session_error(exc)
        return FileResponse(path, media_type="application/octet-stream",
                            headers={"X-Saniti-Checksum-Sha256": output["checksum_sha256"],
                                     "X-Saniti-Format": output["format"]})

    @app.post("/v1/sessions/{session_id}/carried", dependencies=dataneed_routes)
    async def restore_carried(session_id: str, request: Request, request_id: str = Query(..., max_length=128),
                              x_saniti_output_meta: str | None = Header(default=None),
                              key: str | None = Depends(conversation_key)) -> Any:
        """R-STORE: a stored table of this conversation uploaded back into this session (raw Parquet body; its
        metadata as base64url JSON in X-Saniti-Output-Meta)."""
        try:
            meta = json.loads(base64.urlsafe_b64decode((x_saniti_output_meta or "").encode() + b"==="))
            if not isinstance(meta, dict):
                raise ValueError
        except (ValueError, binascii.Error):
            return invalid_body("raw Parquet body with X-Saniti-Output-Meta: base64url JSON {output_id, name, ...}")
        data = await request.body()
        if not data or len(data) > settings.restore_max_bytes:
            return invalid_body(f"a Parquet body of at most {settings.restore_max_bytes} bytes")
        try:
            return await run_in_threadpool(dataneed.sessions.restore_output, session_id_or_404(session_id),
                                           request_id, key, meta, data)
        except SessionError as exc:
            return session_error(exc)

    @app.post("/v1/stored-tables/{op}", dependencies=dataneed_routes)
    async def stored_table(op: str, request: Request, x_saniti_output_meta: str | None = Header(default=None)) -> Any:
        """D0: page, export or recount a stored table without a session. The body is the stored file; its metadata
        (format, checksum_sha256 and the operation's arguments) is base64url JSON in X-Saniti-Output-Meta."""
        if op not in stored_tables.OPS:
            raise HTTPException(status_code=404, detail="Unknown operation")
        try:
            meta = json.loads(base64.urlsafe_b64decode((x_saniti_output_meta or "").encode() + b"==="))
            if not isinstance(meta, dict):
                raise ValueError
        except (ValueError, binascii.Error):
            return invalid_body("the stored file with X-Saniti-Output-Meta: base64url JSON {format, checksum_sha256}")
        data = await request.body()
        if not data or len(data) > settings.restore_max_bytes:
            return invalid_body(f"a file of at most {settings.restore_max_bytes} bytes")
        try:
            if op == "page":
                return await run_in_threadpool(stored_tables.page, data, meta, int(meta.get("offset") or 0),
                                               int(meta.get("limit") or 100))
            if op == "recount":
                return await run_in_threadpool(stored_tables.recount, data, meta)
            body, mime, ext = await run_in_threadpool(stored_tables.export, data, meta)
        except stored_tables.StoredTableError as exc:
            content: dict[str, Any] = {"status": "REJECTED", "error": {"code": exc.code, "message": exc.message,
                                                                        **exc.details}}
            if exc.next_action:
                content["next_action"] = exc.next_action
            return JSONResponse(status_code=exc.http_status, content=content)
        except (ValueError, TypeError, OSError) as exc:  # unreadable file (pyarrow raises ArrowInvalid, a ValueError)
            return JSONResponse(status_code=422, content={"status": "REJECTED", "error": {
                "code": "STORED_TABLE_UNREADABLE", "message": f"The file could not be read: {type(exc).__name__}."}})
        return Response(content=body, media_type=mime, headers={
            "X-Saniti-Checksum-Sha256": hashlib.sha256(body).hexdigest(), "X-Saniti-Extension": ext})

    @app.get("/v1/sessions/{session_id}/outputs/{output_id}", dependencies=dataneed_routes)
    def session_output(session_id: str, output_id: str, request_id: str = Query(..., max_length=128),
                       offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
                       key: str | None = Depends(conversation_key)) -> Any:
        if not OUTPUT_ID.fullmatch(output_id):
            raise HTTPException(status_code=404, detail="Unknown output_id")
        try:
            return dataneed.sessions.read_output(session_id_or_404(session_id), request_id, output_id, offset, limit,
                                                 conversation_key=key)
        except SessionError as exc:
            return session_error(exc)

    @app.post("/v1/sessions/{session_id}/complete", dependencies=dataneed_routes)
    def complete_session(session_id: str, body: Any = Body(...)) -> Any:
        """ExecutionManifest, Coverage Validator and final status; releases the outputs when coverage passes."""
        body = session_body(body, {"request_id"}, {"finalize"})
        if body is None or not isinstance(body.get("finalize", False), bool):
            return invalid_body("{request_id, finalize?}")
        try:
            return dataneed.complete(session_id_or_404(session_id), body["request_id"],
                                     finalize=bool(body.get("finalize", False)))
        except SessionError as exc:
            return session_error(exc)

    @app.post("/v1/research-runs", dependencies=dataneed_routes)
    def promote_research(body: Any = Body(...), key: str | None = Depends(conversation_key)) -> Any:
        """Multi-Angle Research: promote the signed feasibility drafts of an approved research_plan/v2 (one approved
        RESEARCH need per bundle group) after the Research Governor v2 approved its declaration."""
        keys = {"request_id", "origin_request_id", "research_governance", "research_data_plan"}
        if not isinstance(body, dict) or set(body) != keys or not all(
                isinstance(body[k], str) and re.fullmatch(REQUEST_ID, body[k]) for k in ("request_id",
                                                                                         "origin_request_id")):
            return invalid_body("{request_id, origin_request_id, research_governance, research_data_plan}")
        try:
            return dataneed.promote_research(body["request_id"], body["origin_request_id"],
                                             body["research_governance"], body["research_data_plan"],
                                             conversation_key=key)
        except DataNeedError as exc:
            return dataneed_error(exc)

    @app.get("/v1/research-runs/{research_run_id}", dependencies=dataneed_routes)
    def research_run(research_run_id: str, request_id: str = Query(..., max_length=128)) -> Any:
        if not RESEARCH_RUN_ID.fullmatch(research_run_id):
            raise HTTPException(status_code=404, detail="Unknown research_run_id")
        try:
            return dataneed.research_run(request_id, research_run_id)
        except DataNeedError as exc:
            return dataneed_error(exc)

    @app.post("/v1/research-runs/{research_run_id}/groups/{bundle_group_id}/close", dependencies=dataneed_routes)
    def close_research_group(research_run_id: str, bundle_group_id: str, body: Any = Body(...)) -> Any:
        """A bundle group that cannot run: FAILED, and NOT_RUN findings for its angles."""
        if not RESEARCH_RUN_ID.fullmatch(research_run_id) or not GROUP_ID.fullmatch(bundle_group_id):
            raise HTTPException(status_code=404, detail="Unknown research group")
        body = session_body(body, {"request_id", "reason"})
        if body is None or not isinstance(body["reason"], str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{1,59}",
                                                                                    body["reason"]):
            return invalid_body("{request_id, reason: UPPER_CASE_CODE}")
        try:
            return dataneed.close_research_group(body["request_id"], research_run_id, bundle_group_id,
                                                 body["reason"])
        except DataNeedError as exc:
            return dataneed_error(exc)

    @app.post("/v1/sessions/{session_id}/close", dependencies=dataneed_routes)
    def close_session(session_id: str, body: Any = Body(...), key: str | None = Depends(conversation_key)) -> Any:
        body = session_body(body, {"request_id"})
        if body is None:
            return invalid_body("{request_id}")
        try:
            return dataneed.close_session(session_id_or_404(session_id), body["request_id"], conversation_key=key)
        except SessionError as exc:
            return session_error(exc)

    @app.post("/v1/requests/{request_id}/release", dependencies=dataneed_routes)
    def release_request(request_id: str) -> Any:
        """S28: the orchestrator's answer for this request ended; its sessions go WARM_IDLE (completed) or close."""
        if not re.fullmatch(REQUEST_ID, request_id):
            raise HTTPException(status_code=404, detail="Unknown request_id")
        return {"request_id": request_id, "sessions": dataneed.sessions.release(request_id)}

    @app.get("/v1/runs/{request_id}", dependencies=[Depends(authorize)])
    def run_summary(request_id: str) -> Any:
        """Audit view of one orchestrator run (experiments, decisions, analyses, budgets, final report)."""
        if not re.fullmatch(REQUEST_ID, request_id):
            raise HTTPException(status_code=404, detail="Unknown request_id")
        summary = service.run_summary(request_id)
        if summary is None:
            raise HTTPException(status_code=404, detail="Unknown request_id")
        return summary

    @app.post("/v1/runs/{request_id}/report", dependencies=[Depends(authorize)])
    def run_report(request_id: str, body: Any = Body(...)) -> Any:
        if not re.fullmatch(REQUEST_ID, request_id):
            raise HTTPException(status_code=404, detail="Unknown request_id")
        try:
            report = RunReport.model_validate(body)
        except ValidationError as exc:
            return invalid(exc, "run report")
        return service.put_report(request_id, report.model_dump())

    @app.get("/v1/specs/{spec_id}", dependencies=[Depends(authorize)])
    def get_spec(spec_id: str) -> Any:
        if not re.fullmatch(SPEC_ID, spec_id):
            raise HTTPException(status_code=404, detail="Unknown spec_id")
        spec = service.get_spec(spec_id)
        if spec is None:
            raise HTTPException(status_code=404, detail="Unknown spec_id")
        return spec

    @app.post("/v1/analyses", dependencies=[Depends(authorize)])
    def submit(body: Any = Body(...)) -> Any:
        try:
            request = AnalysisRequest.model_validate(body)
        except ValidationError as exc:
            return invalid(exc, "analysis request")
        try:
            return service.submit(request)
        except ServiceUnavailable as exc:
            return unavailable(exc)

    @app.get("/v1/analyses/{analysis_id}", dependencies=[Depends(authorize)])
    def get_analysis(analysis_id: str, wait_seconds: int = Query(default=0, ge=0, le=60)) -> Any:
        analysis_id_or_404(analysis_id)
        try:
            return service.wait(analysis_id, min(wait_seconds, settings.max_poll_wait_seconds))
        except KeyError:
            raise HTTPException(status_code=404, detail="Unknown analysis_id")

    @app.post("/v1/analyses/{analysis_id}/cancel", dependencies=[Depends(authorize)])
    def cancel(analysis_id: str) -> Any:
        analysis_id_or_404(analysis_id)
        try:
            return service.cancel(analysis_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Unknown analysis_id")

    def stored(file_id: str, prefix: str) -> dict[str, Any]:
        if not FILE_ID.fullmatch(file_id) or not file_id.startswith(prefix):
            raise HTTPException(status_code=404, detail="Unknown id")
        entry = service.records.get_file(file_id)
        if entry is None:
            raise HTTPException(status_code=410, detail="This result is unknown or has expired")
        return entry

    @app.get("/v1/results/{result_id}", dependencies=[Depends(authorize)])
    def result_page(result_id: str, offset: int = Query(default=0, ge=0),
                    limit: int = Query(default=100, ge=1, le=PAGE_MAX)) -> Any:
        """Complete TABLE rows, page by page, for backend/frontend presentation (not the model)."""
        entry = stored(result_id, "res_")
        return service.outputs.read_table_page(entry, offset, limit)

    @app.get("/v1/artifacts/{artifact_id}", dependencies=[Depends(authorize)])
    def artifact(artifact_id: str) -> Any:
        entry = stored(artifact_id, "art_")
        return FileResponse(service.outputs.path_for(entry), media_type=CONTENT_TYPES[entry["format"]],
                            filename=f"{artifact_id}.{entry['format'].lower()}")

    return app
