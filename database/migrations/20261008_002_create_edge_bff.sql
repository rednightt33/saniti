-- Approved dev rollout 2026-10-08; live admin schema/grant preflight verified before application.
-- Dedicated operational schema; no AI/market table or canonical retention changes.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';
DO $preflight$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'edge_bff') OR
       EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'edge_bff_runtime') THEN
        RAISE EXCEPTION 'EDGE schema/role exists: reconcile before applying';
    END IF;
END $preflight$;
CREATE ROLE edge_bff_runtime NOLOGIN;
CREATE SCHEMA edge_bff;
REVOKE ALL ON SCHEMA edge_bff FROM PUBLIC;
GRANT USAGE ON SCHEMA edge_bff TO edge_bff_runtime;
CREATE TABLE edge_bff.sessions (
    token_hash text PRIMARY KEY CHECK (token_hash ~ '^[0-9a-f]{64}$'),
    owner_key text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    CHECK (expires_at > created_at)
);
CREATE TABLE edge_bff.jobs (
    request_id text PRIMARY KEY CHECK (request_id ~ '^edge_[0-9a-f]{32}$'),
    owner_key text NOT NULL,
    submission_key text NOT NULL CHECK (length(submission_key) BETWEEN 1 AND 100),
    fingerprint text NOT NULL CHECK (fingerprint ~ '^[0-9a-f]{64}$'),
    input jsonb NOT NULL CHECK (jsonb_typeof(input) = 'object'),
    conversation_id text,
    state text NOT NULL DEFAULT 'QUEUED' CHECK (state IN ('QUEUED','RUNNING','RECOVERING','FINISHED','FAILED','INTERRUPTED')),
    state_version bigint NOT NULL DEFAULT 1 CHECK (state_version > 0),
    attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    lease_token text,
    lease_expires_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at timestamptz,
    run_status text CHECK (run_status IN ('COMPLETED','NEEDS_CLARIFICATION','AWAITING_CONFIRMATION','LIMITED','FAILED')),
    error_code text,
    UNIQUE (owner_key, submission_key),
    CHECK ((state IN ('FINISHED','FAILED','INTERRUPTED')) = (completed_at IS NOT NULL)),
    CHECK ((lease_token IS NULL) = (lease_expires_at IS NULL))
);
-- One active logical job per owner (stricter than one per conversation, including new chats).
CREATE UNIQUE INDEX edge_bff_one_active_owner ON edge_bff.jobs(owner_key)
    WHERE state IN ('QUEUED','RUNNING','RECOVERING');
CREATE INDEX edge_bff_claim ON edge_bff.jobs(created_at)
    WHERE state IN ('QUEUED','RUNNING','RECOVERING');
CREATE TABLE edge_bff.conversation_ui (
    owner_key text NOT NULL,
    conversation_id text NOT NULL CHECK (conversation_id ~ '^conv_[0-9a-f]{32}$'),
    title text NOT NULL CHECK (length(title) BETWEEN 1 AND 200),
    bookmarked boolean NOT NULL DEFAULT false,
    pinned_request_ids text[] NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (owner_key, conversation_id),
    CHECK (cardinality(pinned_request_ids) <= 500)
);
COMMENT ON SCHEMA edge_bff IS 'EDGE sessions, delivery jobs and UI metadata only; Orc owns canonical history/results.';
COMMENT ON COLUMN edge_bff.jobs.input IS 'Original supported execution inputs, needed for dispatch/idempotency; never the response.';
COMMENT ON COLUMN edge_bff.jobs.state_version IS 'Monotonic snapshot version for SSE reconnect; no durable event log.';
COMMENT ON COLUMN edge_bff.conversation_ui.pinned_request_ids IS 'Response turn identities; does not extend canonical retention.';
REVOKE ALL ON ALL TABLES IN SCHEMA edge_bff FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA edge_bff TO edge_bff_runtime;
COMMIT;
