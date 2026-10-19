-- EXEC-ORC-BUDGET (user go 2026-10-19): bounded internal presentation recovery, never a terminal answer.
-- Additive and compatible with the previous app; existing conversation-role table grants cover this column.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';

ALTER TABLE public."AI_conversation_turn" ADD COLUMN execution_checkpoint jsonb;
ALTER TABLE public."AI_conversation_turn" ADD CONSTRAINT ai_conversation_checkpoint_check CHECK (
    execution_checkpoint IS NULL OR (jsonb_typeof(execution_checkpoint) = 'object'
      AND (execution_checkpoint->>'version' = '1') IS TRUE
      AND (jsonb_typeof(execution_checkpoint->'steps') = 'object') IS TRUE
      AND octet_length(execution_checkpoint::text) <= 262144));
COMMENT ON COLUMN public."AI_conversation_turn".execution_checkpoint IS
    'Internal bounded WORK/READY presentation checkpoints per sub-run: fenced by owner, conversation and lease generation. Saved result references and completion contract, never hidden reasoning or raw datasets. NULL means no checkpoint.';

UPDATE public."Table_Catalog" SET source_code_paths = ARRAY(
    SELECT DISTINCT unnest(source_code_paths || ARRAY[
      'apps/market-ai-orc/app/presentation_checkpoint.py',
      'database/migrations/20261019_001_orc_execution_checkpoint.sql']))
WHERE table_schema = 'public' AND table_name = 'AI_conversation_turn';

INSERT INTO public."Column_Catalog" (
 table_schema, table_name, column_name, ordinal_position, data_type, is_nullable, default_expression,
 is_primary_key, definition, source_column_or_expression, unit, null_rule, source_code_paths, documentation_status)
SELECT table_schema, table_name, column_name, ordinal_position, data_type, true, NULL, false,
 'Internal versioned execution checkpoint (maximum 256 KiB) with one phase and saved-result contract per executor sub-run. READY permits presentation-only retry; it does not prove every natural-language deliverable is complete. Owner, conversation and lease-generation fencing is mandatory. No hidden reasoning or raw datasets.',
 'apps/market-ai-orc/app/conversations.py:write_checkpoint', NULL,
 'NULL until a checkpoint is saved; expired conversations delete it with their turns.',
 ARRAY['apps/market-ai-orc/app/conversations.py','apps/market-ai-orc/app/presentation_checkpoint.py',
       'database/migrations/20261019_001_orc_execution_checkpoint.sql'], 'VERIFIED'
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'AI_conversation_turn' AND column_name = 'execution_checkpoint';

DO $verify$
BEGIN
 IF NOT has_column_privilege('market_ai_conversation_store','public."AI_conversation_turn"',
                             'execution_checkpoint','UPDATE') THEN
   RAISE EXCEPTION 'Existing conversation role must retain its table UPDATE privilege';
 END IF;
 IF NOT EXISTS (SELECT 1 FROM public."Column_Catalog" WHERE table_schema='public'
                AND table_name='AI_conversation_turn' AND column_name='execution_checkpoint') THEN
   RAISE EXCEPTION 'Checkpoint column must be cataloged';
 END IF;
END
$verify$;
COMMIT;
