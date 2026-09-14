-- Make per-call audit numbering unambiguous across expired-lease retries.
BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '2min';

ALTER TABLE public."Analysis_Model_Call"
    ADD COLUMN attempt_number integer NOT NULL DEFAULT 1;

ALTER TABLE public."Analysis_Model_Call"
    ALTER COLUMN attempt_number DROP DEFAULT,
    DROP CONSTRAINT "Analysis_Model_Call_request_iteration_key",
    ADD CONSTRAINT "Analysis_Model_Call_request_attempt_iteration_key"
        UNIQUE (request_id, attempt_number, iteration_number),
    ADD CONSTRAINT "Analysis_Model_Call_attempt_check"
        CHECK (attempt_number > 0);

COMMENT ON COLUMN public."Analysis_Model_Call".attempt_number IS
    'One-based Analysis_Request processing attempt; iteration numbering restarts within each lease attempt.';

INSERT INTO public."Column_Catalog" (
    table_schema, table_name, column_name, ordinal_position, data_type,
    is_nullable, default_expression, is_primary_key, definition,
    source_column_or_expression, unit, null_rule, source_code_paths,
    documentation_status
)
SELECT c.table_schema, c.table_name, c.column_name, c.ordinal_position,
       c.data_type, false, c.column_default, false,
       pg_catalog.col_description(pc.oid, pa.attnum),
       'Analysis_Request.attempt_count returned atomically when processing starts.',
       'Count', 'Never NULL.',
       ARRAY['database/migrations/20260914_038_make_model_call_audit_retry_safe.sql',
             'apps/market-ai-backend/app/orchestrator.py'],
       'VERIFIED'
FROM information_schema.columns c
JOIN pg_catalog.pg_class pc
  ON pc.oid = format('%I.%I', c.table_schema, c.table_name)::regclass
JOIN pg_catalog.pg_attribute pa
  ON pa.attrelid = pc.oid AND pa.attname = c.column_name
WHERE c.table_schema='public' AND c.table_name='Analysis_Model_Call'
  AND c.column_name='attempt_number';

UPDATE public."Table_Catalog"
SET source_code_paths = array_append(
        source_code_paths,
        'database/migrations/20260914_038_make_model_call_audit_retry_safe.sql'
    ),
    updated_at = CURRENT_TIMESTAMP
WHERE table_schema='public' AND table_name='Analysis_Model_Call'
  AND NOT ('database/migrations/20260914_038_make_model_call_audit_retry_safe.sql'=ANY(source_code_paths));

COMMIT;
