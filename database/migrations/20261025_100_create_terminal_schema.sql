-- EXEC-TERMINAL-API (user 2026-10-25: "Ok" on DESIGN.md section 5, steps 1-6).
-- Dedicated schema for the subscriber terminal API: subscribers, sessions, quotas and the access audit.
-- Two NOLOGIN groups: terminal_runtime (this schema) and terminal_market_reader (SELECT on the four market tables the
-- terminal serves). Logins are created by scripts/provision_terminal_logins.py, never with a password here.
-- No market table, AI object or existing grant is changed. Rollback: 20261025_001 rollback block at the end (comment).
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';
DO $preflight$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'terminal') OR
       EXISTS (SELECT 1 FROM pg_roles WHERE rolname IN ('terminal_runtime', 'terminal_market_reader')) THEN
        RAISE EXCEPTION 'terminal schema/roles exist: reconcile before applying';
    END IF;
END $preflight$;

CREATE ROLE terminal_runtime NOLOGIN;
CREATE ROLE terminal_market_reader NOLOGIN;
CREATE SCHEMA terminal;
REVOKE ALL ON SCHEMA terminal FROM PUBLIC;
GRANT USAGE ON SCHEMA terminal TO terminal_runtime;

CREATE TABLE terminal.subscriber (
    subscriber_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email text NOT NULL UNIQUE CHECK (email = lower(btrim(email)) AND email ~ '^[^@\s]+@[^@\s]+\.[^@\s]+$'),
    display_name text NOT NULL CHECK (length(btrim(display_name)) BETWEEN 1 AND 120),
    password_hash text NOT NULL CHECK (password_hash ~ '^scrypt\$[0-9a-f]{32}\$[0-9a-f]{64}$'),
    active boolean NOT NULL DEFAULT true,
    expires_at timestamptz NOT NULL,
    disabled_reason text CHECK (disabled_reason IS NULL OR length(disabled_reason) <= 500),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE terminal.session (
    token_hash text PRIMARY KEY CHECK (token_hash ~ '^[0-9a-f]{64}$'),
    subscriber_id bigint NOT NULL REFERENCES terminal.subscriber(subscriber_id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    ip inet,
    CHECK (expires_at > created_at)
);
CREATE INDEX terminal_session_subscriber ON terminal.session(subscriber_id, created_at DESC);

-- Every presigned URL and every fallback query; the quotas are computed from this table.
CREATE TABLE terminal.access_log (
    access_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    subscriber_id bigint NOT NULL REFERENCES terminal.subscriber(subscriber_id) ON DELETE CASCADE,
    at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    kind text NOT NULL CHECK (kind IN ('file', 'history_price', 'history_broker')),
    ticker text NOT NULL CHECK (ticker ~ '^[A-Z0-9]{1,12}$'),
    dataset text,
    year integer,
    object_key text,
    bytes bigint NOT NULL DEFAULT 0 CHECK (bytes >= 0),
    ip inet
);
CREATE INDEX terminal_access_log_subscriber_at ON terminal.access_log(subscriber_id, at DESC);

CREATE TABLE terminal.sign_in_attempt (
    attempt_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email text NOT NULL,
    ip inet,
    ok boolean NOT NULL,
    at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX terminal_sign_in_attempt_email_at ON terminal.sign_in_attempt(email, at DESC);
CREATE INDEX terminal_sign_in_attempt_ip_at ON terminal.sign_in_attempt(ip, at DESC);

-- Named limits; the user may change a value (UPDATE) without a code change.
CREATE TABLE terminal.quota (
    name text PRIMARY KEY CHECK (name ~ '^[a-z0-9_]+$'),
    value integer NOT NULL CHECK (value > 0),
    unit text NOT NULL,
    means text NOT NULL
);
INSERT INTO terminal.quota(name, value, unit, means) VALUES
    ('url_ttl_seconds', 120, 'seconds', 'Lifetime of one presigned file URL'),
    ('files_per_hour', 60, 'files', 'Presigned file URLs one subscriber may receive in a rolling hour'),
    ('tickers_per_hour', 30, 'tickers', 'Distinct tickers one subscriber may open in a rolling hour'),
    ('tickers_per_day', 150, 'tickers', 'Distinct tickers one subscriber may open in a rolling 24 hours'),
    ('megabytes_per_day', 300, 'MB', 'Bytes of files and fallback rows one subscriber may receive in a rolling 24 hours'),
    ('history_per_hour', 20, 'requests', 'Fallback PostgreSQL queries one subscriber may run in a rolling hour'),
    ('sessions_per_subscriber', 2, 'sessions', 'Active sign-ins per subscriber; the oldest is revoked beyond this'),
    ('session_hours', 24, 'hours', 'Lifetime of one sign-in'),
    ('failed_sign_ins_per_email', 10, 'attempts', 'Failed sign-ins per email in 15 minutes before refusal'),
    ('failed_sign_ins_per_ip', 30, 'attempts', 'Failed sign-ins per IP in 15 minutes before refusal');

CREATE TABLE terminal.quota_override (
    subscriber_id bigint NOT NULL REFERENCES terminal.subscriber(subscriber_id) ON DELETE CASCADE,
    name text NOT NULL REFERENCES terminal.quota(name),
    value integer NOT NULL CHECK (value > 0),
    PRIMARY KEY (subscriber_id, name)
);

-- Admin actions through the API (add, disable, extend, reset password).
CREATE TABLE terminal.admin_log (
    admin_log_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    action text NOT NULL,
    subscriber_id bigint,
    detail jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(detail) = 'object'),
    ip inet
);

COMMENT ON SCHEMA terminal IS 'Subscriber terminal API: subscribers, sessions, quotas and access audit only; market data stays in public.';
COMMENT ON TABLE terminal.access_log IS 'One row per presigned URL issued or fallback query run; quotas are computed from it.';
COMMENT ON TABLE terminal.quota IS 'Named per-subscriber limits; terminal.quota_override sets one subscriber''s value.';

REVOKE ALL ON ALL TABLES IN SCHEMA terminal FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA terminal TO terminal_runtime;

GRANT USAGE ON SCHEMA public TO terminal_market_reader;
GRANT SELECT ON public."Price_Stock_Indonesia_IDX",
                public."Feature_05_Foreign_Domestic_Broker_Detail",
                public."IDX_Broker_Profile",
                public."IDX_Stock_Universe"
    TO terminal_market_reader;
COMMIT;

-- Rollback (a new forward migration with this body):
-- BEGIN;
-- REVOKE ALL ON public."Price_Stock_Indonesia_IDX", public."Feature_05_Foreign_Domestic_Broker_Detail",
--     public."IDX_Broker_Profile", public."IDX_Stock_Universe" FROM terminal_market_reader;
-- REVOKE USAGE ON SCHEMA public FROM terminal_market_reader;
-- DROP SCHEMA terminal CASCADE;
-- DROP ROLE terminal_api_login; DROP ROLE terminal_publisher_login;
-- DROP ROLE terminal_runtime; DROP ROLE terminal_market_reader;
-- COMMIT;
