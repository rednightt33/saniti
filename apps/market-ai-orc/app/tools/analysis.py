"""Governed analysis tools: get_dataset_manifest, run_python_analysis, get_analysis_result.

market-ai-orc never executes model-generated Python. run_python_analysis forwards the code to the
separate market-python-sandbox service, which runs it in an isolated process over Parquet
datasets it obtains from market-sql-governor. This module holds only the sandbox's bearer key; it
never sees dataset URLs, bucket or database credentials, or complete result tables. The request
model must stay aligned with apps/market-python-sandbox/app/models.py (tests enforce it).
"""
from __future__ import annotations

import uuid
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .registry import ToolError, ToolSpec
from .request_data import GovernorClient, current_request_id

DATASET_ID_PATTERN = r"^ds_[0-9a-f]{24}$"
ANALYSIS_ID_PATTERN = r"^ana_[0-9a-f]{24}$"
OutputType = Literal["TABLE", "METRICS", "CHART", "ARTIFACT"]
DIAGNOSTIC_CHARS = 1000
# Next step for a request the sandbox refused before creating an analysis.
REJECTION_ACTIONS = {"QUEUE_FULL": "RETRY_LATER", "INVALID_REQUEST": "REVISE_ANALYSIS",
                     "SANDBOX_ISOLATION_UNAVAILABLE": "REPORT_LIMITATION"}


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GetDatasetManifestArgs(Strict):
    dataset_id: str = Field(pattern=DATASET_ID_PATTERN, description="dataset_id from a DATASET_READY result.")


class RunPythonAnalysisArgs(Strict):
    purpose: str = Field(min_length=1, max_length=1000, description="The calculation this code performs and why.")
    dataset_ids: list[str] = Field(
        min_length=1, max_length=4,
        description="dataset_ids from DATASET_READY results to use as inputs (1 to 4, unique).")
    python_code: str = Field(min_length=1, max_length=20000, description="Python source to run in the sandbox.")
    expected_outputs: list[OutputType] = Field(
        min_length=1, max_length=4, description="Output types the code will emit (unique).")

    @field_validator("dataset_ids")
    @classmethod
    def _dataset_ids(cls, values: list[str]) -> list[str]:
        import re

        if any(not re.fullmatch(DATASET_ID_PATTERN, value) for value in values):
            raise ValueError("each dataset_id must match ^ds_[0-9a-f]{24}$")
        if len(set(values)) != len(values):
            raise ValueError("dataset_ids must be unique")
        return values

    @field_validator("expected_outputs")
    @classmethod
    def _unique(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values):
            raise ValueError("expected_outputs must be unique")
        return values


class GetAnalysisResultArgs(Strict):
    analysis_id: str = Field(pattern=ANALYSIS_ID_PATTERN, description="analysis_id from run_python_analysis.")


MANIFEST_DESCRIPTION = (
    "Describe exactly what one governed dataset contains (a dataset_id from a DATASET_READY request_data "
    "result): columns and types, row count, source tables, requested versus actual date range, entities "
    "present and missing, completeness, checksum, numeric-precision warnings, and expiry. This is the "
    "extracted dataset itself, not the catalog's coverage estimate. status is AVAILABLE, or explicitly "
    "DATASET_EXPIRED or DATASET_NOT_FOUND."
)

RUN_DESCRIPTION = (
    "Run Python analysis in an isolated sandbox over 1-4 governed datasets (dataset_ids from DATASET_READY "
    "results). The code runs as a script without network, subprocess, or file access outside its inputs. "
    "Inputs: DATASETS maps each dataset_id to a local Parquet path, e.g. pd.read_parquet(DATASETS[id]), "
    "pl.scan_parquet(DATASETS[id]), or duckdb.sql('SELECT ... FROM read_parquet(?)', params=[DATASETS[id]]); "
    "never write your own file paths. Libraries: numpy, pandas, polars, pyarrow, duckdb, scipy, statsmodels, "
    "matplotlib, and TA-Lib (import talib: RSI, SMA, STDDEV, MACD, BBANDS, candlestick patterns such as "
    "CDLENGULFING, which returns positive values for bullish and negative for bearish patterns). "
    "Helper module saniti: load_dataset(id, columns=None) returns a pandas DataFrame; "
    "iter_series(df, entity, date, min_history) yields (entity, its history sorted by date) and records "
    "entities excluded for short history; prepare_panel(df, entity, date, on_duplicate='error'|'keep_last'|"
    "'keep_first') sorts and handles duplicate observations explicitly; panel_check(df, entity, date) reports "
    "duplicates, ordering, and nulls; add_warning(code, message) records a limitation; SEED is the fixed seed. "
    "Official results must be emitted, not printed: emit_table(name, dataframe, description=''), "
    "emit_metrics(dict), emit_chart(figure, name, title, description), emit_artifact(name, data, "
    "format='PARQUET'|'CSV'|'JSON'); only types listed in expected_outputs may be emitted. Compute indicators "
    "per entity on date-sorted history, never across a multi-entity frame, and do not fill missing values "
    "silently. The call waits briefly; if status is QUEUED or RUNNING, call get_analysis_result after "
    "retry_after_seconds. A TABLE returns row_count, columns, a bounded preview, and a result_id for the "
    "complete table."
)

RESULT_DESCRIPTION = (
    "Get the status and structured outputs of a run_python_analysis job. Waits briefly while it runs. Returns "
    "status (QUEUED, RUNNING, COMPLETED, FAILED, CANCELLED, EXPIRED), next_action, outputs, warnings, and a "
    "structured error."
)


def model_view(result: dict[str, Any]) -> dict[str, Any]:
    """The analysis record as the model sees it: no limits, deployment ids, or usage internals."""
    lineage = dict(result.get("lineage") or {})
    lineage.pop("limits", None)
    lineage.pop("deployment_id", None)
    view = {key: result.get(key) for key in (
        "analysis_id", "status", "next_action", "retry_after_seconds", "purpose", "dataset_ids", "expected_outputs",
        "runtime_ms", "outputs", "warnings", "error", "outputs_expire_at")}
    view["lineage"] = lineage
    diagnostics = result.get("diagnostics") or {}
    if diagnostics:
        view["diagnostics"] = {k: str(v)[-DIAGNOSTIC_CHARS:] for k, v in diagnostics.items() if v}
    return {k: v for k, v in view.items() if v is not None}


class SandboxClient:
    def __init__(self, base_url: str, api_key: str, timeout_seconds: float, poll_wait_seconds: int,
                 transport: httpx.BaseTransport | None = None) -> None:
        self.poll_wait_seconds = poll_wait_seconds
        self._client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout_seconds, transport=transport,
                                    headers={"Authorization": f"Bearer {api_key}"})

    def ready(self) -> bool:
        try:
            response = self._client.get("/ready", timeout=5)
            return response.status_code == 200 and response.json().get("status") == "ready"
        except (httpx.HTTPError, ValueError):
            return False

    def _call(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            return self._client.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            raise ToolError("The Python sandbox did not answer in time; use get_analysis_result if an "
                            "analysis_id was returned earlier.") from exc
        except httpx.HTTPError as exc:
            raise ToolError("The Python sandbox is unreachable.") from exc

    @staticmethod
    def _json(response: httpx.Response) -> dict[str, Any]:
        try:
            body = response.json()
        except ValueError as exc:
            raise ToolError("The Python sandbox returned an invalid response.") from exc
        if not isinstance(body, dict):
            raise ToolError("The Python sandbox returned an invalid response.")
        return body

    def submit(self, arguments: RunPythonAnalysisArgs) -> dict[str, Any]:
        request_id = current_request_id.get() or f"orc-{uuid.uuid4().hex[:16]}"
        response = self._call("POST", "/v1/analyses", json={"request_id": request_id, **arguments.model_dump()})
        body = self._json(response)
        if response.status_code == 200 and "analysis_id" in body:
            return model_view(body)
        error = body.get("error") if isinstance(body.get("error"), dict) else None
        if response.status_code in (422, 429, 503) and error:
            return {"status": "REJECTED", "error": {"code": error.get("code"), "message": error.get("message")},
                    "next_action": REJECTION_ACTIONS.get(error.get("code"), "REPORT_LIMITATION"),
                    **({"retry_after_seconds": body["retry_after_seconds"]} if body.get("retry_after_seconds") else {})}
        raise ToolError(f"The Python sandbox is unavailable (HTTP {response.status_code}).")

    def result(self, analysis_id: str) -> dict[str, Any]:
        response = self._call("GET", f"/v1/analyses/{analysis_id}", params={"wait_seconds": self.poll_wait_seconds})
        if response.status_code == 404:
            return {"analysis_id": analysis_id, "status": "NOT_FOUND", "next_action": "STOP_OR_REFORMULATE",
                    "error": {"code": "ANALYSIS_NOT_FOUND", "message": "No analysis exists with this analysis_id."}}
        body = self._json(response)
        if response.status_code == 200 and "analysis_id" in body:
            return model_view(body)
        raise ToolError(f"The Python sandbox is unavailable (HTTP {response.status_code}).")

    def close(self) -> None:
        self._client.close()


def manifest_spec(client: GovernorClient, *, timeout_seconds: float) -> ToolSpec:
    def handler(arguments: BaseModel) -> dict[str, Any]:
        assert isinstance(arguments, GetDatasetManifestArgs)
        return client.manifest(arguments.dataset_id)

    return ToolSpec(name="get_dataset_manifest", description=MANIFEST_DESCRIPTION,
                    arguments_model=GetDatasetManifestArgs, handler=handler, timeout_seconds=timeout_seconds)


def analysis_specs(client: SandboxClient, *, timeout_seconds: float, max_result_bytes: int) -> list[ToolSpec]:
    def run(arguments: BaseModel) -> dict[str, Any]:
        assert isinstance(arguments, RunPythonAnalysisArgs)
        return client.submit(arguments)

    def result(arguments: BaseModel) -> dict[str, Any]:
        assert isinstance(arguments, GetAnalysisResultArgs)
        return client.result(arguments.analysis_id)

    return [
        ToolSpec(name="run_python_analysis", description=RUN_DESCRIPTION, arguments_model=RunPythonAnalysisArgs,
                 handler=run, timeout_seconds=timeout_seconds, max_result_bytes=max_result_bytes),
        ToolSpec(name="get_analysis_result", description=RESULT_DESCRIPTION, arguments_model=GetAnalysisResultArgs,
                 handler=result, timeout_seconds=timeout_seconds, max_result_bytes=max_result_bytes),
    ]
