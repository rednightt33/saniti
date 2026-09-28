-- Audit store for AI research runs (implementation plan IP2, solution 2; service apps/market-audit-store).
--
-- A dedicated schema ai_audit keeps the audit apart from the public AI_* tables. It is queried only through the
-- market-audit-store API: the SQL Governor and catalog readers, the sandbox and the model have no access.
--   run              one AI research run: stable run_id, unique request_id, conversation/turn, parent run, status
--                    (OPEN -> FINALIZING -> COMPLETE, or INCOMPLETE and retryable), retention class and expiry
--   event            ordered, append-only observable events of a run (tool calls, archival steps); bounded payloads,
--                    large content stored as an artifact and referenced
--   artifact         one content-addressed object (sha256 + byte count) in the private audit bucket, with its state
--                    (PENDING -> READY after server-side verification, REJECTED, DELETED); stored once, shared by runs
--   run_artifact     which run uses which artifact in which role (input Parquet, code, output, manifests, ...)
--   execution        one sandbox code execution: session, source hash, runtime image, library evidence, seed, timezone
--   runtime_image    one runtime inventory (Python, OS, architecture, installed distributions), keyed by fingerprint
--   artifact_access  who was granted a short-lived read of which artifact, when and why (append-only)
--   retention_hold   a pin or legal hold on a run or artifact; while active nothing it covers may be deleted
--   ingest_outbox    durable hand-off from market-ai-orc: the orchestrator may only INSERT a finished run here; the
--                    audit store consumes it idempotently and records the outcome
-- Hidden model reasoning is never stored: no table has a column for it, and producers never send it.
-- AI_research_run_audit stays unchanged as the summary and recovery fallback. No public table, row or grant changes.
-- Table_Catalog documents public tables only (constraint Table_Catalog_target_schema_check), so these tables are
-- documented in apps/market-audit-store/README.md, not in Table_Catalog.
-- Roles (NOLOGIN; logins are created by scripts/provision_market_ai_audit_login.py and
-- scripts/provision_market_ai_orc_login.py):
--   market_ai_audit_store          SELECT, INSERT, UPDATE on the tables (INSERT and SELECT only on event and
--                                  artifact_access); no DELETE or TRUNCATE anywhere
--   market_ai_audit_outbox_writer  INSERT of (source, idempotency_key, request_id, kind, payload) into ingest_outbox
--                                  only; it cannot read, update or delete
-- Forward-only and additive.
BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';

DO $preflight$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'ai_audit') THEN
        RAISE EXCEPTION 'Schema ai_audit already exists: inspect before applying';
    END IF;
END
$preflight$;

CREATE SCHEMA ai_audit;
COMMENT ON SCHEMA ai_audit IS
    'Audit of AI research runs (market-audit-store): runs, ordered events, content-addressed artifacts, executions, runtime inventories, access log, retention holds and the market-ai-orc ingest outbox.';
REVOKE ALL ON SCHEMA ai_audit FROM PUBLIC;

CREATE FUNCTION ai_audit.reject_change() RETURNS trigger
LANGUAGE plpgsql AS $function$
BEGIN
    RAISE EXCEPTION 'ai_audit.% is append-only', TG_TABLE_NAME USING ERRCODE = 'insufficient_privilege';
END
$function$;
REVOKE ALL ON FUNCTION ai_audit.reject_change() FROM PUBLIC;

CREATE TABLE ai_audit.runtime_image (
    runtime_image_id text PRIMARY KEY,
    python_version text NOT NULL,
    python_implementation text NOT NULL,
    os text NOT NULL,
    arch text NOT NULL,
    requirements_sha256 text,
    distributions jsonb NOT NULL,
    distribution_count integer NOT NULL,
    recorded_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT runtime_image_id_check CHECK (runtime_image_id ~ '^rt_[0-9a-f]{64}$'),
    CONSTRAINT runtime_image_requirements_check CHECK (requirements_sha256 IS NULL
                                                       OR requirements_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT runtime_image_distributions_check CHECK (jsonb_typeof(distributions) = 'array'
                                                        AND jsonb_array_length(distributions) = distribution_count),
    CONSTRAINT runtime_image_text_check CHECK (length(python_version) BETWEEN 1 AND 64 AND length(os) BETWEEN 1 AND 200
                                               AND length(arch) BETWEEN 1 AND 64
                                               AND length(python_implementation) BETWEEN 1 AND 64)
);
COMMENT ON TABLE ai_audit.runtime_image IS
    'One sandbox runtime inventory (Python, OS, architecture, installed distributions from importlib.metadata), keyed by the sha256 fingerprint of its canonical JSON.';

CREATE TABLE ai_audit.run (
    run_id text PRIMARY KEY,
    request_id text NOT NULL,
    conversation_id text,
    turn_index integer,
    parent_run_id text REFERENCES ai_audit.run (run_id),
    status text NOT NULL DEFAULT 'OPEN',
    retention_class text NOT NULL DEFAULT 'STANDARD',
    expires_at timestamp with time zone NOT NULL,
    model text,
    provider text,
    deployment jsonb NOT NULL DEFAULT '{}'::jsonb,
    summary jsonb NOT NULL DEFAULT '{}'::jsonb,
    expected jsonb,
    missing jsonb,
    next_event_seq bigint NOT NULL DEFAULT 1,
    created_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finalized_at timestamp with time zone,
    CONSTRAINT run_request_key UNIQUE (request_id),
    CONSTRAINT run_id_check CHECK (run_id ~ '^run_[0-9a-f]{32}$'),
    CONSTRAINT run_request_id_check CHECK (request_id ~ '^[A-Za-z0-9._:-]{1,200}$'),
    CONSTRAINT run_conversation_id_check CHECK (conversation_id IS NULL
                                                OR conversation_id ~ '^[A-Za-z0-9._:-]{1,200}$'),
    CONSTRAINT run_turn_index_check CHECK (turn_index IS NULL OR turn_index >= 0),
    CONSTRAINT run_parent_check CHECK (parent_run_id IS NULL OR parent_run_id <> run_id),
    CONSTRAINT run_status_check CHECK (status IN ('OPEN', 'FINALIZING', 'COMPLETE', 'INCOMPLETE')),
    CONSTRAINT run_retention_class_check CHECK (retention_class IN ('STANDARD', 'PINNED')),
    CONSTRAINT run_expiry_check CHECK (expires_at > created_at),
    CONSTRAINT run_json_check CHECK (jsonb_typeof(deployment) = 'object' AND jsonb_typeof(summary) = 'object'
                                     AND (expected IS NULL OR jsonb_typeof(expected) = 'object')
                                     AND (missing IS NULL OR jsonb_typeof(missing) = 'object')),
    CONSTRAINT run_sequence_check CHECK (next_event_seq >= 1),
    CONSTRAINT run_finalized_check CHECK ((status IN ('COMPLETE', 'INCOMPLETE')) = (finalized_at IS NOT NULL)),
    CONSTRAINT run_timestamp_check CHECK (updated_at >= created_at)
);
CREATE INDEX run_conversation_idx ON ai_audit.run (conversation_id, created_at) WHERE conversation_id IS NOT NULL;
CREATE INDEX run_expiry_idx ON ai_audit.run (expires_at);
CREATE INDEX run_open_idx ON ai_audit.run (status, updated_at) WHERE status IN ('OPEN', 'FINALIZING', 'INCOMPLETE');
COMMENT ON TABLE ai_audit.run IS
    'One AI research run (one market-ai-orc request_id): identity, conversation and turn, parent run of a rerun, status OPEN -> FINALIZING -> COMPLETE or INCOMPLETE (retryable), retention class and expiry, model/provider, deployment and summary.';

CREATE TABLE ai_audit.artifact (
    artifact_id text PRIMARY KEY,
    sha256 text NOT NULL,
    size_bytes bigint NOT NULL,
    media_type text NOT NULL,
    state text NOT NULL DEFAULT 'PENDING',
    object_key text NOT NULL,
    first_source text NOT NULL,
    created_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    staging_key text,
    upload_expires_at timestamp with time zone,
    verify_attempts integer NOT NULL DEFAULT 0,
    verified_at timestamp with time zone,
    rejected_reason text,
    deleted_at timestamp with time zone,
    CONSTRAINT artifact_sha256_key UNIQUE (sha256),
    CONSTRAINT artifact_object_key_key UNIQUE (object_key),
    CONSTRAINT artifact_id_check CHECK (artifact_id ~ '^art_[0-9a-f]{32}$'),
    CONSTRAINT artifact_sha256_check CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT artifact_size_check CHECK (size_bytes >= 0),
    CONSTRAINT artifact_media_type_check CHECK (media_type ~ '^[a-z0-9.+-]+/[a-z0-9.+-]+$'),
    CONSTRAINT artifact_state_check CHECK (state IN ('PENDING', 'READY', 'REJECTED', 'DELETED')),
    CONSTRAINT artifact_object_key_check CHECK (object_key = 'objects/sha256/' || substr(sha256, 1, 2) || '/' || sha256),
    CONSTRAINT artifact_source_check CHECK (first_source IN ('market-ai-orc', 'market-sql-governor',
                                                             'market-python-sandbox', 'market-audit-store')),
    CONSTRAINT artifact_verified_check CHECK ((state = 'READY') <= (verified_at IS NOT NULL)),
    CONSTRAINT artifact_deleted_check CHECK ((state = 'DELETED') = (deleted_at IS NOT NULL)),
    CONSTRAINT artifact_rejected_check CHECK ((state = 'REJECTED') <= (rejected_reason IS NOT NULL)),
    CONSTRAINT artifact_attempts_check CHECK (verify_attempts >= 0),
    CONSTRAINT artifact_staging_check CHECK (staging_key IS NULL
                                             OR staging_key ~ ('^staging/' || artifact_id || '/[0-9a-f]{32}$'))
);
CREATE INDEX artifact_state_idx ON ai_audit.artifact (state, created_at);
COMMENT ON TABLE ai_audit.artifact IS
    'One content-addressed object of the private audit bucket (objects/sha256/<first two>/<sha256>): stored once and shared by every run that references it. A producer uploads to a one-off staging key; READY only after the audit store verified size and sha256 itself and copied the bytes to the content address.';

CREATE TABLE ai_audit.run_artifact (
    run_artifact_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id text NOT NULL REFERENCES ai_audit.run (run_id),
    artifact_id text NOT NULL REFERENCES ai_audit.artifact (artifact_id),
    role text NOT NULL,
    source text NOT NULL,
    execution_id text,
    label text,
    linked_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT run_artifact_role_check CHECK (role IN (
        'RAW_INPUT_PARQUET', 'EXTRACTION_MANIFEST', 'INPUT_BUNDLE_MANIFEST', 'APPROVED_DATANEED_CONTRACT',
        'PYTHON_SOURCE', 'TOOL_TRACE', 'EXECUTION_TRACE', 'OUTPUT', 'EXECUTION_MANIFEST', 'RUNTIME_MANIFEST',
        'FINAL_RESPONSE', 'VALIDATION_RESULT', 'ERROR_DETAIL')),
    CONSTRAINT run_artifact_source_check CHECK (source IN ('market-ai-orc', 'market-sql-governor',
                                                           'market-python-sandbox', 'market-audit-store')),
    CONSTRAINT run_artifact_execution_check CHECK (execution_id IS NULL OR execution_id ~ '^exe_[0-9a-f]{24}$'),
    CONSTRAINT run_artifact_label_check CHECK (label IS NULL OR length(label) BETWEEN 1 AND 200)
);
CREATE UNIQUE INDEX run_artifact_link_key
    ON ai_audit.run_artifact (run_id, artifact_id, role, COALESCE(execution_id, ''), COALESCE(label, ''));
CREATE INDEX run_artifact_artifact_idx ON ai_audit.run_artifact (artifact_id);
CREATE INDEX run_artifact_execution_idx ON ai_audit.run_artifact (execution_id) WHERE execution_id IS NOT NULL;
COMMENT ON TABLE ai_audit.run_artifact IS
    'Which run references which artifact, in which role (raw input Parquet, manifests, contract, code, traces, outputs, final response), for which execution and label.';

CREATE TABLE ai_audit.event (
    run_id text NOT NULL REFERENCES ai_audit.run (run_id),
    seq bigint NOT NULL,
    source text NOT NULL,
    idempotency_key text NOT NULL,
    event_type text NOT NULL,
    occurred_at timestamp with time zone NOT NULL,
    recorded_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    execution_id text,
    artifact_id text REFERENCES ai_audit.artifact (artifact_id),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (run_id, seq),
    CONSTRAINT event_idempotency_key UNIQUE (run_id, source, idempotency_key),
    CONSTRAINT event_seq_check CHECK (seq >= 1),
    CONSTRAINT event_source_check CHECK (source IN ('market-ai-orc', 'market-sql-governor', 'market-python-sandbox',
                                                    'market-audit-store')),
    CONSTRAINT event_key_check CHECK (length(idempotency_key) BETWEEN 1 AND 200),
    CONSTRAINT event_type_check CHECK (event_type ~ '^[a-z][a-z0-9_.]{1,63}$'),
    CONSTRAINT event_execution_check CHECK (execution_id IS NULL OR execution_id ~ '^exe_[0-9a-f]{24}$'),
    CONSTRAINT event_payload_check CHECK (jsonb_typeof(payload) = 'object' AND octet_length(payload::text) <= 16384)
);
CREATE INDEX event_execution_idx ON ai_audit.event (execution_id) WHERE execution_id IS NOT NULL;
CREATE TRIGGER event_append_only BEFORE UPDATE OR DELETE ON ai_audit.event
    FOR EACH ROW EXECUTE FUNCTION ai_audit.reject_change();
COMMENT ON TABLE ai_audit.event IS
    'Ordered, append-only observable events of a run (seq from 1 per run); a payload is bounded to 16 KiB, larger content is stored as an artifact and referenced by artifact_id.';

CREATE TABLE ai_audit.execution (
    execution_id text PRIMARY KEY,
    run_id text NOT NULL REFERENCES ai_audit.run (run_id),
    session_id text NOT NULL,
    bundle_id text,
    seq integer NOT NULL,
    status text NOT NULL,
    source_sha256 text,
    runtime_image_id text REFERENCES ai_audit.runtime_image (runtime_image_id),
    git_commit text,
    deployment_id text,
    random_seed bigint,
    timezone text,
    declared_imports jsonb NOT NULL DEFAULT '[]'::jsonb,
    loaded_distributions jsonb NOT NULL DEFAULT '[]'::jsonb,
    prebound_packages jsonb NOT NULL DEFAULT '[]'::jsonb,
    stdlib_modules jsonb NOT NULL DEFAULT '[]'::jsonb,
    unresolved_modules jsonb NOT NULL DEFAULT '[]'::jsonb,
    input_checksums jsonb NOT NULL DEFAULT '[]'::jsonb,
    contract_sha256 text,
    resample jsonb NOT NULL DEFAULT '[]'::jsonb,
    resource_usage jsonb NOT NULL DEFAULT '{}'::jsonb,
    started_at timestamp with time zone,
    finished_at timestamp with time zone,
    recorded_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT execution_id_check CHECK (execution_id ~ '^exe_[0-9a-f]{24}$'),
    CONSTRAINT execution_session_check CHECK (session_id ~ '^sess_[0-9a-f]{24}$'),
    CONSTRAINT execution_seq_check CHECK (seq >= 1),
    CONSTRAINT execution_status_check CHECK (length(status) BETWEEN 1 AND 64),
    CONSTRAINT execution_hash_check CHECK ((source_sha256 IS NULL OR source_sha256 ~ '^[0-9a-f]{64}$')
                                           AND (contract_sha256 IS NULL OR contract_sha256 ~ '^[0-9a-f]{64}$')),
    CONSTRAINT execution_json_check CHECK (
        jsonb_typeof(declared_imports) = 'array' AND jsonb_typeof(loaded_distributions) = 'array'
        AND jsonb_typeof(prebound_packages) = 'array' AND jsonb_typeof(stdlib_modules) = 'array'
        AND jsonb_typeof(unresolved_modules) = 'array' AND jsonb_typeof(input_checksums) = 'array'
        AND jsonb_typeof(resample) = 'array' AND jsonb_typeof(resource_usage) = 'object')
);
CREATE INDEX execution_run_idx ON ai_audit.execution (run_id, session_id, seq);
CREATE INDEX execution_source_idx ON ai_audit.execution (source_sha256) WHERE source_sha256 IS NOT NULL;
CREATE INDEX execution_runtime_idx ON ai_audit.execution (runtime_image_id) WHERE runtime_image_id IS NOT NULL;
COMMENT ON TABLE ai_audit.execution IS
    'One sandbox code execution: run, session, bundle, sequence, status, exact-source hash, runtime image, library evidence (declared imports, loaded distributions, prebound packages, standard-library and unresolved modules), seed, timezone, input order and resample traces.';

CREATE TABLE ai_audit.artifact_access (
    access_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    artifact_id text NOT NULL REFERENCES ai_audit.artifact (artifact_id),
    run_id text REFERENCES ai_audit.run (run_id),
    accessor text NOT NULL,
    purpose text NOT NULL,
    granted_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    url_expires_at timestamp with time zone NOT NULL,
    CONSTRAINT artifact_access_accessor_check CHECK (accessor ~ '^[A-Za-z0-9._:@-]{1,128}$'),
    CONSTRAINT artifact_access_purpose_check CHECK (length(btrim(purpose)) BETWEEN 3 AND 500),
    CONSTRAINT artifact_access_expiry_check CHECK (url_expires_at > granted_at)
);
CREATE INDEX artifact_access_artifact_idx ON ai_audit.artifact_access (artifact_id, granted_at);
CREATE TRIGGER artifact_access_append_only BEFORE UPDATE OR DELETE ON ai_audit.artifact_access
    FOR EACH ROW EXECUTE FUNCTION ai_audit.reject_change();
COMMENT ON TABLE ai_audit.artifact_access IS
    'Append-only log of every short-lived read granted on an artifact: who, why, for which run, and when the URL expires.';

CREATE TABLE ai_audit.retention_hold (
    hold_id text PRIMARY KEY,
    run_id text REFERENCES ai_audit.run (run_id),
    artifact_id text REFERENCES ai_audit.artifact (artifact_id),
    reason text NOT NULL,
    created_by text NOT NULL,
    created_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    released_at timestamp with time zone,
    released_by text,
    CONSTRAINT retention_hold_id_check CHECK (hold_id ~ '^hold_[0-9a-f]{32}$'),
    CONSTRAINT retention_hold_target_check CHECK (num_nonnulls(run_id, artifact_id) = 1),
    CONSTRAINT retention_hold_reason_check CHECK (length(btrim(reason)) BETWEEN 3 AND 500),
    CONSTRAINT retention_hold_actor_check CHECK (created_by ~ '^[A-Za-z0-9._:@-]{1,128}$'
                                                 AND (released_by IS NULL OR released_by ~ '^[A-Za-z0-9._:@-]{1,128}$')),
    CONSTRAINT retention_hold_release_check CHECK ((released_at IS NULL) = (released_by IS NULL)
                                                   AND (released_at IS NULL OR released_at >= created_at))
);
CREATE INDEX retention_hold_run_idx ON ai_audit.retention_hold (run_id) WHERE released_at IS NULL;
CREATE INDEX retention_hold_artifact_idx ON ai_audit.retention_hold (artifact_id) WHERE released_at IS NULL;
COMMENT ON TABLE ai_audit.retention_hold IS
    'A pin or legal hold on one run or one artifact; while released_at is NULL, nothing it covers may be deleted.';

CREATE TABLE ai_audit.ingest_outbox (
    outbox_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source text NOT NULL,
    idempotency_key text NOT NULL,
    request_id text NOT NULL,
    kind text NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status text NOT NULL DEFAULT 'PENDING',
    attempts integer NOT NULL DEFAULT 0,
    next_attempt_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_error text,
    processed_at timestamp with time zone,
    CONSTRAINT ingest_outbox_key UNIQUE (source, idempotency_key),
    CONSTRAINT ingest_outbox_source_check CHECK (source IN ('market-ai-orc')),
    CONSTRAINT ingest_outbox_key_check CHECK (length(idempotency_key) BETWEEN 1 AND 200),
    CONSTRAINT ingest_outbox_request_check CHECK (request_id ~ '^[A-Za-z0-9._:-]{1,200}$'),
    CONSTRAINT ingest_outbox_kind_check CHECK (kind IN ('RUN_FINISHED')),
    CONSTRAINT ingest_outbox_payload_check CHECK (jsonb_typeof(payload) = 'object'
                                                  AND octet_length(payload::text) <= 4194304),
    CONSTRAINT ingest_outbox_status_check CHECK (status IN ('PENDING', 'COMPLETE', 'FAILED_RETRYABLE', 'INCOMPLETE')),
    CONSTRAINT ingest_outbox_attempts_check CHECK (attempts >= 0),
    CONSTRAINT ingest_outbox_error_check CHECK (last_error IS NULL OR length(last_error) <= 1000),
    CONSTRAINT ingest_outbox_processed_check CHECK ((status = 'COMPLETE') <= (processed_at IS NOT NULL))
);
CREATE INDEX ingest_outbox_due_idx ON ai_audit.ingest_outbox (next_attempt_at, outbox_id)
    WHERE status IN ('PENDING', 'FAILED_RETRYABLE');
COMMENT ON TABLE ai_audit.ingest_outbox IS
    'Durable hand-off of finished market-ai-orc runs: the orchestrator INSERTs one RUN_FINISHED row per request (idempotent on source + idempotency_key) and never reads or changes it; the audit store consumes due rows and records PENDING, COMPLETE, FAILED_RETRYABLE or INCOMPLETE.';

DO $role$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'market_ai_audit_store') THEN
        CREATE ROLE market_ai_audit_store NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'market_ai_audit_outbox_writer') THEN
        CREATE ROLE market_ai_audit_outbox_writer NOLOGIN;
    END IF;
END
$role$;

REVOKE ALL ON ALL TABLES IN SCHEMA ai_audit FROM PUBLIC;
GRANT USAGE ON SCHEMA ai_audit TO market_ai_audit_store, market_ai_audit_outbox_writer;
GRANT SELECT, INSERT, UPDATE ON ai_audit.run, ai_audit.artifact, ai_audit.run_artifact, ai_audit.execution,
    ai_audit.runtime_image, ai_audit.retention_hold, ai_audit.ingest_outbox TO market_ai_audit_store;
GRANT SELECT, INSERT ON ai_audit.event, ai_audit.artifact_access TO market_ai_audit_store;
GRANT INSERT (source, idempotency_key, request_id, kind, payload) ON ai_audit.ingest_outbox
    TO market_ai_audit_outbox_writer;

DO $verify$
DECLARE
    expected_tables text[] := ARRAY['run', 'event', 'artifact', 'run_artifact', 'execution', 'runtime_image',
                                    'artifact_access', 'retention_hold', 'ingest_outbox'];
BEGIN
    IF (SELECT count(*) FROM pg_tables WHERE schemaname = 'ai_audit' AND tablename = ANY (expected_tables)) <> 9
       OR (SELECT count(*) FROM pg_tables WHERE schemaname = 'ai_audit') <> 9 THEN
        RAISE EXCEPTION 'ai_audit must hold exactly the nine audit tables';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema = 'ai_audit' AND column_name ILIKE '%reasoning%') THEN
        RAISE EXCEPTION 'No ai_audit column may hold model reasoning';
    END IF;
    -- the audit store: no DELETE or TRUNCATE; event and artifact_access are append-only
    IF EXISTS (SELECT 1 FROM pg_class c WHERE c.relnamespace = 'ai_audit'::regnamespace AND c.relkind = 'r'
               AND has_table_privilege('market_ai_audit_store', c.oid, 'DELETE,TRUNCATE'))
       OR has_table_privilege('market_ai_audit_store', 'ai_audit.event', 'UPDATE')
       OR has_table_privilege('market_ai_audit_store', 'ai_audit.artifact_access', 'UPDATE')
       OR NOT has_table_privilege('market_ai_audit_store', 'ai_audit.run', 'SELECT,INSERT,UPDATE') THEN
        RAISE EXCEPTION 'market_ai_audit_store has the wrong privileges';
    END IF;
    -- the outbox writer: INSERT into ingest_outbox only, and only of the producer columns
    IF has_table_privilege('market_ai_audit_outbox_writer', 'ai_audit.ingest_outbox', 'SELECT,UPDATE,DELETE,TRUNCATE')
       OR has_column_privilege('market_ai_audit_outbox_writer', 'ai_audit.ingest_outbox', 'status', 'INSERT')
       OR NOT has_column_privilege('market_ai_audit_outbox_writer', 'ai_audit.ingest_outbox', 'payload', 'INSERT')
       OR EXISTS (SELECT 1 FROM pg_class c WHERE c.relnamespace = 'ai_audit'::regnamespace AND c.relkind = 'r'
                  AND c.relname <> 'ingest_outbox'
                  AND has_table_privilege('market_ai_audit_outbox_writer', c.oid, 'SELECT,INSERT,UPDATE,DELETE')) THEN
        RAISE EXCEPTION 'market_ai_audit_outbox_writer must only INSERT producer columns of ingest_outbox';
    END IF;
    -- no other application role reaches the schema
    IF EXISTS (SELECT 1 FROM pg_roles r
               WHERE r.rolname IN ('market_ai_sql_reader', 'market_ai_catalog_reader', 'market_ai_preview_reader',
                                   'market_ai_conversation_store', 'market_ai_research_audit_writer')
                 AND has_schema_privilege(r.oid, 'ai_audit', 'USAGE')) THEN
        RAISE EXCEPTION 'Governor, catalog, preview and conversation roles must not reach ai_audit';
    END IF;
    IF (SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal
        AND tgname IN ('event_append_only', 'artifact_access_append_only')) <> 2 THEN
        RAISE EXCEPTION 'The append-only triggers are missing';
    END IF;
END
$verify$;

COMMIT;
