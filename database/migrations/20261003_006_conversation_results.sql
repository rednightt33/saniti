-- Conversation results for market-ai-orc (round 2026-10-03 phase C2, R-STORE; ROUND_PLAN_2026-10-03_FASE_C.md).
--
-- The python sandbox keeps a released result table for 24 hours and its executions' code only as a hash, so a
-- conversation that came back later lost its tables and could not reproduce them. These tables keep them for the life
-- of the conversation (they are deleted with it):
--   "AI_conversation_output"    a released output (table, JSON, text or chart) with its definition, units, lineage and
--                               the last date of the data it was computed from (data_as_of); the content up to 20 MB
--                               is stored here, a larger one in the bucket market-ai-conversation-outputs (object_key).
--   "AI_conversation_execution" the code of each run_python / run_research_code call (up to 65,536 characters; the
--                               hash is always of the whole code).
--   "AI_conversation_export"    a file the user asked to export (user decision 2026-10-03: a separate Postgres table,
--                               at most 20 MB); written by phase D.
-- market_ai_conversation_store (NOLOGIN; its only member is the login market_ai_conversation) may SELECT, INSERT,
-- UPDATE and DELETE the five conversation tables only. PUBLIC is revoked.
-- Forward-only. No existing table, row or grant is changed.
BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';

DO $preflight$
BEGIN
    IF to_regclass('public."AI_conversation"') IS NULL THEN
        RAISE EXCEPTION 'AI_conversation does not exist (migration 20260927_002)';
    END IF;
    IF to_regclass('public."AI_conversation_output"') IS NOT NULL
       OR to_regclass('public."AI_conversation_execution"') IS NOT NULL
       OR to_regclass('public."AI_conversation_export"') IS NOT NULL THEN
        RAISE EXCEPTION 'A conversation result table already exists: inspect before applying';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'market_ai_conversation_store') THEN
        RAISE EXCEPTION 'The role market_ai_conversation_store does not exist (migration 20260927_002)';
    END IF;
    IF EXISTS (SELECT 1 FROM public."Table_Catalog" WHERE table_schema = 'public'
               AND table_name IN ('AI_conversation_output', 'AI_conversation_execution', 'AI_conversation_export')) THEN
        RAISE EXCEPTION 'Table_Catalog already documents a conversation result table';
    END IF;
END
$preflight$;

CREATE TABLE public."AI_conversation_output" (
    output_id text PRIMARY KEY,
    conversation_id text NOT NULL REFERENCES public."AI_conversation" (conversation_id) ON DELETE CASCADE,
    request_id text NOT NULL,
    session_id text,
    execution_id text,
    name text NOT NULL,
    output_type text NOT NULL,
    format text NOT NULL,
    label text,
    definition jsonb,
    units jsonb,
    lineage jsonb,
    data_as_of date,
    row_count bigint,
    columns jsonb,
    byte_count bigint NOT NULL,
    checksum_sha256 text NOT NULL,
    storage text NOT NULL,
    content bytea,
    object_key text,
    created_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ai_conversation_output_id_check CHECK (output_id ~ '^out_[0-9a-f]{24}$'),
    CONSTRAINT ai_conversation_output_request_check CHECK (request_id ~ '^[A-Za-z0-9._:-]{1,200}$'),
    CONSTRAINT ai_conversation_output_session_check CHECK (session_id IS NULL OR session_id ~ '^sess_[0-9a-f]{24}$'),
    CONSTRAINT ai_conversation_output_execution_check
        CHECK (execution_id IS NULL OR execution_id ~ '^exe_[0-9a-f]{24}$'),
    CONSTRAINT ai_conversation_output_name_check CHECK (length(name) BETWEEN 1 AND 80),
    CONSTRAINT ai_conversation_output_format_check CHECK (format IN ('PARQUET', 'CSV', 'PNG', 'JSON', 'TEXT', 'BIN')),
    CONSTRAINT ai_conversation_output_size_check CHECK (byte_count >= 0 AND (row_count IS NULL OR row_count >= 0)),
    CONSTRAINT ai_conversation_output_checksum_check CHECK (checksum_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ai_conversation_output_storage_check CHECK (
        (storage = 'POSTGRES' AND content IS NOT NULL AND object_key IS NULL
         AND octet_length(content) = byte_count AND byte_count <= 20971520)
        OR (storage = 'BUCKET' AND content IS NULL AND object_key IS NOT NULL
            AND object_key ~ '^outputs/conv_[0-9a-f]{32}/out_[0-9a-f]{24}\.[a-z]{3,7}$')),
    CONSTRAINT ai_conversation_output_json_check CHECK (
        (definition IS NULL OR jsonb_typeof(definition) = 'object') AND (units IS NULL OR jsonb_typeof(units) = 'object')
        AND (lineage IS NULL OR jsonb_typeof(lineage) = 'object') AND (columns IS NULL OR jsonb_typeof(columns) = 'array'))
);
CREATE INDEX ai_conversation_output_conversation_idx ON public."AI_conversation_output" (conversation_id, created_at);
COMMENT ON TABLE public."AI_conversation_output" IS
    'A released output of a market-ai-orc conversation, kept for the life of the conversation (R-STORE).';

CREATE TABLE public."AI_conversation_execution" (
    execution_id text PRIMARY KEY,
    conversation_id text NOT NULL REFERENCES public."AI_conversation" (conversation_id) ON DELETE CASCADE,
    request_id text NOT NULL,
    session_id text,
    code text NOT NULL,
    code_truncated boolean NOT NULL DEFAULT false,
    code_sha256 text NOT NULL,
    modules jsonb,
    access jsonb,
    status text,
    created_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ai_conversation_execution_id_check CHECK (execution_id ~ '^exe_[0-9a-f]{24}$'),
    CONSTRAINT ai_conversation_execution_request_check CHECK (request_id ~ '^[A-Za-z0-9._:-]{1,200}$'),
    CONSTRAINT ai_conversation_execution_session_check
        CHECK (session_id IS NULL OR session_id ~ '^sess_[0-9a-f]{24}$'),
    CONSTRAINT ai_conversation_execution_code_check CHECK (length(code) <= 65536),
    CONSTRAINT ai_conversation_execution_sha_check CHECK (code_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ai_conversation_execution_json_check CHECK (
        (modules IS NULL OR jsonb_typeof(modules) = 'array') AND (access IS NULL OR jsonb_typeof(access) IN ('array', 'object')))
);
CREATE INDEX ai_conversation_execution_conversation_idx
    ON public."AI_conversation_execution" (conversation_id, created_at);
COMMENT ON TABLE public."AI_conversation_execution" IS
    'The code of one sandbox execution of a market-ai-orc conversation, kept for the life of the conversation (R-STORE).';

CREATE TABLE public."AI_conversation_export" (
    export_id text PRIMARY KEY,
    conversation_id text NOT NULL REFERENCES public."AI_conversation" (conversation_id) ON DELETE CASCADE,
    request_id text NOT NULL,
    source_ref text NOT NULL,
    format text NOT NULL,
    file_name text NOT NULL,
    mime_type text NOT NULL,
    size_bytes bigint NOT NULL,
    sha256 text NOT NULL,
    content bytea NOT NULL,
    includes jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ai_conversation_export_id_check CHECK (export_id ~ '^exp_[0-9a-f]{24}$'),
    CONSTRAINT ai_conversation_export_request_check CHECK (request_id ~ '^[A-Za-z0-9._:-]{1,200}$'),
    CONSTRAINT ai_conversation_export_source_check CHECK (length(source_ref) BETWEEN 1 AND 200),
    CONSTRAINT ai_conversation_export_format_check CHECK (format IN ('CSV', 'XLSX', 'PARQUET')),
    CONSTRAINT ai_conversation_export_name_check CHECK (file_name ~ '^[A-Za-z0-9._-]{1,120}$'),
    CONSTRAINT ai_conversation_export_size_check
        CHECK (size_bytes = octet_length(content) AND size_bytes BETWEEN 1 AND 20971520),
    CONSTRAINT ai_conversation_export_sha_check CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ai_conversation_export_includes_check CHECK (jsonb_typeof(includes) = 'object')
);
CREATE INDEX ai_conversation_export_conversation_idx ON public."AI_conversation_export" (conversation_id, created_at);
COMMENT ON TABLE public."AI_conversation_export" IS
    'A file exported from a market-ai-orc conversation for download (phase D), at most 20 MB.';

REVOKE ALL ON public."AI_conversation_output", public."AI_conversation_execution", public."AI_conversation_export"
    FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE, DELETE
    ON public."AI_conversation_output", public."AI_conversation_execution", public."AI_conversation_export"
    TO market_ai_conversation_store;

INSERT INTO public."Table_Catalog" (
    table_schema, table_name, category, definition, grain,
    primary_key_columns, source_system, source_tables, source_code_paths,
    update_rule, related_functions, documentation_status,
    readiness_mode, readiness_date_column, observation_date_column,
    data_available_at_column, availability_rule, point_in_time_status,
    historical_metadata_method
) VALUES (
    'public', 'AI_conversation_output', 'System',
    'Released outputs of market-ai-orc conversations (tables, JSON, text, charts) with their definition, units, lineage and the last date of the data they were computed from; the content up to 20 MB is here, a larger one in the bucket market-ai-conversation-outputs.',
    'One row per sandbox output_id', ARRAY['output_id'],
    'market-ai-orc (app/result_store.py) after a completed analysis or research group released the output',
    ARRAY['AI_conversation']::text[], ARRAY['apps/market-ai-orc/app/result_store.py',
                                             'database/migrations/20261003_006_conversation_results.sql'],
    'Inserted once per released output; deleted with its conversation.',
    ARRAY[]::text[], 'VERIFIED', 'NOT_APPLICABLE', NULL, NULL, 'created_at',
    'Operational conversation state derived from market data, not market data itself.', 'NOT_APPLICABLE', NULL
), (
    'public', 'AI_conversation_execution', 'System',
    'The code of each sandbox execution of a market-ai-orc conversation, so a result can be traced and reproduced after the sandbox copy expired.',
    'One row per sandbox execution_id', ARRAY['execution_id'],
    'market-ai-orc (app/result_store.py) after each run_python or run_research_code call',
    ARRAY['AI_conversation']::text[], ARRAY['apps/market-ai-orc/app/result_store.py',
                                             'database/migrations/20261003_006_conversation_results.sql'],
    'Inserted once per execution; deleted with its conversation.',
    ARRAY[]::text[], 'VERIFIED', 'NOT_APPLICABLE', NULL, NULL, 'created_at',
    'Operational conversation state, not market data.', 'NOT_APPLICABLE', NULL
), (
    'public', 'AI_conversation_export', 'System',
    'Files exported from a market-ai-orc conversation for the user to download (CSV, XLSX or Parquet, at most 20 MB).',
    'One row per export_id', ARRAY['export_id'],
    'market-ai-orc export_result (phase D)',
    ARRAY['AI_conversation', 'AI_conversation_output']::text[],
    ARRAY['database/migrations/20261003_006_conversation_results.sql'],
    'Inserted once per export; deleted with its conversation.',
    ARRAY[]::text[], 'VERIFIED', 'NOT_APPLICABLE', NULL, NULL, 'created_at',
    'Operational conversation state, not market data.', 'NOT_APPLICABLE', NULL
);

INSERT INTO public."Column_Catalog" (
    table_schema, table_name, column_name, ordinal_position, data_type,
    is_nullable, default_expression, is_primary_key, definition,
    source_column_or_expression, unit, null_rule, source_code_paths,
    documentation_status
)
SELECT columns.table_schema, columns.table_name, columns.column_name, columns.ordinal_position,
       columns.data_type, columns.is_nullable = 'YES', columns.column_default,
       (columns.table_name, columns.column_name) IN (('AI_conversation_output', 'output_id'),
                                                    ('AI_conversation_execution', 'execution_id'),
                                                    ('AI_conversation_export', 'export_id')),
       CASE columns.table_name || '.' || columns.column_name
        WHEN 'AI_conversation_output.output_id' THEN 'The sandbox output_id (out_ + 24 hex); the same id the data record and load_output use.'
        WHEN 'AI_conversation_output.conversation_id' THEN 'The conversation the output belongs to.'
        WHEN 'AI_conversation_output.request_id' THEN 'The market-ai-orc request that released the output.'
        WHEN 'AI_conversation_output.session_id' THEN 'The sandbox session that produced the output.'
        WHEN 'AI_conversation_output.execution_id' THEN 'The sandbox execution that produced the output (see AI_conversation_execution).'
        WHEN 'AI_conversation_output.name' THEN 'The output name given in emit_table / emit_json (at most 80 characters).'
        WHEN 'AI_conversation_output.output_type' THEN 'The sandbox output type (TABLE, JSON, TEXT, CHART or FILE).'
        WHEN 'AI_conversation_output.format' THEN 'The stored file format: PARQUET, CSV, PNG, JSON, TEXT or BIN.'
        WHEN 'AI_conversation_output.label' THEN 'The evidence label the sandbox gave the output (for example DATA_COVERAGE_VERIFIED).'
        WHEN 'AI_conversation_output.definition' THEN 'How the output was made: filters, period, entities, thresholds and notes, as declared when it was released.'
        WHEN 'AI_conversation_output.units' THEN 'Unit of each column that has one (FRACTION, PERCENT or P_VALUE).'
        WHEN 'AI_conversation_output.lineage' THEN 'Where the output came from: need_id, bundle_id, execution code hash and reference date.'
        WHEN 'AI_conversation_output.data_as_of' THEN 'The last date of the data the output was computed from (the largest actual end date of its bundle ranges); a recomputation of the conversation uses the same date unless the user asks for newer data.'
        WHEN 'AI_conversation_output.row_count' THEN 'Rows of a table output; NULL for other outputs.'
        WHEN 'AI_conversation_output.columns' THEN 'Column names of a table output, in order; NULL for other outputs.'
        WHEN 'AI_conversation_output.byte_count' THEN 'Size of the stored file in bytes.'
        WHEN 'AI_conversation_output.checksum_sha256' THEN 'SHA-256 of the stored file; checked when the file is loaded into a new session.'
        WHEN 'AI_conversation_output.storage' THEN 'POSTGRES (content holds the file, at most 20 MB) or BUCKET (object_key names it in market-ai-conversation-outputs).'
        WHEN 'AI_conversation_output.content' THEN 'The file when storage is POSTGRES; NULL otherwise.'
        WHEN 'AI_conversation_output.object_key' THEN 'The bucket key (outputs/<conversation_id>/<output_id>.<ext>) when storage is BUCKET; NULL otherwise.'
        WHEN 'AI_conversation_output.created_at' THEN 'When the output was stored.'
        WHEN 'AI_conversation_execution.execution_id' THEN 'The sandbox execution_id (exe_ + 24 hex).'
        WHEN 'AI_conversation_execution.conversation_id' THEN 'The conversation the execution belongs to.'
        WHEN 'AI_conversation_execution.request_id' THEN 'The market-ai-orc request that ran the code.'
        WHEN 'AI_conversation_execution.session_id' THEN 'The sandbox session that ran the code.'
        WHEN 'AI_conversation_execution.code' THEN 'The code that ran (its first 65,536 characters when code_truncated).'
        WHEN 'AI_conversation_execution.code_truncated' THEN 'True when the code was longer than 65,536 characters and only its start is stored.'
        WHEN 'AI_conversation_execution.code_sha256' THEN 'SHA-256 of the whole code, as the sandbox recorded it.'
        WHEN 'AI_conversation_execution.modules' THEN 'Modules the code imported, as the sandbox reported them.'
        WHEN 'AI_conversation_execution.access' THEN 'The data the code read (requests, ranges, carried tables), as the sandbox reported it.'
        WHEN 'AI_conversation_execution.status' THEN 'The execution status the sandbox returned (OK, SCRIPT_ERROR, TIMEOUT, ...).'
        WHEN 'AI_conversation_execution.created_at' THEN 'When the execution was stored.'
        WHEN 'AI_conversation_export.export_id' THEN 'Id of the export (exp_ + 24 hex).'
        WHEN 'AI_conversation_export.conversation_id' THEN 'The conversation the export belongs to.'
        WHEN 'AI_conversation_export.request_id' THEN 'The market-ai-orc request that created the export.'
        WHEN 'AI_conversation_export.source_ref' THEN 'What was exported: an output ref or id, or an evidence reference.'
        WHEN 'AI_conversation_export.format' THEN 'CSV, XLSX or PARQUET.'
        WHEN 'AI_conversation_export.file_name' THEN 'The download file name.'
        WHEN 'AI_conversation_export.mime_type' THEN 'The media type sent with the download.'
        WHEN 'AI_conversation_export.size_bytes' THEN 'Size of the file in bytes (at most 20 MB).'
        WHEN 'AI_conversation_export.sha256' THEN 'SHA-256 of the file.'
        WHEN 'AI_conversation_export.content' THEN 'The file.'
        WHEN 'AI_conversation_export.includes' THEN 'What the file contains besides the rows (definitions, lineage).'
        WHEN 'AI_conversation_export.created_at' THEN 'When the export was created.'
       END,
       'apps/market-ai-orc/app/result_store.py', NULL,
       CASE WHEN columns.is_nullable = 'YES' THEN 'NULL when not applicable, as the definition states.'
            ELSE 'NULL is not permitted.' END,
       ARRAY['apps/market-ai-orc/app/result_store.py'], 'VERIFIED'
FROM information_schema.columns AS columns
WHERE columns.table_schema = 'public'
  AND columns.table_name IN ('AI_conversation_output', 'AI_conversation_execution', 'AI_conversation_export');

DO $verify$
BEGIN
    IF (SELECT count(*) FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'AI_conversation_output') <> 21
       OR (SELECT count(*) FROM information_schema.columns
           WHERE table_schema = 'public' AND table_name = 'AI_conversation_execution') <> 11
       OR (SELECT count(*) FROM information_schema.columns
           WHERE table_schema = 'public' AND table_name = 'AI_conversation_export') <> 12 THEN
        RAISE EXCEPTION 'The conversation result tables do not have the expected columns';
    END IF;
    IF (SELECT count(*) FROM public."Column_Catalog"
        WHERE table_name IN ('AI_conversation_output', 'AI_conversation_execution', 'AI_conversation_export')
          AND definition IS NOT NULL) <> 44 THEN
        RAISE EXCEPTION 'Every conversation result column needs a Column_Catalog definition';
    END IF;
    IF (SELECT count(*) FROM (VALUES ('SELECT'), ('INSERT'), ('UPDATE'), ('DELETE')) AS p(privilege),
               (VALUES ('public."AI_conversation_output"'), ('public."AI_conversation_execution"'),
                       ('public."AI_conversation_export"')) AS t(relation)
        WHERE has_table_privilege('market_ai_conversation_store', t.relation, p.privilege)) <> 12
       OR EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                  WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
                    AND c.relname NOT IN ('AI_conversation', 'AI_conversation_turn', 'AI_conversation_output',
                                          'AI_conversation_execution', 'AI_conversation_export')
                    AND has_table_privilege('market_ai_conversation_store', c.oid, 'SELECT,INSERT,UPDATE,DELETE')) THEN
        RAISE EXCEPTION 'market_ai_conversation_store must reach the five conversation tables only';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles
               WHERE rolname IN ('market_ai_sql_reader', 'market_ai_catalog_reader', 'market_ai_orc')
                 AND (has_table_privilege(oid, 'public."AI_conversation_output"', 'SELECT,INSERT,UPDATE,DELETE')
                      OR has_table_privilege(oid, 'public."AI_conversation_execution"', 'SELECT,INSERT,UPDATE,DELETE')
                      OR has_table_privilege(oid, 'public."AI_conversation_export"', 'SELECT,INSERT,UPDATE,DELETE'))) THEN
        RAISE EXCEPTION 'The Governor, catalog reader and market_ai_orc logins must have no access to conversation results';
    END IF;
END
$verify$;

COMMIT;
