from __future__ import annotations

import json
import hashlib
import socket
import threading
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .compaction import compact_result, decisive_digest, dumps, estimate_tokens
from .config import Settings
from .db import Database
from .analytics_store import AnalyticsSnapshotStore
from .openai_client import ResponsesClient, extract_reasoning_audit, response_usage
from .schemas import FINAL_RESPONSE_SCHEMA, FinalAnalysis
from .tools import ToolError, ToolRegistry


INSTRUCTIONS = """You are the private Saniti Indonesian-market analyst.
Use only supplied catalog-driven tools and never invent data. Begin with the smallest
operation needed for the question. Reuse exact identifiers already known in the
current analysis; use discovery or freshness only when they are genuinely unknown.
Expand tool families when evidence makes it necessary. A bounded generic Analytics
Worker is available for historical validation; it receives immutable Feature snapshots,
never database credentials. Necessary follow-up queries should
run automatically within limits; optional deeper work belongs in
recommended_next_analysis. Treat extreme source-valid observations as useful
anomalies, not automatically bad data. Cite recorded evidence IDs for material
claims. State data-ready date, point-in-time/current-classification limitations,
and survivorship limitations where relevant. Do not confuse database rows with
LLM-facing rows: prefer aggregation/ranking and compact evidence.
The orchestrator automatically loads compact semantics for every relevant output,
filter, ordering, grouping, metric, and condition column before data execution.
Use get_feature_definition only when complete formula/methodology detail is needed;
do not repeat discovery when the exact catalog identifier is already known. Never
load the entire catalog by default.
Copy exact case-sensitive Feature table and column identifiers from discovery
results; never abbreviate them. estimate_query_size already performs structured
query validation, so do not also call validate_query_request for the same payload.
For an obviously bounded single-ticker/single-date retrieval, call query_features
directly because it also enforces validation and limits; estimate first only when
row cost is genuinely uncertain. Request only the tool families needed for the
question; do not request ADVANCED for ordinary retrieval.
check_data_quality is conditional, not a mandatory pre-query ritual. Invoke it only
when a result exposes missing coverage, NULL/gap concerns, stale/cross-feature state,
an anomaly needing source validation, or when scoped quality evidence is material to
the conclusion. For a long find_condition_runs search, check only qualifying episode
neighborhoods needed for interpretation; never scan the full multi-year search span
merely because a quality tool exists. WARNING and PASS-with-anomaly continue analysis;
only an impossible/invalid FAIL blocks the affected conclusion.
After necessary follow-ups, prefer one consolidated record_evidence call containing
the decisive observations, quality result, and query hashes. Use separate evidence
items only when independent claims genuinely require them. Evidence storage does not
end the investigation. When the current question is reliably answered and all
necessary follow-ups are complete, call complete_analysis. Only a successful
complete_analysis call signals finalization; optional deeper work belongs in
recommended_next_analysis and must not be run merely because capacity remains.
Once record_evidence confirms that the minimum analytical-query requirement is
met, the backend locks all data tools. Call complete_analysis next; after it is
accepted, produce only the final structured answer.
Return the final schema JSON without Markdown fences or surrounding prose.
"""

ANALYTICAL_DATA_TOOLS = {
    "query_features", "get_timeseries", "compare_periods", "screen_features",
    "rank_features", "aggregate_features", "compare_groups", "find_condition_runs",
    "run_analytics_job",
}
FINALIZATION_TOOLS = {"record_evidence", "complete_analysis"}


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
    completion_only: bool = False
    final_rejections: int = 0
    cumulative_pressure_compacted: bool = False
    attempt_number: int = 0
    discovery_calls: int = 0
    tool_cache: dict[str, dict[str, Any]] = field(default_factory=dict)
    analytics_handoff: str = ""
    historical_universe_ready: bool = False
    analytics_job_attempted: bool = False


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
            input_items=[],
            analysis_mode=self.settings.ai_analysis_mode,
        )
        state.analytics_handoff = self._analytics_handoff()
        state.input_items = [
            {"role": "user", "content": state.analytics_handoff},
            {"role": "user", "content": question},
        ]
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
            active_tools = self._active_tool_definitions(state)
            context_tokens = estimate_tokens({"instructions": instructions, "input": state.input_items, "tools": active_tools})
            state.peak_context = max(state.peak_context, context_tokens)
            if context_tokens + self.settings.ai_context_reserve_tokens > self.settings.ai_max_context_tokens:
                raise RuntimeError("Hard AI context ceiling would be exceeded")
            payload = {
                "model": self.settings.ai_model,
                "reasoning": {"effort": self.settings.ai_reasoning_effort},
                "instructions": instructions,
                "input": state.input_items,
                "max_output_tokens": self._max_output_tokens(state),
                "store": False,
                "text": {"format": {"type": "json_schema", "name": "market_analysis", "schema": FINAL_RESPONSE_SCHEMA, "strict": True}},
            }
            if active_tools:
                payload["tools"] = active_tools
                payload["parallel_tool_calls"] = False
                payload["tool_choice"] = self._required_tool_choice(state)
            response = self.client.create(payload)
            state.iterations += 1
            usage = self._add_usage(state, response)
            self._log_model_call(state, response, context_tokens, usage)
            self._enforce_budgets(state, after_response=True)
            calls = [item for item in response.get("output", []) if item.get("type") == "function_call"]
            if not calls:
                raw = self._output_text(response)
                if not raw:
                    raise RuntimeError(f"{self.settings.ai_provider} returned neither a function call nor a final answer")
                try:
                    answer = self._parse_final_output(raw)
                except RuntimeError as exc:
                    self._reject_final_candidate(state, response, str(exc))
                    continue
                issue = self._final_contract_issue(state, answer)
                if issue:
                    self._reject_final_candidate(state, response, issue)
                    continue
                return answer

            state.input_items.extend(self._response_items(response))
            for call in calls:
                if state.tool_calls >= self.settings.ai_max_tool_calls:
                    raise RuntimeError("AI_MAX_TOOL_CALLS reached before sufficient evidence")
                name = call["name"]
                try:
                    arguments = json.loads(call["arguments"])
                except (json.JSONDecodeError, TypeError) as exc:
                    result = self._recover_malformed_tool_arguments(state, name, call, exc)
                else:
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
            details = []
            if hasattr(exc, "errors"):
                for item in exc.errors(include_url=False)[:8]:
                    location = ".".join(str(part) for part in item.get("loc") or ()) or "root"
                    details.append(f"{location}: {item.get('msg', 'invalid value')}")
            exact_issue = "; ".join(details) if details else f"{type(exc).__name__}: {exc}"
            raise RuntimeError(
                "Final structured output validation failed "
                f"(characters={len(candidate)}): {exact_issue}"
            ) from exc

    @staticmethod
    def _final_contract_issue(state: RunState, answer: dict[str, Any]) -> str | None:
        cited = set(answer.get("evidence_ids") or [])
        if not state.recorded_evidence_ids:
            return (
                "Do not finish yet. Retrieve sufficient evidence for the question and call "
                "record_evidence before returning the final answer."
            )
        if not state.finalization_ready:
            return (
                "Do not return the final answer yet. Call complete_analysis with "
                "evidence_sufficient=true and necessary_followups_completed=true first."
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

    def _reject_final_candidate(
        self, state: RunState, response: dict[str, Any], issue: str
    ) -> None:
        state.final_rejections += 1
        self._log_step(
            state,
            1_000_000 + state.iterations,
            None,
            {},
            "FAILED",
            result_summary={
                "reason": "final_response_rejected",
                "rejection_number": state.final_rejections,
                "maximum_retries": self.settings.ai_final_response_max_retries,
            },
            error=issue[:1000],
        )
        if state.final_rejections > self.settings.ai_final_response_max_retries:
            raise RuntimeError(
                "Final structured output remained invalid after "
                f"{self.settings.ai_final_response_max_retries} retries: {issue}"
            )
        self._continue_after_rejected_final(
            state,
            response,
            f"Final response rejected ({state.final_rejections}/"
            f"{self.settings.ai_final_response_max_retries} retries): {issue} "
            "Correct exactly this issue. Do not run optional analysis. Return every required "
            "field as bare schema-valid JSON.",
        )

    def _active_tool_definitions(self, state: RunState) -> list[dict[str, Any]]:
        if state.finalization_ready:
            return []
        definitions = self.tools.definitions(state.families)
        if state.completion_only:
            return [item for item in definitions if item.get("name") == "complete_analysis"]
        return definitions

    @classmethod
    def _required_tool_choice(cls, state: RunState) -> str | dict[str, str]:
        if state.completion_only:
            return {"type": "function", "name": "complete_analysis"}
        if (
            cls._initial_stage(state.question) == "HISTORICAL_VALIDATION"
            and state.historical_universe_ready
            and not state.analytics_job_attempted
        ):
            return {"type": "function", "name": "run_analytics_job"}
        return "required"

    def _max_output_tokens(self, state: RunState) -> int:
        remaining = self.settings.ai_max_cumulative_output_tokens - state.cumulative_output
        if not state.completion_only and not state.finalization_ready:
            remaining -= self.settings.ai_finalization_output_reserve_tokens
        if remaining <= 0:
            raise RuntimeError("AI output budget available for the current phase is exhausted")
        return min(self.settings.ai_max_output_tokens, remaining)

    def _execute_and_log(self, state: RunState, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        state.tool_calls += 1
        step_number = state.tool_calls + state.compactions
        sanitized = self._sanitize(arguments)
        try:
            if state.finalization_ready:
                raise ToolError("Analysis is complete; only the final structured answer is allowed")
            if state.completion_only and name != "complete_analysis":
                raise ToolError(
                    "Evidence and required analytical queries are complete; data tools are locked. "
                    "Call complete_analysis now."
                )
            remaining, per_call_tokens = self._tool_result_budget(state, name)
            cache_key = ""
            if name in {"find_features", "get_feature_definition", "list_feature_tables"}:
                cache_key = hashlib.sha256(
                    dumps({"tool": name, "arguments": arguments}).encode("utf-8")
                ).hexdigest()
                if cache_key in state.tool_cache:
                    cache_notice = {
                        "reused_from_session_cache": True,
                        "prior_result_digest": decisive_digest(
                            name, state.tool_cache[cache_key]
                        ),
                        "next_action": "Reuse these identifiers; do not repeat discovery.",
                    }
                    tokens = estimate_tokens(cache_notice)
                    state.tool_result_tokens += tokens
                    digest = decisive_digest(name, cache_notice)
                    state.evidence_digest.append(digest)
                    self._log_step(
                        state, step_number, name, sanitized, "SUCCESS",
                        llm_tokens=tokens, result_summary=digest,
                    )
                    self._persist_usage(state)
                    return cache_notice
                if state.discovery_calls >= self.settings.ai_max_discovery_calls:
                    raise ToolError(
                        "Session discovery budget is complete. Use the identifiers already returned, "
                        "execute a bounded data/analytics query, or finish with an explicit limitation."
                    )
                state.discovery_calls += 1
            auto_semantics = self._auto_load_definitions(state, name, arguments)
            if auto_semantics:
                metadata_tokens = estimate_tokens(auto_semantics)
                state.feature_metadata_tokens += metadata_tokens
                if state.feature_metadata_tokens > self.settings.ai_max_feature_metadata_tokens:
                    raise RuntimeError("Feature metadata token budget exceeded")
            if name == "complete_analysis":
                self._validate_completion(state, arguments)
            execution = self.tools.execute(name, arguments, state.request_id)
            if cache_key:
                state.tool_cache[cache_key] = execution.payload
            if auto_semantics:
                execution.payload["auto_loaded_feature_semantics"] = auto_semantics
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
            analytics_success = not (
                name == "run_analytics_job" and execution.payload.get("status") != "SUCCESS"
            )
            if name == "run_analytics_job":
                state.analytics_job_attempted = True
            if (
                self._initial_stage(state.question) == "HISTORICAL_VALIDATION"
                and name == "query_features"
                and "ticker" in (arguments.get("columns") or [])
                and execution.payload.get("rows")
            ):
                state.historical_universe_ready = True
            if name in ANALYTICAL_DATA_TOOLS and execution.query_hash and analytics_success:
                state.analytical_query_hashes.add(str(execution.query_hash))
            if name == "run_analytics_job":
                state.features_used.update(execution.payload.get("source_tables") or [])
                evidence_id = execution.payload.get("evidence_id")
                if evidence_id:
                    state.recorded_evidence_ids.add(str(evidence_id))
                    if (
                        len(state.analytical_query_hashes) >= self._required_analytical_queries(state)
                        and not state.quality_failures
                    ):
                        state.completion_only = True
                    execution.payload["completion_policy"] = {
                        "data_tools_locked": state.completion_only,
                        "next_action": "Call complete_analysis now." if state.completion_only else "Run only a necessary distinct follow-up.",
                    }
            if name == "check_data_quality" and execution.payload.get("classification") == "FAIL":
                state.quality_failures.append({
                    "table": arguments.get("table"),
                    "tickers": arguments.get("tickers"),
                    "start_date": arguments.get("start_date"),
                    "end_date": arguments.get("end_date"),
                })
                execution.payload["quality_blocks_finalization"] = True
                execution.payload["analysis_may_continue"] = False
                execution.payload["orchestrator_status"] = (
                    "FAIL blocks the affected conclusion; narrow or repair that scope."
                )
            elif name == "check_data_quality":
                execution.payload["quality_blocks_finalization"] = False
                execution.payload["analysis_may_continue"] = True
                execution.payload["orchestrator_status"] = (
                    "Quality result permits analysis to continue. Finish necessary follow-ups, "
                    "record decisive evidence, then complete_analysis."
                )
            if name == "record_evidence" and execution.payload.get("evidence_id"):
                state.recorded_evidence_ids.add(str(execution.payload["evidence_id"]))
                required_queries = self._required_analytical_queries(state)
                minimum_satisfied = len(state.analytical_query_hashes) >= required_queries
                if minimum_satisfied and not state.quality_failures:
                    state.completion_only = True
                execution.payload["completion_policy"] = {
                    "distinct_analytical_queries": len(state.analytical_query_hashes),
                    "required_distinct_analytical_queries": required_queries,
                    "data_tools_locked": state.completion_only,
                    "next_action": (
                        "Data queries are now locked. Call complete_analysis now."
                        if state.completion_only
                        else "Continue with a distinct necessary analytical follow-up before complete_analysis."
                    ),
                }
            if name == "complete_analysis" and execution.payload.get("completion_accepted"):
                state.completion_reason = arguments["completion_reason"].strip()
                state.finalization_ready = True
            state.point_in_time_warnings.update(execution.payload.get("point_in_time_warnings") or [])

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
            digest = decisive_digest(name, compact, execution.query_hash)
            state.evidence_digest.append(digest)
            self._log_step(
                state, step_number, name, sanitized, "COMPACTED" if compacted else "SUCCESS",
                execution=execution, llm_tokens=tokens, result_summary=digest,
            )
            self._persist_usage(state)
            return compact
        except Exception as exc:
            self._log_step(state, step_number, name, sanitized, "FAILED", error=str(exc)[:1000])
            if isinstance(exc, (ToolError, RuntimeError)):
                return {"error": str(exc), "recoverable": isinstance(exc, ToolError)}
            raise

    def _tool_result_budget(self, state: RunState, name: str) -> tuple[int, int]:
        cap = self.settings.ai_max_tool_result_tokens_total
        if name not in FINALIZATION_TOOLS:
            cap -= self.settings.ai_finalization_tool_result_reserve_tokens
        remaining = cap - state.tool_result_tokens
        if remaining <= 0:
            phase = "finalization" if name in FINALIZATION_TOOLS else "analysis"
            raise RuntimeError(f"Cumulative LLM tool-result budget for {phase} is exhausted")
        return remaining, min(self.settings.ai_max_tool_result_tokens_per_call, remaining)

    def _recover_malformed_tool_arguments(
        self,
        state: RunState,
        name: str,
        call: dict[str, Any],
        exc: Exception,
    ) -> dict[str, Any]:
        state.tool_calls += 1
        step_number = state.tool_calls + state.compactions
        raw = call.get("arguments")
        encoded = raw.encode("utf-8", errors="replace") if isinstance(raw, str) else b""
        summary = {
            "argument_characters": len(raw) if isinstance(raw, str) else 0,
            "argument_sha256": hashlib.sha256(encoded).hexdigest(),
            "recovery": "Ask the model to resend one complete schema-valid tool call.",
        }
        self._log_step(
            state, step_number, name, summary, "FAILED",
            result_summary={"reason": "malformed_tool_arguments"},
            error=f"Invalid provider tool arguments: {type(exc).__name__}"[:1000],
        )
        self._persist_usage(state)
        return {
            "error": "Tool arguments were not complete valid JSON. Resend the call with every required field and valid JSON.",
            "recoverable": True,
            "tool_name": name,
        }

    def _compact_context_if_needed(self, state: RunState) -> None:
        if self.settings.ai_context_compaction_mode == "DISABLED":
            return
        context = estimate_tokens({"instructions": self._instructions(state), "input": state.input_items, "tools": self._active_tool_definitions(state)})
        cumulative_threshold = (
            self.settings.ai_max_cumulative_input_tokens
            * self.settings.ai_cumulative_compaction_threshold_percent
            // 100
        )
        active_pressure = context > self.settings.ai_context_compaction_threshold_tokens
        cumulative_pressure = (
            not state.cumulative_pressure_compacted
            and state.cumulative_input >= cumulative_threshold
        )
        if not active_pressure and not cumulative_pressure:
            return
        digest = {
            "prior_analysis_digest": state.evidence_digest,
            "loaded_feature_definitions": [
                {"table": table, "column": column}
                for table, column in sorted(state.loaded_feature_definitions)
            ],
            "instruction": "Earlier tool outputs were superseded and compacted. Use hashes/evidence summaries; re-query only if necessary.",
            "preservation_policy": (
                "Decisive numbers, top/bottom observations, warnings, evidence IDs, and query "
                "hashes are retained; obsolete conversational/tool wrappers are removed."
            ),
        }
        state.input_items = [
            {"role": "user", "content": state.analytics_handoff},
            {"role": "user", "content": state.question},
            {"role": "user", "content": dumps(digest)},
        ]
        state.compactions += 1
        if cumulative_pressure:
            state.cumulative_pressure_compacted = True
        reason = "active_and_cumulative_pressure" if active_pressure and cumulative_pressure else (
            "active_context_threshold" if active_pressure else "cumulative_input_pressure"
        )
        self._log_step(
            state, state.tool_calls + state.compactions, None, {}, "COMPACTED",
            result_summary={
                "reason": reason,
                "prior_context_tokens": context,
                "cumulative_input_tokens": state.cumulative_input,
                "cumulative_threshold_tokens": cumulative_threshold,
            },
        )
        self._persist_usage(state)

    def _enforce_budgets(self, state: RunState, *, after_response: bool = False) -> None:
        if time.monotonic() - state.started_monotonic >= self.settings.ai_max_analysis_seconds:
            raise RuntimeError("Maximum analysis wall-clock budget exhausted")
        input_exhausted = (
            state.cumulative_input > self.settings.ai_max_cumulative_input_tokens
            if after_response
            else state.cumulative_input >= self.settings.ai_max_cumulative_input_tokens
        )
        output_exhausted = (
            state.cumulative_output > self.settings.ai_max_cumulative_output_tokens
            if after_response
            else state.cumulative_output >= self.settings.ai_max_cumulative_output_tokens
        )
        if input_exhausted:
            raise RuntimeError("Cumulative AI input token budget exhausted")
        if output_exhausted:
            raise RuntimeError("Cumulative AI output token budget exhausted")

    def _add_usage(self, state: RunState, response: Any) -> dict[str, int]:
        usage = response_usage(response)
        input_tokens = usage["input_tokens"]
        output_tokens = usage["output_tokens"]
        if input_tokens > self.settings.ai_max_context_tokens:
            # Persisted per-call audit still records this provider-reported violation.
            state.last_openai_response_id = response.get("id") or state.last_openai_response_id
            state.cumulative_input += input_tokens
            state.cumulative_output += output_tokens
            return usage
        state.last_openai_response_id = response.get("id") or state.last_openai_response_id
        state.cumulative_input += input_tokens
        state.cumulative_output += output_tokens
        return usage

    def _log_model_call(
        self,
        state: RunState,
        response: dict[str, Any],
        active_context_tokens: int,
        usage: dict[str, int],
    ) -> None:
        blocks, reasoning_format, decision_summary, summary_source = extract_reasoning_audit(
            response, max_bytes=self.settings.ai_reasoning_max_bytes_per_call
        )
        if not self.settings.ai_store_reasoning_details:
            blocks = []
            reasoning_format = "NONE"
        with self.db.connection() as connection, connection.transaction():
            connection.execute(
                '''INSERT INTO public."Analysis_Model_Call"
                     (request_id,attempt_number,iteration_number,provider,model,reasoning_effort,stage,
                      exposed_tool_families,provider_response_id,decision_summary,
                      decision_summary_source,reasoning_format,reasoning_details,
                      input_tokens,output_tokens,reasoning_tokens,active_context_tokens,
                      reasoning_expires_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                           clock_timestamp()+make_interval(days=>%s))''',
                (
                    state.request_id, state.attempt_number, state.iterations, self.settings.ai_provider,
                    self.settings.ai_model, self.settings.ai_reasoning_effort,
                    self._stage_for(state.families), sorted(state.families), response.get("id"),
                    decision_summary, summary_source, reasoning_format, json.dumps(blocks),
                    usage["input_tokens"], usage["output_tokens"], usage["reasoning_tokens"],
                    active_context_tokens, self.settings.ai_reasoning_retention_days,
                ),
            )
        if usage["input_tokens"] > self.settings.ai_max_context_tokens:
            raise RuntimeError("Provider-reported input exceeded AI_MAX_CONTEXT_TOKENS")

    def _mark_processing(self, state: RunState, stage: str) -> None:
        with self.db.connection() as connection, connection.transaction():
            row = connection.execute(
                '''UPDATE public."Analysis_Request"
                   SET status='PROCESSING', current_stage=%s, exposed_tool_families=%s,
                       model=%s, started_at=COALESCE(started_at,clock_timestamp()),
                       lease_owner=%s, lease_expires_at=clock_timestamp() + make_interval(secs => %s),
                       attempt_count=attempt_count+1
                   WHERE request_id=%s
                   RETURNING attempt_count''',
                (stage, sorted(state.families), self.settings.ai_model, socket.gethostname(), self.settings.worker_lease_seconds, state.request_id),
            ).fetchone()
            if not row:
                raise RuntimeError("Analysis request disappeared before processing")
            state.attempt_number = int(row["attempt_count"])

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
            if state.evidence_digest or state.analytical_query_hashes:
                connection.execute(
                    '''INSERT INTO public."Analysis_Evidence"
                         (request_id,evidence_type,claim,compact_payload,query_hash,source_tables)
                       SELECT %s,'WARNING','Analysis stopped before a reliable final answer',%s,%s,%s
                       WHERE (SELECT count(*) FROM public."Analysis_Evidence" WHERE request_id=%s) < 25''',
                    (
                        state.request_id,
                        dumps({
                            "failure": message,
                            "decisive_digest": state.evidence_digest[-10:],
                            "query_hashes": sorted(state.analytical_query_hashes),
                        }),
                        next(iter(sorted(state.analytical_query_hashes)), None),
                        sorted(state.features_used), state.request_id,
                    ),
                )
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
            "orchestrator_version": "release-2-generic-worker-v1", "prompt_version": "release-2-generic-worker-v1",
            "analysis_mode": state.analysis_mode,
            "max_analysis_seconds": self.settings.ai_max_analysis_seconds,
            "context_compaction_mode": self.settings.ai_context_compaction_mode,
            "cumulative_input_limit": self.settings.ai_max_cumulative_input_tokens,
            "final_response_max_retries": self.settings.ai_final_response_max_retries,
            "completion_reason": state.completion_reason,
            "distinct_analytical_queries": len(state.analytical_query_hashes),
            "feature_versions": [dict(row) for row in feature_versions],
            "tool_versions": [dict(row) for row in tool_versions],
            "query_hashes": self._digest_query_hashes(state.evidence_digest),
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
        methodology = {
            "analysis_ready_date": state.analysis_ready_date,
            "universe_mode": "current_universe_or_source_coverage",
            "survivorship_warning": "Current universe/reference metadata can introduce survivorship bias in historical comparisons.",
            "point_in_time_warnings": sorted(state.point_in_time_warnings),
            "look_ahead_validation": "Predictive claims require a successful bounded Analytics Worker job with explicit signal and forward horizons.",
        }
        return snapshot, methodology

    @staticmethod
    def _digest_query_hashes(items: list[dict[str, Any]]) -> list[str]:
        hashes: set[str] = set()
        for item in items:
            value = item.get("query_hash")
            if isinstance(value, list):
                hashes.update(str(part) for part in value if part)
            elif value:
                hashes.add(str(value))
            hashes.update(str(part) for part in item.get("query_hashes") or [] if part)
        return sorted(hashes)

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

    def _analytics_handoff(self) -> str:
        return (
            "ANALYTICS SESSION HANDOFF (load once and follow throughout this request): "
            "Use ordinary query/screen tools for bounded retrieval, ranking, and simple episodes. "
            "Use run_analytics_job only for multi-table joins, forward outcomes, window logic, or "
            "other niche computation. It creates catalog-validated Feature-only datasets, checks "
            f"size, and sends at most {self.settings.analytics_max_rows} rows / "
            f"{self.settings.analytics_max_input_bytes} bytes across "
            f"{self.settings.analytics_max_datasets} datasets to an isolated SQL worker. "
            "The worker has no database credentials. Filter before snapshotting; request only needed "
            "columns; never use LIMIT as a biased sample; use unique stable job_label values so retries "
            "are idempotent. QC is conditional and scoped: continue on WARNING or valid anomaly, block "
            "only impossible-data FAIL. Reuse identifiers and auto-loaded compact semantics; do not "
            f"repeat discovery more than {self.settings.ai_max_discovery_calls} times. Once the answer "
            "has decisive evidence and necessary follow-ups are complete, record/accept completion and "
            "stop; put optional work in recommended_next_analysis. For forward-outcome or cross-table "
            "historical questions, use this efficient route: check shared readiness at most once; discover "
            "only missing identifiers; if a universe is described by sector/industry, resolve its ticker "
            "list with one bounded query_features call; then call run_analytics_job immediately. The job "
            "validates and estimates every dataset itself, so do not call estimate_query_size first and "
            "do not aggregate the whole market merely to discover a small universe."
        )

    def _validate_completion(self, state: RunState, arguments: dict[str, Any]) -> None:
        if not state.recorded_evidence_ids:
            raise ToolError("Record at least one evidence item before complete_analysis")
        if arguments.get("evidence_sufficient") is not True:
            raise ToolError("Evidence is not yet sufficient for completion")
        if arguments.get("necessary_followups_completed") is not True:
            raise ToolError("Necessary follow-up analysis is not yet complete")
        if state.quality_failures:
            raise ToolError(
                "Impossible/invalid data quality FAIL blocks finalization for the affected scope; "
                "narrow the scope or resolve the invalid data before completing"
            )
        required_queries = self._required_analytical_queries(state)
        if len(state.analytical_query_hashes) < required_queries:
            raise ToolError(
                "INSIGHT mode requires at least "
                f"{required_queries} distinct successful analytical queries "
                "before completion; run a justified follow-up, not a duplicate query"
            )

    def _required_analytical_queries(self, state: RunState) -> int:
        if self._initial_stage(state.question) == "HISTORICAL_VALIDATION":
            return 1
        if (
            state.analysis_mode == "INSIGHT"
            and self._initial_stage(state.question) == "SCREENING"
        ):
            return self.settings.ai_min_insight_data_calls
        return 0

    @staticmethod
    def _semantic_requirements(name: str, arguments: dict[str, Any]) -> set[tuple[str, str]]:
        if name == "run_analytics_job":
            result: set[tuple[str, str]] = set()
            for dataset in arguments.get("datasets") or []:
                dataset_table = str(dataset.get("table") or "")
                dataset_columns = set(dataset.get("columns") or [])
                dataset_columns.update(
                    item.get("column") for item in dataset.get("filters") or []
                )
                result.update(
                    (dataset_table, column)
                    for column in dataset_columns
                    if dataset_table and isinstance(column, str) and column
                )
            return result
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

    def _auto_load_definitions(
        self, state: RunState, name: str, arguments: dict[str, Any]
    ) -> list[dict[str, Any]]:
        required = self._semantic_requirements(name, arguments)
        missing = required - state.loaded_feature_definitions
        if not missing:
            return []
        rows = self.tools.semantic_summaries(missing)
        found = {
            (str(row["feature_table"]), str(row["feature_column"])) for row in rows
        }
        unresolved = sorted(missing - found)
        if unresolved:
            detail = [{"table": table, "column": column} for table, column in unresolved]
            raise ToolError(
                "Active semantic definitions are missing from Feature_Catalog: "
                + json.dumps(detail, separators=(",", ":"))
            )
        state.loaded_feature_definitions.update(found)
        return rows

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
                 dumps(result_summary) if result_summary is not None else None, status, error),
            )

    @staticmethod
    def _sanitize(arguments: dict[str, Any]) -> dict[str, Any]:
        # Tool schemas contain no credentials; cap audit payloads defensively.
        encoded = dumps(arguments)
        return arguments if len(encoded) <= 16000 else {"compacted": True, "keys": sorted(arguments)}

    @staticmethod
    def _initial_stage(question: str) -> str:
        text = question.lower()
        historical_terms = (
            "backtest", "event study", "forward return", "setelah sinyal", "sesudah sinyal",
            "mendahului", "historical validation", "uji historis", "next month",
            "bulan berikut", "hari berikut", "predict", "prediksi", "korelasi", "correlation",
        )
        if any(term in text for term in historical_terms):
            return "HISTORICAL_VALIDATION"
        screening_terms = (
            "screen", "rank", "top ", "bottom ", "banding", "compare", "perbandingan",
            "tertinggi", "terendah", "find ", "report ", "show ", "retrieve ", "cari ",
            "tampilkan ", "laporkan ", "berapa ", "berturut", "consecutive", "streak",
        )
        return "SCREENING" if any(term in text for term in screening_terms) else "DISCOVERY"

    @classmethod
    def _initial_families(cls, question: str) -> set[str]:
        stage = cls._initial_stage(question)
        if stage == "DISCOVERY":
            return set(ToolRegistry.CORE_FAMILIES)
        if stage == "HISTORICAL_VALIDATION":
            return set(ToolRegistry.STAGE_FAMILIES["HISTORICAL_VALIDATION"])
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
        self.last_reasoning_cleanup = 0.0
        self.last_snapshot_cleanup = 0.0

    def start(self) -> None:
        self.thread = threading.Thread(target=self._loop, name="analysis-worker", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=10)

    def _loop(self) -> None:
        while not self.stop_event.is_set():
            self._purge_expired_reasoning_if_due()
            self._purge_analytics_snapshots_if_due()
            claimed = self._claim()
            if claimed:
                self.orchestrator.run(str(claimed["request_id"]), claimed["question"])
            else:
                self.stop_event.wait(self.settings.worker_poll_seconds)

    def _purge_expired_reasoning_if_due(self) -> None:
        now = time.monotonic()
        if now - self.last_reasoning_cleanup < self.settings.ai_reasoning_cleanup_interval_seconds:
            return
        try:
            with self.db.connection() as connection, connection.transaction():
                connection.execute(
                    '''UPDATE public."Analysis_Model_Call"
                       SET reasoning_details='[]'::jsonb,reasoning_format='PURGED',
                           reasoning_purged_at=clock_timestamp()
                       WHERE reasoning_expires_at <= clock_timestamp()
                         AND reasoning_format NOT IN ('NONE','PURGED')'''
                )
            self.last_reasoning_cleanup = now
        except Exception as exc:
            print(json.dumps({"event": "reasoning_cleanup_failed", "error": str(exc)[:500]}), flush=True)

    def _purge_analytics_snapshots_if_due(self) -> None:
        if not self.settings.analytics_enabled:
            return
        now = time.monotonic()
        if now - self.last_snapshot_cleanup < 3600:
            return
        try:
            with self.db.query_transaction() as connection:
                rows = connection.execute(
                    '''SELECT s.snapshot_id,s.object_key
                       FROM public."Analytics_Dataset_Snapshot" s
                       WHERE s.status='AVAILABLE' AND (
                         s.expires_at <= clock_timestamp() OR EXISTS (
                           SELECT 1 FROM public."Analytics_Job" j
                           WHERE j.snapshot_id=s.snapshot_id
                             AND j.status IN ('SUCCESS','FAILED','CANCELLED')
                             AND j.completed_at <= clock_timestamp()-make_interval(secs=>%s)
                         ))
                       ORDER BY s.expires_at LIMIT 100''',
                    (self.settings.analytics_terminal_snapshot_grace_seconds,),
                ).fetchall()
            store = AnalyticsSnapshotStore(self.settings)
            for row in rows:
                store.delete(row["object_key"])
                with self.db.connection() as connection, connection.transaction():
                    connection.execute(
                        '''UPDATE public."Analytics_Dataset_Snapshot"
                           SET status='DELETED',deleted_at=clock_timestamp()
                           WHERE snapshot_id=%s AND status='AVAILABLE' ''',
                        (row["snapshot_id"],),
                    )
            self.last_snapshot_cleanup = now
        except Exception as exc:
            print(json.dumps({"event": "analytics_snapshot_cleanup_failed", "error": str(exc)[:500]}), flush=True)
            self.last_snapshot_cleanup = now

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
