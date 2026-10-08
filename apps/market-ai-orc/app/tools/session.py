"""Analysis session tools (DataNeed flow, behind AI_ENABLE_DATANEED): open_analysis_session, run_python,
inspect_session, get_session_output.

A session is a persistent, isolated Python process in market-python-sandbox, bound to this request and one READY
governed bundle. Variables and functions survive between run_python calls, so the model can load the data, check
the Data Quality Manifest, define and call functions, look at intermediate results, fix errors and rerun. The code
has no network, no database, no subprocesses and read-only inputs. Outputs are stored with checksums and are
released for the final answer only when complete_analysis passes coverage.
"""
from __future__ import annotations

import contextvars
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..compaction import dumps
from .analysis import SandboxClient
from .artifacts import current_results, read_execution, read_output_any, resolve_ref
from .registry import ToolError, ToolSpec
from .request_data import current_request_id

# 2d (2026-10-02): the output ids of the carried tables the approved research plan names, set by the orchestrator
# for the run that executes the plan (None: no approved plan, so the sandbox's own rule applies)
# R-STORE (round 2026-10-03 C2d): (session_id, open view, allowed output ids or None) -> what was restored; set by
# the orchestrator for a run whose conversation keeps its results, so a new session gets back the conversation's
# stored tables that the sandbox no longer holds
current_carried_restorer: contextvars.ContextVar[Any] = contextvars.ContextVar("current_carried_restorer",
                                                                              default=None)
RESTORED_NOTE = ("Tables of earlier answers that the sandbox no longer held were put back from the conversation's "
                 "store (restored_outputs): load them with load_output(output_id) as before; each keeps its label, "
                 "definition and data date. A table listed as STORED_NOT_LOADED or RESTORE_FAILED is not available "
                 "in this session.")


def restore_into(result: dict[str, Any], allowed: list[str] | None) -> None:
    """Put the conversation's stored tables back into a session that just opened (R-STORE); never fails the open."""
    restorer = current_carried_restorer.get()
    if restorer is None or not result.get("session_id"):
        return
    try:
        restored = restorer(str(result["session_id"]), result, allowed)
    except Exception:  # noqa: BLE001 - the open stands without the restored tables
        restored = []
    if restored:
        result["restored_outputs"] = [{k: r.get(k) for k in ("output_id", "name", "status")} for r in restored]
        result["restored_note"] = RESTORED_NOTE


def output_file(client: SandboxClient, session_id: str, output_id: str, request_id: str, timeout: float = 120.0
                ) -> bytes:
    """R-STORE: the file of a released output, checked against the sandbox's checksum."""
    import hashlib

    response = client._call("GET", f"/v1/sessions/{session_id}/outputs/{output_id}/file", timeout=timeout,
                            params={"request_id": request_id})
    response.raise_for_status()
    data = response.content
    if hashlib.sha256(data).hexdigest() != response.headers.get("X-Saniti-Checksum-Sha256"):
        raise ToolError("The output file does not match its checksum.")
    return data


def restore_carried(client: SandboxClient, session_id: str, request_id: str, meta: dict[str, Any], data: bytes,
                    timeout: float = 120.0) -> dict[str, Any]:
    """R-STORE: upload a stored table into a session of the same conversation (POST /v1/sessions/{id}/carried)."""
    import base64
    import json

    encoded = base64.urlsafe_b64encode(json.dumps(meta, default=str).encode()).decode().rstrip("=")
    response = client._call("POST", f"/v1/sessions/{session_id}/carried", timeout=timeout,
                            params={"request_id": request_id}, content=data,
                            headers={"X-Saniti-Output-Meta": encoded, "Content-Type": "application/octet-stream"})
    body = client._json(response)
    if response.status_code == 200:
        return body
    error = body.get("error") if isinstance(body.get("error"), dict) else {}
    return {"status": "REJECTED", "code": error.get("code") or f"HTTP_{response.status_code}"}


current_carried_outputs: contextvars.ContextVar[list[str] | None] = contextvars.ContextVar(
    "current_carried_outputs", default=None)

SESSION_PATTERN = r"^sess_[0-9a-f]{24}$"
BUNDLE_PATTERN = r"^bundle_[0-9a-f]{24}$"
OUTPUT_PATTERN = r"^out_[0-9a-f]{24}$"
EXECUTION_PATTERN = r"^exe_[0-9a-f]{24}$"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OpenAnalysisSessionArgs(Strict):
    input_bundle_id: str = Field(pattern=BUNDLE_PATTERN, description="input_bundle_id of a READY bundle.")


class OpenAnalysisSessionLimitArgs(OpenAnalysisSessionArgs):
    """EXEC-V 2026-10-08: with several sessions per answer, the model may close one of this answer's sessions it no
    longer needs before opening another (the way out of SESSION_LIMIT_PER_REQUEST); never closed by the backend."""
    close_session_id: str | None = Field(pattern=SESSION_PATTERN, description=(
        "Optional: a session of this answer to close before opening, only when the open was refused with "
        "SESSION_LIMIT_PER_REQUEST; pick one that is completed or no longer needed (its released outputs stay "
        "readable, its variables are gone). Null otherwise."))


class RunPythonArgs(Strict):
    session_id: str = Field(pattern=SESSION_PATTERN)
    code: str = Field(min_length=1, max_length=20000, description="Python to run in the session's namespace.")


class RunPythonCompleteArgs(RunPythonArgs):
    """EXEC-P5 (user approval 2026-10-06, AI_ENABLE_MERGED_STEPS): the last call completes the analysis without
    another turn."""
    complete: bool | None = Field(description=(
        "true on the last call: when this code runs OK the backend calls complete_analysis at once and returns its "
        "result with this one; null or false keeps the session open."))


class InspectSessionArgs(Strict):
    session_id: str = Field(pattern=SESSION_PATTERN)
    names: list[str] | None = Field(max_length=20, description="Variables to describe with a preview; null lists "
                                                               "every variable (names, types, shapes).")
    max_rows: int | None = Field(ge=0, le=20, description="Preview rows per DataFrame (default 5).")
    dataset: str | None = Field(min_length=1, max_length=120, description=(
        "A dataset of the session's bundle (logical name): its full column statistics instead of variables."))


class CompleteAnalysisArgs(Strict):
    session_id: str = Field(pattern=SESSION_PATTERN)


class GetSessionOutputArgs(Strict):
    session_id: str | None = Field(pattern=SESSION_PATTERN, description=(
        "The session that made the output; null for an output of an earlier answer."))
    output_id: str | None = Field(pattern=OUTPUT_PATTERN)
    ref: str | None = Field(pattern=r"^(out\.)?o[1-9][0-9]{0,3}$", description=(
        "The value reference of an output (out.o3), instead of output_id."))
    execution_id: str | None = Field(pattern=EXECUTION_PATTERN, description=(
        "An execution instead of an output: its code, what it read and the outputs it released."))
    include_content: bool | None = Field(description="With execution_id: true also returns the code.")
    offset: int | None = Field(ge=0, description="First row (tables) or chunk (text); default 0.")
    limit: int | None = Field(ge=1, le=200, description="Rows (tables) or chunks (text) to return; default 50.")

    @model_validator(mode="after")
    def _one_source(self) -> "GetSessionOutputArgs":
        given = [n for n in ("output_id", "ref", "execution_id") if getattr(self, n) is not None]
        if len(given) != 1:
            raise ValueError("give exactly one of output_id, ref or execution_id")
        return self


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
                **{k: v for k, v in error.items() if k in ("close_reason", "retry_after_seconds", "execution_id",
                                                           "waited_seconds", "open_sessions",
                                                           "max_sessions_per_request")}}
    raise ToolError(f"The Python sandbox is unavailable (HTTP {response.status_code}).")


OPEN_DESCRIPTION = (
    "Open a persistent Python analysis session on a READY governed bundle (input_bundle_id from "
    "prepare_data_bundle). Returns session_id, the datasets (data_request_id, logical name, columns, rows_extracted "
    "with the buffer rows, rows_in_ranges inside the approved ranges, ranges, quality flags), the relationships with their join semantics, the helper functions and the limits. Variables and "
    "functions persist across run_python calls until the session closes (idle timeout, limits, or a restart of the "
    "sandbox: then open a new session on the same bundle)."
)

RUN_DESCRIPTION = (
    "Run Python in the session. pandas as pd, numpy as np and saniti with all its helpers are pre-bound; TA-Lib "
    "(import talib), scipy, statsmodels, polars, duckdb and matplotlib are available. Read data only through the "
    "helpers: load(request) returns a whole dataset (every row of every range, including warm-up history), "
    "load_range(request, range_id, include_buffers=False) one approved range (also saniti.range; plain range() "
    "is Python's built-in), in_period(frame, request) the mask of the rows inside the approved ranges (count and "
    "summarise only those; warm-up rows feed indicators), sql(query) DuckDB over one view per logical "
    "name, join(relationship_id) the approved relationship with its point-in-time semantics, quality(request) the "
    "Data Quality Manifest, requests() and manifest() the bundle, resample(frame, request) the catalog rules. "
    "Reads outside the helpers count as not processed. Each dataset of the session shows materialize: DIRECT "
    "(load() may read it whole) or AGGREGATE_FIRST (reduce it in sql() first, e.g. GROUP BY its entity and date "
    "columns): load(), range() and sql() refuse a pandas frame larger than the session's frame budget with "
    "MaterializationLimitExceeded, before anything is loaded; the session, its data and variables stay, so revise "
    "the code, never the data need. Write any logic you need; define functions and call them "
    "later. Emit results with emit_table(name, frame), emit_json(name, value), emit_text(name, text), "
    "emit_chart(figure, name, title), emit_file(name, data, format); emit_table and emit_json take units={column: "
    "'FRACTION' | 'PERCENT' | 'P_VALUE'} for every column holding a share or a return as a decimal, a value "
    "already in percent, or a p-value, so the answer's value references are formatted by the data's "
    "unit, and definition={'filters': [{'column', 'operator', 'value'}], 'period': {'start', 'end'}, 'entities', "
    "'thresholds', 'notes'}: how the result was made beyond the data request (filters in the data need's operators "
    "EQ, NEQ, GT, GTE, LT, LTE, IN, NOT_IN, BETWEEN, IS_NULL, IS_NOT_NULL; {} when the code applied none), which "
    "later turns read instead of guessing; complete_analysis does not release a table or JSON without one. A "
    "table of an earlier result opened with load_output carries its definition in .attrs; each returns output "
    "metadata and the tool "
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
    "with dtypes and up to max_rows preview rows. Use it to check intermediate results before emitting outputs. "
    "With dataset, the profiler's statistics of every column of that dataset (nulls, min/median/max, distinct "
    "counts, entities with gaps), no rows."
)

OUTPUT_DESCRIPTION = (
    "Read back one output: table rows page by page (offset, limit), JSON content or text chunks; charts and files "
    "return metadata only. released is false until complete_analysis passes: only released outputs may be cited in "
    "the final answer. An output of an earlier answer opens by its ref (out.o3) or output_id, also after the sandbox "
    "deleted it; execution_id opens the code an execution ran (include_content true), what it read and released."
)


EVENT_STUDY_VERSION = 1  # the sandbox's event_study capability version this service describes
# Appended to RUN_DESCRIPTION and COMPLETE_DESCRIPTION only with AI_ENABLE_EVENT_STUDY (G2, 2026-10-02).
EVENT_STUDY_SENTENCE = (
    " Event study: event_study(request, event, outcome, horizon, range_id=None, overlap_policy='NON_OVERLAPPING', "
    "baseline='ALL_ELIGIBLE', min_events=None, holdout_start=None, outcome_unit=None, name=None) measures the "
    "outcome after an event against a baseline. event is a condition expression over the request's columns, per "
    "entity and past values only (+ - * / **, comparisons, & | ~, abs log exp sqrt sign min max where, lag(x, k), "
    "rolling_sum(x, n), rolling_mean(x, n)), e.g. 'close / lag(close, 1) - 1 <= -0.05'; outcome is "
    "{'forward_return': '<price column>'} (add 'request': '<data_request_id>' when the price is in another request); "
    "horizon counts observations; the request needs one row per entity and date. NON_OVERLAPPING keeps an entity's "
    "next event only a horizon after the last one; ALL_ELIGIBLE compares with every row, NON_EVENT with the rows "
    "without the event; holdout_start adds IN_SAMPLE and OUT_OF_SAMPLE rows. It emits <name> (one row per segment: "
    "event_count, event_dates, effective_event_dates, mean, median, hit_rate, baseline_count, baseline_mean, "
    "baseline_median, delta_mean, delta_ci_low, delta_ci_high, delta_p_value with dates as clusters, censored_count, "
    "overlapping_dropped, meets_min_events), <name>_events (date, entity, outcome), <name>_baseline and <name>_flow "
    "(rows_in_window, condition_unknown, condition_true = the qualifying events, censored, overlapping_dropped, used; "
    "condition_true = censored + overlapping_dropped + used): quote each count from <name>_flow, never derive it; "
    "never overwrite or re-emit them."
)
BACKTEST_VERSION = 1  # the sandbox's backtest capability version this service describes
# Appended to RUN_DESCRIPTION and COMPLETE_DESCRIPTION when the sandbox reports backtest (P32 layer 3, 2026-10-05).
BACKTEST_SENTENCE = (
    " Backtest: backtest(request, frame, signal, exit_signal=None, stop=None, target=None, max_hold=None, fee=None, "
    "unit=None, prices=None, range_id=None, name=None) simulates long trades of a stated rule on the bundle prices: "
    "signal (and exit_signal) are boolean columns of your frame, True on the bar whose close triggers the order "
    "(filled at the next open); stop and target are fractions of the entry price; only bars inside the approved "
    "ranges trade (warm-up rows feed indicators). Use only the exit rules the user or the script states. It emits "
    "<name>_trades and <name>_summary (signals, trades, win_rate, mean and median return, average win and loss, "
    "realized_reward_risk, profit_factor, cumulative_return, max_drawdown, bars_in_period, bars_buffer): quote "
    "them, never overwrite or re-emit them."
)
COMPLETE_BACKTEST_SENTENCE = (
    " The tables of saniti.backtest are re-run by the backend on the bundle prices from their signal dates: "
    "final_status.backtests lists each (PASS, FAIL with CALCULATION_MISMATCH, INVALID); the signals themselves are "
    "the code's and are not recomputed."
)
COMPLETE_EVENT_STUDY_SENTENCE = (
    " Exception: the tables of saniti.event_study are recomputed by the backend from their declaration. "
    "final_status.event_studies lists each study (PASS, FAIL with CALCULATION_MISMATCH, INVALID) and "
    "verified_output_ids the matched tables; calculation_validation is then PARTIAL (other outputs exist) or "
    "FORMULA_AND_STATISTICS_VERIFIED. Only those tables may be called independently recalculated; a FAIL makes the "
    "completion INCOMPLETE: run the event study again and complete again."
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
RESULT_STORE_VERSION = 1  # R-STORE: the sandbox's output file and carried restore routes
SESSION_RELEASE_VERSION = 2  # S28: the sandbox's POST /v1/requests/{request_id}/release; 2 (EXEC-V 2026-10-08):
# several open sessions per request (max_sessions_per_request), none closed by opening another
NUMBER_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight"}
SESSION_LIMIT_SENTENCE = (
    " Each READY bundle gets its own session. One answer may keep up to {limit} sessions open at once, and opening "
    "one never closes another; activity in any of them keeps all of them open while the answer runs. An open beyond "
    "the limit is refused (SESSION_LIMIT_PER_REQUEST) with this answer's open sessions listed: continue in one of "
    "them, or open again with close_session_id naming a completed or unneeded one of them.")
CAPACITY_OWN_MESSAGE = (
    "Every analysis session slot of the sandbox is in use{waited}. This answer's own sessions stay open: continue in "
    "one of them (open_sessions), or return response_type \"LIMITATION\" for the part that needs another session.")
CAPACITY_MESSAGE = (
    "Every analysis session slot of the sandbox is in use by other requests{waited}. Do not retry open_analysis_session or "
    "prepare_data_bundle in this run: return response_type \"LIMITATION\" saying that the analysis could not start "
    "because the analysis sandbox was busy and that the question can be asked again later."
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


def output_label(body: dict[str, Any], output_id: str, final_status: dict[str, Any] | None) -> str:
    """P5: how the backend checked a released table. The sandbox's own label wins; an older sandbox's is derived from
    the completion the same way (a recomputed event-study table, else the completion's evidence label)."""
    if body.get("label"):
        return str(body["label"])
    status = final_status or {}
    if output_id in (status.get("verified_output_ids") or []):
        return "CALCULATION_VERIFIED"
    return str(status.get("evidence_label") or "DATA_COVERAGE_VERIFIED")


def released_contents(client: SandboxClient, session_id: str, outputs: list[dict[str, Any]], timeout: float,
                      request_id: str, byte_budget: int | None = None,
                      final_status: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """The content of released outputs (bounded), so the answer can cite them and provenance can check them.
    With byte_budget the contents together stay within it, so a wide table cannot push the whole complete_analysis
    result over the tool result limit (which would hide the completion from the model). Each entry carries its label
    (P5), counted inside the budget."""
    contents: list[dict[str, Any]] = []
    for output in outputs[:RELEASED_PREVIEW_OUTPUTS]:
        if output.get("type") not in ("TABLE", "PARQUET", "CSV", "JSON", "TEXT"):
            continue
        body = _call(client, "GET", f"/v1/sessions/{session_id}/outputs/{output['output_id']}", timeout=timeout,
                     params={"request_id": request_id, "offset": 0, "limit": RELEASED_PREVIEW_ROWS})
        if body.get("status") == "REJECTED" or not body.get("released"):
            continue
        entry = {"output_id": output["output_id"], "name": output.get("name"), "type": output.get("type"),
                 "label": output_label(body, output["output_id"], final_status)}
        units = (body.get("meta") or {}).get("units") if isinstance(body.get("meta"), dict) else None
        if units:
            entry["units"] = units  # P23: the declared unit of each column, so a figure is shown by its unit
        meta = body.get("meta") if isinstance(body.get("meta"), dict) else {}
        if isinstance(meta.get("definition"), dict) or isinstance(output.get("definition"), dict):
            # H1 (M63): how the result was made, so the answer and later turns read it instead of guessing
            entry["definition"] = meta.get("definition") if isinstance(meta.get("definition"), dict) \
                else output["definition"]
        if isinstance(output.get("lineage"), dict):
            entry["lineage"] = output["lineage"]
        if "rows" in body:
            entry.update(rows=body["rows"], row_count=body.get("row_count"),
                         truncated=body.get("next_offset") is not None)
        else:
            entry.update(content=body.get("content"), truncated=body.get("next_offset") is not None)
        contents.append(entry)
    return contents if byte_budget is None else _within(contents, byte_budget)


def read_output(client: SandboxClient, session_id: str, output_id: str, request_id: str, offset: int, limit: int,
                timeout: float = 15.0) -> dict[str, Any]:
    """One page of a released output, read by the backend (M44: rows an answer references but the run did not read)."""
    return _call(client, "GET", f"/v1/sessions/{session_id}/outputs/{output_id}", timeout=timeout,
                 params={"request_id": request_id, "offset": offset, "limit": limit})


def release_request(client: SandboxClient, request_id: str, timeout: float = 15.0) -> list[dict[str, Any]]:
    """S28: the answer of this request ended. The sandbox moves each of its sessions that completed to WARM_IDLE
    (reusable, or evicted when a slot is needed) and closes the others; [{session_id, status}]."""
    response = client._call("POST", f"/v1/requests/{request_id}/release", timeout=timeout)
    response.raise_for_status()
    return list(response.json().get("sessions") or [])


def close_sessions(client: SandboxClient, request_id: str, session_ids: list[str], timeout: float = 15.0
                   ) -> dict[str, str]:
    """Close sessions of this request (S05): session_id -> close_reason, or CLOSE_FAILED. The sandbox closes a
    session itself only when complete_analysis passes; any other session would hold one of its few slots until the
    idle timeout. Closing an already closed session is harmless."""
    closed: dict[str, str] = {}
    for session_id in session_ids:
        try:
            body = _call(client, "POST", f"/v1/sessions/{session_id}/close", timeout=timeout,
                         json={"request_id": request_id})
            closed[session_id] = str(body.get("close_reason") or body.get("code") or body.get("status"))
        except Exception:  # noqa: BLE001 - best effort; the sandbox's idle timeout still closes it
            closed[session_id] = "CLOSE_FAILED"
    return closed


def session_specs(client: SandboxClient, *, timeout_seconds: float, execution_timeout_seconds: float,
                  max_result_bytes: int, standard_period_return: bool = False, event_study: bool = False,
                  backtest: bool = False, merged_steps: bool = False, session_limit: int | None = None
                  ) -> list[ToolSpec]:
    def request_id() -> str:
        return current_request_id.get() or ""

    def open_session(arguments: BaseModel) -> dict[str, Any]:
        assert isinstance(arguments, OpenAnalysisSessionArgs)
        closed = None
        close_id = getattr(arguments, "close_session_id", None)
        if close_id:
            # the model's own choice after SESSION_LIMIT_PER_REQUEST; the sandbox closes only a session of this request
            closed = _call(client, "POST", f"/v1/sessions/{close_id}/close", timeout=timeout_seconds,
                           json={"request_id": request_id()})
            if closed.get("status") == "REJECTED":
                return {**closed, "message": f"close_session_id {close_id} was not closed: {closed.get('message')}"}
        body: dict[str, Any] = {"request_id": request_id(), "bundle_id": arguments.input_bundle_id}
        carried = current_carried_outputs.get()
        if carried is not None:
            body["carried_outputs"] = carried
        # S28: the sandbox may wait up to its open_wait_seconds for a slot before it answers
        result = _call(client, "POST", "/v1/sessions", timeout=timeout_seconds + client.open_wait_seconds, json=body)
        restore_into(result, carried)
        if result.get("status") == "REJECTED" and result.get("code") == "SESSION_CAPACITY_EXCEEDED":
            # The sandbox's RETRY_LATER is for callers that can wait; it already waited, and a retry within this run
            # meets the same slots.
            result.pop("retry_after_seconds", None)
            waited = result.get("waited_seconds")
            waited = f" (the sandbox waited {waited} seconds for a slot)" if waited else ""
            if result.get("open_sessions"):
                result.update(message=CAPACITY_OWN_MESSAGE.format(waited=waited), next_action="USE_OPEN_SESSION")
            else:
                result.update(message=CAPACITY_MESSAGE.format(waited=waited), next_action="REPORT_LIMITATION")
        if closed is not None:
            result["closed_session"] = {k: closed.get(k) for k in ("session_id", "status", "close_reason")}
        return result

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
        if arguments.dataset is not None:
            body["dataset"] = arguments.dataset  # D1: the dataset's column statistics, not variables
        return _call(client, "POST", f"/v1/sessions/{arguments.session_id}/inspect", timeout=timeout_seconds,
                     json=body)

    def output(arguments: BaseModel) -> dict[str, Any]:
        assert isinstance(arguments, GetSessionOutputArgs)
        results = current_results.get()
        if arguments.execution_id is not None:
            return read_execution(results, arguments.execution_id, bool(arguments.include_content))
        output_id, session_id = arguments.output_id, arguments.session_id
        if arguments.ref is not None:
            entry = resolve_ref(results.record if results is not None else {}, arguments.ref)
            if entry is None:
                return {"status": "REJECTED", "code": "REF_NOT_FOUND", "next_action": "FIX_ARGUMENTS",
                        "message": "No output of this conversation has this reference; the data record lists them."}
            output_id, session_id = str(entry["output_id"]), entry.get("session_id")
        result = read_output_any(client, session_id, str(output_id), request_id(), arguments.offset or 0,
                                 arguments.limit or 50, timeout_seconds)
        if session_id and "session_id" not in result and result.get("status") != "REJECTED":
            result["session_id"] = session_id  # the owner, for value references (the call may have named a ref)
        return result

    def complete(arguments: BaseModel) -> dict[str, Any]:
        assert isinstance(arguments, CompleteAnalysisArgs)
        result = _call(client, "POST", f"/v1/sessions/{arguments.session_id}/complete", timeout=timeout_seconds * 2,
                       json={"request_id": request_id()})
        if result.get("status") == "COMPLETED" and result.get("released_outputs"):
            envelope = _size({"ok": True, "tool": "complete_analysis", "result": {**result, "released_contents": []}})
            result["released_contents"] = released_contents(
                client, arguments.session_id, result["released_outputs"], timeout_seconds, request_id(),
                byte_budget=max(0, max_result_bytes - envelope - RESULT_ENVELOPE_MARGIN),
                final_status=result.get("final_status"))
        return result

    return [
        ToolSpec(name="complete_analysis", effect="COMPUTES",
                 description=COMPLETE_DESCRIPTION + (COMPLETE_EVENT_STUDY_SENTENCE if event_study else "")
                 + (COMPLETE_BACKTEST_SENTENCE if backtest else ""),
                 arguments_model=CompleteAnalysisArgs,
                 handler=complete, timeout_seconds=timeout_seconds * 4, max_result_bytes=max_result_bytes),
        ToolSpec(name="open_analysis_session", effect="COMPUTES",
                 description=OPEN_DESCRIPTION + (SESSION_LIMIT_SENTENCE.format(
                     limit=NUMBER_WORDS.get(session_limit, str(session_limit))) if session_limit else ""),
                 arguments_model=OpenAnalysisSessionLimitArgs if session_limit else OpenAnalysisSessionArgs,
                 handler=open_session, timeout_seconds=timeout_seconds + 30, max_result_bytes=max_result_bytes),
        ToolSpec(name="run_python", effect="COMPUTES", description=RUN_DESCRIPTION + (PERIOD_RETURN_SENTENCE if standard_period_return
                                                                   else "")
                 + (EVENT_STUDY_SENTENCE if event_study else "") + (BACKTEST_SENTENCE if backtest else ""),
                 arguments_model=RunPythonCompleteArgs if merged_steps else RunPythonArgs, handler=run,
                 timeout_seconds=execution_timeout_seconds + 5, max_result_bytes=max_result_bytes),
        ToolSpec(name="inspect_session", effect="READS", description=INSPECT_DESCRIPTION, arguments_model=InspectSessionArgs,
                 handler=inspect, timeout_seconds=timeout_seconds + 5, max_result_bytes=max_result_bytes),
        ToolSpec(name="get_session_output", effect="READS", description=OUTPUT_DESCRIPTION, arguments_model=GetSessionOutputArgs,
                 handler=output, timeout_seconds=timeout_seconds + 5, max_result_bytes=max_result_bytes),
    ]
