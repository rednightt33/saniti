-- EXEC-MU-RUNTIME Phase 1b, T1 (user 2026-10-28: "Saya preferably opsi A ... terminal, backtest, dan screener dibuat
-- sedemikian rupa menurut opsi A"; EXEC.md EXEC-MU-RUNTIME; verification/edge_multiuser/runtime/terminal.md T1):
-- service accounts for backtest-worker and screener-worker, apart from the people's accounts.
-- - terminal.subscriber.kind: 'person' (every existing row, and every row the admin route adds) or 'service'.
-- - Two service rows, backtest-worker@terminal.local and screener-worker@terminal.local: active, expiring 2100-01-01,
--   with no usable password (the all-zero scrypt verifier, which no password derives; terminal-api also refuses a
--   service account at sign-in). terminal-api maps its variable TERMINAL_SERVICE_KEY_<NAME> to the row
--   <name>@terminal.local of kind 'service' (apps/terminal-api/app/config.py).
-- - terminal.usage_hour: a service account's grants, files and bytes per clock hour (UTC), the counter its ceilings
--   are checked against (one UPSERT inside each grant's transaction; apps/terminal-api/app/store.py meter).
-- - terminal.quota rows service_grants_per_hour, service_files_per_hour and service_megabytes_per_hour: the ceilings, a
--   runaway guard per service account (its own value: terminal.quota_override). TEMPORARY values, about 2-6 times
--   the INFERENCE peak at 200 users (terminal.md section 7), until Phase 0 measures the services.
-- Operational schema terminal: no Table/Column_Catalog row (as 20261025_100 and 20261026_100; the catalogs cover public
-- data tables, DATABASE_CATALOG.md). No market table, role, login or existing grant changes; existing rows keep their
-- values. Idempotent: applied again it changes nothing (IF NOT EXISTS, ON CONFLICT DO NOTHING; a value the
-- administrator changed is kept) and verifies again. scripts/provision_terminal_logins.py lists terminal.usage_hour in
-- the relations terminal_api_login reaches. Rollback block at the end (comment).
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';
DO $preflight$
DECLARE
    taken boolean;
BEGIN
    IF to_regclass('terminal.subscriber') IS NULL OR to_regclass('terminal.quota') IS NULL
       OR NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'terminal_runtime') THEN
        RAISE EXCEPTION 'terminal schema or terminal_runtime is missing: apply 20261025_100 first';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'terminal'
                   AND table_name = 'access_log' AND column_name = 'file_count') THEN
        RAISE EXCEPTION 'terminal.access_log.file_count is missing: apply 20261026_100 first';
    END IF;
    -- a person already holding a service account's address would be booked as that service: reconcile first
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'terminal'
                   AND table_name = 'subscriber' AND column_name = 'kind') THEN
        IF EXISTS (SELECT 1 FROM terminal.subscriber
                   WHERE email IN ('backtest-worker@terminal.local', 'screener-worker@terminal.local')) THEN
            RAISE EXCEPTION 'a subscriber already uses a service account address: reconcile before applying';
        END IF;
    ELSE
        EXECUTE $q$SELECT EXISTS (SELECT 1 FROM terminal.subscriber WHERE email IN ('backtest-worker@terminal.local',
                   'screener-worker@terminal.local') AND kind <> 'service')$q$ INTO taken;
        IF taken THEN
            RAISE EXCEPTION 'a person uses a service account address: reconcile before applying';
        END IF;
    END IF;
END $preflight$;

ALTER TABLE terminal.subscriber
    ADD COLUMN IF NOT EXISTS kind text NOT NULL DEFAULT 'person'
        CONSTRAINT subscriber_kind_check CHECK (kind IN ('person', 'service'));

CREATE TABLE IF NOT EXISTS terminal.usage_hour (
    subscriber_id bigint NOT NULL REFERENCES terminal.subscriber(subscriber_id) ON DELETE CASCADE,
    hour_start timestamptz NOT NULL CONSTRAINT usage_hour_whole_hour CHECK (hour_start = date_trunc('hour', hour_start, 'UTC')),
    grants integer NOT NULL DEFAULT 0 CHECK (grants >= 0),
    files bigint NOT NULL DEFAULT 0 CHECK (files >= 0),
    bytes bigint NOT NULL DEFAULT 0 CHECK (bytes >= 0),
    PRIMARY KEY (subscriber_id, hour_start)
);

INSERT INTO terminal.subscriber (email, display_name, password_hash, expires_at, kind) VALUES
    ('backtest-worker@terminal.local', 'Backtest worker (service account)',
     'scrypt$' || repeat('0', 32) || '$' || repeat('0', 64), '2100-01-01T00:00:00Z', 'service'),
    ('screener-worker@terminal.local', 'Screener worker (service account)',
     'scrypt$' || repeat('0', 32) || '$' || repeat('0', 64), '2100-01-01T00:00:00Z', 'service')
ON CONFLICT (email) DO NOTHING;

INSERT INTO terminal.quota (name, value, unit, means) VALUES
    ('service_grants_per_hour', 20000, 'grants',
     'Grants (one /bundle, /files, /xsection or /reference answer) one service account may receive in a clock hour (UTC); a runaway guard for a worker, not a person''s quota'),
    ('service_files_per_hour', 100000, 'files',
     'Files one service account may be granted in a clock hour (UTC); a runaway guard for a worker'),
    ('service_megabytes_per_hour', 100000, 'MB',
     'Megabytes of files one service account may be granted in a clock hour (UTC); a runaway guard for a worker')
ON CONFLICT (name) DO NOTHING;

COMMENT ON COLUMN terminal.subscriber.kind IS
    'person: a subscriber or the EDGE gateway account (rolling quotas from terminal.access_log); service: a worker''s own account, reached only with its TERMINAL_SERVICE_KEY_<NAME>, never signed into, counted per clock hour in terminal.usage_hour (EXEC-MU-RUNTIME T1).';
COMMENT ON TABLE terminal.usage_hour IS
    'Service accounts only: grants, files and bytes granted per clock hour (UTC), checked against the service_* ceilings in the grant''s transaction; rows older than the audit retention (90 days) are deleted by terminal-api (EXEC-MU-RUNTIME T1).';

-- What terminal-api does to the counter and no more: UPSERT ... RETURNING (SELECT, INSERT, UPDATE) and the retention
-- DELETE.
REVOKE ALL ON terminal.usage_hour FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE, DELETE ON terminal.usage_hour TO terminal_runtime;

DO $verify$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'terminal' AND table_name = 'subscriber'
                   AND column_name = 'kind' AND is_nullable = 'NO' AND column_default LIKE '''person''%')
       OR NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'terminal.subscriber'::regclass
                      AND conname = 'subscriber_kind_check' AND contype = 'c') THEN
        RAISE EXCEPTION 'terminal.subscriber.kind is not NOT NULL DEFAULT person with its check';
    END IF;
    IF (SELECT count(*) FROM terminal.subscriber WHERE kind = 'service'
        AND email IN ('backtest-worker@terminal.local', 'screener-worker@terminal.local')) <> 2 THEN
        RAISE EXCEPTION 'the two service accounts are not both present as kind service';
    END IF;
    IF (SELECT array_agg(a.attname ORDER BY k.n) FROM pg_index i
        CROSS JOIN LATERAL unnest(i.indkey) WITH ORDINALITY AS k(attnum, n)
        JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = k.attnum
        WHERE i.indrelid = 'terminal.usage_hour'::regclass AND i.indisprimary) IS DISTINCT FROM
       ARRAY['subscriber_id', 'hour_start']::name[] THEN
        RAISE EXCEPTION 'terminal.usage_hour has no primary key (subscriber_id, hour_start)';
    END IF;
    IF (SELECT count(*) FROM terminal.quota WHERE value > 0 AND name IN
        ('service_grants_per_hour', 'service_files_per_hour', 'service_megabytes_per_hour')) <> 3 THEN
        RAISE EXCEPTION 'a service ceiling is missing from terminal.quota';
    END IF;
    -- one privilege per call: has_table_privilege with a list is true when any one of them is held
    IF EXISTS (SELECT 1 FROM unnest(ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE']) AS p(privilege)
               WHERE NOT has_table_privilege('terminal_runtime', 'terminal.usage_hour', p.privilege)) THEN
        RAISE EXCEPTION 'terminal_runtime cannot use terminal.usage_hour';
    END IF;
    -- and nothing else: TRUNCATE would empty every service's counter at once (a list: true when any one is held)
    IF has_table_privilege('terminal_runtime', 'terminal.usage_hour', 'TRUNCATE, REFERENCES, TRIGGER') THEN
        RAISE EXCEPTION 'terminal_runtime has more than terminal.usage_hour needs';
    END IF;
    IF has_table_privilege('public', 'terminal.usage_hour', 'SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER') THEN
        RAISE EXCEPTION 'PUBLIC can use terminal.usage_hour';
    END IF;
    -- terminal-api reads the new column through its existing table grant
    IF NOT has_column_privilege('terminal_runtime', 'terminal.subscriber', 'kind', 'SELECT') THEN
        RAISE EXCEPTION 'terminal_runtime cannot read terminal.subscriber.kind';
    END IF;
    -- and its login inherits all of it, where the login exists (scripts/provision_terminal_logins.py)
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'terminal_api_login')
       AND NOT (has_table_privilege('terminal_api_login', 'terminal.usage_hour', 'INSERT')
                AND has_table_privilege('terminal_api_login', 'terminal.usage_hour', 'UPDATE')
                AND has_column_privilege('terminal_api_login', 'terminal.subscriber', 'kind', 'SELECT')) THEN
        RAISE EXCEPTION 'terminal_api_login does not reach terminal.usage_hour and terminal.subscriber.kind';
    END IF;
END $verify$;
COMMIT;

-- Rollback (a new forward migration with this body), only after terminal-api runs code that does not read kind or
-- usage_hour (the commit before EXEC-MU-RUNTIME Phase 1b) and the workers no longer present their service keys:
-- BEGIN;
-- DELETE FROM terminal.quota_override WHERE name IN ('service_grants_per_hour', 'service_files_per_hour', 'service_megabytes_per_hour');
-- DELETE FROM terminal.quota WHERE name IN ('service_grants_per_hour', 'service_files_per_hour', 'service_megabytes_per_hour');
-- DROP TABLE terminal.usage_hour;
-- DELETE FROM terminal.subscriber WHERE kind = 'service';   -- cascades their audit rows, sessions and overrides
-- ALTER TABLE terminal.subscriber DROP COLUMN kind;
-- COMMIT;
