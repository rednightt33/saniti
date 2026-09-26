"""Analysis session tools (DataNeed flow, behind AI_ENABLE_DATANEED): open_analysis_session, run_python,
inspect_session, get_session_output.

A session is a persistent, isolated Python process in market-python-sandbox, bound to this request and one READY
governed bundle. Variables and functions survive between run_python calls, so the model can load the data, check
the Data Quality Manifest, define and call functions, look at intermediate results, fix errors and rerun. The code
has no network, no database, no subprocesses and read-only inputs. Outputs are stored with checksums and are
released for the final answer only when complete_analysis passes coverage.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..compaction import dumps
from .analysis import SandboxClient
from .registry import ToolError, ToolSpec
from .request_data import current_request_id

SESSION_PATTERN = r"^sess_[0-9a-f]{24}$"
BUNDLE_PATTERN = r"^bundle_[0-9a-f]{24}$"
OUTPUT_PATTERN = r"^out_[0-9a-f]{24}$"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OpenAnalysisSessionArgs(Strict):
    input_bundle_id: str = Field(pattern=BUNDLE_PATTERN, description="input_bundle_id of a READY bundle.")


class RunPythonArgs(Strict):
    session_id: str = Field(pattern=SESSION_PATTERN)
    code: str = Field(min_length=1, max_length=20000, description="Python to run in the session's namespace.")


class InspectSessionArgs(Strict):
    session_id: str = Field(pattern=SESSION_PATTERN)
    names: list[str] | None = Field(max_length=20, description="Variables to describe with a preview; null lists "
                                                               "every variable (names, types, shapes).")
    max_rows: int | None = Field(ge=0, le=20, description="Preview rows per DataFrame (default 5).")


class CompleteAnalysisArgs(Strict):
    session_id: str = Field(pattern=SESSION_PATTERN)


class GetSessionOutputArgs(Strict):
    session_id: str = Field(pattern=SESSION_PATTERN)
    output_id: str = Field(pattern=OUTPUT_PATTERN)
    offset: int | None = Field(ge=0, description="First row (tables) or chunk (text); default 0.")
    limit: int | None = Field(ge=1, le=200, description="Rows (tables) or chunks (text) to return; default 50.")


def _call(client: SandboxClient, method: str, path: str, timeout: float | None = None, **kwargs: Any
          ) -> dict[str, Any]:
    if timeout is not None:
        kwargs["timeout"] = timeout
    response = client._call(method, path, **kwargs)
    body = client._json(response)
    if response.status_code == 200:
        return body
    error = body.get("error") if isinstance(body.get("error"), dict) else None
    if error and response.status_code in (404, 409, 410, 422, 429, 500, 503):
        return {"status": "REJECTED", "code": error.get("code"), "message": str(error.get("message") or "")[:600],
                "next_action": body.get("next_action") or "REPORT_LIMITATION",
                **{k: v for k, v in error.items() if k in ("close_reason", "retry_after_seconds", "execution_id")}}
    raise ToolError(f"The Python sandbox is unavailable (HTTP {response.status_code}).")


OPEN_DESCRIPTION = (
    "Open a persistent Python analysis session on a READY governed bundle (input_bundle_id from "
    "prepare_data_bundle). Returns session_id, the datasets (data_request_id, logical name, columns, rows, ranges, "
    "quality flags), the relationships with their join semantics, the helper functions and the limits. Variables and "
    "functions persist across run_python calls until the session closes (idle timeout, limits, or a restart of the "
    "sandbox: then open a new session on the same bundle)."
)

RUN_DESCRIPTION = (
    "Run Python in the session. pandas as pd, numpy as np and saniti with all its helpers are pre-bound; TA-Lib "
    "(import talib), scipy, statsmodels, polars, duckdb and matplotlib are available. Read data only through the "
    "helpers: load(request) returns a whole dataset (every row of every range, including warm-up history), "
    "range(request, range_id, include_buffers=False) one approved range, sql(query) DuckDB over one view per logical "
    "name, join(relationship_id) the approved relationship with its point-in-time semantics, quality(request) the "
    "Data Quality Manifest, requests() and manifest() the bundle, resample(frame, request) the catalog rules. "
    "Reads outside the helpers count as not processed. Write any logic you need; define functions and call them "
    "later. Emit results with emit_table(name, frame), emit_json(name, value), emit_text(name, text), "
    "emit_chart(figure, name, title), emit_file(name, data, format); each returns output metadata and the tool "
    "result lists output_ids. print() is diagnostics only. Results: OK; SCRIPT_ERROR with error_type, line, field "
    "(e.g. a missing column) and traceback: fix the code and rerun (earlier variables remain); TIMEOUT (the "
    "execution was interrupted, the session remains); INSUFFICIENT_INPUT_DATA after "
    "saniti.insufficient_data(request, range_id, value, unit, reason): revise the DataNeedSpec (for example more "
    "history). No network, database, subprocess or writes outside intermediate_path(name)."
)
# Appended to RUN_DESCRIPTION only with AI_ENABLE_STANDARD_PERIOD_RETURN, so the description is unchanged without it.
PERIOD_RETURN_SENTENCE = (
    " Named calendar-period returns (YTD, month, quarter, year, a comparable calendar period) use "
    "period_return(request, range_id, value_column='close'): one row per entity with base_date, base_value (the last "
    "valid value strictly before the range start), end_date, end_value (the last valid value on or before the range "
    "end), return_decimal, return_pct (full precision) and calculation_status (COMPLETE, NO_PRIOR_CLOSE, "
    "NO_END_VALUE, INVALID_BASE_VALUE, INSUFFICIENT_INPUT_DATA, DUPLICATE_BOUNDARY_OBSERVATION); it needs "
    "history_buffer 1 TRADING_OBSERVATIONS on the request."
)

INSPECT_DESCRIPTION = (
    "Describe session variables: with names null, every variable (name, type, shape); with names, up to 20 variables "
    "with dtypes and up to max_rows preview rows. Use it to check intermediate results before emitting outputs."
)

OUTPUT_DESCRIPTION = (
    "Read back one output of the session: table rows page by page (offset, limit), JSON content or text chunks; "
    "charts and files return metadata only. released is false until complete_analysis passes: only released "
    "outputs may be cited in the final answer."
)


COMPLETE_DESCRIPTION = (
    "Finish the analysis of a session. The backend builds the ExecutionManifest and runs the Coverage Validator: "
    "every approved data request and range must have been delivered as approved and read in full through the saniti "
    "helpers in a successful execution, with at least one output. Returns final_status (data_coverage PASS/FAIL, "
    "sandbox_execution, calculation_validation NOT_PERFORMED, evidence_label, warnings, claims_allowed, "
    "claims_forbidden) and, on PASS, the released outputs with their content (JSON outputs and the first table rows). "
    "Only released outputs may be cited in the answer; disclose the warnings. On FAIL follow next_action: RUN_PYTHON "
    "(read what was not processed, then complete again), REVISE_DATA_NEED_SPEC, or REPORT_LIMITATION. The backend "
    "does not recalculate your formulas: never say a calculation was independently verified."
)
RELEASED_PREVIEW_ROWS = 200
RELEASED_PREVIEW_OUTPUTS = 10
# Room left in the tool result for fields the registry adds (ignored_arguments, omitted_fields_set_to_null).
RESULT_ENVELOPE_MARGIN = 1024


def _size(value: Any) -> int:
    return len(dumps(value).encode("utf-8"))


def _fit(entry: dict[str, Any], budget: int) -> dict[str, Any]:
    """The entry within budget bytes: the longest prefix of its rows, or no content, with a note saying how to read
    the rest (released outputs can be paged with get_session_output). The notes hold no digits, because provenance
    reads the numbers of released content."""
    if _size(entry) < budget:
        return entry
    if "rows" not in entry:
        return {**entry, "content": None, "truncated": True,
                "note": "The content did not fit the tool result size limit; read it with get_session_output."}
    rows = entry["rows"]
    note = ("Only the rows shown fit the tool result size limit; read the rest with get_session_output, with offset "
            "equal to the number of rows shown.")

    def cut(count: int) -> dict[str, Any]:
        return {**entry, "rows": rows[:count], "truncated": True, "note": note}

    low, high = 0, len(rows)
    while low < high:
        middle = (low + high + 1) // 2
        if _size(cut(middle)) < budget:
            low = middle
        else:
            high = middle - 1
    return cut(low)


def _within(contents: list[dict[str, Any]], budget: int) -> list[dict[str, Any]]:
    """The contents within budget bytes. Non-table contents (often a small summary) stay whole when they fit, the
    largest dropped first when they do not; the tables share what is left, each cut to its rows' longest prefix."""
    if _size(contents) < budget:
        return contents
    out = list(contents)
    tables = [i for i, entry in enumerate(out) if "rows" in entry]
    for i in tables:
        out[i] = _fit(out[i], 0)
    for i in sorted((i for i, entry in enumerate(out) if "rows" not in entry), key=lambda i: -_size(out[i])):
        if _size(out) < budget:
            break
        out[i] = _fit(out[i], 0)
    for n, i in enumerate(tables):
        share = (budget - _size(out)) // (len(tables) - n)
        out[i] = _fit(contents[i], _size(out[i]) + share)
    return out


def released_contents(client: SandboxClient, session_id: str, outputs: list[dict[str, Any]], timeout: float,
                      request_id: str, byte_budget: int | None = None) -> list[dict[str, Any]]:
    """The content of released outputs (bounded), so the answer can cite them and provenance can check them.
    With byte_budget the contents together stay within it, so a wide table cannot push the whole complete_analysis
    result over the tool result limit (which would hide the completion from the model)."""
    contents: list[dict[str, Any]] = []
    for output in outputs[:RELEASED_PREVIEW_OUTPUTS]:
        if output.get("type") not in ("TABLE", "PARQUET", "CSV", "JSON", "TEXT"):
            continue
        body = _call(client, "GET", f"/v1/sessions/{session_id}/outputs/{output['output_id']}", timeout=timeout,
                     params={"request_id": request_id, "offset": 0, "limit": RELEASED_PREVIEW_ROWS})
        if body.get("status") == "REJECTED" or not body.get("released"):
            continue
        entry = {"output_id": output["output_id"], "name": output.get("name"), "type": output.get("type")}
        if "rows" in body:
            entry.update(rows=body["rows"], row_count=body.get("row_count"),
                         truncated=body.get("next_offset") is not None)
        else:
            entry.update(content=body.get("content"), truncated=body.get("next_offset") is not None)
        contents.append(entry)
    return contents if byte_budget is None else _within(contents, byte_budget)


def session_specs(client: SandboxClient, *, timeout_seconds: float, execution_timeout_seconds: float,
                  max_result_bytes: int, standard_period_return: bool = False) -> list[ToolSpec]:
    def request_id() -> str:
        return current_request_id.get() or ""

    def open_session(arguments: BaseModel) -> dict[str, Any]:
        assert isinstance(arguments, OpenAnalysisSessionArgs)
        return _call(client, "POST", "/v1/sessions", timeout=timeout_seconds,
                     json={"request_id": request_id(), "bundle_id": arguments.input_bundle_id})

    def run(arguments: BaseModel) -> dict[str, Any]:
        assert isinstance(arguments, RunPythonArgs)
        return _call(client, "POST", f"/v1/sessions/{arguments.session_id}/execute", timeout=execution_timeout_seconds,
                     json={"request_id": request_id(), "code": arguments.code})

    def inspect(arguments: BaseModel) -> dict[str, Any]:
        assert isinstance(arguments, InspectSessionArgs)
        body: dict[str, Any] = {"request_id": request_id(), "max_rows": 5 if arguments.max_rows is None
                                else arguments.max_rows}
        if arguments.names is not None:
            body["names"] = arguments.names
        return _call(client, "POST", f"/v1/sessions/{arguments.session_id}/inspect", timeout=timeout_seconds,
                     json=body)

    def output(arguments: BaseModel) -> dict[str, Any]:
        assert isinstance(arguments, GetSessionOutputArgs)
        return _call(client, "GET", f"/v1/sessions/{arguments.session_id}/outputs/{arguments.output_id}",
                     timeout=timeout_seconds, params={"request_id": request_id(), "offset": arguments.offset or 0,
                                                      "limit": arguments.limit or 50})

    def complete(arguments: BaseModel) -> dict[str, Any]:
        assert isinstance(arguments, CompleteAnalysisArgs)
        result = _call(client, "POST", f"/v1/sessions/{arguments.session_id}/complete", timeout=timeout_seconds * 2,
                       json={"request_id": request_id()})
        if result.get("status") == "COMPLETED" and result.get("released_outputs"):
            envelope = _size({"ok": True, "tool": "complete_analysis", "result": {**result, "released_contents": []}})
            result["released_contents"] = released_contents(
                client, arguments.session_id, result["released_outputs"], timeout_seconds, request_id(),
                byte_budget=max(0, max_result_bytes - envelope - RESULT_ENVELOPE_MARGIN))
        return result

    return [
        ToolSpec(name="complete_analysis", description=COMPLETE_DESCRIPTION, arguments_model=CompleteAnalysisArgs,
                 handler=complete, timeout_seconds=timeout_seconds * 4, max_result_bytes=max_result_bytes),
        ToolSpec(name="open_analysis_session", description=OPEN_DESCRIPTION, arguments_model=OpenAnalysisSessionArgs,
                 handler=open_session, timeout_seconds=timeout_seconds + 30, max_result_bytes=max_result_bytes),
        ToolSpec(name="run_python", description=RUN_DESCRIPTION + (PERIOD_RETURN_SENTENCE if standard_period_return
                                                                   else ""),
                 arguments_model=RunPythonArgs, handler=run,
                 timeout_seconds=execution_timeout_seconds + 5, max_result_bytes=max_result_bytes),
        ToolSpec(name="inspect_session", description=INSPECT_DESCRIPTION, arguments_model=InspectSessionArgs,
                 handler=inspect, timeout_seconds=timeout_seconds + 5, max_result_bytes=max_result_bytes),
        ToolSpec(name="get_session_output", description=OUTPUT_DESCRIPTION, arguments_model=GetSessionOutputArgs,
                 handler=output, timeout_seconds=timeout_seconds + 5, max_result_bytes=max_result_bytes),
    ]
