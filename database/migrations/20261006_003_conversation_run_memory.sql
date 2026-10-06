-- Run memory for market-ai-orc conversations (EXEC.md EXEC-C; user decisions 2026-10-06: "Seharusnya AI membawa
-- semuanya tanpa terkecuali", Q1 "pakai MEMO", Q2 "BACKEND + AI").
--
-- Every run of a server-side conversation (a turn, or a step of a mode 4 turn) leaves one row, written when the run
-- ends whatever its outcome, and deleted with its conversation (30 days after the last activity):
--   memo       the run's block for the prompt of later runs, written by the backend from what the run recorded (tools,
--              released results, design values with their origin, every refusal of a gate or a tool, web facts, code,
--              catalog read) plus the model's own note; rendered once, never changed, read oldest first (append-only);
--   content    the full texts the memo names (message, answer with assumptions, limitations and methodology, plan,
--              each refusal message with the draft it refused, design values, web entries, catalog details);
--   sources    what the run made citable (fact, metric, reference, web, a JSON output's content), registered again
--              under the same address by later runs;
--   note       the note the model wrote for later runs in its final response (memo_note);
--   reasoning  the run's full reasoning text, read only with read_conversation_memory (never sent to the model again,
--              never sent to the audit store).
-- market_ai_conversation_store may SELECT, INSERT, UPDATE and DELETE the seven conversation tables only. PUBLIC is
-- revoked. Forward-only. No existing table, row or grant is changed.
BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';

DO $preflight$
BEGIN
    IF to_regclass('public."AI_conversation"') IS NULL THEN
        RAISE EXCEPTION 'AI_conversation does not exist (migration 20260927_002)';
    END IF;
    IF to_regclass('public."AI_conversation_run_memory"') IS NOT NULL THEN
        RAISE EXCEPTION 'AI_conversation_run_memory already exists: inspect before applying';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'market_ai_conversation_store') THEN
        RAISE EXCEPTION 'The role market_ai_conversation_store does not exist (migration 20260927_002)';
    END IF;
    IF EXISTS (SELECT 1 FROM public."Table_Catalog" WHERE table_schema = 'public'
               AND table_name = 'AI_conversation_run_memory') THEN
        RAISE EXCEPTION 'Table_Catalog already documents AI_conversation_run_memory';
    END IF;
END
$preflight$;

CREATE TABLE public."AI_conversation_run_memory" (
    run_id text PRIMARY KEY,
    conversation_id text NOT NULL REFERENCES public."AI_conversation" (conversation_id) ON DELETE CASCADE,
    turn_request_id text NOT NULL,
    seq bigint GENERATED ALWAYS AS IDENTITY,
    status text NOT NULL,
    response_type text,
    error_code text,
    memo text NOT NULL,
    content jsonb NOT NULL,
    sources jsonb NOT NULL DEFAULT '{}'::jsonb,
    note text,
    reasoning text,
    created_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ai_conversation_run_memory_run_check CHECK (run_id ~ '^[A-Za-z0-9._:-]{1,200}$'),
    CONSTRAINT ai_conversation_run_memory_turn_check CHECK (turn_request_id ~ '^[A-Za-z0-9._:-]{1,200}$'),
    CONSTRAINT ai_conversation_run_memory_status_check
        CHECK (status IN ('COMPLETED', 'NEEDS_CLARIFICATION', 'AWAITING_CONFIRMATION', 'LIMITED', 'FAILED')),
    CONSTRAINT ai_conversation_run_memory_size_check
        CHECK (length(memo) BETWEEN 1 AND 200000 AND (note IS NULL OR length(note) <= 20000)
               AND (reasoning IS NULL OR length(reasoning) <= 800000)),
    CONSTRAINT ai_conversation_run_memory_json_check
        CHECK (jsonb_typeof(content) = 'object' AND jsonb_typeof(sources) = 'object')
);
CREATE UNIQUE INDEX ai_conversation_run_memory_conversation_idx
    ON public."AI_conversation_run_memory" (conversation_id, seq);
COMMENT ON TABLE public."AI_conversation_run_memory" IS
    'What each run of a market-ai-orc conversation leaves for the runs after it (EXEC-C): memo, full texts, citable '
    'sources, the model''s note and its reasoning; deleted with the conversation.';

REVOKE ALL ON public."AI_conversation_run_memory" FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE, DELETE ON public."AI_conversation_run_memory" TO market_ai_conversation_store;

INSERT INTO public."Table_Catalog" (
    table_schema, table_name, category, definition, grain,
    primary_key_columns, source_system, source_tables, source_code_paths,
    update_rule, related_functions, documentation_status,
    readiness_mode, readiness_date_column, observation_date_column,
    data_available_at_column, availability_rule, point_in_time_status,
    historical_metadata_method
) VALUES (
    'public', 'AI_conversation_run_memory', 'System',
    'What each run of a market-ai-orc conversation (a turn or a step of a mode 4 turn) leaves for the runs after it: the memo later runs read in their prompt, the full texts it names (message, answer, plan, refusals with the refused drafts, design values with their origin, web facts, catalog details), the values it made citable, the model''s own note and its reasoning.',
    'One row per run (run_id = the run''s request id)', ARRAY['run_id'],
    'market-ai-orc (app/run_memory.py) when a run of a server-side conversation ends (AI_ENABLE_RUN_MEMORY)',
    ARRAY['AI_conversation']::text[],
    ARRAY['apps/market-ai-orc/app/run_memory.py', 'apps/market-ai-orc/app/tools/memory.py',
          'database/migrations/20261006_003_conversation_run_memory.sql'],
    'Inserted once per run (a retried run id is left as it is); deleted with its conversation.',
    ARRAY[]::text[], 'VERIFIED', 'NOT_APPLICABLE', NULL, NULL, 'created_at',
    'Operational conversation state derived from market data and model output, not market data itself.',
    'NOT_APPLICABLE', NULL
);

INSERT INTO public."Column_Catalog" (
    table_schema, table_name, column_name, ordinal_position, data_type,
    is_nullable, default_expression, is_primary_key, definition,
    source_column_or_expression, unit, null_rule, source_code_paths,
    documentation_status
)
SELECT columns.table_schema, columns.table_name, columns.column_name, columns.ordinal_position,
       columns.data_type, columns.is_nullable = 'YES', columns.column_default,
       columns.column_name = 'run_id',
       CASE columns.column_name
        WHEN 'run_id' THEN 'The run''s request id: a turn''s request_id, or <request_id>-m4a ... for a step of a mode 4 turn.'
        WHEN 'conversation_id' THEN 'The conversation the run belongs to.'
        WHEN 'turn_request_id' THEN 'The request id of the turn the run belongs to (the run''s own id for a turn that is one run).'
        WHEN 'seq' THEN 'The order runs ended in; later runs read the memos in this order (oldest first).'
        WHEN 'status' THEN 'The run''s status: COMPLETED, NEEDS_CLARIFICATION, AWAITING_CONFIRMATION, LIMITED or FAILED.'
        WHEN 'response_type' THEN 'ANSWER, CLARIFICATION, RESEARCH_PLAN_CONFIRMATION or LIMITATION; NULL when the run failed without a response.'
        WHEN 'error_code' THEN 'The run''s error code (for example ANALYSIS_TIMEOUT); NULL without one.'
        WHEN 'memo' THEN 'The run''s memo as later runs of the conversation read it in their prompt (written by the backend from the run''s events plus the model''s note); never changed.'
        WHEN 'content' THEN 'The full texts the memo names: message, answer (with assumptions, limitations and methodology), plan, refusals with the drafts they refused, design values with their origin, web entries, catalog details, code executions, error.'
        WHEN 'sources' THEN 'The values the run made citable (fact, metric, reference, web, the content of a JSON output) with their evidence label, units and origin; later runs register them again under the same address.'
        WHEN 'note' THEN 'The note the model wrote for later runs in its final response (memo_note); NULL when it wrote none.'
        WHEN 'reasoning' THEN 'The run''s reasoning text (each model call in order), read only with read_conversation_memory; NULL when the provider returned none.'
        WHEN 'created_at' THEN 'When the run ended and its memory was stored.'
       END,
       'apps/market-ai-orc/app/run_memory.py', NULL,
       CASE WHEN columns.is_nullable = 'YES' THEN 'NULL when not applicable, as the definition states.'
            ELSE 'NULL is not permitted.' END,
       ARRAY['apps/market-ai-orc/app/run_memory.py'], 'VERIFIED'
FROM information_schema.columns AS columns
WHERE columns.table_schema = 'public' AND columns.table_name = 'AI_conversation_run_memory';

DO $verify$
BEGIN
    IF (SELECT count(*) FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'AI_conversation_run_memory') <> 13 THEN
        RAISE EXCEPTION 'AI_conversation_run_memory does not have the expected columns';
    END IF;
    IF (SELECT count(*) FROM public."Column_Catalog"
        WHERE table_name = 'AI_conversation_run_memory' AND definition IS NOT NULL) <> 13 THEN
        RAISE EXCEPTION 'Every AI_conversation_run_memory column needs a Column_Catalog definition';
    END IF;
    IF (SELECT count(*) FROM (VALUES ('SELECT'), ('INSERT'), ('UPDATE'), ('DELETE')) AS p(privilege)
        WHERE has_table_privilege('market_ai_conversation_store', 'public."AI_conversation_run_memory"',
                                  p.privilege)) <> 4
       OR EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                  WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
                    AND c.relname NOT IN ('AI_conversation', 'AI_conversation_turn', 'AI_conversation_output',
                                          'AI_conversation_execution', 'AI_conversation_export',
                                          'AI_conversation_evidence', 'AI_conversation_run_memory')
                    AND has_table_privilege('market_ai_conversation_store', c.oid, 'SELECT,INSERT,UPDATE,DELETE')) THEN
        RAISE EXCEPTION 'market_ai_conversation_store must reach the seven conversation tables only';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles
               WHERE rolname IN ('market_ai_sql_reader', 'market_ai_catalog_reader', 'market_ai_orc')
                 AND has_table_privilege(oid, 'public."AI_conversation_run_memory"', 'SELECT,INSERT,UPDATE,DELETE')) THEN
        RAISE EXCEPTION 'The Governor, catalog reader and market_ai_orc logins must have no access to the run memory';
    END IF;
END
$verify$;

COMMIT;
