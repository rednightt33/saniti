from __future__ import annotations

import json
import socket
import threading
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .compaction import compact_result, dumps, estimate_tokens
from .config import Settings
from .db import Database
from .openai_client import ResponsesClient
from .schemas import FINAL_RESPONSE_SCHEMA, FinalAnalysis
from .tools import ToolError, ToolRegistry


INSTRUCTIONS = """You are the private Saniti Indonesian-market analyst.
Use only supplied catalog-driven tools and never invent data. Begin with freshness,
quality, and feature discovery. Expand to QUERY/SCREENING only through list_tools
when evidence makes it necessary. Release 1B has no historical-validation worker:
do not claim causation or predictive evidence. Necessary follow-up queries should
run automatically within limits; optional deeper work belongs in
recommended_next_analysis. Treat extreme source-valid observations as useful
anomalies, not automatically bad data. Cite recorded evidence IDs for material
claims. State data-ready date, point-in-time/current-classification limitations,
and survivorship limitations where relevant. Do not confuse database rows with
LLM-facing rows: prefer aggregation/ranking and compact evidence.
Before executing a data-retrieval or aggregation tool, load the definitions of
every relevant output, filter, ordering, grouping, and metric column with
get_feature_definition. If semantic preflight reports missing definitions, load
exactly those definitions and retry; never load the entire catalog by default.
Copy exact case-sensitive Feature table and column identifiers from discovery
results; never abbreviate them. estimate_query_size already performs structured
query validation, so do not also call validate_query_request for the same payload.
For an obviously bounded single-ticker/single-date retrieval, call query_features
directly because it also enforces validation and limits; estimate first only when
row cost is genuinely uncertain. Request only the tool families needed for the
question; do not request ADVANCED for ordinary retrieval.
After necessary follow-ups, prefer one consolidated record_evidence call containing
the decisive observations, quality result, and query hashes. Use separate evidence
items only when independent claims genuinely require them. Evidence storage does not
end the investigation. When the current question is reliably answered and all
necessary follow-ups are complete, call complete_analysis. Only a successful
complete_analysis call signals finalization; optional deeper work belongs in
recommended_next_analysis and must not be run merely because capacity remains.
Return the final schema JSON without Markdown fences or surrounding prose.
"""

ANALYTICAL_DATA_TOOLS = {
    "query_features", "get_timeseries", "compare_periods", "screen_features",
    "rank_features", "aggregate_features", "compare_groups", "find_condition_runs",
}


@dataclass
class RunState:
    request_id: str
    question: str
    families: set[str]
    input_items: list[dict[str, Any]]
    cumulative_input: int = 0
    cumulative_output: int = 0
    tool_result_tokens: int = 0
    feature_metadata_tokens: int = 0
    history_tokens: int = 0
    tool_calls: int = 0
    iterations: int = 0
    compactions: int = 0
    peak_context: int = 0
    evidence_digest: list[dict[str, Any]] = field(default_factory=list)
    recorded_evidence_ids: set[str] = field(default_factory=set)
    features_used: set[str] = field(default_factory=set)
    analysis_ready_date: str | None = None
    last_openai_response_id: str | None = None
    point_in_time_warnings: set[str] = field(default_factory=set)
    loaded_feature_definitions: set[tuple[str, str]] = field(default_factory=set)
    analytical_query_hashes: set[str] = field(default_factory=set)
    quality_failures: list[dict[str, Any]] = field(default_factory=list)
    analysis_mode: str = "QUICK"
    completion_reason: str | None = None
    started_monotonic: float = field(default_factory=time.monotonic)
    finalization_ready: bool = False


class AnalysisOrchestrator:
    def __init__(self, db: Database, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.tools = ToolRegistry(db, settings)
        self.client = ResponsesClient(
            settings.ai_provider, settings.ai_api_key, settings.ai_request_timeout_seconds
        )

    def run(self, request_id: str, question: str) -> None:
        initial_stage = self._initial_stage(question)
        families = self._initial_families(question)
        state = RunState(
            request_id=request_id,
            question=question,
            families=families,
            input_items=[{"role": "user", "content": question}],
            analysis_mode=self.settings.ai_analysis_mode,
        )
        try:
            self._mark_processing(state, initial_stage)
            answer = self._tool_loop(state)
            self._finish_success(state, answer)
        except Exception as exc:
            self._finish_failed(state, exc)

    def close(self) -> None:
        self.client.close()

    def _tool_loop(self, state: RunState) -> dict[str, Any]:
        while state.iterations < self.settings.ai_max_tool_iterations:
            self._enforce_budgets(state)
            self._compact_context_if_needed(state)
            instructions = self._instructions(state)
            active_tools = [] if state.finalization_ready else self.tools.definitions(state.families)
            context_tokens = estimate_tokens({"instructions": instructions, "input": state.input_items, "tools": active_tools})
            state.peak_context = max(state.peak_context, context_tokens)
            if context_tokens + self.settings.ai_context_reserve_tokens > self.settings.ai_max_context_tokens:
                raise RuntimeError("Hard AI context ceiling would be exceeded")
            payload = {
                "model": self.settings.ai_model,
                "reasoning": {"effort": self.settings.ai_reasoning_effort},
                "instructions": instructions,
                "input": state.input_items,
                "max_output_tokens": self.settings.ai_max_output_tokens,
                "store": False,
                "text": {"format": {"type": "json_schema", "name": "market_analysis", "schema": FINAL_RESPONSE_SCHEMA, "strict": True}},
            }
            if active_tools:
                payload["tools"] = active_tools
                payload["parallel_tool_calls"] = False
            response = self.client.create(payload)
            state.iterations += 1
            self._add_usage(state, response)
            calls = [item for item in response.get("output", []) if item.get("type") == "function_call"]
            if not calls:
                raw = self._output_text(response)
                if not raw:
                    raise RuntimeError(f"{self.settings.ai_provider} returned neither a function call nor a final answer")
                try:
                    answer = self._parse_final_output(raw)
                except RuntimeError as exc:
                    self._continue_after_rejected_final(
                        state,
                        response,
                        "The prior final response did not match the required JSON schema. "
                        "Continue any unfinished analysis, then return every required final field as schema-valid JSON.",
                    )
                    if state.iterations >= self.settings.ai_max_tool_iterations:
                        raise exc
                    continue
                issue = self._final_contract_issue(state, answer)
                if issue:
                    self._continue_after_rejected_final(state, response, issue)
                    if state.iterations >= self.settings.ai_max_tool_iterations:
                        raise RuntimeError(issue)
                    continue
                return answer

            state.input_items.extend(self._response_items(response))
            for call in calls:
                if state.tool_calls >= self.settings.ai_max_tool_calls:
                    raise RuntimeError("AI_MAX_TOOL_CALLS reached before sufficient evidence")
                name = call["name"]
                arguments = json.loads(call["arguments"])
                result = self._execute_and_log(state, name, arguments)
                state.input_items.append({"type": "function_call_output", "call_id": call["call_id"], "output": dumps(result)})
        raise RuntimeError("AI_MAX_TOOL_ITERATIONS reached before final answer")

    @staticmethod
    def _response_items(response: dict[str, Any]) -> list[dict[str, Any]]:
        return [item for item in response.get("output", []) if isinstance(item, dict)]

    @staticmethod
    def _output_text(response: dict[str, Any]) -> str:
        parts: list[str] = []
        for item in response.get("output", []):
            if item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                    parts.append(content["text"])
        return "".join(parts)

    @staticmethod
    def _parse_final_output(raw: str) -> dict[str, Any]:
        candidate = raw.strip()
        if candidate.startswith("```"):
            lines = candidate.splitlines()
            if len(lines) < 3 or lines[0].strip().lower() not in {"```", "```json"} or lines[-1].strip() != "```":
                raise RuntimeError("Final structured output used an invalid Markdown wrapper")
            candidate = "\n".join(lines[1:-1]).strip()
        try:
            return FinalAnalysis.model_validate_json(candidate).model_dump(mode="json")
        except Exception as exc:
            raise RuntimeError(
                f"Final structured output validation failed (characters={len(candidate)})"
            ) from exc

    @staticmethod
    def _final_contract_issue(state: RunState, answer: dict[str, Any]) -> str | None:
        cited = set(answer.get("evidence_ids") or [])
        if not state.recorded_evidence_ids:
            return (
                "Do not finish yet. Retrieve sufficient evidence for the question and call "
                "record_evidence before returning the final answer."
            )
        if not cited:
            return "The final answer must cite at least one evidence ID returned by record_evidence."
        unknown = sorted(cited - state.recorded_evidence_ids)
        if unknown:
            return (
                "The final answer cited unverified evidence IDs. Cite only exact IDs returned by "
                f"record_evidence in this request; unknown IDs: {unknown}."
            )
        return None

    def _continue_after_rejected_final(
        self, state: RunState, response: dict[str, Any], instruction: str
    ) -> None:
        state.input_items.extend(self._response_items(response))
        state.input_items.append({"role": "user", "content": instruction})
        self._persist_usage(state)

    def _execute_and_log(self, state: RunState, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        state.tool_calls += 1
        step_number = state.tool_calls + state.compactions
        sanitized = self._sanitize(arguments)
        try:
            self._require_loaded_definitions(state, name, arguments)
            if name == "complete_analysis":
                self._validate_completion(state, arguments)
            execution = self.tools.execute(name, arguments, state.request_id)
            if name == "list_tools":
                state.families.update(execution.payload.get("approved_expansion") or [])
            if name in {"query_features", "get_timeseries", "screen_features", "rank_features", "aggregate_features", "compare_groups", "compare_periods", "find_condition_runs"}:
                table = arguments.get("table")
                if table:
                    state.features_used.add(table)
            if name == "check_data_freshness":
                state.analysis_ready_date = execution.payload.get("analysis_ready_date")
            if name == "get_feature_definition":
                state.loaded_feature_definitions.update(
                    (str(row["feature_table"]), str(row["feature_column"]))
                    for row in execution.payload.get("rows", [])
                )
            if name in ANALYTICAL_DATA_TOOLS and execution.query_hash:
                state.analytical_query_hashes.add(str(execution.query_hash))
            if name == "check_data_quality" and execution.payload.get("classification") == "FAIL":
                state.quality_failures.append({
                    "table": arguments.get("table"),
                    "tickers": arguments.get("tickers"),
                    "start_date": arguments.get("start_date"),
                    "end_date": arguments.get("end_date"),
                })
            if name == "record_evidence" and execution.payload.get("evidence_id"):
                state.recorded_evidence_ids.add(str(execution.payload["evidence_id"]))
                required_queries = (
                    self.settings.ai_min_insight_data_calls
                    if state.analysis_mode == "INSIGHT" and self._initial_stage(state.question) == "SCREENING"
                    else 0
                )
                execution.payload["completion_policy"] = {
                    "distinct_analytical_queries": len(state.analytical_query_hashes),
                    "required_distinct_analytical_queries": required_queries,
                    "next_action": (
                        "Call complete_analysis now if all necessary follow-ups are complete."
                        if len(state.analytical_query_hashes) >= required_queries
                        else "Continue with a distinct necessary analytical follow-up before complete_analysis."
                    ),
                }
            if name == "complete_analysis" and execution.payload.get("completion_accepted"):
                state.completion_reason = arguments["completion_reason"].strip()
                state.finalization_ready = True
            state.point_in_time_warnings.update(execution.payload.get("point_in_time_warnings") or [])

            remaining = self.settings.ai_max_tool_result_tokens_total - state.tool_result_tokens
            if remaining <= 0:
                raise RuntimeError("Cumulative LLM tool-result budget exhausted")
            per_call_tokens = min(self.settings.ai_max_tool_result_tokens_per_call, remaining)
            compact, tokens, compacted = compact_result(
                execution.payload,
                max_rows=self.settings.llm_tool_result_max_rows,
                max_bytes=self.settings.llm_tool_result_max_bytes,
                max_tokens=per_call_tokens,
            )
            state.tool_result_tokens += tokens
            if name == "get_feature_definition":
                state.feature_metadata_tokens += tokens
                if state.feature_metadata_tokens > self.settings.ai_max_feature_metadata_tokens:
                    raise RuntimeError("Feature metadata token budget exceeded")
            if name == "get_analysis_history":
                state.history_tokens += tokens
                if state.history_tokens > self.settings.ai_max_history_tokens:
                    raise RuntimeError("Analysis history token budget exceeded")
            digest = {
                "tool": name, "query_hash": execution.query_hash,
                "summary": {key: compact.get(key) for key in ("table", "total_rows", "classification", "analysis_ready_date", "warnings", "selection") if key in compact},
            }
            state.evidence_digest.append(digest)
            self._log_step(
                state, step_number, name, sanitized, "COMPACTED" if compacted else "SUCCESS",
                execution=execution, llm_tokens=tokens, result_summary=digest["summary"],
            )
            self._persist_usage(state)
            return compact
        except Exception as exc:
            self._log_step(state, step_number, name, sanitized, "FAILED", error=str(exc)[:1000])
            if isinstance(exc, (ToolError, RuntimeError)):
                return {"error": str(exc), "recoverable": isinstance(exc, ToolError)}
            raise

    def _compact_context_if_needed(self, state: RunState) -> None:
        context = estimate_tokens({"instructions": self._instructions(state), "input": state.input_items, "tools": self.tools.definitions(state.families)})
        if context <= self.settings.ai_context_compaction_threshold_tokens:
            return
        digest = {
            "prior_analysis_digest": state.evidence_digest,
            "loaded_feature_definitions": [
                {"table": table, "column": column}
                for table, column in sorted(state.loaded_feature_definitions)
            ],
            "instruction": "Earlier tool outputs were superseded and compacted. Use hashes/evidence summaries; re-query only if necessary.",
        }
        state.input_items = [
            {"role": "user", "content": state.question},
            {"role": "user", "content": dumps(digest)},
        ]
        state.compactions += 1
        self._log_step(state, state.tool_calls + state.compactions, None, {}, "COMPACTED", result_summary={"reason": "context_threshold", "prior_context_tokens": context})

    def _enforce_budgets(self, state: RunState) -> None:
        if time.monotonic() - state.started_monotonic >= self.settings.ai_max_analysis_seconds:
            raise RuntimeError("Maximum analysis wall-clock budget exhausted")
        if state.cumulative_input >= self.settings.ai_max_cumulative_input_tokens:
            raise RuntimeError("Cumulative AI input token budget exhausted")
        if state.cumulative_output >= self.settings.ai_max_cumulative_output_tokens:
            raise RuntimeError("Cumulative AI output token budget exhausted")

    def _add_usage(self, state: RunState, response: Any) -> None:
        usage = response.get("usage") or {}
        input_tokens = int(usage.get("input_tokens", 0) or 0)
        output_tokens = int(usage.get("output_tokens", 0) or 0)
        if input_tokens > self.settings.ai_max_context_tokens:
            raise RuntimeError("OpenAI-reported input exceeded AI_MAX_CONTEXT_TOKENS")
        state.last_openai_response_id = response.get("id") or state.last_openai_response_id
        state.cumulative_input += input_tokens
        state.cumulative_output += output_tokens
        self._enforce_budgets(state)

    def _mark_processing(self, state: RunState, stage: str) -> None:
        with self.db.connection() as connection, connection.transaction():
            connection.execute(
                '''UPDATE public."Analysis_Request"
                   SET status='PROCESSING', current_stage=%s, exposed_tool_families=%s,
                       model=%s, started_at=COALESCE(started_at,clock_timestamp()),
                       lease_owner=%s, lease_expires_at=clock_timestamp() + make_interval(secs => %s),
                       attempt_count=attempt_count+1
                   WHERE request_id=%s''',
                (stage, sorted(state.families), self.settings.ai_model, socket.gethostname(), self.settings.worker_lease_seconds, state.request_id),
            )

    def _persist_usage(self, state: RunState) -> None:
        context = estimate_tokens({"instructions": self._instructions(state), "input": state.input_items})
        state.peak_context = max(state.peak_context, context)
        with self.db.connection() as connection, connection.transaction():
            connection.execute(
                '''UPDATE public."Analysis_Request" SET input_tokens=%s,output_tokens=%s,total_tokens=%s,
                     tool_result_tokens=%s,history_tokens=%s,feature_metadata_tokens=%s,
                     tool_call_count=%s,tool_iteration_count=%s,context_compaction_count=%s,
                     current_context_tokens=%s,peak_context_tokens=%s,exposed_tool_families=%s,
                     openai_response_id=%s,
                     lease_expires_at=clock_timestamp() + make_interval(secs => %s)
                   WHERE request_id=%s''',
                (state.cumulative_input, state.cumulative_output, state.cumulative_input + state.cumulative_output,
                 state.tool_result_tokens, state.history_tokens, state.feature_metadata_tokens,
                 state.tool_calls, state.iterations, state.compactions, context, state.peak_context,
                 sorted(state.families), state.last_openai_response_id,
                 self.settings.worker_lease_seconds, state.request_id),
            )

    def _finish_success(self, state: RunState, answer: dict[str, Any]) -> None:
        recommended = answer.get("recommended_next_analysis") or []
        answer_ready = answer.get("analysis_ready_date") or state.analysis_ready_date
        answer["analysis_ready_date"] = answer_ready
        snapshot, methodology = self._snapshots(state)
        with self.db.connection() as connection, connection.transaction():
            connection.execute(
                '''UPDATE public."Analysis_Request" SET status='SUCCESS',current_stage='FINAL',
                     analysis_ready_date=%s,features_used=%s,answer=%s,recommended_next_analysis=%s,
                     input_tokens=%s,output_tokens=%s,total_tokens=%s,tool_result_tokens=%s,
                     history_tokens=%s,feature_metadata_tokens=%s,tool_call_count=%s,
                     tool_iteration_count=%s,context_compaction_count=%s,current_context_tokens=%s,
                     peak_context_tokens=%s,openai_response_id=%s,
                     version_snapshot=%s,methodology_metadata=%s,
                     lease_owner=NULL,lease_expires_at=NULL,completed_at=clock_timestamp()
                   WHERE request_id=%s''',
                (answer_ready, sorted(state.features_used), json.dumps(answer), json.dumps(recommended),
                 state.cumulative_input, state.cumulative_output, state.cumulative_input + state.cumulative_output,
                 state.tool_result_tokens, state.history_tokens, state.feature_metadata_tokens,
                 state.tool_calls, state.iterations, state.compactions, 0, state.peak_context,
                 state.last_openai_response_id, json.dumps(snapshot), json.dumps(methodology), state.request_id),
            )

    def _finish_failed(self, state: RunState, exc: Exception) -> None:
        message = f"{type(exc).__name__}: {exc}"[:2000]
        print(json.dumps({"event": "analysis_failed", "request_id": state.request_id, "error": message, "trace": traceback.format_exc(limit=5)}), flush=True)
        with self.db.connection() as connection, connection.transaction():
            connection.execute(
                '''UPDATE public."Analysis_Request" SET status='FAILED',error_message=%s,
                     input_tokens=%s,output_tokens=%s,total_tokens=%s,tool_result_tokens=%s,
                     tool_call_count=%s,tool_iteration_count=%s,context_compaction_count=%s,
                     current_context_tokens=0,peak_context_tokens=%s,openai_response_id=%s,lease_owner=NULL,
                     lease_expires_at=NULL,completed_at=clock_timestamp() WHERE request_id=%s''',
                (message, state.cumulative_input, state.cumulative_output, state.cumulative_input + state.cumulative_output,
                 state.tool_result_tokens, state.tool_calls, state.iterations, state.compactions,
                 state.peak_context, state.last_openai_response_id, state.request_id),
            )

    def _snapshots(self, state: RunState) -> tuple[dict[str, Any], dict[str, Any]]:
        with self.db.query_transaction() as connection:
            feature_versions = connection.execute(
                '''SELECT feature_table,version,count(*)::integer AS columns
                   FROM public."Feature_Catalog" WHERE is_active AND feature_table=ANY(%s)
                   GROUP BY feature_table,version ORDER BY feature_table,version''',
                (sorted(state.features_used),),
            ).fetchall() if state.features_used else []
            tool_versions = connection.execute(
                '''SELECT tool_name,version FROM public."Tool_Catalog" WHERE is_active ORDER BY tool_name'''
            ).fetchall()
        snapshot = {
            "provider": self.settings.ai_provider, "model": self.settings.ai_model,
            "orchestrator_version": "release-1b-v2", "prompt_version": "release-1b-v2",
            "analysis_mode": state.analysis_mode,
            "max_analysis_seconds": self.settings.ai_max_analysis_seconds,
            "completion_reason": state.completion_reason,
            "distinct_analytical_queries": len(state.analytical_query_hashes),
            "feature_versions": [dict(row) for row in feature_versions],
            "tool_versions": [dict(row) for row in tool_versions],
            "query_hashes": sorted({item["query_hash"] for item in state.evidence_digest if item.get("query_hash")}),
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
        methodology = {
            "analysis_ready_date": state.analysis_ready_date,
            "universe_mode": "current_universe_or_source_coverage",
            "survivorship_warning": "Current universe/reference metadata can introduce survivorship bias in historical comparisons.",
            "point_in_time_warnings": sorted(state.point_in_time_warnings),
            "look_ahead_validation": "No predictive claim is allowed in Release 1B; historical-validation tools are inactive.",
        }
        return snapshot, methodology

    def _instructions(self, state: RunState) -> str:
        if state.analysis_mode != "INSIGHT":
            return INSTRUCTIONS + "\nAnalysis mode QUICK: answer once direct evidence is sufficient.\n"
        return INSTRUCTIONS + (
            "\nAnalysis mode INSIGHT: for a data or screening question, do not stop at the first "
            "descriptive result. Run at least one distinct high-value follow-up that is necessary "
            "to interpret the result, such as a relevant comparison, persistence check, volume/"
            "volatility context, or broader benchmark, while staying within available Feature "
            "1-3 data and resource limits. Do not run optional deep exploration.\n"
        )

    def _validate_completion(self, state: RunState, arguments: dict[str, Any]) -> None:
        if not state.recorded_evidence_ids:
            raise ToolError("Record at least one evidence item before complete_analysis")
        if arguments.get("evidence_sufficient") is not True:
            raise ToolError("Evidence is not yet sufficient for completion")
        if arguments.get("necessary_followups_completed") is not True:
            raise ToolError("Necessary follow-up analysis is not yet complete")
        if (
            state.analysis_mode == "INSIGHT"
            and self._initial_stage(state.question) == "SCREENING"
            and not state.quality_failures
            and len(state.analytical_query_hashes) < self.settings.ai_min_insight_data_calls
        ):
            raise ToolError(
                "INSIGHT mode requires at least "
                f"{self.settings.ai_min_insight_data_calls} distinct successful analytical queries "
                "before completion; run a justified follow-up, not a duplicate query"
            )

    @staticmethod
    def _semantic_requirements(name: str, arguments: dict[str, Any]) -> set[tuple[str, str]]:
        table = str(arguments.get("table") or "")
        if not table:
            return set()
        columns: set[str] = set()
        if name in {"query_features", "screen_features"}:
            columns.update(arguments.get("columns") or [])
            columns.update(item.get("column") for item in arguments.get("filters") or [])
            columns.update(item.get("column") for item in arguments.get("order_by") or [])
        elif name == "get_timeseries":
            columns.update(["date", "ticker", *(arguments.get("columns") or [])])
        elif name == "rank_features":
            columns.update(["date", "ticker", arguments.get("column")])
        elif name == "aggregate_features":
            columns.update(arguments.get("group_by") or [])
            columns.update(item.get("column") for item in arguments.get("metrics") or [])
        elif name == "compare_groups":
            columns.update([arguments.get("group_column"), arguments.get("metric_column")])
        elif name == "compare_periods":
            columns.update(["ticker", arguments.get("column")])
        elif name == "find_condition_runs":
            columns.update(["date", "ticker"])
            columns.update(item.get("column") for item in arguments.get("conditions") or [])
        return {(table, column) for column in columns if isinstance(column, str) and column}

    def _require_loaded_definitions(
        self, state: RunState, name: str, arguments: dict[str, Any]
    ) -> None:
        required = self._semantic_requirements(name, arguments)
        missing = sorted(required - state.loaded_feature_definitions)
        if missing:
            detail = [{"table": table, "column": column} for table, column in missing]
            raise ToolError(
                "Semantic definitions must be loaded with get_feature_definition before data execution: "
                + json.dumps(detail, separators=(",", ":"))
            )

    def _log_step(self, state: RunState, step_number: int, tool_name: str | None, arguments: dict[str, Any], status: str, *, execution: Any = None, llm_tokens: int | None = None, result_summary: dict[str, Any] | None = None, error: str | None = None) -> None:
        with self.db.connection() as connection, connection.transaction():
            connection.execute(
                '''INSERT INTO public."Analysis_Step_Log"
                     (request_id,step_number,stage,tool_name,sanitized_arguments,estimated_rows,
                      processed_rows,returned_rows,returned_bytes,llm_result_tokens,duration_ms,
                      query_hash,result_summary,status,error_message)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (request_id,step_number) DO UPDATE SET status=EXCLUDED.status,
                     error_message=EXCLUDED.error_message,result_summary=EXCLUDED.result_summary''',
                (state.request_id, step_number, self._stage_for(state.families), tool_name, json.dumps(arguments),
                 getattr(execution, "estimated_rows", None), getattr(execution, "processed_rows", None),
                 len(execution.payload.get("rows") or []) if execution else None,
                 len(dumps(execution.payload).encode("utf-8")) if execution else None,
                 llm_tokens, getattr(execution, "duration_ms", None), getattr(execution, "query_hash", None),
                 json.dumps(result_summary) if result_summary is not None else None, status, error),
            )

    @staticmethod
    def _sanitize(arguments: dict[str, Any]) -> dict[str, Any]:
        # Tool schemas contain no credentials; cap audit payloads defensively.
        encoded = dumps(arguments)
        return arguments if len(encoded) <= 16000 else {"compacted": True, "keys": sorted(arguments)}

    @staticmethod
    def _initial_stage(question: str) -> str:
        text = question.lower()
        screening_terms = (
            "screen", "rank", "top ", "bottom ", "banding", "compare", "perbandingan",
            "tertinggi", "terendah", "find ", "report ", "show ", "retrieve ", "cari ",
            "tampilkan ", "laporkan ", "berapa ", "berturut", "consecutive", "streak",
        )
        return "SCREENING" if any(term in text for term in screening_terms) else "DISCOVERY"

    @classmethod
    def _initial_families(cls, question: str) -> set[str]:
        if cls._initial_stage(question) == "DISCOVERY":
            return set(ToolRegistry.CORE_FAMILIES)
        families = set(ToolRegistry.CORE_FAMILIES) | {"QUERY"}
        text = question.lower()
        screening_terms = (
            "screen", "rank", "top ", "bottom ", "tertinggi", "terendah",
            "saring", "peringkat", "mana saja", "daftar saham", "list saham",
            "berturut", "consecutive", "streak", "rangkaian kondisi",
        )
        if any(term in text for term in screening_terms):
            families.add("SCREENING")
        return families

    @staticmethod
    def _stage_for(families: set[str]) -> str:
        if "ADVANCED" in families:
            return "ADVANCED"
        if "HISTORICAL_VALIDATION" in families:
            return "HISTORICAL_VALIDATION"
        if "QUERY" in families or "SCREENING" in families:
            return "SCREENING"
        return "DISCOVERY"


class AnalysisWorker:
    def __init__(self, db: Database, settings: Settings, orchestrator: AnalysisOrchestrator) -> None:
        self.db = db
        self.settings = settings
        self.orchestrator = orchestrator
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.owner = f"{socket.gethostname()}:{threading.get_native_id()}"

    def start(self) -> None:
        self.thread = threading.Thread(target=self._loop, name="analysis-worker", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=10)

    def _loop(self) -> None:
        while not self.stop_event.is_set():
            claimed = self._claim()
            if claimed:
                self.orchestrator.run(str(claimed["request_id"]), claimed["question"])
            else:
                self.stop_event.wait(self.settings.worker_poll_seconds)

    def _claim(self) -> dict[str, Any] | None:
        with self.db.connection() as connection, connection.transaction():
            row = connection.execute(
                '''SELECT request_id,question FROM public."Analysis_Request"
                   WHERE status='PENDING' OR (status='PROCESSING' AND lease_expires_at < clock_timestamp())
                   ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1'''
            ).fetchone()
            if not row:
                return None
            connection.execute(
                '''UPDATE public."Analysis_Request" SET status='PROCESSING',lease_owner=%s,
                     lease_expires_at=clock_timestamp()+make_interval(secs=>%s)
                   WHERE request_id=%s''',
                (self.owner, self.settings.worker_lease_seconds, row["request_id"]),
            )
            return dict(row)
