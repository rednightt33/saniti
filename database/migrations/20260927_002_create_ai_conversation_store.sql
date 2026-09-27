-- Conversation store for market-ai-orc (implementation plan 2026-09-27, phase H1; AI_ENABLE_CONVERSATION_STORE).
--
-- "AI_conversation" is one chat box: its owner, retention and the single-active-run lease. "AI_conversation_turn" is
-- one message and its stored response. With history_mode SERVER the orchestrator reads earlier turns from here, so
-- the caller no longer sends history. The owner is the X-Saniti-Owner header of the trusted server-side caller (the
-- holder of the internal bearer), never a value from the model; a conversation_id is not a credential.
-- Operational state, not an audit: rows are updated while a turn runs and deleted after retention (30 days after the
-- last activity by default). AI_research_run_audit stays the insert-only audit.
-- The third table of the plan (AI_conversation_resource) belongs to the resource reuse phases (S1, S2) and is not
-- created here.
-- market_ai_conversation_store (NOLOGIN) may SELECT, INSERT, UPDATE and DELETE these two tables only; the login
-- market_ai_conversation (scripts/provision_market_ai_conversation_login.py) is its only member. PUBLIC is revoked.
-- Forward-only. No market-data table, catalog reader, SQL Governor grant, or existing row is changed.
BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';

DO $preflight$
BEGIN
    IF to_regclass('public."AI_conversation"') IS NOT NULL OR to_regclass('public."AI_conversation_turn"') IS NOT NULL THEN
        RAISE EXCEPTION 'A conversation table already exists: inspect before applying';
    END IF;
    IF EXISTS (SELECT 1 FROM public."Table_Catalog"
               WHERE table_schema = 'public' AND table_name IN ('AI_conversation', 'AI_conversation_turn')) THEN
        RAISE EXCEPTION 'Table_Catalog already documents a conversation table';
    END IF;
END
$preflight$;

CREATE TABLE public."AI_conversation" (
    conversation_id text PRIMARY KEY,
    owner_key text NOT NULL,
    created_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at timestamp with time zone NOT NULL,
    next_turn_index integer NOT NULL DEFAULT 0,
    active_request_id text,
    lease_generation bigint NOT NULL DEFAULT 0,
    lease_expires_at timestamp with time zone,
    state jsonb NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT ai_conversation_id_check CHECK (conversation_id ~ '^conv_[0-9a-f]{32}$'),
    CONSTRAINT ai_conversation_owner_check CHECK (owner_key ~ '^[A-Za-z0-9._:@-]{1,128}$'),
    CONSTRAINT ai_conversation_turn_index_check CHECK (next_turn_index >= 0 AND lease_generation >= 0),
    CONSTRAINT ai_conversation_lease_check CHECK ((active_request_id IS NULL) = (lease_expires_at IS NULL)),
    CONSTRAINT ai_conversation_expiry_check CHECK (expires_at > created_at),
    CONSTRAINT ai_conversation_state_check CHECK (jsonb_typeof(state) = 'object')
);
CREATE INDEX ai_conversation_owner_idx ON public."AI_conversation" (owner_key, updated_at DESC);
CREATE INDEX ai_conversation_expiry_idx ON public."AI_conversation" (expires_at);
COMMENT ON TABLE public."AI_conversation" IS
    'One market-ai-orc chat box (history_mode SERVER): owner, retention and the single-active-run lease.';

CREATE TABLE public."AI_conversation_turn" (
    request_id text PRIMARY KEY,
    conversation_id text NOT NULL REFERENCES public."AI_conversation" (conversation_id) ON DELETE CASCADE,
    turn_index integer NOT NULL,
    request_fingerprint text NOT NULL,
    user_message text NOT NULL,
    status text NOT NULL,
    lease_generation bigint NOT NULL,
    run_status text,
    response_type text,
    assistant_text text,
    response jsonb,
    error_code text,
    created_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at timestamp with time zone,
    CONSTRAINT ai_conversation_turn_position_key UNIQUE (conversation_id, turn_index),
    CONSTRAINT ai_conversation_turn_request_id_check CHECK (request_id ~ '^[A-Za-z0-9._:-]{1,200}$'),
    CONSTRAINT ai_conversation_turn_index_check CHECK (turn_index >= 0 AND lease_generation >= 0),
    CONSTRAINT ai_conversation_turn_fingerprint_check CHECK (request_fingerprint ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ai_conversation_turn_text_check CHECK (length(user_message) BETWEEN 1 AND 20000
        AND (assistant_text IS NULL OR length(assistant_text) <= 40000)),
    CONSTRAINT ai_conversation_turn_status_check
        CHECK (status IN ('RUNNING', 'COMPLETED', 'FAILED', 'INTERRUPTED')),
    CONSTRAINT ai_conversation_turn_finished_check CHECK ((status = 'RUNNING') = (completed_at IS NULL)),
    CONSTRAINT ai_conversation_turn_response_check CHECK (response IS NULL OR jsonb_typeof(response) = 'object')
);
COMMENT ON TABLE public."AI_conversation_turn" IS
    'One message of a market-ai-orc conversation and the response returned for it (history_mode SERVER).';

DO $role$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'market_ai_conversation_store') THEN
        CREATE ROLE market_ai_conversation_store NOLOGIN;
    END IF;
END
$role$;
REVOKE ALL ON public."AI_conversation", public."AI_conversation_turn" FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE, DELETE ON public."AI_conversation", public."AI_conversation_turn"
    TO market_ai_conversation_store;

INSERT INTO public."Table_Catalog" (
    table_schema, table_name, category, definition, grain,
    primary_key_columns, source_system, source_tables, source_code_paths,
    update_rule, related_functions, documentation_status,
    readiness_mode, readiness_date_column, observation_date_column,
    data_available_at_column, availability_rule, point_in_time_status,
    historical_metadata_method
) VALUES (
    'public', 'AI_conversation', 'System',
    'market-ai-orc conversations kept by the server (history_mode SERVER): one row per chat box with its owner, retention and the lease that allows one active run at a time.',
    'One row per conversation_id', ARRAY['conversation_id'],
    'market-ai-orc (app/conversations.py) when a SERVER-mode request starts or finishes a turn',
    ARRAY[]::text[], ARRAY['apps/market-ai-orc/app/conversations.py',
                           'database/migrations/20260927_002_create_ai_conversation_store.sql'],
    'Created by the first SERVER-mode message; updated when a turn starts and ends; deleted after expires_at by the orchestrator''s cleanup.',
    ARRAY[]::text[], 'VERIFIED', 'NOT_APPLICABLE', NULL, NULL, 'updated_at',
    'Operational chat state, not market data.', 'NOT_APPLICABLE', NULL
), (
    'public', 'AI_conversation_turn', 'System',
    'One message of a market-ai-orc conversation: the user message, the run status and the response returned to the caller.',
    'One row per market-ai-orc request_id in SERVER mode', ARRAY['request_id'],
    'market-ai-orc (app/conversations.py) when a SERVER-mode turn starts and when it ends',
    ARRAY['AI_conversation']::text[], ARRAY['apps/market-ai-orc/app/conversations.py',
                                             'database/migrations/20260927_002_create_ai_conversation_store.sql'],
    'Inserted RUNNING when a turn starts; set to COMPLETED, FAILED or INTERRUPTED once; deleted with its conversation.',
    ARRAY[]::text[], 'VERIFIED', 'NOT_APPLICABLE', NULL, NULL, 'created_at',
    'Operational chat state, not market data.', 'NOT_APPLICABLE', NULL
);

INSERT INTO public."Column_Catalog" (
    table_schema, table_name, column_name, ordinal_position, data_type,
    is_nullable, default_expression, is_primary_key, definition,
    source_column_or_expression, unit, null_rule, source_code_paths,
    documentation_status
)
SELECT columns.table_schema, columns.table_name, columns.column_name, columns.ordinal_position,
       columns.data_type, columns.is_nullable = 'YES', columns.column_default,
       (columns.table_name, columns.column_name) IN (('AI_conversation', 'conversation_id'),
                                                    ('AI_conversation_turn', 'request_id')),
       CASE columns.table_name || '.' || columns.column_name
        WHEN 'AI_conversation.conversation_id' THEN 'Server-generated id of the chat box (conv_ + 32 hex). Not a credential: every lookup also checks owner_key.'
        WHEN 'AI_conversation.owner_key' THEN 'The owner given by the trusted server-side caller in the X-Saniti-Owner header (default when absent); never taken from the model.'
        WHEN 'AI_conversation.created_at' THEN 'When the conversation was created.'
        WHEN 'AI_conversation.updated_at' THEN 'Last activity: a turn started or finished.'
        WHEN 'AI_conversation.expires_at' THEN 'When the cleanup may delete the conversation and its turns: updated_at plus AI_CONVERSATION_RETENTION_DAYS.'
        WHEN 'AI_conversation.next_turn_index' THEN 'The turn_index the next message receives.'
        WHEN 'AI_conversation.active_request_id' THEN 'request_id of the running turn; NULL when no turn runs.'
        WHEN 'AI_conversation.lease_generation' THEN 'Incremented by every turn start; a turn may finish only with the generation it started with (fencing).'
        WHEN 'AI_conversation.lease_expires_at' THEN 'When a running turn''s lease lapses and another message may take over; NULL when no turn runs.'
        WHEN 'AI_conversation.state' THEN 'Structured conversation state kept by the orchestrator (for example the latest Research Plan reference); never model-written text.'
        WHEN 'AI_conversation_turn.request_id' THEN 'The market-ai-orc request_id of the turn; unique across all conversations.'
        WHEN 'AI_conversation_turn.conversation_id' THEN 'The conversation the turn belongs to.'
        WHEN 'AI_conversation_turn.turn_index' THEN 'Position of the turn in its conversation, from 0.'
        WHEN 'AI_conversation_turn.request_fingerprint' THEN 'SHA-256 of the request content; a retry with the same request_id must match it.'
        WHEN 'AI_conversation_turn.user_message' THEN 'The user''s message.'
        WHEN 'AI_conversation_turn.status' THEN 'RUNNING, COMPLETED (a response was returned), FAILED (the run raised no response) or INTERRUPTED (the lease lapsed before the turn finished).'
        WHEN 'AI_conversation_turn.lease_generation' THEN 'The conversation lease generation the turn started with.'
        WHEN 'AI_conversation_turn.run_status' THEN 'The status returned to the caller (COMPLETED, NEEDS_CLARIFICATION, AWAITING_CONFIRMATION, LIMITED, FAILED); NULL while running.'
        WHEN 'AI_conversation_turn.response_type' THEN 'ANSWER, CLARIFICATION, RESEARCH_PLAN_CONFIRMATION or LIMITATION; NULL without a response.'
        WHEN 'AI_conversation_turn.assistant_text' THEN 'The text that later turns see as the assistant message: the answer, or the clarification question for a CLARIFICATION.'
        WHEN 'AI_conversation_turn.response' THEN 'The complete response returned to the caller, so a retry of the same request_id returns it without a new run.'
        WHEN 'AI_conversation_turn.error_code' THEN 'Error code of a failed or interrupted turn; NULL otherwise.'
        WHEN 'AI_conversation_turn.created_at' THEN 'When the turn started.'
        WHEN 'AI_conversation_turn.completed_at' THEN 'When the turn finished; NULL while RUNNING.'
       END,
       'apps/market-ai-orc/app/conversations.py', NULL,
       CASE WHEN columns.is_nullable = 'YES' THEN 'NULL when not applicable, as the definition states.'
            ELSE 'NULL is not permitted.' END,
       ARRAY['apps/market-ai-orc/app/conversations.py'], 'VERIFIED'
FROM information_schema.columns AS columns
WHERE columns.table_schema = 'public' AND columns.table_name IN ('AI_conversation', 'AI_conversation_turn');

DO $verify$
BEGIN
    IF (SELECT count(*) FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'AI_conversation') <> 10
       OR (SELECT count(*) FROM information_schema.columns
           WHERE table_schema = 'public' AND table_name = 'AI_conversation_turn') <> 14 THEN
        RAISE EXCEPTION 'The conversation tables do not have the expected columns';
    END IF;
    IF (SELECT count(*) FROM public."Column_Catalog"
        WHERE table_name IN ('AI_conversation', 'AI_conversation_turn') AND definition IS NOT NULL) <> 24 THEN
        RAISE EXCEPTION 'Every conversation column needs a Column_Catalog definition';
    END IF;
    IF (SELECT count(*) FROM (VALUES ('SELECT'), ('INSERT'), ('UPDATE'), ('DELETE')) AS p(privilege),
               (VALUES ('public."AI_conversation"'), ('public."AI_conversation_turn"')) AS t(relation)
        WHERE has_table_privilege('market_ai_conversation_store', t.relation, p.privilege)) <> 8
       OR has_table_privilege('market_ai_conversation_store', 'public."AI_conversation"', 'TRUNCATE,REFERENCES')
       OR EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                  WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
                    AND c.relname NOT IN ('AI_conversation', 'AI_conversation_turn')
                    AND has_table_privilege('market_ai_conversation_store', c.oid, 'SELECT,INSERT,UPDATE,DELETE')) THEN
        RAISE EXCEPTION 'market_ai_conversation_store must have SELECT, INSERT, UPDATE and DELETE on the two tables only';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles
               WHERE rolname IN ('market_ai_sql_reader', 'market_ai_catalog_reader', 'market_ai_orc')
                 AND (has_table_privilege(oid, 'public."AI_conversation"', 'SELECT,INSERT,UPDATE,DELETE')
                      OR has_table_privilege(oid, 'public."AI_conversation_turn"', 'SELECT,INSERT,UPDATE,DELETE'))) THEN
        RAISE EXCEPTION 'The Governor, catalog reader and market_ai_orc logins must have no access to conversations';
    END IF;
END
$verify$;

COMMIT;
