from __future__ import annotations

import hmac
import logging
import re
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.responses import FileResponse, JSONResponse
from pydantic import ValidationError

from .config import Settings
from .bundles import BUNDLE_ID
from .dataneed_service import DataNeedError, DataNeedService
from .sessions import SessionError
from .dataneed_store import DataNeedStore
from .models import ANALYSIS_ID, REQUEST_ID, AnalysisRequest, RunReport
from .outputs import CONTENT_TYPES
from .service import AnalysisService, ServiceUnavailable
from .spec import SPEC_ID
from .spec_v2 import SpecRequestAny

FILE_ID = re.compile(r"^(res|art)_[0-9a-f]{24}$")
NEED_ID = re.compile(r"^need_[0-9a-f]{24}$")
SESSION_ID = re.compile(r"^sess_[0-9a-f]{24}$")
OUTPUT_ID = re.compile(r"^out_[0-9a-f]{24}$")
DATA_NEED_KEYS = {"request_id", "reference_time", "timezone", "spec", "research_governance"}
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
                "limits": {**settings.child_limits(), "max_runtime_seconds": settings.max_runtime_seconds,
                           "max_memory_mb": settings.max_memory_mb, "duckdb_memory_mb": settings.duckdb_memory_mb,
                           "max_logical_datasets": settings.max_logical_datasets,
                           "max_input_files": settings.max_input_files, "max_input_rows": settings.max_input_rows,
                           "max_input_bytes": settings.max_input_bytes,
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

    @app.post("/v1/data-needs", dependencies=dataneed_routes)
    def submit_data_need(body: Any = Body(...)) -> Any:
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
        try:
            return dataneed.submit(body["request_id"], reference_time, timezone[:64], body["spec"],
                                   body.get("research_governance"))
        except DataNeedError as exc:
            return dataneed_error(exc)

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
    def open_session(body: Any = Body(...)) -> Any:
        """A persistent analysis session on a READY bundle of the same request."""
        body = session_body(body, {"request_id", "bundle_id"})
        if body is None or not isinstance(body["bundle_id"], str) or not BUNDLE_ID.fullmatch(body["bundle_id"]):
            return invalid_body("{request_id, bundle_id}")
        try:
            return dataneed.open_session(body["request_id"], body["bundle_id"])
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
        body = session_body(body, {"request_id"}, {"names", "max_rows"})
        if body is None:
            return invalid_body("{request_id, names?, max_rows?}")
        rows = body.get("max_rows", 5)
        if isinstance(rows, bool) or not isinstance(rows, int):
            return invalid_body("{request_id, names?, max_rows: integer}")
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

    @app.get("/v1/sessions/{session_id}/outputs/{output_id}", dependencies=dataneed_routes)
    def session_output(session_id: str, output_id: str, request_id: str = Query(..., max_length=128),
                       offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500)) -> Any:
        if not OUTPUT_ID.fullmatch(output_id):
            raise HTTPException(status_code=404, detail="Unknown output_id")
        try:
            return dataneed.sessions.read_output(session_id_or_404(session_id), request_id, output_id, offset, limit)
        except SessionError as exc:
            return session_error(exc)

    @app.post("/v1/sessions/{session_id}/complete", dependencies=dataneed_routes)
    def complete_session(session_id: str, body: Any = Body(...)) -> Any:
        """ExecutionManifest, Coverage Validator and final status; releases the outputs when coverage passes."""
        body = session_body(body, {"request_id"})
        if body is None:
            return invalid_body("{request_id}")
        try:
            return dataneed.complete(session_id_or_404(session_id), body["request_id"])
        except SessionError as exc:
            return session_error(exc)

    @app.post("/v1/sessions/{session_id}/close", dependencies=dataneed_routes)
    def close_session(session_id: str, body: Any = Body(...)) -> Any:
        body = session_body(body, {"request_id"})
        if body is None:
            return invalid_body("{request_id}")
        try:
            dataneed.sessions.state(session_id_or_404(session_id), body["request_id"])
        except SessionError as exc:
            return session_error(exc)
        return dataneed.sessions.close(session_id, "CLOSED_BY_CALLER")

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
