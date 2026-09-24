-- Research AI: the per-run audit table, its INSERT-only writer role, and the new analysis tool contracts.
--
-- "AI_research_run_audit" holds one summary row per market-ai-orc run, copied after the run finishes:
-- what was asked, what the AI finally reported, the evidence label and gate outcome, and every experiment
-- with its Research Governor decision, validation, evidence decision, and code/dataset fingerprints.
-- Operational run state stays in market-python-sandbox; this table is the durable audit copy. No hidden
-- model reasoning, secret, or raw dataset is stored.
-- market_ai_research_audit_writer (NOLOGIN) may only INSERT into it; it is granted to the orchestrator login
-- market_ai_orc when that login exists. Nobody else gets access; PUBLIC is revoked.
-- Tool_Catalog: create_analysis_spec v2 (research block, EVENT_STUDY, CUSTOM expressions, governor
-- decisions), run_python_analysis v3 and get_analysis_result v3 (evidence_assessment, leakage_check) at
-- runtime commit 0e0234c; the previous versions are marked superseded. All stay is_active = false.
-- Forward-only. No market-data table, SQL Governor grant, or source data is changed.
BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';

DO $preflight$
BEGIN
    IF to_regclass('public."AI_research_run_audit"') IS NOT NULL THEN
        RAISE EXCEPTION 'AI_research_run_audit already exists: inspect before applying';
    END IF;
    IF EXISTS (SELECT 1 FROM public."Tool_Catalog"
               WHERE (tool_name = 'create_analysis_spec' AND version = 'v2')
                  OR (tool_name IN ('run_python_analysis', 'get_analysis_result') AND version = 'v3')) THEN
        RAISE EXCEPTION 'The Research AI tool versions are already registered in Tool_Catalog';
    END IF;
    IF (SELECT count(*) FROM public."Tool_Catalog"
        WHERE tool_specific_limits->>'runtime_service' = 'market-ai-orc' AND NOT is_active
          AND tool_specific_limits->>'runtime_commit' = '27e118a'
          AND ((tool_name = 'create_analysis_spec' AND version = 'v1')
               OR (tool_name IN ('run_python_analysis', 'get_analysis_result') AND version = 'v2'))) <> 3 THEN
        RAISE EXCEPTION 'Expected create_analysis_spec v1, run_python_analysis v2 and get_analysis_result v2 at 27e118a';
    END IF;
END
$preflight$;

CREATE TABLE public."AI_research_run_audit" (
    request_id text PRIMARY KEY,
    recorded_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status text NOT NULL,
    response_type text,
    evidence_label text,
    validation_gate text NOT NULL,
    error_code text,
    question_sha256 text NOT NULL,
    question text NOT NULL,
    answer_sha256 text,
    answer text,
    limitations jsonb NOT NULL DEFAULT '[]'::jsonb,
    number_provenance jsonb,
    experiments jsonb NOT NULL DEFAULT '[]'::jsonb,
    datasets jsonb NOT NULL DEFAULT '[]'::jsonb,
    budget jsonb NOT NULL DEFAULT '{}'::jsonb,
    model text NOT NULL,
    tool_call_count integer NOT NULL,
    total_tokens integer NOT NULL,
    duration_ms integer NOT NULL,
    sandbox_summary_status text NOT NULL,
    CONSTRAINT ai_research_run_audit_request_id_check CHECK (request_id ~ '^[A-Za-z0-9._:-]{1,200}$'),
    CONSTRAINT ai_research_run_audit_status_check
        CHECK (status IN ('COMPLETED', 'NEEDS_CLARIFICATION', 'LIMITED', 'FAILED')),
    CONSTRAINT ai_research_run_audit_response_check
        CHECK (response_type IS NULL OR response_type IN ('ANSWER', 'CLARIFICATION', 'LIMITATION')),
    CONSTRAINT ai_research_run_audit_gate_check
        CHECK (validation_gate IN ('NOT_APPLICABLE', 'PASSED', 'ANNOTATED', 'FORCED_LIMITATION')),
    CONSTRAINT ai_research_run_audit_hash_check CHECK (question_sha256 ~ '^[0-9a-f]{64}$'
        AND (answer_sha256 IS NULL OR answer_sha256 ~ '^[0-9a-f]{64}$')),
    CONSTRAINT ai_research_run_audit_text_check CHECK (length(question) <= 16000
        AND (answer IS NULL OR length(answer) <= 20000)),
    CONSTRAINT ai_research_run_audit_json_check CHECK (jsonb_typeof(limitations) = 'array'
        AND jsonb_typeof(experiments) = 'array' AND jsonb_typeof(datasets) = 'array'
        AND jsonb_typeof(budget) = 'object'),
    CONSTRAINT ai_research_run_audit_counts_check CHECK (tool_call_count >= 0 AND total_tokens >= 0
        AND duration_ms >= 0),
    CONSTRAINT ai_research_run_audit_sandbox_check CHECK (sandbox_summary_status IN
        ('REPORTED', 'AWAITING_REPORT', 'ACTIVE', 'UNAVAILABLE', 'NOT_USED'))
);
CREATE INDEX ai_research_run_audit_recorded_idx ON public."AI_research_run_audit" (recorded_at);
COMMENT ON TABLE public."AI_research_run_audit" IS
    'One audit row per market-ai-orc run: question, final answer, evidence label, and experiments with their governor, validation and evidence decisions. Written once (INSERT only).';

DO $role$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'market_ai_research_audit_writer') THEN
        CREATE ROLE market_ai_research_audit_writer NOLOGIN;
    END IF;
END
$role$;
REVOKE ALL ON public."AI_research_run_audit" FROM PUBLIC;
GRANT INSERT ON public."AI_research_run_audit" TO market_ai_research_audit_writer;
DO $grant$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'market_ai_orc') THEN
        GRANT market_ai_research_audit_writer TO market_ai_orc;
    END IF;
END
$grant$;

INSERT INTO public."Table_Catalog" (
    table_schema, table_name, category, definition, grain,
    primary_key_columns, source_system, source_tables, source_code_paths,
    update_rule, related_functions, documentation_status,
    readiness_mode, readiness_date_column, observation_date_column,
    data_available_at_column, availability_rule, point_in_time_status,
    historical_metadata_method
) VALUES (
    'public', 'AI_research_run_audit', 'System',
    'Durable audit of market-ai-orc runs: the question, the final answer, its evidence label and gate outcome, and every experiment with its Research Governor decision, validation, evidence decision and fingerprints.',
    'One row per market-ai-orc request_id', ARRAY['request_id'],
    'market-ai-orc (app/audit.py) after each run, from its own result and the market-python-sandbox run record',
    ARRAY[]::text[], ARRAY['apps/market-ai-orc/app/audit.py',
                           'database/migrations/20260924_004_create_research_run_audit.sql'],
    'INSERT once per run by the orchestrator; never updated or deleted by the application.',
    ARRAY[]::text[], 'VERIFIED', 'NOT_APPLICABLE', NULL, NULL, 'recorded_at',
    'Written when the run finishes; audit metadata, not market data.',
    'NOT_APPLICABLE', NULL
);

INSERT INTO public."Column_Catalog" (
    table_schema, table_name, column_name, ordinal_position, data_type,
    is_nullable, default_expression, is_primary_key, definition,
    source_column_or_expression, unit, null_rule, source_code_paths,
    documentation_status
)
SELECT columns.table_schema, columns.table_name, columns.column_name, columns.ordinal_position,
       columns.data_type, columns.is_nullable = 'YES', columns.column_default, columns.column_name = 'request_id',
       CASE columns.column_name
        WHEN 'request_id' THEN 'The orchestrator request_id of the run (one research run = one market-ai-orc request).'
        WHEN 'recorded_at' THEN 'When the audit row was written.'
        WHEN 'status' THEN 'Run status returned to the caller: COMPLETED, NEEDS_CLARIFICATION, LIMITED or FAILED.'
        WHEN 'response_type' THEN 'ANSWER, CLARIFICATION or LIMITATION; NULL for a failed run.'
        WHEN 'evidence_label' THEN 'The evidence label of the final answer (FACT ... NOT_VALIDATED); NULL without data numbers.'
        WHEN 'validation_gate' THEN 'What the answer gate did: NOT_APPLICABLE, PASSED, ANNOTATED or FORCED_LIMITATION.'
        WHEN 'error_code' THEN 'Error code of a failed run, else NULL.'
        WHEN 'question_sha256' THEN 'SHA-256 of the user''s message.'
        WHEN 'question' THEN 'The user''s message (at most 16000 characters).'
        WHEN 'answer_sha256' THEN 'SHA-256 of the final answer text; NULL for a failed run.'
        WHEN 'answer' THEN 'The final answer text (at most 20000 characters); NULL for a failed run.'
        WHEN 'limitations' THEN 'JSON array of the limitation lines returned with the answer.'
        WHEN 'number_provenance' THEN 'JSON {checked, unsupported} of the answer''s numbers, or NULL.'
        WHEN 'experiments' THEN 'JSON array of the run''s analysis specs: governor decision, validation, evidence decision, whether the answer relies on it (RETAINED/DISCARDED/FOLLOWED_UP/NOT_RUN), code and dataset fingerprints.'
        WHEN 'datasets' THEN 'JSON array of governed datasets used: dataset_id, checksum, row count, source tables, completeness.'
        WHEN 'budget' THEN 'JSON of the run''s budgets as the sandbox counted them (analyses, specs, CPU, research experiments).'
        WHEN 'model' THEN 'The OpenRouter model identifier the run used.'
        WHEN 'tool_call_count' THEN 'Tool calls in the run.'
        WHEN 'total_tokens' THEN 'Provider-reported total tokens of the run.'
        WHEN 'duration_ms' THEN 'Run duration in milliseconds.'
        WHEN 'sandbox_summary_status' THEN 'State of the sandbox run record when copied: REPORTED, AWAITING_REPORT, ACTIVE, UNAVAILABLE or NOT_USED.'
       END,
       'apps/market-ai-orc/app/audit.py', NULL,
       CASE WHEN columns.is_nullable = 'YES' THEN 'NULL when not applicable to the run.'
            ELSE 'NULL is not permitted.' END,
       ARRAY['apps/market-ai-orc/app/audit.py'], 'VERIFIED'
FROM information_schema.columns AS columns
WHERE columns.table_schema = 'public' AND columns.table_name = 'AI_research_run_audit';

UPDATE public."Tool_Catalog"
SET tool_specific_limits = tool_specific_limits || '{"superseded_by": "v2"}'::jsonb, updated_at = CURRENT_TIMESTAMP
WHERE tool_name = 'create_analysis_spec' AND version = 'v1' AND tool_specific_limits->>'runtime_service' = 'market-ai-orc';

UPDATE public."Tool_Catalog"
SET tool_specific_limits = tool_specific_limits || '{"superseded_by": "v3"}'::jsonb, updated_at = CURRENT_TIMESTAMP
WHERE tool_name = 'run_python_analysis' AND version = 'v2' AND tool_specific_limits->>'runtime_service' = 'market-ai-orc';

UPDATE public."Tool_Catalog"
SET tool_specific_limits = tool_specific_limits || '{"superseded_by": "v3"}'::jsonb, updated_at = CURRENT_TIMESTAMP
WHERE tool_name = 'get_analysis_result' AND version = 'v2' AND tool_specific_limits->>'runtime_service' = 'market-ai-orc';

UPDATE public."Tool_Catalog"
SET purpose = 'Return which backend capabilities (catalog discovery, full catalog read, market-data preview, database query, fact lookup, Python analysis, web search, external data) and tools are currently available to this agent.', updated_at = CURRENT_TIMESTAMP
WHERE tool_name = 'get_system_capabilities' AND version = 'v1'
  AND tool_specific_limits->>'runtime_service' = 'market-ai-orc';

INSERT INTO public."Tool_Catalog" (
    tool_name, tool_family, tool_type, purpose, input_schema, output_schema,
    execution_type, handler_name, default_output_rows, max_output_rows,
    max_input_rows, max_tickers, max_date_range_days, max_estimated_rows,
    timeout_seconds, max_output_bytes, max_llm_result_rows,
    max_llm_result_bytes, max_llm_result_tokens,
    requires_analytics_worker, requires_feature_catalog, requires_data_readiness,
    tool_specific_limits, version, is_active
)
VALUES
    ('create_analysis_spec', 'ADVANCED', 'VALIDATION', 'Required before any Python analysis: propose the machine-readable contract of the calculation. The service checks it against the user''s own messages and returns APPROVED (with spec_id), APPROVED_WITH_UNVERIFIED (spec_id plus requirements the user did not state, which must be disclosed), ANALYSIS_SPEC_MISMATCH (fix the spec to match the request; never change the request to fit limits), NEEDS_CLARIFICATION (ask the user), INVALID_SPEC, or for research specs the Research Governor''s REPLAN_REQUIRED (correct the experiment as the governor.reason_code says) or REJECTED (the run''s research budget is used: report what was found). It also returns the resolved analysis period and required_input: the warm-up history and the date range to request with request_data. Sending the same spec again returns the same spec_id. provenance per requirement: USER_EXPLICIT only for what the user stated, USER_CLARIFIED for answers to your clarification question, APPROVED_DEFAULT with default_id for a documented default, AI_INFERRED otherwise. Definitions follow TA-Lib first, then AI_formula_reference, then your own formula (CUSTOM). Defaults: DEFAULT_TRAILING_CALENDAR_WINDOW (''last N months'' = TRAILING), DEFAULT_TRADING_DAYS, DEFAULT_LATEST, DEFAULT_MONTH_WITHOUT_YEAR, DEFAULT_UNIVERSE_ALL_IN_SOURCE (''all stocks''), DEFAULT_FREQUENCY_DAILY, DEFAULT_ROLLING_WINDOW_UNIT, DEFAULT_STD_DDOF (0, TA-Lib STDDEV), DEFAULT_ZSCORE_DDOF (1), DEFAULT_ZSCORE_INCLUDES_CURRENT (true for a price, false for a return series), DEFAULT_RETURN_KIND (SIMPLE), DEFAULT_RETURN_HORIZON (1), DEFAULT_RETURN_AS_PERCENT (false), DEFAULT_RSI_PERIOD (14), DEFAULT_RSI_SMOOTHING (WILDER, TA-Lib), DEFAULT_FORWARD_RETURN_ENTRY (NEXT_OPEN: close[t+h] / open[t+1] - 1; SIGNAL_CLOSE only when the user asks), DEFAULT_CORRELATION_METHOD, DEFAULT_CORRELATION_TRANSFORM (SIMPLE_RETURN), DEFAULT_CORRELATION_MIN_OVERLAP, DEFAULT_EVENT_OVERLAP_POLICY (NON_OVERLAPPING), DEFAULT_EVENT_BASELINE (ALL_ELIGIBLE), DEFAULT_EVENT_MIN_EVENTS (30), DEFAULT_ZERO_DENOMINATOR (NULL). Omitted method parameters get their default. Methods with independent recalculation (params): SMA(window), ROLLING_STD(window, ddof), ROLLING_ZSCORE(window, ddof, include_current), RETURN(horizon, kind SIMPLE|LOG, as_percent), FORWARD_RETURN(horizon, kind, as_percent, entry NEXT_OPEN|SIGNAL_CLOSE; columns [close, open] for NEXT_OPEN, [close] for SIGNAL_CLOSE), RSI(period), ROLLING_CORRELATION(window, method, transform; two columns), CORRELATION(method, transform, min_overlap; ENTITY_PAIR output over a TICKERS universe), EVENT_STUDY(min_events, overlap_policy, baseline; no columns; input_calculation = the FORWARD_RETURN outcome; signal = predicates on earlier trailing calculations; one SUMMARY output with columns segment, event_count, mean, median, hit_rate, baseline_count, baseline_mean, baseline_median, delta_mean, censored_count, overlapping_dropped and rows ALL, plus IN_SAMPLE and OUT_OF_SAMPLE when research.holdout is set). Any other formula is CUSTOM with formula, time_alignment, covers, and ideally an expression, which is recalculated independently: input columns and earlier calculation ids with + - * / **, comparisons, & | ~, abs, log, exp, sqrt, sign, min, max, where(c, a, b), lag(x, k), rolling_sum(x, n), rolling_mean(x, n) (past only). A CUSTOM without an expression is never independently recalculated (optional warmup_observations param). Add formula_refs (CALC_### ids it adapts), meaning, and unit to CUSTOM. Chain a method on another calculation with input_calculation (e.g. ROLLING_STD of a RETURN). outputs: each TABLE the code emits, by name. grain ENTITY_DATE (one row per entity and date in the period), ENTITY (one row per entity at its latest observation in the period), ENTITY_PAIR, SUMMARY (EVENT_STUDY), or UNSPECIFIED (not checkable). coverage FULL (every entity/date in scope) or SELECTION (only rows meeting the selection predicates, e.g. RSI < 30). Only declared outputs with a checkable grain can pass validation. research: null for a calculation, screen, or description the user asked for. For a research question set evidence_standard (HISTORICAL_PATTERN and PREDICTIVE need a hypothesis and an EVENT_STUDY; PREDICTIVE also a holdout; EXPLORATORY for bounded exploration; SCENARIO for hypotheticals), objective, hypothesis {id H1.., statement}, method_ref (AI_research_catalog method_id), candidates (conditions or lags tested), and followup_of (spec_id of a completed experiment on the same hypothesis) for a follow-up.', '{"additionalProperties":false,"properties":{"analysis_period":{"additionalProperties":false,"properties":{"count":{"anyOf":[{"type":"integer"},{"type":"null"}],"description":"Units for TRAILING, dates for TRADING_DAYS, else null."},"default_id":{"anyOf":[{"type":"string"},{"type":"null"}]},"end":{"anyOf":[{"type":"string"},{"type":"null"}],"description":"YYYY-MM-DD for EXPLICIT_DATES, else null."},"mode":{"enum":["EXPLICIT_DATES","TRAILING","TRADING_DAYS","LATEST"],"type":"string"},"provenance":{"enum":["USER_EXPLICIT","USER_CLARIFIED","APPROVED_DEFAULT","AI_INFERRED"],"type":"string"},"start":{"anyOf":[{"type":"string"},{"type":"null"}],"description":"YYYY-MM-DD for EXPLICIT_DATES, else null."},"unit":{"anyOf":[{"enum":["DAY","WEEK","MONTH","YEAR"],"type":"string"},{"type":"null"}],"description":"TRAILING calendar unit, else null."}},"required":["mode","start","end","unit","count","provenance","default_id"],"type":"object"},"calculations":{"items":{"additionalProperties":false,"properties":{"columns":{"description":"Input columns ([] when input_calculation is set).","items":{"type":"string"},"type":"array"},"covers":{"anyOf":[{"items":{"enum":["RSI","SMA","STD","ZSCORE","RETURN","FORWARD_RETURN","CORRELATION","EVENT_STUDY"],"type":"string"},"type":"array"},{"type":"null"}],"description":"CUSTOM only: requested method families it implements."},"data_policies":{"anyOf":[{"additionalProperties":false,"properties":{"missing":{"type":"string"},"zero_denominator":{"enum":["NULL","ZERO"],"type":"string"}},"required":["zero_denominator","missing"],"type":"object"},{"type":"null"}],"description":"CUSTOM only: zero_denominator NULL (default) or ZERO; missing PROPAGATE."},"dataset":{"description":"Logical input name.","type":"string"},"default_id":{"anyOf":[{"type":"string"},{"type":"null"}]},"expression":{"anyOf":[{"type":"string"},{"type":"null"}],"description":"CUSTOM only: recalculable expression over the input columns and earlier calculation ids, e.g. rolling_sum(net_value, 20) / rolling_sum(value, 20); null for free-form code that cannot be recalculated."},"formula":{"anyOf":[{"type":"string"},{"type":"null"}],"description":"Required for CUSTOM; null for other methods."},"formula_refs":{"anyOf":[{"items":{"type":"string"},"type":"array"},{"type":"null"}],"description":"CUSTOM only: AI_formula_reference ids (CALC_###) the formula adapts; null if none."},"id":{"type":"string"},"input_calculation":{"anyOf":[{"type":"string"},{"type":"null"}],"description":"id of an earlier calculation used as input, or null."},"meaning":{"anyOf":[{"type":"string"},{"type":"null"}],"description":"CUSTOM only: what the value means financially."},"method":{"enum":["SMA","ROLLING_STD","ROLLING_ZSCORE","RETURN","FORWARD_RETURN","RSI","ROLLING_CORRELATION","CORRELATION","EVENT_STUDY","CUSTOM"],"type":"string"},"output_column":{"description":"Column holding this value in the outputs.","type":"string"},"params":{"items":{"additionalProperties":false,"properties":{"default_id":{"anyOf":[{"type":"string"},{"type":"null"}]},"name":{"type":"string"},"provenance":{"enum":["USER_EXPLICIT","USER_CLARIFIED","APPROVED_DEFAULT","AI_INFERRED"],"type":"string"},"value":{"anyOf":[{"type":"integer"},{"type":"number"},{"type":"string"},{"type":"boolean"},{"type":"null"}],"description":"The parameter value; null applies the method''s approved default (recorded as APPROVED_DEFAULT)."}},"required":["name","value","provenance","default_id"],"type":"object"},"type":"array"},"provenance":{"enum":["USER_EXPLICIT","USER_CLARIFIED","APPROVED_DEFAULT","AI_INFERRED"],"type":"string"},"signal":{"anyOf":[{"items":{"additionalProperties":false,"properties":{"calculation":{"type":"string"},"default_id":{"anyOf":[{"type":"string"},{"type":"null"}]},"op":{"enum":[">",">=","<","<=","==","!="],"type":"string"},"provenance":{"enum":["USER_EXPLICIT","USER_CLARIFIED","APPROVED_DEFAULT","AI_INFERRED"],"type":"string"},"value":{"type":"number"}},"required":["calculation","op","value","provenance","default_id"],"type":"object"},"type":"array"},{"type":"null"}],"description":"EVENT_STUDY only: predicates on earlier trailing calculations that define an event (all must hold at t); null otherwise."},"time_alignment":{"anyOf":[{"type":"string"},{"type":"null"}],"description":"Required for CUSTOM; null otherwise."},"unit":{"anyOf":[{"type":"string"},{"type":"null"}],"description":"CUSTOM only: unit of the value (ratio, IDR, percent)."}},"required":["id","method","dataset","columns","input_calculation","params","output_column","formula","time_alignment","covers","signal","expression","formula_refs","meaning","unit","data_policies","provenance","default_id"],"type":"object"},"type":"array"},"exclusion_rules":{"items":{"additionalProperties":false,"properties":{"default_id":{"anyOf":[{"type":"string"},{"type":"null"}]},"provenance":{"enum":["USER_EXPLICIT","USER_CLARIFIED","APPROVED_DEFAULT","AI_INFERRED"],"type":"string"},"rule":{"enum":["MIN_OBSERVATIONS_IN_PERIOD","MAX_STALENESS_DAYS","EXCLUDE_TICKERS"],"type":"string"},"value":{"anyOf":[{"type":"integer"},{"items":{"type":"string"},"type":"array"}]}},"required":["rule","value","provenance","default_id"],"type":"object"},"type":"array"},"frequency":{"additionalProperties":false,"properties":{"default_id":{"anyOf":[{"type":"string"},{"type":"null"}]},"provenance":{"enum":["USER_EXPLICIT","USER_CLARIFIED","APPROVED_DEFAULT","AI_INFERRED"],"type":"string"},"value":{"enum":["1D","1W","1M"],"type":"string"}},"required":["value","provenance","default_id"],"type":"object"},"inputs":{"items":{"additionalProperties":false,"properties":{"columns":{"description":"Columns the analysis needs.","items":{"type":"string"},"type":"array"},"date_column":{"anyOf":[{"type":"string"},{"type":"null"}],"description":"Date column; null uses the table''s default."},"entity_column":{"anyOf":[{"type":"string"},{"type":"null"}],"description":"Entity column (e.g. ticker); null uses the table''s default."},"name":{"description":"Logical input name, e.g. prices.","type":"string"},"source_table":{"description":"Catalog table the data comes from.","type":"string"}},"required":["name","source_table","entity_column","date_column","columns"],"type":"object"},"type":"array"},"outputs":{"items":{"additionalProperties":false,"properties":{"calculations":{"items":{"type":"string"},"type":"array"},"coverage":{"enum":["FULL","SELECTION"],"type":"string"},"date_column":{"anyOf":[{"type":"string"},{"type":"null"}]},"entity_column":{"anyOf":[{"type":"string"},{"type":"null"}]},"grain":{"enum":["ENTITY_DATE","ENTITY","ENTITY_PAIR","SUMMARY","UNSPECIFIED"],"type":"string"},"name":{"description":"The name the code passes to emit_table.","type":"string"},"pair_columns":{"anyOf":[{"items":{"type":"string"},"type":"array"},{"type":"null"}],"description":"Two entity columns for ENTITY_PAIR, else null."},"selection":{"anyOf":[{"items":{"additionalProperties":false,"properties":{"calculation":{"type":"string"},"default_id":{"anyOf":[{"type":"string"},{"type":"null"}]},"op":{"enum":[">",">=","<","<=","==","!="],"type":"string"},"provenance":{"enum":["USER_EXPLICIT","USER_CLARIFIED","APPROVED_DEFAULT","AI_INFERRED"],"type":"string"},"value":{"type":"number"}},"required":["calculation","op","value","provenance","default_id"],"type":"object"},"type":"array"},{"type":"null"}],"description":"Predicates for SELECTION, else null."}},"required":["name","grain","coverage","calculations","selection","entity_column","date_column","pair_columns"],"type":"object"},"type":"array"},"question":{"description":"The analytical request, restated.","type":"string"},"research":{"anyOf":[{"additionalProperties":false,"properties":{"candidates":{"anyOf":[{"type":"integer"},{"type":"null"}],"description":"Conditions, lags or combinations this experiment evaluates; null = 1."},"evidence_standard":{"enum":["CALCULATION","SCREEN","DESCRIPTIVE","HISTORICAL_PATTERN","EXPLORATORY","PREDICTIVE","SCENARIO"],"type":"string"},"followup_of":{"anyOf":[{"type":"string"},{"type":"null"}],"description":"spec_id of the completed experiment this follows up, or null."},"holdout":{"anyOf":[{"additionalProperties":false,"properties":{"end":{"anyOf":[{"type":"string"},{"type":"null"}],"description":"Last out-of-sample date, or null."},"start":{"description":"First out-of-sample date (YYYY-MM-DD).","type":"string"}},"required":["start","end"],"type":"object"},{"type":"null"}]},"hypothesis":{"anyOf":[{"additionalProperties":false,"properties":{"id":{"description":"H1, H2, ...","type":"string"},"statement":{"type":"string"}},"required":["id","statement"],"type":"object"},{"type":"null"}]},"method_ref":{"anyOf":[{"type":"string"},{"type":"null"}],"description":"AI_research_catalog method_id used as methodology reference, or null."},"objective":{"type":"string"}},"required":["evidence_standard","objective","hypothesis","method_ref","followup_of","candidates","holdout"],"type":"object"},{"type":"null"}],"description":"null for a plain calculation, screen, or description. For research (a historical pattern, predictive, exploratory, or scenario question) the experiment''s evidence standard, hypothesis, and follow-up link; the Research Governor approves it against the run''s budget."},"universe":{"additionalProperties":false,"properties":{"default_id":{"anyOf":[{"type":"string"},{"type":"null"}]},"provenance":{"enum":["USER_EXPLICIT","USER_CLARIFIED","APPROVED_DEFAULT","AI_INFERRED"],"type":"string"},"tickers":{"anyOf":[{"items":{"type":"string"},"type":"array"},{"type":"null"}],"description":"Upper-case tickers for TICKERS, else null."},"type":{"enum":["ALL_IN_SOURCE","TICKERS"],"type":"string"}},"required":["type","tickers","provenance","default_id"],"type":"object"}},"required":["question","universe","analysis_period","frequency","inputs","calculations","outputs","exclusion_rules","research"],"type":"object"}'::jsonb, '{"description":"The market-python-sandbox spec review with the Research Governor decision (model view).","properties":{"clarification_needed":{},"convention_notes":{},"derived_features":{},"governor":{},"mismatches":{},"next_action":{},"output_contract":{},"problems":{},"reference":{},"replayed":{},"required_input":{},"resolved_period":{},"spec_id":{},"status":{},"unverified_requirements":{}},"type":"object"}'::jsonb,
     'ORCHESTRATOR', NULL, NULL, NULL, NULL, NULL, NULL, NULL, 50, 20000, NULL, 20000, NULL,
     false, false, false, '{"convention_precedence":["TA-Lib","AI_formula_reference","AI-generated CUSTOM formula"],"evidence_standards":["CALCULATION","SCREEN","DESCRIPTIVE","HISTORICAL_PATTERN","EXPLORATORY","PREDICTIVE","SCENARIO"],"executor_service":"market-python-sandbox","handler":"app/tools/analysis.py","idempotent":"same request, spec and user messages -> same spec_id","max_calculations":12,"max_exclusion_rules":8,"max_inputs":4,"max_outputs":8,"methods":["SMA","ROLLING_STD","ROLLING_ZSCORE","RETURN","FORWARD_RETURN","RSI","ROLLING_CORRELATION","CORRELATION","EVENT_STUDY","CUSTOM"],"provenance_values":["USER_EXPLICIT","USER_CLARIFIED","APPROVED_DEFAULT","AI_INFERRED"],"registry_state":"Registered in market-ai-orc; is_active=false keeps it out of market-ai-backend tool lists.","request_budget_source":"market-python-sandbox PY_SANDBOX_* configuration (not model-controlled)","research_governor":"deterministic; market-python-sandbox app/research_policy.py","research_policy_source":"market-python-sandbox PY_SANDBOX_RESEARCH_* configuration (not model-controlled)","runtime_commit":"0e0234c","runtime_service":"market-ai-orc","server_supplied_fields":["request_id","reference_time","timezone","user_messages"],"spec_storage":"immutable in the sandbox record store (spec_id, sha256); run audit summary in AI_research_run_audit","statuses":["APPROVED","APPROVED_WITH_UNVERIFIED","ANALYSIS_SPEC_MISMATCH","NEEDS_CLARIFICATION","INVALID_SPEC","REQUEST_BUDGET_EXCEEDED","REPLAN_REQUIRED","REJECTED"]}'::jsonb, 'v2', false),
    ('run_python_analysis', 'ADVANCED', 'COMPUTATION', 'Run Python analysis in an isolated sandbox against an approved spec_id. Bind every logical input of the spec to the DATASET_READY dataset_ids that hold it (several dataset_ids may form one input only if they come from the same table with identical columns). The code runs without network, subprocess, or file access outside its workspace. The helper module saniti and its functions, pandas as pd and numpy as np are already imported. Inputs are DuckDB views named after the logical inputs. load(name, columns=[...]) returns the whole input as a pandas DataFrame sorted by entity and date (date columns hold datetime.date objects; use pd.to_datetime for Timestamps), including the warm-up history before the analysis period; sql(''SELECT ... FROM prices WHERE ...'', [params]) runs DuckDB SQL (filter and aggregate in SQL; large results are refused). Compute every indicator per entity on that full date-sorted history, then keep the period rows with out = df[in_period(df)], which applies the approved period (including LATEST and trading-day periods) the same way the validator does; never cut the input to the period before computing. INPUTS lists each input''s columns; SPEC is the approved spec; ANALYSIS_START, ANALYSIS_END and REFERENCE_DATE are the resolved period. Write intermediate Parquet only to intermediate_path(name). Libraries: numpy 2, pandas 3 (groupby().apply drops the grouping columns; prefer groupby()[col].transform), polars, pyarrow, duckdb, scipy, statsmodels, matplotlib, TA-Lib (import talib). Helpers: iter_series, prepare_panel, panel_check, add_warning. Emit every spec output with emit_table(output_name, dataframe, description='''') (no other arguments); the dataframe''s columns must include the output''s entity_column, date_column or pair_columns, and the output_column of each calculation it lists. Also emit_metrics(dict), emit_chart(figure, name, title, description), emit_artifact(name, data, format). print() is not a result, and nothing the code reports about itself counts as evidence. The result has execution_status and validation_status (PASS, INCOMPLETE, FAILED, UNVERIFIED) with validation_level, reason_codes, expected_scope, actual_scope and validation_evidence; a CALCULATION_MISMATCH can carry a diagnosis naming the parameter or procedure the values match. evidence_assessment says what the validated evidence supports for the spec''s evidence standard (decision SUPPORTED, PARTIALLY_SUPPORTED, INSUFFICIENT_EVIDENCE or INVALID, evidence_level, checks, the validator''s own statistics) and the reporting_constraints your answer must follow. CUSTOM code without an expression is re-run on data truncated at a cutoff date: values that change reveal look-ahead (TEMPORAL_LEAKAGE_DETECTED).', '{"additionalProperties":false,"properties":{"expected_outputs":{"description":"Output types the code will emit (unique).","items":{"enum":["TABLE","METRICS","CHART","ARTIFACT"],"type":"string"},"type":"array"},"inputs":{"items":{"additionalProperties":false,"properties":{"dataset_ids":{"description":"DATASET_READY dataset_ids holding this input (same table and columns).","items":{"type":"string"},"type":"array"},"duplicate_policy":{"enum":["ERROR_ON_CONFLICT","PREFER_LATEST_SNAPSHOT"],"type":"string"},"name":{"description":"A logical input name from the approved spec.","type":"string"}},"required":["name","dataset_ids","duplicate_policy"],"type":"object"},"type":"array"},"python_code":{"description":"Python source to run in the sandbox.","type":"string"},"spec_id":{"description":"spec_id of an approved analysis spec.","type":"string"}},"required":["spec_id","inputs","python_code","expected_outputs"],"type":"object"}'::jsonb, '{"description":"The market-python-sandbox analysis record (model view): execution, validation, and the post-run evidence assessment are separate.","properties":{"actual_scope":{},"analysis_id":{},"database_features":{},"derived_features":{},"diagnostics":{},"error":{},"evidence_assessment":{},"execution_status":{},"expected_outputs":{},"expected_scope":{},"inputs":{},"leakage_check":{},"lineage":{},"next_action":{},"outputs":{},"outputs_expire_at":{},"question":{},"reason_codes":{},"retry_after_seconds":{},"runtime_ms":{},"spec_id":{},"validation_evidence":{},"validation_level":{},"validation_status":{},"warnings":{}},"type":"object"}'::jsonb,
     'ORCHESTRATOR', NULL, NULL, NULL, NULL, NULL, NULL, NULL, 50, 40000, 50, 40000, NULL,
     false, false, false, '{"derived_features":"exploratory artifacts only (EXPLORATORY_UNVALIDATED); never written to PostgreSQL","evidence_decisions":["SUPPORTED","PARTIALLY_SUPPORTED","INSUFFICIENT_EVIDENCE","INVALID"],"execution_statuses":["QUEUED","RUNNING","COMPLETED","FAILED","CANCELLED","EXPIRED"],"executor_service":"market-python-sandbox","handler":"app/tools/analysis.py","isolation":"fresh process, non-root slot user, rlimits, seccomp (no sockets/exec/fork), locked DuckDB; not a network namespace","max_code_chars":20000,"max_dataset_ids_per_input":8,"max_logical_inputs":4,"output_types":["TABLE","METRICS","CHART","ARTIFACT"],"registry_state":"Registered in market-ai-orc; is_active=false keeps it out of market-ai-backend tool lists.","runtime_commit":"0e0234c","runtime_service":"market-ai-orc","sandbox_limits_source":"market-python-sandbox PY_SANDBOX_* configuration (not model-controlled)","table_preview_rows":50,"validation":"preflight (inputs, period, universe, warm-up, units) and postflight in a separate confined validator process; independent recalculation of registered methods, EVENT_STUDY summaries and CUSTOM expressions; prefix re-run leakage check for other CUSTOM code","validation_levels":["EXECUTION_ONLY","SCOPE_VERIFIED","CALCULATION_VERIFIED"],"validation_statuses":["PENDING","PASS","INCOMPLETE","FAILED","UNVERIFIED"]}'::jsonb, 'v3', false),
    ('get_analysis_result', 'ADVANCED', 'RETRIEVAL', 'Get the execution_status, validation_status, validation_level, and structured outputs of a run_python_analysis job. Waits briefly while it runs.', '{"additionalProperties":false,"properties":{"analysis_id":{"description":"analysis_id from run_python_analysis.","type":"string"}},"required":["analysis_id"],"type":"object"}'::jsonb, '{"description":"The market-python-sandbox analysis record (model view): execution, validation, and the post-run evidence assessment are separate.","properties":{"actual_scope":{},"analysis_id":{},"database_features":{},"derived_features":{},"diagnostics":{},"error":{},"evidence_assessment":{},"execution_status":{},"expected_outputs":{},"expected_scope":{},"inputs":{},"leakage_check":{},"lineage":{},"next_action":{},"outputs":{},"outputs_expire_at":{},"question":{},"reason_codes":{},"retry_after_seconds":{},"runtime_ms":{},"spec_id":{},"validation_evidence":{},"validation_level":{},"validation_status":{},"warnings":{}},"type":"object"}'::jsonb,
     'ORCHESTRATOR', NULL, NULL, NULL, NULL, NULL, NULL, NULL, 50, 40000, 50, 40000, NULL,
     false, false, false, '{"evidence_decisions":["SUPPORTED","PARTIALLY_SUPPORTED","INSUFFICIENT_EVIDENCE","INVALID"],"execution_statuses":["QUEUED","RUNNING","COMPLETED","FAILED","CANCELLED","EXPIRED"],"executor_service":"market-python-sandbox","handler":"app/tools/analysis.py","poll_wait_seconds":20,"registry_state":"Registered in market-ai-orc; is_active=false keeps it out of market-ai-backend tool lists.","runtime_commit":"0e0234c","runtime_service":"market-ai-orc","validation_levels":["EXECUTION_ONLY","SCOPE_VERIFIED","CALCULATION_VERIFIED"],"validation_statuses":["PENDING","PASS","INCOMPLETE","FAILED","UNVERIFIED"]}'::jsonb, 'v3', false);

DO $verify$
BEGIN
    IF (SELECT count(*) FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'AI_research_run_audit') <> 21 THEN
        RAISE EXCEPTION 'AI_research_run_audit column count does not match';
    END IF;
    IF (SELECT count(*) FROM public."Column_Catalog" WHERE table_name = 'AI_research_run_audit'
          AND definition IS NOT NULL) <> 21 THEN
        RAISE EXCEPTION 'Every AI_research_run_audit column needs a Column_Catalog definition';
    END IF;
    IF NOT has_table_privilege('market_ai_research_audit_writer', 'public."AI_research_run_audit"', 'INSERT')
       OR has_table_privilege('market_ai_research_audit_writer', 'public."AI_research_run_audit"',
                              'SELECT,UPDATE,DELETE,TRUNCATE') THEN
        RAISE EXCEPTION 'The audit writer must have INSERT only';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname IN ('market_ai_sql_reader', 'market_ai_catalog_reader')
               AND has_table_privilege(oid, 'public."AI_research_run_audit"', 'SELECT,INSERT,UPDATE,DELETE')) THEN
        RAISE EXCEPTION 'The SQL Governor and catalog reader roles must have no access to the audit table';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'market_ai_orc')
       AND NOT pg_has_role('market_ai_orc', 'market_ai_research_audit_writer', 'MEMBER') THEN
        RAISE EXCEPTION 'market_ai_orc must be a member of market_ai_research_audit_writer';
    END IF;
    IF (SELECT count(*) FROM public."Tool_Catalog"
        WHERE tool_specific_limits->>'runtime_service' = 'market-ai-orc' AND NOT is_active
          AND tool_specific_limits->>'runtime_commit' = '0e0234c') <> 3 THEN
        RAISE EXCEPTION 'Expected three inactive Research AI tool rows at runtime_commit 0e0234c';
    END IF;
    IF (SELECT count(*) FROM public."Tool_Catalog"
        WHERE tool_specific_limits->>'superseded_by' IS NOT NULL
          AND ((tool_name = 'create_analysis_spec' AND version = 'v1')
               OR (tool_name IN ('run_python_analysis', 'get_analysis_result') AND version = 'v2'))) <> 3 THEN
        RAISE EXCEPTION 'Expected the three previous versions to be marked superseded';
    END IF;
    IF EXISTS (SELECT 1 FROM public."Tool_Catalog"
               WHERE is_active AND tool_specific_limits->>'runtime_service' = 'market-ai-orc'
                 AND tool_name NOT IN ('discover_catalog', 'get_catalog_details', 'read_catalog_rows')) THEN
        RAISE EXCEPTION 'Only the three catalog tools may be active market-ai-orc rows';
    END IF;
END
$verify$;

COMMIT;
