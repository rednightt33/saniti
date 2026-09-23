from __future__ import annotations

import hmac
import logging
import re
import sys
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.responses import FileResponse, JSONResponse
from pydantic import ValidationError

from .config import Settings
from .models import ANALYSIS_ID, AnalysisRequest
from .outputs import CONTENT_TYPES
from .service import AnalysisService, ServiceUnavailable
from .spec import SPEC_ID, SpecRequest

FILE_ID = re.compile(r"^(res|art)_[0-9a-f]{24}$")
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
               run_workers: bool = True) -> FastAPI:
    """Private analysis service for market-ai-orc. No public domain, no docs routes."""
    _configure_logging()
    settings = settings or Settings.from_env()
    service = service or AnalysisService(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        service.start(run_workers=run_workers)
        yield
        service.stop()

    app = FastAPI(title="Saniti Market Python Sandbox", version="2.0.0", docs_url=None, redoc_url=None,
                  openapi_url=None, lifespan=lifespan)
    app.state.service = service
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
            request = SpecRequest.model_validate(body)
        except ValidationError as exc:
            return invalid(exc, "analysis spec")
        return service.create_spec(request)

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
