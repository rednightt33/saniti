-- EXEC-ASK-BRANCH (user 2026-10-24: "Ok untuk Q1 dan Q2 ... buat imlpementation plan"): a conversation may continue
-- another one from one of its answers (EDGE "Branch" in a new tab, and the side chat "Ask about this answer"). The new
-- conversation keeps the line of conversations it continues in "AI_conversation".lineage, oldest first, each entry
-- {"conversation_id", "through_turn", "cut_at"}: their turns up to through_turn are its history, and their outputs,
-- executions, evidence, exports and run memories created up to cut_at (the completed_at of that turn) are readable from
-- it (apps/market-ai-orc/app/conversation_lineage.py). Nothing is copied. A lineage never changes after it is written.
-- No foreign key: each turn of the new conversation extends the retention of the ones it continues, so they outlive it,
-- and the existing per-conversation cleanup stays as it is.
-- The table grants of market_ai_conversation_store cover the new column. Forward-only; no existing row changes
-- (every conversation keeps the empty lineage).
-- Rollback (forward migration): ALTER TABLE public."AI_conversation" DROP COLUMN lineage and its Column_Catalog row.
BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';

DO $preflight$
BEGIN
    IF to_regclass('public."AI_conversation"') IS NULL THEN
        RAISE EXCEPTION 'AI_conversation is missing: apply 20260927_002 first';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema = 'public' AND table_name = 'AI_conversation' AND column_name = 'lineage') THEN
        RAISE EXCEPTION 'AI_conversation.lineage exists: reconcile before applying';
    END IF;
    IF EXISTS (SELECT 1 FROM public."Column_Catalog"
               WHERE table_schema = 'public' AND table_name = 'AI_conversation' AND column_name = 'lineage') THEN
        RAISE EXCEPTION 'Column_Catalog already documents AI_conversation.lineage';
    END IF;
END
$preflight$;

ALTER TABLE public."AI_conversation"
    ADD COLUMN lineage jsonb NOT NULL DEFAULT '[]'::jsonb
        CONSTRAINT ai_conversation_lineage_check CHECK (jsonb_typeof(lineage) = 'array' AND jsonb_array_length(lineage) <= 20);

COMMENT ON COLUMN public."AI_conversation".lineage IS
    'The conversations this one continues (EDGE Branch or side chat), oldest first: conversation_id, through_turn and cut_at; empty for a conversation started on its own.';

INSERT INTO public."Column_Catalog" (
    table_schema, table_name, column_name, ordinal_position, data_type,
    is_nullable, default_expression, is_primary_key, definition,
    source_column_or_expression, unit, null_rule, source_code_paths,
    documentation_status
)
SELECT columns.table_schema, columns.table_name, columns.column_name, columns.ordinal_position, columns.data_type,
       false, columns.column_default, false,
       'The conversations this one continues (EDGE Branch or side chat), oldest first: each entry names the conversation, '
       'the last turn of it this one continues (through_turn) and that turn''s completed_at (cut_at). Their turns up to '
       'through_turn are this conversation''s history, and their stored results created up to cut_at are readable from '
       'it. Empty for a conversation started on its own; never changed after it is written.',
       NULL, NULL, 'NULL is not permitted; an empty array when the conversation continues none.',
       ARRAY['apps/market-ai-orc/app/conversations.py', 'apps/market-ai-orc/app/conversation_lineage.py'], 'VERIFIED'
FROM information_schema.columns AS columns
WHERE columns.table_schema = 'public' AND columns.table_name = 'AI_conversation' AND columns.column_name = 'lineage';

DO $verify$
BEGIN
    IF (SELECT count(*) FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'AI_conversation') <> 11 THEN
        RAISE EXCEPTION 'AI_conversation does not have the expected 11 columns';
    END IF;
    IF EXISTS (SELECT 1 FROM public."AI_conversation" WHERE lineage <> '[]'::jsonb) THEN
        RAISE EXCEPTION 'an existing conversation has a lineage';
    END IF;
    IF (SELECT count(*) FROM public."Column_Catalog"
        WHERE table_name = 'AI_conversation' AND definition IS NOT NULL) <> 11 THEN
        RAISE EXCEPTION 'Every AI_conversation column needs a Column_Catalog definition';
    END IF;
    IF NOT (has_column_privilege('market_ai_conversation_store', 'public."AI_conversation"', 'lineage', 'SELECT')
            AND has_column_privilege('market_ai_conversation_store', 'public."AI_conversation"', 'lineage', 'INSERT')
            AND has_column_privilege('market_ai_conversation_store', 'public."AI_conversation"', 'lineage', 'UPDATE')) THEN
        RAISE EXCEPTION 'market_ai_conversation_store cannot use AI_conversation.lineage';
    END IF;
END
$verify$;

COMMIT;
