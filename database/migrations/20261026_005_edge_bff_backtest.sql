-- EDGE backtest (user 2026-10-26: steps 1-5 approved; apps/edge-bff/backtest/CONTRACT.md sections 7, 9 and 11): edge-bff's
-- backtest jobs, their stored results and the trials counted per strategy line (K3). Three new tables in the existing
-- operational schema edge_bff, used by edge_bff_runtime only; no market data is stored here (the worker reads it from
-- terminal-api), no existing table, role or grant changes. Forward-only; rollback block at the end (comment).
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';
DO $preflight$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'edge_bff') OR
       NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'edge_bff_runtime') THEN
        RAISE EXCEPTION 'edge_bff schema/role is missing: apply 20261008_002 first';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'edge_bff'
               AND table_name IN ('backtest_jobs', 'backtest_results', 'backtest_trials')) THEN
        RAISE EXCEPTION 'an edge_bff backtest table exists: reconcile before applying';
    END IF;
END $preflight$;

-- One row per submitted backtest. QUEUED -> RUNNING (claimed by edge-bff's loop with a lease, handed to the worker) ->
-- FINISHED | FAILED | CANCELLED. A RUNNING row whose lease expired is never handed to the worker again (FAILED
-- WORKER_LOST): a job is computed at most once.
CREATE TABLE edge_bff.backtest_jobs (
    request_id text PRIMARY KEY CHECK (request_id ~ '^bt_[0-9a-f]{32}$'),
    owner_key text NOT NULL,
    submission_key text NOT NULL CHECK (length(submission_key) BETWEEN 1 AND 100),
    request jsonb NOT NULL CHECK (jsonb_typeof(request) = 'object'),
    lineage_key text NOT NULL CHECK (lineage_key ~ '^[0-9a-f]{64}$'),
    variant_hash text NOT NULL CHECK (variant_hash ~ '^[0-9a-f]{64}$'),
    state text NOT NULL DEFAULT 'QUEUED' CHECK (state IN ('QUEUED','RUNNING','FINISHED','FAILED','CANCELLED')),
    cancel_requested boolean NOT NULL DEFAULT false,
    progress jsonb CHECK (progress IS NULL OR jsonb_typeof(progress) = 'object'),
    lease_token text,
    lease_expires_at timestamptz,
    error jsonb CHECK (error IS NULL OR (jsonb_typeof(error) = 'object' AND jsonb_typeof(error->'code') = 'string')),
    engine_version text CHECK (length(engine_version) BETWEEN 1 AND 200),
    registry_version text CHECK (length(registry_version) BETWEEN 1 AND 200),
    data_version text CHECK (data_version ~ '^[0-9a-f]{64}$'),
    result_bytes bigint CHECK (result_bytes >= 0),
    duration_ms bigint CHECK (duration_ms >= 0),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at timestamptz,
    finished_at timestamptz,
    UNIQUE (owner_key, submission_key),
    CHECK ((state IN ('FINISHED','FAILED','CANCELLED')) = (finished_at IS NOT NULL)),
    CHECK ((lease_token IS NULL) = (lease_expires_at IS NULL)),
    CHECK ((state = 'RUNNING') = (lease_token IS NOT NULL)),
    CHECK (state NOT IN ('RUNNING','FINISHED','FAILED') OR started_at IS NOT NULL),
    CHECK ((state = 'FAILED') = (error IS NOT NULL)),
    CHECK (state <> 'FINISHED' OR (data_version IS NOT NULL AND result_bytes IS NOT NULL))
);
-- At most one running backtest per owner (the worker computes one job at a time); the queue limit is edge-bff's.
CREATE UNIQUE INDEX backtest_jobs_one_running_owner ON edge_bff.backtest_jobs(owner_key) WHERE state = 'RUNNING';
CREATE INDEX backtest_jobs_claim ON edge_bff.backtest_jobs(created_at) WHERE state IN ('QUEUED','RUNNING');
CREATE INDEX backtest_jobs_owner_created ON edge_bff.backtest_jobs(owner_key, created_at DESC);

-- The worker's result split on ingest (CONTRACT.md section 9): part 'core' (everything except events.conditions and
-- events.exits) and one part 'events:<ticker>' ({conditions, exits} of that ticker). Gzip JSON; kept 30 days.
CREATE TABLE edge_bff.backtest_results (
    request_id text NOT NULL REFERENCES edge_bff.backtest_jobs(request_id) ON DELETE CASCADE,
    part text NOT NULL CHECK (part = 'core' OR part ~ '^events:[A-Z0-9]{1,12}$'),
    payload bytea NOT NULL,
    bytes bigint NOT NULL CHECK (bytes = octet_length(payload)),
    sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (request_id, part)
);
CREATE INDEX backtest_results_created ON edge_bff.backtest_results(created_at);

-- Trials per owner and strategy line (K3): every distinct variant a finished run evaluated (the run itself and its
-- sensitivity cells) with its daily Sharpe; passed to the worker as prior_trials for the next run of the same line.
-- Never reset; the first recorded Sharpe of a variant is kept. request_id names the run that recorded it (no foreign
-- key: trials outlive their job rows).
CREATE TABLE edge_bff.backtest_trials (
    owner_key text NOT NULL,
    lineage_key text NOT NULL CHECK (lineage_key ~ '^[0-9a-f]{64}$'),
    variant_hash text NOT NULL CHECK (variant_hash ~ '^[0-9a-f]{64}$'),
    sharpe_daily double precision NOT NULL CHECK (sharpe_daily > '-Infinity'::double precision
                                                  AND sharpe_daily < 'Infinity'::double precision),
    kind text NOT NULL CHECK (kind IN ('run','sensitivity')),
    request_id text NOT NULL CHECK (request_id ~ '^bt_[0-9a-f]{32}$'),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (owner_key, lineage_key, variant_hash)
);

COMMENT ON TABLE edge_bff.backtest_jobs IS 'EDGE backtest jobs: the request as submitted, state, progress and versions; never market data or the result.';
COMMENT ON COLUMN edge_bff.backtest_jobs.request IS 'The BacktestRequest as the page sent it (contract.ts), without client_request_id; handed to the worker unchanged.';
COMMENT ON COLUMN edge_bff.backtest_jobs.submission_key IS 'client_request_id of the submission (generated when absent): the same key returns the same job.';
COMMENT ON COLUMN edge_bff.backtest_jobs.error IS 'ApiError.error of a FAILED job: the worker''s error, or WORKER_LOST / TIMEOUT / RESULT_INVALID set by edge-bff.';
COMMENT ON COLUMN edge_bff.backtest_jobs.result_bytes IS 'Sum of the stored gzip parts (edge_bff.backtest_results.bytes) of a FINISHED job.';
COMMENT ON COLUMN edge_bff.backtest_jobs.duration_ms IS 'The worker''s own compute time (result meta.duration_ms, or its job status).';
COMMENT ON TABLE edge_bff.backtest_results IS 'Gzip JSON parts of a finished backtest result per (request_id, part); deleted after 30 days.';
COMMENT ON TABLE edge_bff.backtest_trials IS 'K3 trial count: distinct variants per owner and lineage with their daily Sharpe; never reset.';

REVOKE ALL ON edge_bff.backtest_jobs, edge_bff.backtest_results, edge_bff.backtest_trials FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE, DELETE ON edge_bff.backtest_jobs, edge_bff.backtest_results, edge_bff.backtest_trials
    TO edge_bff_runtime;
DO $verify$
BEGIN
    IF NOT (has_table_privilege('edge_bff_runtime', 'edge_bff.backtest_jobs', 'SELECT, INSERT, UPDATE, DELETE')
            AND has_table_privilege('edge_bff_runtime', 'edge_bff.backtest_results', 'SELECT, INSERT, UPDATE, DELETE')
            AND has_table_privilege('edge_bff_runtime', 'edge_bff.backtest_trials', 'SELECT, INSERT, UPDATE, DELETE')) THEN
        RAISE EXCEPTION 'edge_bff_runtime cannot use the backtest tables';
    END IF;
    IF has_table_privilege('public', 'edge_bff.backtest_jobs', 'SELECT') THEN
        RAISE EXCEPTION 'PUBLIC can read edge_bff.backtest_jobs';
    END IF;
END $verify$;
COMMIT;

-- Rollback (a new forward migration with this body; it deletes every backtest job, result and recorded trial):
-- BEGIN;
-- DROP TABLE edge_bff.backtest_results;
-- DROP TABLE edge_bff.backtest_trials;
-- DROP TABLE edge_bff.backtest_jobs;
-- COMMIT;
