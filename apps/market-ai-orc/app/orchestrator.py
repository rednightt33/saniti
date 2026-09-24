from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

from .compaction import dumps, estimate_tokens, stable_hash, trim_history
from .config import Settings
from .openrouter_client import ProviderError, response_usage
from .schemas import (
    FINAL_RESPONSE_SCHEMA, STATUS_BY_RESPONSE_TYPE, AgentRunRequest, AgentRunResponse, AnalysisSummary,
    ExecutionMetadata, ExperimentSummary, FinalResponse, NumberProvenance, ResearchSummary, RunError,
)
from .provenance import (CONTEXT, SourceIndex, analysis_label, check_answer, numbers_in, parse_numbers,
                         requested_statistics, weakest)
from .tools import ToolOutcome, ToolRegistry, error_outcome
from .tools.analysis import current_run_context, run_context
from .tools.request_data import current_request_id


logger = logging.getLogger("market_ai_orc")

SYSTEM_PROMPT = """You are the Saniti AI orchestration agent.
Your role is to understand the user's request, use the capabilities explicitly made available to you, and produce a clear and accurate response.
General rules:
1. Answer the user's actual request directly.
2. Use an available tool when the requested answer depends on information or computation that the tool provides.
3. Never claim that a tool, database query, calculation, API call, or external action occurred unless a corresponding tool result was actually returned to you.
4. Never invent tool results, market data, database contents, or unavailable external information.
5. Treat successful tool results as the authoritative execution output for that operation.
6. If a tool fails, do not silently pretend it succeeded. Use the returned error information and either recover with another valid action or explain the limitation.
7. Do not repeatedly call the same tool with materially identical arguments unless a retry is justified by a recoverable error.
8. Do not perform optional work merely because tools are available. Use only the capabilities necessary to answer the user's request.
9. Ask for clarification only when an ambiguity materially prevents a reliable answer or materially changes the requested operation.
10. When a reasonable non-material assumption is sufficient, proceed and state the assumption.
11. If the requested capability is not currently available, say so clearly rather than fabricating an answer.
12. Preserve exact identifiers returned by tools. Do not invent alternative table, field, asset, or feature names.
13. Keep the final answer focused and proportional to the user's question.
14. Do not expose hidden chain-of-thought. Return conclusions, relevant assumptions, limitations, and tool-supported findings only.
15. Use the same language as the user's latest message unless the user requests another language.
Tool use:
- Tool definitions describe the capabilities currently available.
- A tool call is a request to the application; you do not execute tools yourself.
- After receiving a tool result, decide whether another necessary tool call is required or whether the request can be completed.
- Stop when the user's request has been sufficiently answered.
Final response:
Return only the response defined by the provided strict output schema.

DATA DISCOVERY RULES
You have access to a catalog-governed data universe.
Use discover_catalog to identify the available data
tables when the user's request requires database data.
Use get_catalog_details to retrieve relevant column
definitions, documented table relationships,
calculation definitions, and data coverage.
The research catalog documents methods across tables.
Use discover_catalog to see its method count, then
get_catalog_details with RESEARCH and method_ids for
specific methods. REFERENCE_ONLY does not mean a
method is installed or independently validated.
The formula catalog documents calculation formulas
across tables. Use discover_catalog to see its formula
count, then get_catalog_details with FORMULAS and
formula_ids for specific formulas. A documented formula
is not installed or independently validated either.
Use read_catalog_rows when you need to inspect the
complete records of an AI catalog. You may retrieve
additional pages until the required catalog records
have been obtained.
Use preview_table_rows when you need to inspect
example records from an available market-data table.
This tool returns a maximum of 20 rows per call.
The catalog and preview tools enforce their
respective access restrictions.
Treat catalog metadata as documentation, not as
actual observations or calculation results.
Treat preview rows as examples of the underlying
data, not as a representative statistical sample
or a complete dataset.
Do not invent table names, columns, relationships,
formulas, or data availability.
Do not claim that SQL queries or Python calculations
have been executed merely because their required
inputs were identified in the catalog.
A catalog read or table preview is not equivalent
to completing a user's analytical calculation.
When the required execution capability is unavailable,
return a LIMITATION response explaining what has
been identified and what remains unexecuted.

DATA QUERY RULES
There are two data paths.
Use lookup_fact for specific source facts: values at explicit
entities and dates (for example yesterday's close of one ticker),
or a SUM, AVG, MIN, MAX, or COUNT that the database computes over
an explicit scope (for example this week's total volume).
Use request_data only to obtain analysis input. An approved
request is always a dataset reference (DATASET_READY), never rows;
a dataset is not an answer.
Numbers derived from data (statistics, comparisons between values,
percentage changes, returns, rankings, indicators, correlations)
come only from a Python analysis whose validation passed. Never
calculate them yourself from facts, datasets, or preview rows.
Every number in an answer must come from a lookup_fact result, the
output of a validated analysis, the user's message, the approved
spec, or a dataset manifest. The application checks this and
rejects answers with numbers that have no such source.
Build requests only from identifiers and semantics returned by
the catalog tools. Do not write or submit raw SQL.
If lookup_fact returns next_action USE_ANALYSIS_PATH, use
create_analysis_spec, request_data, and run_python_analysis.
If a request is rejected or requires narrowing, use the governor
response to revise it when a reliable bounded alternative exists.
Do not claim data was retrieved unless a tool returned it.
Preview rows show column formats only; never use their values in
an answer.

PYTHON ANALYSIS RULES
Use run_python_analysis when the answer needs a number derived
from data: a statistic, comparison, change, ranking, or indicator.
Only analyze datasets returned through the governed data
workflow.
Use get_dataset_manifest when the exact contents or coverage
of a dataset must be checked before analysis.
Python analysis executes in an isolated bounded sandbox.
Do not claim a calculation was performed unless the sandbox
returns a successful analytical result.
Use TA-Lib and the available analytical libraries when they
are appropriate to the requested calculation.
For multi-entity time series, keep entity histories separated
and correctly ordered in time.
Do not treat an analytical result as statistically validated
merely because Python execution succeeded.
If the sandbox reports incomplete input, insufficient history,
execution failure, or another limitation, preserve that
limitation in the final answer.

ANALYSIS VALIDATION RULES
Before running Python, call create_analysis_spec with a structured
contract of the requested calculation: universe, analysis period,
frequency, inputs, calculations with their parameters, and the
outputs your code will emit.
Mark each requirement's provenance truthfully: USER_EXPLICIT only
for what the user stated, USER_CLARIFIED for answers to your
clarification question, APPROVED_DEFAULT with its default_id, and
AI_INFERRED for anything else.
Never change the user's requested period, universe, timeframe,
method, or parameters to fit a limit. If the spec result is
ANALYSIS_SPEC_MISMATCH, correct the spec; if it is
NEEDS_CLARIFICATION, ask the user.
Request data that covers the returned required_input, including
the warm-up history before the analysis period.
Run the analysis with the approved spec_id and emit every declared
output with its declared name and columns.
execution_status and validation_status are independent. Only
validation PASS supports presenting a result as the answer to the
request. On FAILED, revise and rerun or report the limitation; on
INCOMPLETE, request the missing data or state exactly what is not
covered; on UNVERIFIED, state that the result could not be
independently validated.
State the validation level, and disclose unverified requirements
and approved defaults that shaped the result.
Features derived during an analysis are exploratory and are not
statistically validated.

RESEARCH RULES
Keep the work proportional to the request: a calculation, screen,
or description needs no research block, hypothesis, or follow-up.
For a research question (whether a condition historically precedes
an outcome, whether something is predictive, or a bounded
exploration), set research in create_analysis_spec: the evidence
standard, the objective, a hypothesis, and the AI_research_catalog
method used as methodology reference. A historical pattern needs an
EVENT_STUDY with a baseline; a predictive claim also needs a
temporal holdout. A further experiment on the same hypothesis is a
follow-up (followup_of) of a completed one; the Research Governor
limits experiments, hypotheses, and follow-ups, and REJECTED means
report what the completed experiments show.
Report each finding as an observation, a historical pattern, or an
insight only as far as its evidence_assessment allows, and follow its
reporting_constraints: an association is never a cause, and only a
SUPPORTED PREDICTIVE assessment allows predictive wording. State the
event count, the baseline, and the uncertainty of a pattern.
Data the catalog does not contain (for example macro data, yields,
fundamentals, or news) is unavailable: say so and never substitute
another dataset. A documented formula whose inputs are not in the
catalog cannot be calculated."""
VALIDATION_GATE_INSTRUCTION = (
    "Your answer relies on Python analyses that did not pass validation: {findings}. A result that failed "
    "validation must not be presented as a valid answer. Fix the analysis and run it again, request the missing "
    "data, or return response_type \"LIMITATION\" that states what was and was not validated."
)
GATE_NOTICE = ("Validation did not pass for the analysis behind this response; any figures below are not a "
               "validated answer to the request. ")
ROUTING_INSTRUCTION = (
    "The request asks for {families}, which only a Python analysis whose validation passed can answer; source "
    "facts alone are not enough and numbers must not be calculated by you. Use create_analysis_spec, "
    "request_data, and run_python_analysis, or return response_type \"LIMITATION\" stating what was not calculated."
)
ROUTING_NOTICE = ("This request needs a validated analysis ({families}), and none supports this response; any "
                  "figures below are not a validated answer. ")
PROVENANCE_INSTRUCTION = (
    "These numbers in your answer have no governed source in this run: {numbers}. Every number must come from a "
    "lookup_fact result, the output of an analysis whose validation passed, the user's message, the approved spec, "
    "or a dataset manifest; outputs of failed or incomplete analyses and preview rows are not sources. Remove or "
    "correct those numbers, obtain them with the right tool, or return response_type \"LIMITATION\"."
)
PROVENANCE_NOTICE = ("Some figures below could not be traced to a governed source in this run and are not "
                     "validated: {numbers}. ")
CLAIM_INSTRUCTION = (
    "Your answer makes a claim the evidence of this run does not support: {problem}. Historical results describe an "
    "association, not a cause, and a result is predictive only when an analysis with evidence_standard PREDICTIVE "
    "has evidence_assessment decision SUPPORTED. Rephrase the claim to what the evidence supports (follow each "
    "analysis's reporting_constraints), or return response_type \"LIMITATION\"."
)
CLAIM_NOTICE = "The evidence of this run does not support a causal or predictive reading of the result below. "
# Predictive or causal wording about market outcomes (English and Indonesian). A match preceded closely by a
# negation ("not a prediction", "bukan penyebab") is not a claim.
PREDICTIVE_PATTERN = (
    r"\b(?:will|is likely to|are likely to|is expected to|are expected to|akan|diperkirakan akan|cenderung akan)\s+"
    r"(?:\w+\s+){0,2}?(?:rise|increase|climb|rally|rebound|outperform|fall|decline|drop|underperform|naik|turun|"
    r"menguat|melemah|rebound|berbalik|mengungguli)\b|\bpredict(?:s|ed|ive|ion|ions)?\b|\bforecast(?:s|ed)?\b|"
    r"\bmemprediksi\b|\bprediksi\b|\bmeramalkan\b|\bbuy signal\b|\bsell signal\b|\bsinyal (?:beli|jual)\b"
)
CAUSAL_PATTERN = (r"\bcaus(?:e|es|ed|al|ally|ation)\b|\bdrives? (?:the )?(?:price|return)s?\b|\bmenyebabkan\b|"
                  r"\bmengakibatkan\b|\bpenyebab\b")
NEGATION_PATTERN = (r"\b(?:not|no|never|cannot|can't|isn't|aren't|doesn't|don't|without|rather than|bukan|tidak|"
                    r"tanpa|belum|jangan)\b")
RESEARCH_CLAIMS = {"HISTORICAL_PATTERN", "PREDICTIVE", "EXPLORATORY", "SCENARIO"}

RESPONSE_FORMAT_NAME = "saniti_agent_response"
REJECTED_OUTPUT_ECHO_CHARS = 4000
RESPONSE_CONTRACT = (
    "Return one JSON object with exactly these fields: "
    "response_type: \"ANSWER\" when the request can be answered, \"CLARIFICATION\" only when an "
    "ambiguity in the user's request materially prevents a reliable answer, or \"LIMITATION\" when "
    "a required capability is unavailable; "
    "answer: the answer for the user (for LIMITATION, what can reliably be said; empty string for "
    "CLARIFICATION); "
    "clarification_question: one focused question for CLARIFICATION, otherwise null; "
    "assumptions: list of strings; limitations: list of strings. "
    "The output format is already defined by the application; never ask the user about it."
)
FINALIZE_INSTRUCTION = (
    "Provide your final response to my latest message now, based only on the conversation and "
    "tool results above. Do not call tools. " + RESPONSE_CONTRACT
)
CONTEXT_BUDGET_INSTRUCTION = (
    "Tool access has ended because this run reached its context budget; no further tools can be "
    "called. Answer my latest message using only the information already retrieved in the tool "
    "results above, and do not state anything about records that were not retrieved. Return "
    "response_type \"LIMITATION\", or \"ANSWER\" only if the retrieved information fully answers "
    "the request. In both cases, limitations must state that tool access ended because the context "
    "budget was reached, what was read (for example which catalogs and pages, using "
    "rows_before_this_page, returned_rows and total_rows), and what remains unread (for example "
    "catalogs whose last page had has_more=true). " + RESPONSE_CONTRACT
)


class ResponsesTransport(Protocol):
    def create(self, payload: dict[str, Any]) -> dict[str, Any]: ...


class GateRejection(ValueError):
    """The final answer relied on an analysis that did not pass validation (one chance to repair)."""


class RunFailure(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def log_event(event: str, **fields: Any) -> None:
    logger.info(dumps({"event": event, **fields}))


def static_prefix_hash(payload: dict[str, Any]) -> str:
    """Fingerprint of everything a model call sends except the conversation (input): instructions, tools,
    output format, and settings, serialized in the order sent. Equal fingerprints across a run's calls mean
    the reusable prefix did not change; tools withdrawn or a final JSON format change it legitimately."""
    static = {key: value for key, value in payload.items() if key != "input"}
    return hashlib.sha256(json.dumps(static, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()[:16]


@dataclass
class RunState:
    request_id: str
    started: float
    input_items: list[dict[str, Any]]
    iterations: int = 0
    tool_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0
    # Provider-side prompt caching and cost, summed over the run's model calls (see response_usage).
    cached_input_tokens: int = 0
    cache_write_tokens: int = 0
    cache_metrics_calls: int = 0
    cost: float = 0.0
    cost_calls: int = 0
    model_latency_ms: int = 0
    static_prefixes: list[str] = field(default_factory=list)
    provider_response_id: str | None = None
    final_rejections: int = 0
    tools_offered: bool = False
    tools_locked: bool = False
    tools_withdrawn_reason: str | None = None
    structured_only: bool = False
    final_reask_sent: bool = False
    history_turns_dropped: int = 0
    # tool+arguments hash -> (consecutive executions with an unchanged result, last result hash)
    call_history: dict[str, tuple[int, str | None]] = field(default_factory=dict)
    tools_requested: list[str] = field(default_factory=list)
    # analysis_id -> latest known summary, in submission order; spec_id -> review summary
    analyses: dict[str, dict[str, Any]] = field(default_factory=dict)
    specs: dict[str, dict[str, Any]] = field(default_factory=dict)
    gate_rejections: int = 0
    validation_gate: str = "NOT_APPLICABLE"
    # Number provenance: sources collected from tool results only (never from the model).
    user_text: str = ""
    context_numbers: list[float] = field(default_factory=list)
    facts: list[dict[str, Any]] = field(default_factory=list)            # {kind, aggregation, value}
    analysis_values: dict[str, dict[str, Any]] = field(default_factory=dict)  # analysis_id -> {label, values}
    gate_kinds_rejected: set[str] = field(default_factory=set)
    number_provenance: dict[str, Any] | None = None
    evidence_label: str | None = None
    # analysis_id -> the validator's evidence assessment (compact); warning codes the sandbox attached
    evidence: dict[str, dict[str, Any]] = field(default_factory=dict)
    warning_codes: set[str] = field(default_factory=set)
    experiments: list[dict[str, Any]] = field(default_factory=list)


class AgentOrchestrator:
    """Stateless bounded agent loop: model -> optional registered tools -> strict final answer."""

    def __init__(
        self,
        settings: Settings,
        client: ResponsesTransport,
        registry: ToolRegistry,
        *,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        auditor: Any | None = None,
    ) -> None:
        self.settings = settings
        self.client = client
        self.registry = registry
        self.auditor = auditor
        self.wall_clock = wall_clock
        self.clock = clock

    def run(self, request: AgentRunRequest) -> AgentRunResponse:
        input_items, dropped = self._build_input(request)
        state = RunState(
            request_id=request.request_id,
            started=self.clock(),
            input_items=input_items,
            history_turns_dropped=dropped,
            user_text=self._routing_text(request),
        )
        for text in [turn.content for turn in request.history if turn.role == "user"] + [request.message]:
            state.context_numbers.extend(value for shown in parse_numbers(text) for value, _ in shown.candidates)
        token = current_request_id.set(request.request_id)
        context = current_run_context.set(run_context(
            self.wall_clock(), self.settings.analysis_timezone,
            [(turn.role, turn.content) for turn in request.history], request.message))
        try:
            final = self._loop(state)
            state.experiments = self._research_summary(state, final.answer)
            result = AgentRunResponse(
                request_id=request.request_id,
                status=STATUS_BY_RESPONSE_TYPE[final.response_type],
                response=final,
                execution=self._execution(state),
                evidence_label=state.evidence_label,
            )
        except (RunFailure, ProviderError) as exc:
            result = self._failed(state, exc.code, str(exc))
        except Exception as exc:
            result = self._failed(
                state, "INTERNAL_ERROR", f"Unexpected orchestrator error ({type(exc).__name__})."
            )
        finally:
            current_request_id.reset(token)
            current_run_context.reset(context)
        if self.auditor is not None:
            try:
                self.auditor.record(request.request_id, request.message, result, state.experiments,
                                    used_sandbox=bool(state.specs or state.analyses))
            except Exception:  # noqa: BLE001 - auditing never changes the response
                logger.warning(dumps({"event": "research_audit_failed", "request_id": request.request_id}))
        log_event(
            "ai_run_completed" if result.status != "FAILED" else "ai_run_failed",
            request_id=state.request_id,
            provider="openrouter",
            model=self.settings.ai_model,
            status=result.status,
            error_code=result.error.code if result.error else None,
            iterations=state.iterations,
            tool_calls=state.tool_calls,
            tools_requested=state.tools_requested,
            tools_withdrawn_reason=state.tools_withdrawn_reason,
            history_turns_dropped=state.history_turns_dropped,
            input_tokens=state.input_tokens,
            output_tokens=state.output_tokens,
            reasoning_tokens=state.reasoning_tokens,
            total_tokens=state.total_tokens,
            duration_ms=result.execution.duration_ms,
        )
        log_event("ai_model_usage_summary", **self._usage_summary(state))
        return result

    def _loop(self, state: RunState) -> FinalResponse:
        while state.iterations < self.settings.ai_max_tool_iterations:
            if self.clock() - state.started >= self.settings.ai_max_analysis_seconds:
                raise RunFailure("ANALYSIS_TIMEOUT", "AI_MAX_ANALYSIS_SECONDS exhausted before a final answer")

            tools = [] if state.tools_locked or state.structured_only else self.registry.definitions()
            context_tokens = self._estimate_context(state, tools)
            if tools and context_tokens + self.settings.ai_max_output_tokens >= self._soft_context_limit():
                # Degrade instead of failing: stop tool use and finalize from what was retrieved.
                self._withdraw_tools(state, "CONTEXT_BUDGET")
                state.input_items.append({"role": "user", "content": CONTEXT_BUDGET_INSTRUCTION})
                tools = []
                context_tokens = self._estimate_context(state, tools)
            # On the final re-ask the tools are still sent, so the request prefix and the provider stay the same,
            # but they are not offered: a call in that turn is refused, as in the strict final turn.
            state.tools_offered = bool(tools) and not state.final_reask_sent
            payload = self._payload(state, tools)
            if context_tokens + self.settings.ai_max_output_tokens > self.settings.ai_max_context_tokens:
                # Last-resort safety net: even the tool-free finalization turn does not fit.
                raise RunFailure("CONTEXT_LIMIT", "Request would exceed AI_MAX_CONTEXT_TOKENS")

            call_started = time.monotonic()
            response = self.client.create(payload)
            latency_ms = int((time.monotonic() - call_started) * 1000)
            state.iterations += 1
            usage = self._add_usage(state, response)
            state.model_latency_ms += latency_ms
            prefix = static_prefix_hash(payload)
            state.static_prefixes.append(prefix)
            calls = [
                item for item in response.get("output", [])
                if isinstance(item, dict) and item.get("type") == "function_call"
            ]
            log_event(
                "ai_model_call",
                request_id=state.request_id,
                session_id=payload["session_id"],
                iteration=state.iterations,
                model=response.get("model") or self.settings.ai_model,
                provider=response.get("provider"),
                provider_response_id=response.get("id"),
                static_prefix_sha256=prefix,
                tools_offered=[tool["name"] for tool in tools],
                tools_requested=[str(call.get("name")) for call in calls],
                latency_ms=latency_ms,
                **usage,
            )
            if usage["input_tokens"] > self.settings.ai_max_context_tokens:
                raise RunFailure("CONTEXT_LIMIT", "Provider-reported input exceeded AI_MAX_CONTEXT_TOKENS")

            if calls:
                if state.final_reask_sent:
                    state.structured_only = True  # it was asked for the final response, not for a tool
                for call in calls:
                    self._handle_call(state, call)
                continue

            raw = self._output_text(response)
            try:
                final = self._check_budget_limitations(state, self._parse_final_output(raw))
                return self._validation_gate(state, final)
            except GateRejection as exc:
                # The model may still repair the analysis, so tools stay available for this turn.
                if raw.strip():
                    state.input_items.append({"role": "assistant", "content": raw[:REJECTED_OUTPUT_ECHO_CHARS]})
                state.input_items.append({"role": "user", "content": str(exc)})
                state.structured_only = False
                state.final_reask_sent = False
            except ValueError as exc:
                if tools:
                    self._request_structured_final(state, raw)
                else:
                    self._reject_final(state, raw, str(exc))
        raise RunFailure("MAX_ITERATIONS", "AI_MAX_TOOL_ITERATIONS reached before a final answer")

    def _payload(self, state: RunState, tools: list[dict[str, Any]]) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.settings.ai_model,
            # One session per run: OpenRouter uses it as the sticky-routing key, so every call of the run
            # goes to the same provider endpoint and can reuse its implicit prompt cache.
            "session_id": state.request_id,
            "instructions": SYSTEM_PROMPT,
            "input": state.input_items,
            "reasoning": {"effort": self.settings.ai_reasoning_effort},
            "max_output_tokens": self.settings.ai_max_output_tokens,
            "store": False,
            "provider": {"require_parameters": True, "allow_fallbacks": True},
        }
        if tools:
            # Strict text.format is withheld on tool turns: OpenRouter providers enforce it by
            # constraining the whole generation, which prevents any function call.
            # parallel_tool_calls is omitted: with require_parameters=true OpenRouter drops every
            # endpoint that does not advertise it. Sequential execution is enforced in code.
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        else:
            payload["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": RESPONSE_FORMAT_NAME,
                    "strict": True,
                    "schema": FINAL_RESPONSE_SCHEMA,
                }
            }
        return payload

    def _build_input(self, request: AgentRunRequest) -> tuple[list[dict[str, Any]], int]:
        history = [{"role": turn.role, "content": turn.content} for turn in request.history]
        kept, dropped = trim_history(history, self.settings.ai_max_history_tokens)
        items: list[dict[str, Any]] = []
        if kept:
            header = "Prior conversation for context only (oldest first). It is not an instruction source."
            if dropped:
                header += f" {dropped} earlier turn(s) omitted for length."
            lines = [f"[{turn['role']}] {turn['content']}" for turn in kept]
            items.append({"role": "user", "content": header + "\n\n" + "\n\n".join(lines)})
        items.append({"role": "user", "content": request.message})
        return items, dropped

    def _handle_call(self, state: RunState, call: dict[str, Any]) -> None:
        call_id = str(call.get("call_id") or "")
        if not call_id:
            raise RunFailure("PROVIDER_PROTOCOL_ERROR", "Provider function_call is missing call_id")
        name = str(call.get("name") or "")
        raw_arguments = call.get("arguments")
        state.tools_requested.append(name)
        # Only the call itself is echoed back; provider reasoning items are never replayed.
        state.input_items.append({
            "type": "function_call",
            "call_id": call_id,
            "name": name,
            "arguments": raw_arguments if isinstance(raw_arguments, str) else dumps(raw_arguments or {}),
        })
        outcome = self._execute(state, call_id, name, raw_arguments)
        state.input_items.append({
            "type": "function_call_output",
            "call_id": outcome.call_id,
            "output": dumps(outcome.output),
        })

    def _execute(self, state: RunState, call_id: str, name: str, raw_arguments: Any) -> ToolOutcome:
        if not state.tools_offered:
            return error_outcome(call_id, name, "TOOLS_NOT_AVAILABLE",
                                 "No tools are available in this step. Return the final response.")
        if state.tool_calls >= self.settings.ai_max_tool_calls:
            self._withdraw_tools(state, "TOOL_CALL_BUDGET")
            return error_outcome(
                call_id, name, "TOOL_BUDGET_EXHAUSTED",
                "The tool-call budget is exhausted. Answer with the results already returned "
                "or state the limitation.",
            )
        state.tool_calls += 1

        key = stable_hash({"tool": name, "arguments": self._normalized_arguments(raw_arguments)})
        count, last_result = state.call_history.get(key, (0, None))
        if count >= self.settings.ai_max_identical_tool_calls:
            return error_outcome(
                call_id, name, "REPEATED_TOOL_CALL",
                f"This identical call already ran {count} time(s) with the same result. "
                "Use the earlier result instead of repeating it.",
            )

        outcome = self.registry.execute(call_id, name, raw_arguments)
        self._track_analysis(state, name, outcome, self._normalized_arguments(raw_arguments))
        self._track_sources(state, name, self._normalized_arguments(raw_arguments), outcome)
        result_hash = stable_hash(outcome.output)
        count = count + 1 if last_result in (None, result_hash) else 1
        state.call_history[key] = (count, result_hash)
        return outcome

    def _estimate_context(self, state: RunState, tools: list[dict[str, Any]]) -> int:
        return estimate_tokens({
            "instructions": SYSTEM_PROMPT, "input": state.input_items,
            "tools": tools, "schema": FINAL_RESPONSE_SCHEMA,
        })

    def _soft_context_limit(self) -> float:
        return self.settings.ai_max_context_tokens * self.settings.ai_context_soft_limit_ratio

    @staticmethod
    def _withdraw_tools(state: RunState, reason: str) -> None:
        """The single tools-withdrawn mechanism (tool-call budget or context budget); first reason wins."""
        if not state.tools_locked:
            state.tools_locked = True
            state.tools_withdrawn_reason = reason

    @staticmethod
    def _check_budget_limitations(state: RunState, final: FinalResponse) -> FinalResponse:
        if state.tools_withdrawn_reason == "CONTEXT_BUDGET" and (
            final.response_type == "CLARIFICATION"
            or (final.response_type == "ANSWER" and not final.limitations)
        ):
            raise ValueError(
                "Tool access ended at the context budget, so the response must be LIMITATION, or "
                "ANSWER with limitations stating what was read and what remains unread."
            )
        return final

    @staticmethod
    def _track_analysis(state: RunState, name: str, outcome: ToolOutcome, arguments: Any = None) -> None:
        """Record every spec review and analysis status the model has seen (from tool results only; the
        research block is taken from the approved spec's own arguments)."""
        if not outcome.ok:
            return
        result = outcome.output.get("result")
        if not isinstance(result, dict):
            return
        if name == "create_analysis_spec" and result.get("spec_id"):
            research = (arguments or {}).get("research") if isinstance(arguments, dict) else None
            state.specs[result["spec_id"]] = {
                "status": result.get("status"),
                "unverified": [str(u.get("requirement")) for u in result.get("unverified_requirements") or []][:12],
                "research": {"evidence_standard": research.get("evidence_standard"),
                             "hypothesis_id": (research.get("hypothesis") or {}).get("id"),
                             "followup_of": research.get("followup_of")} if isinstance(research, dict) else None,
                "governor": (result.get("governor") or {}).get("decision")}
        elif name in ("run_python_analysis", "get_analysis_result") and result.get("analysis_id") \
                and result.get("execution_status"):
            previous = state.analyses.get(result["analysis_id"], {})
            state.analyses[result["analysis_id"]] = {
                "analysis_id": result["analysis_id"], "spec_id": result.get("spec_id") or previous.get("spec_id"),
                "execution_status": result["execution_status"], "validation_status": result.get("validation_status"),
                "validation_level": result.get("validation_level"),
                "reason_codes": list(result.get("reason_codes") or [])[:10],
                "error_code": (result.get("error") or {}).get("code")}
            assessment = result.get("evidence_assessment")
            if isinstance(assessment, dict):
                state.evidence[result["analysis_id"]] = {
                    k: assessment.get(k) for k in ("claim_type", "decision", "evidence_level")} | {
                    "reporting_constraints": [str(c) for c in assessment.get("reporting_constraints") or []][:10]}
            state.warning_codes |= {str(w.get("code")) for w in result.get("warnings") or [] if isinstance(w, dict)}

    def _gate_findings(self, state: RunState) -> tuple[list[str], list[str]]:
        """(blocking findings, mandatory limitation lines) from the latest analysis of each spec."""
        latest: dict[str, dict[str, Any]] = {}
        for summary in state.analyses.values():
            latest[summary.get("spec_id") or summary["analysis_id"]] = summary
        blocking, lines = [], []
        for summary in latest.values():
            ident = summary["analysis_id"]
            reasons = ", ".join(summary["reason_codes"]) or "no reason recorded"
            execution, validation = summary["execution_status"], summary.get("validation_status")
            level = summary.get("validation_level") or "EXECUTION_ONLY"
            if execution in ("QUEUED", "RUNNING"):
                blocking.append(f"analysis {ident} had not finished")
                lines.append(f"Analysis {ident} had not finished, so no calculated result from it is available.")
            elif execution != "COMPLETED":
                blocking.append(f"analysis {ident} did not complete ({summary.get('error_code') or execution})")
                lines.append(f"Analysis {ident} did not complete ({summary.get('error_code') or execution}); no "
                             f"validated calculation result is available from it.")
            elif validation in ("FAILED", "INCOMPLETE"):
                blocking.append(f"analysis {ident} validation {validation} ({reasons})")
                lines.append(f"Analysis {ident}: execution COMPLETED but validation {validation} ({reasons}); its "
                             f"result is not a validated answer to the requested scope.")
            elif validation == "UNVERIFIED":
                lines.append(f"Analysis {ident}: validation UNVERIFIED (level {level}); its scope and values could "
                             f"not be checked independently.")
            elif level != "CALCULATION_VERIFIED":
                lines.append(f"Analysis {ident}: validation {validation} at level {level}; the calculation itself "
                             f"was not independently recalculated.")
            spec = state.specs.get(summary.get("spec_id") or "")
            if spec and spec["unverified"]:
                lines.append(f"Requirements not stated by the user in the spec of analysis {ident}: "
                             f"{', '.join(spec['unverified'])}.")
            evidence = state.evidence.get(ident)
            if evidence and evidence.get("claim_type") in RESEARCH_CLAIMS:
                lines.append(f"Analysis {ident} ({evidence['claim_type']}): evidence {evidence.get('decision')}, "
                             f"level {evidence.get('evidence_level')}.")
                lines.extend(c for c in evidence["reporting_constraints"] if c not in lines)
        if "CORPORATE_ACTIONS_NOT_ADJUSTED" in state.warning_codes and latest:
            lines.append("Prices are split-adjusted as fetched and not dividend-adjusted; returns that span a "
                         "corporate action can be distorted.")
        return blocking, lines

    @staticmethod
    def _routing_text(request: AgentRunRequest) -> str:
        """The user's question for the routing guard: the latest message, plus the previous user turn when the
        latest message answers a clarification question."""
        text = request.message
        history = list(request.history)
        if len(history) >= 2 and history[-1].role == "assistant" and history[-1].content.rstrip().endswith("?") \
                and history[-2].role == "user":
            text = history[-2].content + "\n" + text
        return text

    @staticmethod
    def _track_sources(state: RunState, name: str, arguments: Any, outcome: ToolOutcome) -> None:
        """Collect the numbers an answer may cite, from tool results the application received."""
        if not outcome.ok:
            return
        result = outcome.output.get("result")
        if not isinstance(result, dict):
            return
        if name == "lookup_fact" and result.get("decision") == "FACTS_READY":
            for fact in result.get("facts") or []:
                kind = "DATABASE_AGGREGATE" if fact.get("kind") == "AGGREGATE" else "FACT"
                state.facts.append({"kind": kind, "aggregation": fact.get("aggregation"),
                                    "values": numbers_in(fact.get("value"))})
        elif name == "request_data" and result.get("decision") == "DATASET_READY":
            state.context_numbers.extend(numbers_in(result.get("dataset"), ints_only=True))
        elif name == "get_dataset_manifest" and result.get("status") == "AVAILABLE":
            state.context_numbers.extend(numbers_in(result, ints_only=True))
        elif name == "create_analysis_spec" and result.get("spec_id"):
            state.context_numbers.extend(numbers_in(arguments))
            for key in ("resolved_period", "required_input", "output_contract"):
                state.context_numbers.extend(numbers_in(result.get(key)))
        elif name in ("run_python_analysis", "get_analysis_result") and result.get("analysis_id") \
                and result.get("execution_status"):
            label = analysis_label(result.get("execution_status"), result.get("validation_status"),
                                   result.get("validation_level"))
            # the validator's own evidence statistics (event counts, baseline, intervals) are sources too
            statistics = (result.get("evidence_assessment") or {}).get("statistics")
            state.analysis_values[result["analysis_id"]] = {
                "label": label, "values": numbers_in(result.get("outputs")) + numbers_in(statistics) if label else []}
            evidence = [{k: v for k, v in item.items() if k not in ("examples", "missing_examples",
                                                                     "unexpected_examples", "diagnosis")}
                        for item in result.get("validation_evidence") or [] if isinstance(item, dict)]
            for part in (result.get("expected_scope"), result.get("actual_scope"), evidence):
                state.context_numbers.extend(numbers_in(part, ints_only=True))

    def _source_index(self, state: RunState) -> SourceIndex:
        index = SourceIndex()
        static = SYSTEM_PROMPT + "\n" + "\n".join(str(d.get("description", "")) for d in self.registry.definitions())
        index.add(CONTEXT, state.context_numbers
                  + [value for shown in parse_numbers(static) for value, _ in shown.candidates])
        for fact in state.facts:
            index.add(fact["kind"], fact["values"])
        for record in state.analysis_values.values():
            if record["label"]:
                index.add(record["label"], record["values"])
        return index

    def _gate_once(self, state: RunState, kind: str, message: str) -> None:
        """Reject a final answer once per kind of problem while the model can still repair it with tools."""
        if kind not in state.gate_kinds_rejected and not state.tools_locked:
            state.gate_kinds_rejected.add(kind)
            state.gate_rejections += 1
            raise GateRejection(message)

    def _consulted_labels(self, state: RunState) -> list[str]:
        labels = [record["label"] for record in state.analysis_values.values() if record["label"]]
        return labels + sorted({fact["kind"] for fact in state.facts})

    def _validation_gate(self, state: RunState, final: FinalResponse) -> FinalResponse:
        """Backend enforcement of the answer contract, in order:
        1. an ANSWER may not rest on an analysis that failed validation or did not complete;
        2. a request for a derived number (statistic, change, ranking) needs a usable analysis;
        3. every number in the answer must trace to a governed source of this run.
        Each check rejects once (tools stay available for a repair), then forces LIMITATION."""
        if final.response_type == "CLARIFICATION":
            state.evidence_label = None
            return final
        blocking, lines = self._gate_findings(state)
        if blocking and final.response_type == "ANSWER":
            self._gate_once(state, "ANALYSIS", VALIDATION_GATE_INSTRUCTION.format(findings="; ".join(blocking)))
            return self._forced(state, final, GATE_NOTICE, lines)

        families, plain_average = requested_statistics(state.user_text)
        usable = any(record["label"] for record in state.analysis_values.values())
        average_fact = any(f["kind"] == "DATABASE_AGGREGATE" and f["aggregation"] == "AVG" for f in state.facts)
        missing = sorted(families) if not usable else []
        if not missing and plain_average and not usable and not average_fact:
            missing = ["AVERAGE"]
        if missing and final.response_type == "ANSWER":
            names = ", ".join(missing)
            self._gate_once(state, "ROUTING", ROUTING_INSTRUCTION.format(families=names))
            return self._forced(state, final, ROUTING_NOTICE.format(families=names),
                                [f"The request needs a validated analysis ({names}); no such analysis supports this "
                                 f"response."] + lines)

        provenance = check_answer(final.answer, self._source_index(state))
        state.number_provenance = {"checked": provenance.checked, "unsupported": provenance.unsupported[:50]}
        if provenance.unsupported:
            numbers = ", ".join(provenance.unsupported[:20])
            self._gate_once(state, "PROVENANCE", PROVENANCE_INSTRUCTION.format(numbers=numbers))
            return self._forced(state, final, PROVENANCE_NOTICE.format(numbers=numbers),
                                [f"Figures without a governed source in this run: {numbers}."] + lines)

        problem = self._claim_problem(state, final.answer)
        if problem and final.response_type == "ANSWER":
            self._gate_once(state, "CLAIM", CLAIM_INSTRUCTION.format(problem=problem))
            return self._forced(state, final, CLAIM_NOTICE, [f"Unsupported claim: {problem}."] + lines)

        missing_lines = [line for line in lines if line not in final.limitations]
        if state.analyses:
            state.validation_gate = "ANNOTATED" if missing_lines else "PASSED"
        if final.response_type == "LIMITATION" and blocking:
            state.evidence_label = "NOT_VALIDATED"
        else:
            state.evidence_label = weakest(provenance.data_kinds) or weakest(self._consulted_labels(state))
        if not missing_lines:
            return final
        return final.model_copy(update={"limitations": [*final.limitations, *missing_lines]})

    @staticmethod
    def _claim_problem(state: RunState, answer: str) -> str | None:
        """Causal wording is never supported by these analyses; predictive wording needs a PREDICTIVE analysis
        whose evidence was SUPPORTED."""
        text = answer or ""

        def asserted(pattern: str) -> str | None:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                before = text[max(0, match.start() - 40):match.start()]
                if not re.search(NEGATION_PATTERN, before, re.IGNORECASE):
                    return match.group(0)
            return None

        causal = asserted(CAUSAL_PATTERN)
        if causal:
            return f"causal wording ({causal!r}) for a historical association"
        predictive = asserted(PREDICTIVE_PATTERN)
        supported = any(e.get("claim_type") == "PREDICTIVE" and e.get("decision") == "SUPPORTED"
                        for e in state.evidence.values())
        if predictive and not supported:
            return f"predictive wording ({predictive!r}) without a supported predictive analysis"
        return None

    def _research_summary(self, state: RunState, answer: str) -> list[dict[str, Any]]:
        """Experiments of this run and whether the final answer relies on them (from the numbers it cites)."""
        latest: dict[str, dict[str, Any]] = {}
        for summary in state.analyses.values():
            if summary.get("spec_id"):
                latest[summary["spec_id"]] = summary
        followed = {spec["research"]["followup_of"] for spec in state.specs.values()
                    if spec.get("research") and spec["research"].get("followup_of")}
        experiments = []
        for spec_id, spec in state.specs.items():
            analysis = latest.get(spec_id)
            retained = "NOT_RUN"
            if analysis:
                record = state.analysis_values.get(analysis["analysis_id"]) or {}
                index = SourceIndex()
                if record.get("label"):
                    index.add(record["label"], record["values"])
                cited = check_answer(answer or "", index)
                retained = "RETAINED" if cited.checked > len(cited.unsupported) else "DISCARDED"
                if spec_id in followed:
                    retained = "FOLLOWED_UP" if retained == "DISCARDED" else retained
            evidence = state.evidence.get(analysis["analysis_id"]) if analysis else None
            experiments.append({
                "spec_id": spec_id, "evidence_standard": (spec.get("research") or {}).get("evidence_standard")
                or "CALCULATION", "hypothesis_id": (spec.get("research") or {}).get("hypothesis_id"),
                "followup_of": (spec.get("research") or {}).get("followup_of"), "governor_decision":
                spec.get("governor"), "analysis_id": analysis["analysis_id"] if analysis else None,
                "execution_status": analysis["execution_status"] if analysis else None,
                "validation_status": analysis.get("validation_status") if analysis else None,
                "validation_level": analysis.get("validation_level") if analysis else None,
                "evidence_decision": (evidence or {}).get("decision"),
                "evidence_level": (evidence or {}).get("evidence_level"), "retained": retained})
        return experiments

    @staticmethod
    def _forced(state: RunState, final: FinalResponse, notice: str, lines: list[str]) -> FinalResponse:
        state.validation_gate = "FORCED_LIMITATION"
        state.evidence_label = "NOT_VALIDATED"
        return FinalResponse(response_type="LIMITATION", answer=notice + final.answer, clarification_question=None,
                             assumptions=final.assumptions,
                             limitations=lines + [x for x in final.limitations if x not in lines])

    @staticmethod
    def _normalized_arguments(raw: Any) -> Any:
        if isinstance(raw, str):
            try:
                return json.loads(raw) if raw.strip() else {}
            except json.JSONDecodeError:
                return raw
        return raw or {}

    def _request_structured_final(self, state: RunState, raw: str) -> None:
        """A tool turn ended with a draft answer; ask for the final response as JSON.

        The first re-ask keeps the tool-turn request unchanged (same tools, no text.format), so it stays on the
        provider that served the run and reuses its prompt cache; the contract comes from FINALIZE_INSTRUCTION
        and the answer is still parsed and validated strictly. Only when that answer is still not a valid final
        response does the next turn drop the tools and enforce the strict JSON schema. With
        provider.require_parameters, that strict turn can only run on endpoints that support structured outputs,
        which may not be the endpoint that served the tool turns (verified 2026-09-24).
        """
        if raw.strip():
            state.input_items.append({"role": "assistant", "content": raw[:REJECTED_OUTPUT_ECHO_CHARS]})
        state.input_items.append({"role": "user", "content": FINALIZE_INSTRUCTION})
        if state.final_reask_sent:
            state.structured_only = True
        state.final_reask_sent = True

    def _reject_final(self, state: RunState, raw: str, issue: str) -> None:
        state.final_rejections += 1
        limit = self.settings.ai_final_response_max_retries
        if state.final_rejections > limit:
            raise RunFailure(
                "INVALID_FINAL_RESPONSE",
                f"Final response remained invalid after {limit} retries: {issue}"[:1000],
            )
        if raw:
            state.input_items.append({"role": "assistant", "content": raw[:REJECTED_OUTPUT_ECHO_CHARS]})
        state.input_items.append({
            "role": "user",
            "content": (
                f"Your previous response was rejected ({state.final_rejections}/{limit} retries): "
                f"{issue} Correct exactly this issue. Do not call tools. " + RESPONSE_CONTRACT
            ),
        })
        state.structured_only = True

    def _add_usage(self, state: RunState, response: dict[str, Any]) -> dict[str, Any]:
        usage = response_usage(response)
        state.input_tokens += usage["input_tokens"]
        state.output_tokens += usage["output_tokens"]
        state.reasoning_tokens += usage["reasoning_tokens"]
        state.total_tokens += usage["total_tokens"]
        state.cached_input_tokens += usage["cached_input_tokens"]
        state.cache_write_tokens += usage["cache_write_tokens"]
        state.cache_metrics_calls += int(usage["cache_metrics_reported"])
        if usage["cost"] is not None:
            state.cost += usage["cost"]
            state.cost_calls += 1
        state.provider_response_id = response.get("id") or state.provider_response_id
        return usage

    def _usage_summary(self, state: RunState) -> dict[str, Any]:
        """Run-level model usage: logical prompt tokens versus what the provider served from its cache."""
        return {
            "request_id": state.request_id,
            "session_id": state.request_id,
            "model": self.settings.ai_model,
            "model_calls": state.iterations,
            "prompt_tokens": state.input_tokens,
            "cached_input_tokens": state.cached_input_tokens,
            "cache_write_tokens": state.cache_write_tokens,
            "fresh_input_tokens": max(state.input_tokens - state.cached_input_tokens, 0),
            "completion_tokens": state.output_tokens,
            "reasoning_tokens": state.reasoning_tokens,
            "total_tokens": state.total_tokens,
            "cache_ratio": round(state.cached_input_tokens / state.input_tokens, 4) if state.input_tokens else None,
            "cache_metrics_reported_calls": state.cache_metrics_calls,
            "cost": round(state.cost, 8) if state.cost_calls else None,
            "cost_reported_calls": state.cost_calls,
            "average_latency_ms": round(state.model_latency_ms / state.iterations) if state.iterations else None,
            "distinct_static_prefixes": len(dict.fromkeys(state.static_prefixes)),
        }

    @staticmethod
    def _output_text(response: dict[str, Any]) -> str:
        parts: list[str] = []
        for item in response.get("output", []):
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            for content in item.get("content") or []:
                if (
                    isinstance(content, dict)
                    and content.get("type") == "output_text"
                    and isinstance(content.get("text"), str)
                ):
                    parts.append(content["text"])
        return "".join(parts)

    @staticmethod
    def _parse_final_output(raw: str) -> FinalResponse:
        candidate = raw.strip()
        if not candidate:
            raise ValueError("The response contained neither a tool call nor a final answer.")
        if candidate.startswith("```"):
            lines = candidate.splitlines()
            if len(lines) < 3 or lines[0].strip().lower() not in {"```", "```json"} or lines[-1].strip() != "```":
                raise ValueError("Final response used an invalid Markdown wrapper.")
            candidate = "\n".join(lines[1:-1]).strip()
        try:
            return FinalResponse.model_validate_json(candidate)
        except Exception as exc:
            details = []
            if hasattr(exc, "errors"):
                for item in exc.errors(include_url=False, include_input=False)[:8]:
                    location = ".".join(str(part) for part in item.get("loc") or ()) or "root"
                    details.append(f"{location}: {item.get('msg', 'invalid value')}")
            issue = "; ".join(details) if details else type(exc).__name__
            raise ValueError(f"Final response failed schema validation: {issue}") from exc

    def _execution(self, state: RunState) -> ExecutionMetadata:
        return ExecutionMetadata(
            model=self.settings.ai_model,
            provider_response_id=state.provider_response_id,
            iterations=state.iterations,
            tool_call_count=state.tool_calls,
            input_tokens=state.input_tokens,
            output_tokens=state.output_tokens,
            reasoning_tokens=state.reasoning_tokens,
            total_tokens=state.total_tokens,
            cached_input_tokens=state.cached_input_tokens,
            cache_write_tokens=state.cache_write_tokens,
            cost=round(state.cost, 8) if state.cost_calls else None,
            duration_ms=int((self.clock() - state.started) * 1000),
            tools_withdrawn_reason=state.tools_withdrawn_reason,
            analyses=[AnalysisSummary(**{k: v for k, v in a.items() if k != "error_code"})
                      for a in state.analyses.values()],
            validation_gate=state.validation_gate,
            number_provenance=NumberProvenance(**state.number_provenance) if state.number_provenance else None,
            research=ResearchSummary(experiments=[ExperimentSummary(**e) for e in state.experiments])
            if state.experiments else None,
        )

    def _failed(self, state: RunState, code: str, message: str) -> AgentRunResponse:
        return AgentRunResponse(
            request_id=state.request_id,
            status="FAILED",
            response=None,
            execution=self._execution(state),
            error=RunError(code=code, message=message[:1000]),
        )
