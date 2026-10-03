-- Evidence per claim for market-ai-orc (round 2026-10-03 D6, HIGH_ALERT_PLAN.md Prioritas 2;
-- ROUND_PLAN_2026-10-03_FASE_D.md).
--
-- Every claim the model checks with get_evidence is recomputed on a path separate from its own code: tier 1 by the SQL
-- Governor's summary over the governed tables (WAREHOUSE), tier 2 by the sandbox from the base table the analysis
-- released (BASE_TABLE). "AI_conversation_evidence" keeps each check with the conversation (deleted with it): the
-- claim, the number as written, the recipe, the backend's value, the status (TERCEK, TIDAK_COCOK, TIDAK_BISA_DICEK,
-- TIDAK_DICEK_BATAS), at most 200 rows of evidence a user can read, and where they came from. The API returns them as
-- evidence[]; export_result can turn one into a file.
-- market_ai_conversation_store may SELECT, INSERT, UPDATE and DELETE the six conversation tables only. PUBLIC is
-- revoked. Forward-only. No existing table, row or grant is changed.
BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';

DO $preflight$
BEGIN
    IF to_regclass('public."AI_conversation"') IS NULL THEN
        RAISE EXCEPTION 'AI_conversation does not exist (migration 20260927_002)';
    END IF;
    IF to_regclass('public."AI_conversation_evidence"') IS NOT NULL THEN
        RAISE EXCEPTION 'AI_conversation_evidence already exists: inspect before applying';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'market_ai_conversation_store') THEN
        RAISE EXCEPTION 'The role market_ai_conversation_store does not exist (migration 20260927_002)';
    END IF;
    IF EXISTS (SELECT 1 FROM public."Table_Catalog" WHERE table_schema = 'public'
               AND table_name = 'AI_conversation_evidence') THEN
        RAISE EXCEPTION 'Table_Catalog already documents AI_conversation_evidence';
    END IF;
END
$preflight$;

CREATE TABLE public."AI_conversation_evidence" (
    evidence_id text PRIMARY KEY,
    conversation_id text NOT NULL REFERENCES public."AI_conversation" (conversation_id) ON DELETE CASCADE,
    request_id text NOT NULL,
    claim text NOT NULL,
    value_text text NOT NULL,
    kind text NOT NULL,
    recipe jsonb NOT NULL,
    status text NOT NULL,
    backend_value double precision,
    difference double precision,
    source jsonb NOT NULL DEFAULT '{}'::jsonb,
    rows jsonb NOT NULL DEFAULT '[]'::jsonb,
    rows_matched bigint,
    created_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ai_conversation_evidence_id_check CHECK (evidence_id ~ '^evd_[0-9a-f]{24}$'),
    CONSTRAINT ai_conversation_evidence_request_check CHECK (request_id ~ '^[A-Za-z0-9._:-]{1,200}$'),
    CONSTRAINT ai_conversation_evidence_claim_check CHECK (length(claim) BETWEEN 1 AND 300
                                                           AND length(value_text) BETWEEN 1 AND 40),
    CONSTRAINT ai_conversation_evidence_kind_check CHECK (kind IN ('WAREHOUSE', 'BASE_TABLE')),
    CONSTRAINT ai_conversation_evidence_status_check
        CHECK (status IN ('TERCEK', 'TIDAK_COCOK', 'TIDAK_BISA_DICEK', 'TIDAK_DICEK_BATAS')),
    CONSTRAINT ai_conversation_evidence_json_check CHECK (
        jsonb_typeof(recipe) = 'object' AND jsonb_typeof(source) = 'object' AND jsonb_typeof(rows) = 'array'
        AND jsonb_array_length(rows) <= 200)
);
CREATE INDEX ai_conversation_evidence_conversation_idx
    ON public."AI_conversation_evidence" (conversation_id, created_at);
COMMENT ON TABLE public."AI_conversation_evidence" IS
    'A claim of a market-ai-orc answer recomputed by the backend (Governor summary or base table), with its status and '
    'at most 200 rows of evidence, kept for the life of the conversation (round 2026-10-03 D6).';

REVOKE ALL ON public."AI_conversation_evidence" FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE, DELETE ON public."AI_conversation_evidence" TO market_ai_conversation_store;

INSERT INTO public."Table_Catalog" (
    table_schema, table_name, category, definition, grain,
    primary_key_columns, source_system, source_tables, source_code_paths,
    update_rule, related_functions, documentation_status,
    readiness_mode, readiness_date_column, observation_date_column,
    data_available_at_column, availability_rule, point_in_time_status,
    historical_metadata_method
) VALUES (
    'public', 'AI_conversation_evidence', 'System',
    'Claims of market-ai-orc answers recomputed by the backend on a path separate from the model''s code (SQL Governor summary or the released base table), with the status, the backend value and at most 200 rows of evidence.',
    'One row per checked claim (evidence_id)', ARRAY['evidence_id'],
    'market-ai-orc get_evidence (app/tools/evidence.py)',
    ARRAY['AI_conversation', 'AI_conversation_output']::text[],
    ARRAY['apps/market-ai-orc/app/tools/evidence.py',
          'database/migrations/20261003_009_conversation_evidence.sql'],
    'Inserted once per checked claim; deleted with its conversation.',
    ARRAY[]::text[], 'VERIFIED', 'NOT_APPLICABLE', NULL, NULL, 'created_at',
    'Operational conversation state derived from market data, not market data itself.', 'NOT_APPLICABLE', NULL
);

INSERT INTO public."Column_Catalog" (
    table_schema, table_name, column_name, ordinal_position, data_type,
    is_nullable, default_expression, is_primary_key, definition,
    source_column_or_expression, unit, null_rule, source_code_paths,
    documentation_status
)
SELECT columns.table_schema, columns.table_name, columns.column_name, columns.ordinal_position,
       columns.data_type, columns.is_nullable = 'YES', columns.column_default,
       columns.column_name = 'evidence_id',
       CASE columns.column_name
        WHEN 'evidence_id' THEN 'Id of the check (evd_ + 24 hex); export_result takes it as a source.'
        WHEN 'conversation_id' THEN 'The conversation the claim belongs to.'
        WHEN 'request_id' THEN 'The market-ai-orc request that checked the claim.'
        WHEN 'claim' THEN 'The claim in words, as the model stated it (at most 300 characters).'
        WHEN 'value_text' THEN 'The number as written in the answer (for example 1,25 miliar or 116); compared with the rounding it shows.'
        WHEN 'kind' THEN 'WAREHOUSE (recomputed by a SQL Governor summary) or BASE_TABLE (recomputed from a released base table).'
        WHEN 'recipe' THEN 'How the backend recomputed the claim: table, filters, measure and period, or the base table, conditions and measure.'
        WHEN 'status' THEN 'TERCEK (matches within the rounding shown), TIDAK_COCOK, TIDAK_BISA_DICEK (the recipe was refused) or TIDAK_DICEK_BATAS (over the per-answer limit).'
        WHEN 'backend_value' THEN 'The value the backend computed; NULL when it could not.'
        WHEN 'difference' THEN 'backend_value minus the claimed value; NULL when not compared.'
        WHEN 'source' THEN 'Where the evidence came from: output id and reference, or source table, Governor query id and period.'
        WHEN 'rows' THEN 'At most 200 rows of evidence a user can read (the matching base rows or the summary rows).'
        WHEN 'rows_matched' THEN 'Rows that matched the recipe before the 200-row limit.'
        WHEN 'created_at' THEN 'When the claim was checked.'
       END,
       columns.column_name, NULL, NULL, ARRAY['database/migrations/20261003_009_conversation_evidence.sql'],
       'VERIFIED'
FROM information_schema.columns
WHERE columns.table_schema = 'public' AND columns.table_name = 'AI_conversation_evidence';

DO $verify$
BEGIN
    IF (SELECT count(*) FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'AI_conversation_evidence') <> 14 THEN
        RAISE EXCEPTION 'AI_conversation_evidence does not have the expected columns';
    END IF;
    IF (SELECT count(*) FROM public."Column_Catalog"
        WHERE table_name = 'AI_conversation_evidence' AND definition IS NOT NULL) <> 14 THEN
        RAISE EXCEPTION 'Every AI_conversation_evidence column needs a Column_Catalog definition';
    END IF;
    IF (SELECT count(*) FROM (VALUES ('SELECT'), ('INSERT'), ('UPDATE'), ('DELETE')) AS p(privilege)
        WHERE has_table_privilege('market_ai_conversation_store', 'public."AI_conversation_evidence"',
                                  p.privilege)) <> 4
       OR EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                  WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
                    AND c.relname NOT IN ('AI_conversation', 'AI_conversation_turn', 'AI_conversation_output',
                                          'AI_conversation_execution', 'AI_conversation_export',
                                          'AI_conversation_evidence')
                    AND has_table_privilege('market_ai_conversation_store', c.oid, 'SELECT,INSERT,UPDATE,DELETE')) THEN
        RAISE EXCEPTION 'market_ai_conversation_store must reach the six conversation tables only';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles
               WHERE rolname IN ('market_ai_sql_reader', 'market_ai_catalog_reader', 'market_ai_orc')
                 AND has_table_privilege(oid, 'public."AI_conversation_evidence"', 'SELECT,INSERT,UPDATE,DELETE')) THEN
        RAISE EXCEPTION 'The Governor, catalog reader and market_ai_orc logins must have no access to evidence';
    END IF;
END
$verify$;

COMMIT;
