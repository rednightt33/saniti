-- EXEC-ASK-BRANCH (user 2026-10-24: "Ok untuk Q1 dan Q2"): EDGE's list row of a conversation that continues another
-- one. kind MAIN is a conversation started on its own; BRANCH one made by "Branch" (opened in a new tab, listed like any
-- other); SIDE the side chat of one answer ("Ask about this answer"), which the conversation list leaves out (Q2) and
-- the answer links to. parent_conversation_id / parent_request_id name the conversation and the answer it continues;
-- Orc keeps the history itself ("AI_conversation".lineage, migration 20261024_001). edge_bff_runtime's table grants
-- cover the new columns. Forward-only; every existing row becomes MAIN.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';
DO $preflight$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'edge_bff' AND table_name = 'conversation_ui' AND column_name = 'hidden_at') THEN
        RAISE EXCEPTION 'edge_bff.conversation_ui.hidden_at is missing: apply 20261012_008 first';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema = 'edge_bff' AND table_name = 'conversation_ui'
                 AND column_name IN ('kind', 'parent_conversation_id', 'parent_request_id')) THEN
        RAISE EXCEPTION 'edge_bff.conversation_ui already has a branch column: reconcile before applying';
    END IF;
END $preflight$;
ALTER TABLE edge_bff.conversation_ui
    ADD COLUMN kind text NOT NULL DEFAULT 'MAIN' CHECK (kind IN ('MAIN', 'BRANCH', 'SIDE')),
    ADD COLUMN parent_conversation_id text CHECK (parent_conversation_id ~ '^conv_[0-9a-f]{32}$'),
    ADD COLUMN parent_request_id text CHECK (length(parent_request_id) BETWEEN 1 AND 200),
    ADD CONSTRAINT conversation_ui_parent_check CHECK ((kind = 'MAIN') = (parent_conversation_id IS NULL)
                                                       AND (kind = 'MAIN') = (parent_request_id IS NULL));
CREATE UNIQUE INDEX conversation_ui_side_chat_key ON edge_bff.conversation_ui (owner_key, parent_request_id)
    WHERE kind = 'SIDE';
COMMENT ON COLUMN edge_bff.conversation_ui.kind IS
    'MAIN (started on its own), BRANCH (EDGE Branch of an answer, listed) or SIDE (the side chat of one answer, left out of the list).';
COMMENT ON COLUMN edge_bff.conversation_ui.parent_conversation_id IS
    'The conversation a BRANCH or SIDE conversation continues; NULL for MAIN.';
COMMENT ON COLUMN edge_bff.conversation_ui.parent_request_id IS
    'The answer (request id) a BRANCH or SIDE conversation continues from; one SIDE conversation per answer; NULL for MAIN.';
DO $verify$
BEGIN
    IF EXISTS (SELECT 1 FROM edge_bff.conversation_ui WHERE kind <> 'MAIN') THEN
        RAISE EXCEPTION 'an existing row is not MAIN';
    END IF;
    IF NOT (has_column_privilege('edge_bff_runtime', 'edge_bff.conversation_ui', 'kind', 'SELECT')
            AND has_column_privilege('edge_bff_runtime', 'edge_bff.conversation_ui', 'kind', 'INSERT')
            AND has_column_privilege('edge_bff_runtime', 'edge_bff.conversation_ui', 'parent_request_id', 'INSERT')) THEN
        RAISE EXCEPTION 'edge_bff_runtime cannot use the new columns';
    END IF;
END $verify$;
COMMIT;
