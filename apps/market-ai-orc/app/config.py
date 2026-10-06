from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .research_plan import MAX_TTL_SECONDS, weak_key_problem

REASONING_EFFORTS = {"minimal", "low", "medium", "high", "xhigh", "max"}


class ConfigError(RuntimeError):
    pass


def _integer(env: Mapping[str, str], name: str, default: int, minimum: int = 1) -> int:
    raw = env.get(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc
    if value < minimum:
        raise ConfigError(f"{name} must be at least {minimum}")
    return value


def _ratio(env: Mapping[str, str], name: str, default: float, low: float, high: float) -> float:
    raw = env.get(name, str(default))
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number") from exc
    if not low <= value <= high:
        raise ConfigError(f"{name} must be between {low} and {high}")
    return value


RESULT_BUCKET_KEYS = {"name": "RESULT_BUCKET_NAME", "endpoint": "RESULT_BUCKET_ENDPOINT",
                      "region": "RESULT_BUCKET_REGION", "access_key_id": "RESULT_BUCKET_ACCESS_KEY_ID",
                      "secret_access_key": "RESULT_BUCKET_SECRET_ACCESS_KEY"}


def _result_bucket(env: Mapping[str, str]) -> dict[str, str] | None:
    """The R-STORE bucket's settings when all are set; None when none is; an error when only some are."""
    values = {k: (env.get(v) or "").strip() for k, v in RESULT_BUCKET_KEYS.items()}
    if not any(values.values()):
        return None
    missing = [RESULT_BUCKET_KEYS[k] for k, v in values.items() if not v and k != "region"]
    if missing:
        raise ConfigError(f"Set every RESULT_BUCKET_* variable or none (missing: {', '.join(missing)})")
    return values


def _boolean(env: Mapping[str, str], name: str, default: bool) -> bool:
    raw = env.get(name, "true" if default else "false").strip().lower()
    if raw not in {"true", "false"}:
        raise ConfigError(f"{name} must be true or false")
    return raw == "true"


def _optional(env: Mapping[str, str], name: str) -> str | None:
    value = env.get(name, "").strip()
    return value or None


@dataclass(frozen=True)
class Settings:
    internal_api_key: str = field(repr=False)
    openrouter_api_key: str = field(repr=False)
    ai_model: str
    ai_reasoning_effort: str
    ai_request_timeout_seconds: int
    ai_max_output_tokens: int
    ai_max_tool_iterations: int
    ai_max_tool_calls: int
    ai_max_identical_tool_calls: int
    ai_max_analysis_seconds: int
    ai_max_context_tokens: int
    ai_context_soft_limit_ratio: float
    ai_max_history_tokens: int
    ai_final_response_max_retries: int
    openrouter_http_referer: str | None
    openrouter_x_title: str
    catalog_database_url: str | None = field(repr=False)
    catalog_connect_timeout_seconds: int
    catalog_statement_timeout_ms: int
    catalog_page_size_default: int
    catalog_page_size_max: int
    catalog_page_max_bytes: int
    market_data_preview_enabled: bool
    sql_governor_url: str | None
    sql_governor_api_key: str | None = field(repr=False)
    sql_governor_timeout_seconds: int
    request_data_max_result_bytes: int
    py_sandbox_url: str | None = None
    py_sandbox_api_key: str | None = field(default=None, repr=False)
    py_sandbox_request_timeout_seconds: int = 45
    py_sandbox_poll_wait_seconds: int = 20
    python_analysis_max_result_bytes: int = 40000
    # Relative analysis periods ("last three months") are resolved in this time zone.
    analysis_timezone: str = "Asia/Jakarta"
    # PostgreSQL DSN whose login may INSERT into "AI_research_run_audit"; unset disables the copy.
    research_audit_database_url: str | None = None
    # Model-facing tool flags (two-path migration). lookup_fact stays on until the prepared-analysis path has
    # parity for single source values and grouped counts; request_data (model-written data requests) is off:
    # data requests are compiled by the backend from the approved spec (prepare_analysis_data).
    ai_enable_lookup_fact: bool = True
    ai_enable_request_data: bool = False
    # DataNeed flow (DataNeedSpec -> governed bundle -> analysis session -> coverage): its tools are registered only
    # when this is on; the sandbox must run with PY_SANDBOX_DATANEED_ENABLED as well.
    ai_enable_dataneed: bool = False
    # HTTP timeout of one run_python call: above the sandbox's PY_SANDBOX_SESSION_EXECUTION_SECONDS plus its grace
    py_sandbox_session_timeout_seconds: int = 180
    # The same tool rejection (tool + reason code) may be repaired this many times per run.
    ai_max_repair_attempts: int = 3
    # Research Plan confirmation (DataNeed flow): research-mode data needs run only after the user approved a
    # backend-signed Research Plan. The key signs the plan continuation tokens (HMAC-SHA256); tokens expire after the TTL.
    ai_require_research_plan_confirmation: bool = False
    ai_research_plan_signing_key: str | None = field(default=None, repr=False)
    ai_research_plan_ttl_seconds: int = 3600
    # Named calendar-period returns use saniti.period_return (base: last valid value before the period start).
    ai_enable_standard_period_return: bool = False
    # G2 (2026-10-02): run_python and complete_analysis describe saniti.event_study and its backend recalculation
    ai_enable_event_study: bool = False
    # G3 (2026-10-02): the hypothesis plan (research plan v1, findings v1) beside the multi-angle plan
    ai_enable_hypothesis_plan: bool = False
    # 4b (2026-10-02): the menu of analysis methods at the start of every run and get_method_guide
    ai_enable_method_guides: bool = False
    # 4d (2026-10-02): mode 4 routes every later turn (CLARIFY, INSIGHT, CONTINUE, ...) instead of a new round
    ai_enable_conversation_router: bool = False
    # first-message router (user decision 2026-10-04, ROUTER_BENCHMARK_2026-10-04.md): every first message is routed
    # (CHAT, FACT, ANALYSIS, RESEARCH, EXPLORE) instead of taking AI_MODE_SWITCH's default; needs AI_ENABLE_MODE4
    ai_enable_first_turn_router: bool = False
    # EXEC-3 (user approvals 2026-10-05/06): the routers may ask back (one question with quick choices, nothing runs),
    # a failed router call is retried once and then asked back with a fixed question, the routers return the
    # understood intent and every design value with ADD, REPLACE or REMOVE (variants), and the plan-reply reader
    # returns them too (P3b); needs AI_ENABLE_FIRST_TURN_ROUTER
    ai_enable_ask_back: bool = False
    # EXEC-C (user decisions 2026-10-06: "Seharusnya AI membawa semuanya tanpa terkecuali", Q1 "pakai MEMO", Q2
    # "BACKEND + AI"): every run of a server-side conversation leaves a memory (AI_conversation_run_memory): a memo
    # written by the backend from the run's events plus the model's own note, given to every later run of the
    # conversation (append-only, after the history), its sources registered again under the same address, and its
    # full texts readable with read_conversation_memory; needs AI_ENABLE_CONVERSATION_STORE
    ai_enable_run_memory: bool = False
    # EXEC-P1 (user approval 2026-10-06): mode 4's first round stops after the analysis and its Research Plan, which
    # waits for the user's approval; true restores the earlier behaviour (the plan runs at once, then a suggestion)
    ai_mode4_auto_research: bool = False
    # EXEC-P5 (user approval 2026-10-06): an APPROVED data need is followed at once by prepare_data_bundle and
    # open_analysis_session, and run_python(complete=true) by complete_analysis, in the same turn
    ai_enable_merged_steps: bool = False
    # OpenRouter provider routing for the agent's model calls: provider.sort "price", "throughput" or "latency". Unset
    # keeps OpenRouter's default load balancing, which is weighted to the lowest price.
    ai_provider_sort: str | None = None
    # After a run, look up the provider that served each model call (OpenRouter /generation, in the background) and
    # log it as ai_model_call_provider; the Responses API does not return it.
    ai_log_provider: bool = False
    # Providers whose cache-read price is above this share of their prompt price are skipped (provider.ignore), derived
    # from OpenRouter's endpoint pricing and re-read every AI_PROVIDER_POLICY_TTL_SECONDS (user decision 2026-10-04).
    # Unset keeps OpenRouter's default routing.
    ai_provider_max_cache_price_ratio: float | None = None
    ai_provider_policy_ttl_seconds: int = 3600
    # Preferred minimum median output speed in tokens/s (provider.preferred_min_throughput p50, user decision
    # 2026-10-05): slower endpoints move to the end of OpenRouter's list instead of being excluded, and the price
    # weighting still applies among the faster ones. Unset keeps OpenRouter's default routing.
    ai_provider_min_throughput: float | None = None
    # The final-response JSON contract (and, with Research Plan confirmation, the plan's field skeleton) is part of the
    # system prompt, so a finished run answers in JSON at once instead of a prose draft that is re-asked as JSON.
    ai_final_contract_in_prompt: bool = False
    # A compact summary of the AI catalog (tables, columns, relationships, coverage, capabilities) is part of the
    # system prompt, so most runs skip the discovery round trips. Refreshed at most every
    # AI_CATALOG_SUMMARY_TTL_SECONDS; the prompt changes only when the catalog does.
    ai_catalog_summary_in_prompt: bool = False
    ai_catalog_summary_ttl_seconds: int = 900
    # Catalog discovery v2: discover_catalog filters and paging, formula search, join-semantics and resample fields,
    # table metadata and completeness in get_catalog_details (implementation plan 2026-09-27, phases C1-C2).
    ai_enable_catalog_discovery_v2: bool = False
    # The discovery protocol (phase C3): a short prompt rule, reuse of successful catalog results within a run, and a
    # guard that refuses submit_data_need_spec for tables, columns or relationships not read in the run. Needs v2.
    ai_enable_catalog_protocol: bool = False
    # Server-side conversation history (phase H1): history_mode SERVER reads earlier turns from PostgreSQL through
    # CONVERSATION_DATABASE_URL (the market_ai_conversation login). Conversations expire after the retention days;
    # one message runs at a time per conversation under a lease (0: AI_MAX_ANALYSIS_SECONDS + 120 s).
    ai_enable_conversation_store: bool = False
    conversation_database_url: str | None = field(default=None, repr=False)
    ai_conversation_retention_days: int = 30
    ai_conversation_lease_seconds: int = 0
    ai_conversation_upkeep_seconds: int = 3600
    # Conversation reuse (phases S1/S2): in history_mode SERVER, released outputs, bundles and warm Python sessions of
    # earlier messages of the conversation. Needs the conversation store and a sandbox that reports the capability.
    ai_enable_conversation_reuse: bool = False
    # R-STORE (round 2026-10-03 C2): released outputs and executions kept with the conversation; tables larger than
    # Postgres keeps go to the bucket named by RESULT_BUCKET_* (references to market-ai-conversation-outputs)
    ai_enable_result_store: bool = False
    result_bucket: dict[str, str] | None = field(default=None, repr=False)
    # D3 (round 2026-10-03): get_lineage, where an output's numbers came from (needs DataNeed and a sandbox reporting
    # bundle_lineage version 1)
    ai_enable_lineage_tool: bool = False
    # D4 (round 2026-10-03): export_result and GET /v1/exports/{export_id}/download (needs the result store and a
    # sandbox reporting stored_tables version 1)
    ai_enable_export: bool = False
    # D5 (round 2026-10-03): query_metric, the official metrics of AI_metric_catalog in one SQL Governor summary per
    # period (needs the catalog and the Governor; off when the catalog has no active metric)
    ai_enable_query_metric: bool = False
    # A model-written methodology note beside a DataNeed answer: data, steps, methods and parameters in plain words,
    # its numbers checked like the answer's (plus the parameters of the code that ran). Only in the DataNeed flow.
    ai_enable_methodology: bool = False
    # Research Plan feasibility: before a plan is presented, its DataNeedSpec is validated (sandbox draft) and
    # estimated by the Governor without extraction (check_data_feasibility); a plan is issued only after a FEASIBLE
    # check and the approved turn starts from that draft. Needs Research Plan confirmation and the DataNeed flow.
    ai_enable_plan_feasibility: bool = False
    # data_need_spec/v2 (IP1 Stage B): submit_data_need_spec and check_data_feasibility name every entity key pair of
    # a relationship (left_columns / right_columns), so composite keys such as Broker Summary <-> Feature 02 are
    # usable. Needs a sandbox that reports data_need_spec/v2 in GET /v1/runtime (otherwise inactive).
    ai_enable_composite_keys: bool = False
    # IP1 Stage D: data_need_spec/v2 time_basis. HISTORICAL_DESCRIPTIVE (the default) may use current-state reference
    # data with disclosure; POINT_IN_TIME uses only what was in effect and already recorded on each date, and the
    # sandbox refuses it where that history does not exist. Needs AI_ENABLE_COMPOSITE_KEYS (v2) and a sandbox that
    # reports point_in_time in GET /v1/runtime (otherwise inactive).
    ai_enable_point_in_time: bool = False
    # IP2 solution 1: weekly and monthly analysis derived from daily rows (saniti.resample semantics version 1). Needs
    # a sandbox that reports derived_frequency in GET /v1/runtime (otherwise inactive).
    ai_enable_derived_frequency: bool = False
    # research findings v1: backend sample category and verdict, interpretation in research answers
    ai_enable_research_findings: bool = False
    # Caller-chosen path: AgentRunRequest.analysis_path ANALYSIS or RESEARCH fixes the data-need mode of the request
    # (enforced on submit_data_need_spec); null keeps the model's choice. Needs AI_ENABLE_DATANEED and
    # AI_REQUIRE_RESEARCH_PLAN_CONFIRMATION (otherwise inactive and a request that sets it is refused).
    ai_enable_analysis_path: bool = False
    # A0/A2 (G10): the Execution Planner estimates every extraction part (EXPLAIN only) before the first extraction
    # and takes the fewest date parts that all fit; feasibility uses the same estimate. Off: the envelope estimate and
    # the extract-then-split loop as before.
    ai_enable_preflight_parts: bool = False
    # G15 (plan step 2.4): parts the Execution Planner extracts at the same time once the preflight chose them, 1-4;
    # 1 is the sequential order as before. Each part is still one Governor request with its own checks.
    ai_planner_parallel_parts: int = 1
    # M45 (plan step 6): a refused final draft that is a JSON object may be repaired with an edit object
    # ({"edits": [{"find", "replace"}], "fields": {...}}) instead of a full rewrite; every check runs again on the
    # edited answer and an edit that does not apply exactly falls back to the full rewrite. Off: as before.
    ai_enable_edit_repair: bool = False
    # AI_CAPTURE_REASONING (user decision 2026-10-01, dev measurement only): log the reasoning text of each model call
    # as ai_model_reasoning events (app/reasoning_capture.py). Never sent to the audit store or back to the model.
    ai_capture_reasoning: bool = False
    # S4c (K7, PLAN_FINAL_2026-10-04.md): the reasoning items of a run's earlier tool turns are sent back, exactly as
    # received, so a conclusion reached in reasoning is not lost a few steps later. Never across messages. A provider
    # that refuses them turns it off for the rest of the run.
    ai_replay_reasoning: bool = False
    # S4b (K8): find_web_fact, one fact that is not in the data from market-web-governor POST /v1/fact
    ai_enable_web_fact: bool = False
    # Item 12 (plan 2026-10-05): research_web, facts, numbers, events, series and lists from market-web-governor
    # POST /v1/orc/web in a citable envelope; never together with find_web_fact (start refused)
    ai_enable_web_research: bool = False
    # P34 (plan 2026-10-05 Fase D option A): lookup_reference reads the static reference tables, and find_web_fact is
    # refused once when one of their columns holds the asked attribute (one small matcher call; fail-open)
    ai_enable_reference_lookup: bool = False
    web_governor_url: str | None = None
    web_governor_api_key: str | None = field(default=None, repr=False)
    # Multi-Angle Research (MULTI_ANGLE_RESEARCH.md): research_plan/v2 with 3-6 angles, rpc2, per-angle data contracts,
    # grouped execution behind start/run/complete_research_run and backend findings per angle. Needs DataNeed v2,
    # Research Plan confirmation and feasibility, and a sandbox reporting the matching multi_angle_research capability
    # (otherwise inactive: research v1 as before). Angle limits may only narrow 2-6 (the minimum 2 since 2026-09-29,
    # user decision: do not force many angles); groups run one at a time. AI_RESEARCH_MIN_FAMILIES (0 = off) makes a
    # plan use at least that many of the five method families (prepared, off by default).
    ai_enable_multi_angle_research: bool = False
    ai_research_min_angles: int = 2
    ai_research_max_angles: int = 6
    ai_research_min_families: int = 0
    ai_research_max_bundle_groups: int = 3
    ai_research_max_parallel_groups: int = 1
    # S16 (user decision 2026-09-30): a group whose session crashed (WORKER_CRASHED, SESSION_STATE_CORRUPTED,
    # PROTOCOL_ERROR) may open a new session this many times; 0 closes the group at once. Session limits never reopen.
    ai_research_max_session_restarts: int = 1
    # P11 (user decision 2026-09-30): the model writes data figures as value references ({{finding.x.path|fmt}}) that
    # the backend fills in and formats, and multi-angle findings are rendered from the backend (#15). DataNeed only.
    ai_enable_value_references: bool = False
    # 10.1-10.4 (plan 2026-10-05 item 10, user decision): every tool result that holds values lists their full value
    # references (an address menu the model copies), check_references renders addresses before the answer is written,
    # and a field a hypothesis finding lacks is read from its research_summary output. Needs value references.
    ai_enable_address_menu: bool = False
    # Round 2026-10-03 (ENV, ROUND_PLAN_2026-10-03.md A2): every tool result the model reads in one envelope
    # (status, data, warnings, errors with next_action, meta); the orchestrator's own reading of results is unchanged.
    ai_enable_tool_envelope: bool = False
    # Mode 4 (user decision 2026-09-30, app/mode4.py): a request without analysis_path (or with MODE4) is answered by
    # an analysis, then research of at least two angles built on it runs at once, then one follow-up angle is
    # proposed for the user's confirmation; an approval runs that angle and proposes the next one
    ai_enable_mode4: bool = False
    # Mode switcher (user decision 2026-09-30, app/modes.py): the mode of a request that sets no analysis_path and
    # replies to no plan: 1 AUTO (the model chooses), 2 ANALYSIS, 3 RESEARCH, 4 MODE4
    ai_mode_switch: int = 1
    # the wall-clock budget of one whole mode 4 request (its sub-runs share it; each also keeps AI_MAX_ANALYSIS_SECONDS)
    ai_mode4_max_seconds: int = 3600
    # IP2 solution 2: archive every finished run to market-audit-store through ai_audit.ingest_outbox (INSERT only,
    # AUDIT_OUTBOX_DATABASE_URL). With AI_AUDIT_STORE_REQUIRED false an archive failure is logged and never changes
    # the answer; true withholds the answer when the run cannot be handed to the outbox (regulated mode).
    ai_audit_store_enabled: bool = False
    ai_audit_store_required: bool = False
    audit_outbox_database_url: str | None = field(default=None, repr=False)
    # Model switcher (user decision 2026-09-30): AI_MODEL_SWITCH 1 runs AI_MODEL (deepseek/deepseek-v4.1-flash, the
    # default), 2 runs AI_MODEL_2 (xiaomi/mimo-v2.6-pro). ai_model is the model in use. MiMo exposes no reasoning
    # effort levels on OpenRouter (2026-09-30), so switch 2 sends reasoning.enabled instead of reasoning.effort.
    ai_model_switch: int = 1
    ai_model_1: str = "deepseek/deepseek-v4.1-flash"
    ai_model_2: str = "xiaomi/mimo-v2.6-pro"
    # How model 2 takes reasoning (K1, 2026-10-04): "enabled" (on/off, the default) or "effort" (the level itself), so
    # a model 2 that honours levels needs no code change.
    ai_model_2_reasoning_form: str = "enabled"

    def reasoning(self, effort: str) -> dict[str, Any]:
        """The OpenRouter reasoning setting for a call of the given effort, in the form the selected model accepts."""
        if self.ai_model_switch == 2 and self.ai_model_2_reasoning_form == "enabled":
            return {"enabled": effort not in ("none", "minimal", "low")}
        return {"effort": effort}

    @property
    def conversation_lease_seconds(self) -> int:
        return self.ai_conversation_lease_seconds or self.longest_run_seconds + 120

    @property
    def longest_run_seconds(self) -> int:
        """The longest one request may run: AI_MAX_ANALYSIS_SECONDS, or AI_MODE4_MAX_SECONDS with mode 4."""
        return max(self.ai_max_analysis_seconds, self.ai_mode4_max_seconds if self.ai_enable_mode4 else 0)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if env is None else env
        secrets = {
            "MARKET_AI_ORC_API_KEY": env.get("MARKET_AI_ORC_API_KEY", ""),
            "OPENROUTER_API_KEY": env.get("OPENROUTER_API_KEY", ""),
        }
        missing = [name for name, value in secrets.items() if not value.strip()]
        if missing:
            raise ConfigError(f"Missing required variables: {', '.join(missing)}")

        settings = cls(
            internal_api_key=secrets["MARKET_AI_ORC_API_KEY"],
            openrouter_api_key=secrets["OPENROUTER_API_KEY"],
            ai_model=(env.get("AI_MODEL_2", "").strip() or "xiaomi/mimo-v2.6-pro")
            if (env.get("AI_MODEL_SWITCH") or "").strip() == "2"
            else env.get("AI_MODEL", "").strip() or "deepseek/deepseek-v4.1-flash",
            ai_model_switch=_integer(env, "AI_MODEL_SWITCH", 1),
            ai_model_1=env.get("AI_MODEL", "").strip() or "deepseek/deepseek-v4.1-flash",
            ai_model_2=env.get("AI_MODEL_2", "").strip() or "xiaomi/mimo-v2.6-pro",
            ai_model_2_reasoning_form=(env.get("AI_MODEL_2_REASONING_FORM") or "").strip().lower() or "enabled",
            ai_reasoning_effort=env.get("AI_REASONING_EFFORT", "").strip().lower() or "high",
            ai_request_timeout_seconds=_integer(env, "AI_REQUEST_TIMEOUT_SECONDS", 180),
            ai_max_output_tokens=_integer(env, "AI_MAX_OUTPUT_TOKENS", 8000),
            ai_max_tool_iterations=_integer(env, "AI_MAX_TOOL_ITERATIONS", 8),
            ai_max_tool_calls=_integer(env, "AI_MAX_TOOL_CALLS", 12),
            ai_max_identical_tool_calls=_integer(env, "AI_MAX_IDENTICAL_TOOL_CALLS", 2),
            ai_max_analysis_seconds=_integer(env, "AI_MAX_ANALYSIS_SECONDS", 600),
            ai_max_context_tokens=_integer(env, "AI_MAX_CONTEXT_TOKENS", 64000),
            ai_context_soft_limit_ratio=_ratio(env, "AI_CONTEXT_SOFT_LIMIT_RATIO", 0.8, 0.5, 0.95),
            ai_max_history_tokens=_integer(env, "AI_MAX_HISTORY_TOKENS", 4000),
            ai_final_response_max_retries=_integer(
                env, "AI_FINAL_RESPONSE_MAX_RETRIES", 2, minimum=0
            ),
            openrouter_http_referer=_optional(env, "OPENROUTER_HTTP_REFERER"),
            openrouter_x_title=_optional(env, "OPENROUTER_X_TITLE") or "Saniti Market AI",
            catalog_database_url=_optional(env, "CATALOG_DATABASE_URL"),
            catalog_connect_timeout_seconds=_integer(env, "CATALOG_CONNECT_TIMEOUT_SECONDS", 5),
            catalog_statement_timeout_ms=_integer(env, "CATALOG_STATEMENT_TIMEOUT_MS", 5000, minimum=100),
            catalog_page_size_default=_integer(env, "CATALOG_PAGE_SIZE_DEFAULT", 100),
            catalog_page_size_max=_integer(env, "CATALOG_PAGE_SIZE_MAX", 200),
            catalog_page_max_bytes=_integer(env, "CATALOG_PAGE_MAX_BYTES", 16000, minimum=4096),
            market_data_preview_enabled=_boolean(env, "MARKET_DATA_PREVIEW_ENABLED", True),
            sql_governor_url=_optional(env, "SQL_GOVERNOR_URL"),
            ai_enable_lookup_fact=_boolean(env, "AI_ENABLE_LOOKUP_FACT", True),
            ai_enable_request_data=_boolean(env, "AI_ENABLE_REQUEST_DATA", False),
            ai_enable_dataneed=_boolean(env, "AI_ENABLE_DATANEED", False),
            py_sandbox_session_timeout_seconds=_integer(env, "PY_SANDBOX_SESSION_TIMEOUT_SECONDS", 180, minimum=20),
            ai_max_repair_attempts=_integer(env, "AI_MAX_REPAIR_ATTEMPTS", 3, minimum=1),
            ai_require_research_plan_confirmation=_boolean(env, "AI_REQUIRE_RESEARCH_PLAN_CONFIRMATION", False),
            ai_research_plan_signing_key=env.get("AI_RESEARCH_PLAN_SIGNING_KEY") or None,
            ai_research_plan_ttl_seconds=_integer(env, "AI_RESEARCH_PLAN_TTL_SECONDS", 3600, minimum=60),
            ai_enable_standard_period_return=_boolean(env, "AI_ENABLE_STANDARD_PERIOD_RETURN", False),
            ai_enable_event_study=_boolean(env, "AI_ENABLE_EVENT_STUDY", False),
            ai_enable_hypothesis_plan=_boolean(env, "AI_ENABLE_HYPOTHESIS_PLAN", False),
            ai_enable_method_guides=_boolean(env, "AI_ENABLE_METHOD_GUIDES", False),
            ai_enable_conversation_router=_boolean(env, "AI_ENABLE_CONVERSATION_ROUTER", False),
            ai_enable_first_turn_router=_boolean(env, "AI_ENABLE_FIRST_TURN_ROUTER", False),
            ai_enable_ask_back=_boolean(env, "AI_ENABLE_ASK_BACK", False),
            ai_enable_run_memory=_boolean(env, "AI_ENABLE_RUN_MEMORY", False),
            ai_mode4_auto_research=_boolean(env, "AI_MODE4_AUTO_RESEARCH", False),
            ai_enable_merged_steps=_boolean(env, "AI_ENABLE_MERGED_STEPS", False),
            ai_provider_sort=(env.get("AI_PROVIDER_SORT") or "").strip().lower() or None,
            ai_log_provider=_boolean(env, "AI_LOG_PROVIDER", False),
            ai_provider_max_cache_price_ratio=_ratio(env, "AI_PROVIDER_MAX_CACHE_PRICE_RATIO", 0.0, 0.0, 1.0)
            if (env.get("AI_PROVIDER_MAX_CACHE_PRICE_RATIO") or "").strip() else None,
            ai_provider_policy_ttl_seconds=_integer(env, "AI_PROVIDER_POLICY_TTL_SECONDS", 3600, minimum=60),
            ai_provider_min_throughput=_ratio(env, "AI_PROVIDER_MIN_THROUGHPUT", 0.0, 1.0, 10000.0)
            if (env.get("AI_PROVIDER_MIN_THROUGHPUT") or "").strip() else None,
            ai_final_contract_in_prompt=_boolean(env, "AI_FINAL_CONTRACT_IN_PROMPT", False),
            ai_catalog_summary_in_prompt=_boolean(env, "AI_CATALOG_SUMMARY_IN_PROMPT", False),
            ai_catalog_summary_ttl_seconds=_integer(env, "AI_CATALOG_SUMMARY_TTL_SECONDS", 900, minimum=60),
            ai_enable_catalog_discovery_v2=_boolean(env, "AI_ENABLE_CATALOG_DISCOVERY_V2", False),
            ai_enable_catalog_protocol=_boolean(env, "AI_ENABLE_CATALOG_PROTOCOL", False),
            ai_enable_conversation_store=_boolean(env, "AI_ENABLE_CONVERSATION_STORE", False),
            conversation_database_url=_optional(env, "CONVERSATION_DATABASE_URL"),
            ai_conversation_retention_days=_integer(env, "AI_CONVERSATION_RETENTION_DAYS", 30),
            ai_conversation_lease_seconds=_integer(env, "AI_CONVERSATION_LEASE_SECONDS", 0, minimum=0),
            ai_conversation_upkeep_seconds=_integer(env, "AI_CONVERSATION_UPKEEP_SECONDS", 3600, minimum=60),
            ai_enable_conversation_reuse=_boolean(env, "AI_ENABLE_CONVERSATION_REUSE", False),
            ai_enable_result_store=_boolean(env, "AI_ENABLE_RESULT_STORE", False),
            ai_enable_lineage_tool=_boolean(env, "AI_ENABLE_LINEAGE_TOOL", False),
            ai_enable_export=_boolean(env, "AI_ENABLE_EXPORT", False),
            ai_enable_query_metric=_boolean(env, "AI_ENABLE_QUERY_METRIC", False),
            result_bucket=_result_bucket(env),
            ai_enable_methodology=_boolean(env, "AI_ENABLE_METHODOLOGY", False),
            ai_enable_plan_feasibility=_boolean(env, "AI_ENABLE_PLAN_FEASIBILITY", False),
            ai_enable_composite_keys=_boolean(env, "AI_ENABLE_COMPOSITE_KEYS", False),
            ai_enable_point_in_time=_boolean(env, "AI_ENABLE_POINT_IN_TIME", False),
            ai_enable_derived_frequency=_boolean(env, "AI_ENABLE_DERIVED_FREQUENCY", False),
            ai_enable_research_findings=_boolean(env, "AI_ENABLE_RESEARCH_FINDINGS", False),
            ai_enable_analysis_path=_boolean(env, "AI_ENABLE_ANALYSIS_PATH", False),
            ai_enable_preflight_parts=_boolean(env, "AI_ENABLE_PREFLIGHT_PARTS", False),
            ai_planner_parallel_parts=_integer(env, "AI_PLANNER_PARALLEL_PARTS", 1),
            ai_enable_edit_repair=_boolean(env, "AI_ENABLE_EDIT_REPAIR", False),
            ai_capture_reasoning=_boolean(env, "AI_CAPTURE_REASONING", False),
            ai_replay_reasoning=_boolean(env, "AI_REPLAY_REASONING", False),
            ai_enable_web_fact=_boolean(env, "AI_ENABLE_WEB_FACT", False),
            ai_enable_web_research=_boolean(env, "AI_ENABLE_WEB_RESEARCH", False),
            ai_enable_reference_lookup=_boolean(env, "AI_ENABLE_REFERENCE_LOOKUP", False),
            web_governor_url=_optional(env, "WEB_GOVERNOR_URL"),
            web_governor_api_key=_optional(env, "WEB_GOVERNOR_API_KEY"),
            ai_enable_multi_angle_research=_boolean(env, "AI_ENABLE_MULTI_ANGLE_RESEARCH", False),
            ai_research_min_angles=_integer(env, "AI_RESEARCH_MIN_ANGLES", 2),
            ai_research_max_angles=_integer(env, "AI_RESEARCH_MAX_ANGLES", 6),
            ai_research_min_families=_integer(env, "AI_RESEARCH_MIN_FAMILIES", 0, minimum=0),
            ai_research_max_bundle_groups=_integer(env, "AI_RESEARCH_MAX_BUNDLE_GROUPS", 3),
            ai_research_max_parallel_groups=_integer(env, "AI_RESEARCH_MAX_PARALLEL_GROUPS", 1),
            ai_research_max_session_restarts=_integer(env, "AI_RESEARCH_MAX_SESSION_RESTARTS", 1, minimum=0),
            ai_enable_value_references=_boolean(env, "AI_ENABLE_VALUE_REFERENCES", False),
            ai_enable_address_menu=_boolean(env, "AI_ENABLE_ADDRESS_MENU", False),
            ai_enable_tool_envelope=_boolean(env, "AI_ENABLE_TOOL_ENVELOPE", False),
            ai_enable_mode4=_boolean(env, "AI_ENABLE_MODE4", False),
            ai_mode4_max_seconds=_integer(env, "AI_MODE4_MAX_SECONDS", 3600, minimum=60),
            ai_mode_switch=_integer(env, "AI_MODE_SWITCH", 1),
            ai_audit_store_enabled=_boolean(env, "AI_AUDIT_STORE_ENABLED", False),
            ai_audit_store_required=_boolean(env, "AI_AUDIT_STORE_REQUIRED", False),
            audit_outbox_database_url=_optional(env, "AUDIT_OUTBOX_DATABASE_URL"),
            sql_governor_api_key=_optional(env, "SQL_GOVERNOR_API_KEY"),
            sql_governor_timeout_seconds=_integer(env, "SQL_GOVERNOR_TIMEOUT_SECONDS", 90),
            request_data_max_result_bytes=_integer(env, "REQUEST_DATA_MAX_RESULT_BYTES", 40000, minimum=8192),
            py_sandbox_url=_optional(env, "PY_SANDBOX_URL"),
            py_sandbox_api_key=_optional(env, "PY_SANDBOX_API_KEY"),
            py_sandbox_request_timeout_seconds=_integer(env, "PY_SANDBOX_REQUEST_TIMEOUT_SECONDS", 45, minimum=10),
            py_sandbox_poll_wait_seconds=_integer(env, "PY_SANDBOX_POLL_WAIT_SECONDS", 20, minimum=0),
            python_analysis_max_result_bytes=_integer(env, "PYTHON_ANALYSIS_MAX_RESULT_BYTES", 40000, minimum=8192),
            analysis_timezone=env.get("ANALYSIS_TIMEZONE", "").strip() or "Asia/Jakarta",
            research_audit_database_url=_optional(env, "RESEARCH_AUDIT_DATABASE_URL"),
        )
        try:
            from zoneinfo import ZoneInfo

            ZoneInfo(settings.analysis_timezone)
        except Exception as exc:  # noqa: BLE001 - any lookup failure is a configuration error
            raise ConfigError("ANALYSIS_TIMEZONE must be an IANA time zone such as Asia/Jakarta") from exc
        if settings.ai_reasoning_effort not in REASONING_EFFORTS:
            raise ConfigError(
                "AI_REASONING_EFFORT must be one of: " + ", ".join(sorted(REASONING_EFFORTS))
            )
        if settings.ai_max_output_tokens >= settings.ai_max_context_tokens:
            raise ConfigError("AI_MAX_OUTPUT_TOKENS must be below AI_MAX_CONTEXT_TOKENS")
        if settings.ai_max_output_tokens >= settings.ai_max_context_tokens * settings.ai_context_soft_limit_ratio:
            raise ConfigError(
                "AI_MAX_OUTPUT_TOKENS must be below AI_MAX_CONTEXT_TOKENS x AI_CONTEXT_SOFT_LIMIT_RATIO"
            )
        if settings.ai_max_history_tokens >= settings.ai_max_context_tokens:
            raise ConfigError("AI_MAX_HISTORY_TOKENS must be below AI_MAX_CONTEXT_TOKENS")
        if settings.catalog_database_url and not settings.catalog_database_url.startswith(
            ("postgresql://", "postgres://")
        ):
            raise ConfigError("CATALOG_DATABASE_URL must be a postgresql:// connection URL")
        if settings.research_audit_database_url and not settings.research_audit_database_url.startswith(
            ("postgresql://", "postgres://")
        ):
            raise ConfigError("RESEARCH_AUDIT_DATABASE_URL must be a postgresql:// connection URL")
        if settings.catalog_connect_timeout_seconds > 30 or settings.catalog_statement_timeout_ms > 30000:
            raise ConfigError("Catalog connect/statement timeouts must not exceed 30 seconds")
        if settings.catalog_page_size_default > settings.catalog_page_size_max:
            raise ConfigError("CATALOG_PAGE_SIZE_DEFAULT must not exceed CATALOG_PAGE_SIZE_MAX")
        if settings.catalog_page_size_max > 1000 or settings.catalog_page_max_bytes > 131072:
            raise ConfigError("CATALOG_PAGE_SIZE_MAX must be <= 1000 and CATALOG_PAGE_MAX_BYTES <= 131072")
        if settings.sql_governor_url:
            if not settings.sql_governor_url.startswith(("http://", "https://")):
                raise ConfigError("SQL_GOVERNOR_URL must be an http(s):// URL")
            if not settings.sql_governor_api_key or len(settings.sql_governor_api_key) < 32:
                raise ConfigError("SQL_GOVERNOR_API_KEY (at least 32 characters) is required with SQL_GOVERNOR_URL")
        if settings.sql_governor_timeout_seconds > 300 or settings.request_data_max_result_bytes > 131072:
            raise ConfigError("SQL_GOVERNOR_TIMEOUT_SECONDS must be <= 300 and REQUEST_DATA_MAX_RESULT_BYTES <= 131072")
        if settings.py_sandbox_url:
            if not settings.py_sandbox_url.startswith(("http://", "https://")):
                raise ConfigError("PY_SANDBOX_URL must be an http(s):// URL")
            if not settings.py_sandbox_api_key or len(settings.py_sandbox_api_key) < 32:
                raise ConfigError("PY_SANDBOX_API_KEY (at least 32 characters) is required with PY_SANDBOX_URL")
        if settings.py_sandbox_session_timeout_seconds > 960:
            raise ConfigError("PY_SANDBOX_SESSION_TIMEOUT_SECONDS must be at most 960")
        if settings.py_sandbox_request_timeout_seconds > 300 or settings.python_analysis_max_result_bytes > 131072:
            raise ConfigError("PY_SANDBOX_REQUEST_TIMEOUT_SECONDS must be <= 300 and "
                              "PYTHON_ANALYSIS_MAX_RESULT_BYTES <= 131072")
        if settings.py_sandbox_poll_wait_seconds > min(60, settings.py_sandbox_request_timeout_seconds - 10):
            raise ConfigError("PY_SANDBOX_POLL_WAIT_SECONDS must be <= 60 and at least 10 s below "
                              "PY_SANDBOX_REQUEST_TIMEOUT_SECONDS")
        if settings.ai_request_timeout_seconds > settings.ai_max_analysis_seconds:
            raise ConfigError("AI_REQUEST_TIMEOUT_SECONDS must not exceed AI_MAX_ANALYSIS_SECONDS")
        if settings.ai_planner_parallel_parts > 4:
            raise ConfigError("AI_PLANNER_PARALLEL_PARTS must be from 1 to 4")
        if settings.ai_enable_web_fact and settings.ai_enable_web_research:
            raise ConfigError("AI_ENABLE_WEB_FACT and AI_ENABLE_WEB_RESEARCH are exclusive: turn one off")
        if not 2 <= settings.ai_research_min_angles <= settings.ai_research_max_angles <= 6:
            raise ConfigError("AI_RESEARCH_MIN_ANGLES and AI_RESEARCH_MAX_ANGLES must satisfy 2 <= min <= max <= 6")
        if not 0 <= settings.ai_research_min_families <= min(5, settings.ai_research_max_angles):
            raise ConfigError("AI_RESEARCH_MIN_FAMILIES must be from 0 (off) to 5 and at most AI_RESEARCH_MAX_ANGLES")
        if settings.ai_mode_switch not in (1, 2, 3, 4):
            raise ConfigError("AI_MODE_SWITCH must be 1 (AUTO), 2 (ANALYSIS), 3 (RESEARCH) or 4 (MODE4)")
        if settings.ai_enable_first_turn_router and not settings.ai_enable_mode4:
            raise ConfigError("AI_ENABLE_FIRST_TURN_ROUTER needs AI_ENABLE_MODE4=true")
        if settings.ai_enable_ask_back and not settings.ai_enable_first_turn_router:
            raise ConfigError("AI_ENABLE_ASK_BACK needs AI_ENABLE_FIRST_TURN_ROUTER=true")
        if settings.ai_enable_run_memory and not settings.ai_enable_conversation_store:
            raise ConfigError("AI_ENABLE_RUN_MEMORY needs AI_ENABLE_CONVERSATION_STORE=true")
        if settings.ai_mode_switch == 4 and not settings.ai_enable_mode4:
            raise ConfigError("AI_MODE_SWITCH=4 needs AI_ENABLE_MODE4=true")
        if settings.ai_mode_switch in (2, 3) and not settings.ai_enable_analysis_path:
            raise ConfigError("AI_MODE_SWITCH=2 or 3 needs AI_ENABLE_ANALYSIS_PATH=true")
        if settings.ai_model_switch not in (1, 2):
            raise ConfigError("AI_MODEL_SWITCH must be 1 (AI_MODEL) or 2 (AI_MODEL_2)")
        if not 0 <= settings.ai_research_max_session_restarts <= 3:
            raise ConfigError("AI_RESEARCH_MAX_SESSION_RESTARTS must be from 0 (close the group) to 3")
        if not 1 <= settings.ai_research_max_bundle_groups <= 6:
            raise ConfigError("AI_RESEARCH_MAX_BUNDLE_GROUPS must be between 1 and 6")
        if settings.ai_research_max_parallel_groups != 1:
            # the sandbox has few session slots for every run together and a run keeps one open session (S08)
            raise ConfigError("AI_RESEARCH_MAX_PARALLEL_GROUPS must be 1 in this release (groups run one at a time)")
        if settings.ai_research_plan_ttl_seconds > MAX_TTL_SECONDS:
            raise ConfigError(f"AI_RESEARCH_PLAN_TTL_SECONDS must be at most {MAX_TTL_SECONDS}")
        if settings.ai_model_2_reasoning_form not in ("enabled", "effort"):
            raise ConfigError("AI_MODEL_2_REASONING_FORM must be enabled or effort")
        if settings.ai_provider_sort not in (None, "price", "throughput", "latency"):
            raise ConfigError("AI_PROVIDER_SORT must be price, throughput or latency")
        if settings.ai_catalog_summary_in_prompt and not settings.catalog_database_url:
            raise ConfigError("AI_CATALOG_SUMMARY_IN_PROMPT needs CATALOG_DATABASE_URL")
        if settings.ai_enable_export and not settings.ai_enable_result_store:
            raise ConfigError("AI_ENABLE_EXPORT requires AI_ENABLE_RESULT_STORE (exports are kept with the conversation)")
        if settings.ai_enable_result_store and not settings.ai_enable_conversation_reuse:
            raise ConfigError("AI_ENABLE_RESULT_STORE requires AI_ENABLE_CONVERSATION_REUSE (and the conversation "
                              "store): results are kept per server conversation")
        if settings.ai_enable_conversation_reuse and not settings.ai_enable_conversation_store:
            raise ConfigError("AI_ENABLE_CONVERSATION_REUSE needs AI_ENABLE_CONVERSATION_STORE")
        if settings.ai_audit_store_enabled:
            # the outbox URL is required only while the feature is on
            if not settings.audit_outbox_database_url:
                raise ConfigError("AI_AUDIT_STORE_ENABLED needs AUDIT_OUTBOX_DATABASE_URL")
            if not settings.audit_outbox_database_url.startswith(("postgresql://", "postgres://")):
                raise ConfigError("AUDIT_OUTBOX_DATABASE_URL must be a postgresql:// connection URL")
        if settings.ai_audit_store_required and not settings.ai_audit_store_enabled:
            raise ConfigError("AI_AUDIT_STORE_REQUIRED needs AI_AUDIT_STORE_ENABLED")
        if settings.ai_enable_conversation_store and not settings.conversation_database_url:
            raise ConfigError("AI_ENABLE_CONVERSATION_STORE needs CONVERSATION_DATABASE_URL")
        if settings.conversation_database_url and not settings.conversation_database_url.startswith(
            ("postgresql://", "postgres://")
        ):
            raise ConfigError("CONVERSATION_DATABASE_URL must be a postgresql:// connection URL")
        if settings.ai_conversation_lease_seconds and \
                settings.ai_conversation_lease_seconds <= settings.longest_run_seconds:
            # a lease shorter than a run would let a second message take over a conversation still running
            raise ConfigError("AI_CONVERSATION_LEASE_SECONDS must exceed AI_MAX_ANALYSIS_SECONDS (and "
                              "AI_MODE4_MAX_SECONDS when AI_ENABLE_MODE4 is on)")
        if settings.ai_enable_catalog_protocol and not settings.ai_enable_catalog_discovery_v2:
            # the protocol tells the model to filter discovery and read completeness, which only v2 provides
            raise ConfigError("AI_ENABLE_CATALOG_PROTOCOL needs AI_ENABLE_CATALOG_DISCOVERY_V2")
        if settings.ai_require_research_plan_confirmation:
            problem = weak_key_problem(settings.ai_research_plan_signing_key)
            if problem:
                raise ConfigError(problem)
        return settings
