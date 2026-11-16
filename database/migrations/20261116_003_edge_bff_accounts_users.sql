-- EDGE multi-user Phase 1 (EXEC-MU-ACCOUNTS, go 2026-11-16 "B": Fase 0 + Fase 1; contract
-- verification/edge_multiuser/access_tiers/CONTRACT.md sections 1, 2 and 4b): the account tables of edge-bff, behind the
-- switch EDGE_MULTIUSER (off until Phase 6). With the switch off edge-bff only seeds user #1 (the configured owner,
-- EDGE_OWNER, role admin) and serves the account preferences (4b); nothing else reads these tables.
--
-- New tables in the operational schema edge_bff: users, identities, email_codes, mfa_totp, mfa_recovery_codes,
-- email_outbox, email_suppression, admin_audit, user_preferences. edge_bff.sessions gains user_id, last_seen_at,
-- mfa_passed_at and created_ip_hash (owner_key stays: the switch-off read path). Each table is granted to
-- edge_bff_runtime with exactly what edge-bff does to it, nothing to PUBLIC. No market table, no other role changes.
-- Indexes beyond the keys: none (CONTRACT.md section 1: users and sessions number in the thousands at most; AGENTS.md no
-- speculative index). Forward-only; rollback block at the end (comment).
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';
DO $preflight$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'edge_bff') OR
       NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'edge_bff_runtime') THEN
        RAISE EXCEPTION 'edge_bff schema/role is missing: apply 20261008_002 first';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'edge_bff' AND table_name = 'auth_throttle') THEN
        RAISE EXCEPTION 'edge_bff.auth_throttle is missing: apply 20261116_002 first';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'edge_bff' AND table_name IN (
                   'users', 'identities', 'email_codes', 'mfa_totp', 'mfa_recovery_codes', 'email_outbox',
                   'email_suppression', 'admin_audit', 'user_preferences'))
       OR EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'edge_bff' AND table_name = 'sessions'
                  AND column_name IN ('user_id', 'last_seen_at', 'mfa_passed_at', 'created_ip_hash')) THEN
        RAISE EXCEPTION 'an EDGE account table or session column exists: reconcile before applying';
    END IF;
END $preflight$;

-- ---- users ------------------------------------------------------------------------------------------------------------
-- One row per EDGE account. owner_key is the key every owned row (jobs, conversations, backtests, screens, layouts,
-- drawings, watchlists, preferences) is stored under; it is made by edge-bff ('u_' + 24 hexadecimal digits from
-- secrets, app/principal.py new_owner_key) and never changes (trigger below). The one exception is the seed, user #1:
-- the configured EDGE_OWNER (edge-private on dev), so the owner's existing rows stay its own. Reserved keys are never
-- issued: default, golden-*, test-*, someone-else (Orc's test owners), and edge-private outside the seed.
CREATE TABLE edge_bff.users (
    user_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    owner_key text NOT NULL UNIQUE CHECK (owner_key ~ '^[A-Za-z0-9._:@-]{1,128}$'),
    username text NOT NULL UNIQUE CHECK (username ~ '^[a-z0-9_]{3,30}$'
        AND username NOT IN ('admin', 'root', 'support', 'edge', 'system')),
    email text UNIQUE CHECK (email = lower(btrim(email)) AND char_length(email) BETWEEN 3 AND 254
        AND email ~ '^[^@[:space:]]+@[^@[:space:]]+$'),
    email_verified_at timestamptz,
    first_name text CHECK (first_name = btrim(first_name) AND char_length(first_name) BETWEEN 1 AND 100),
    last_name text CHECK (last_name = btrim(last_name) AND char_length(last_name) BETWEEN 1 AND 100),
    phone_e164 text CHECK (phone_e164 ~ '^\+[1-9][0-9]{6,14}$'),
    role text NOT NULL DEFAULT 'user' CHECK (role IN ('admin', 'user')),
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'active', 'disabled')),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_sign_in_at timestamptz,
    -- a generated account always has an email (registration); only the seed may have none
    CONSTRAINT users_email_required CHECK (email IS NOT NULL OR owner_key !~ '^u_[0-9a-f]{24}$')
);
-- at most one row ever holds a key edge-bff did not generate: the seed
CREATE UNIQUE INDEX users_one_seed ON edge_bff.users ((true)) WHERE owner_key !~ '^u_[0-9a-f]{24}$';

CREATE FUNCTION edge_bff.users_owner_key_rules() RETURNS trigger LANGUAGE plpgsql
SET search_path = pg_catalog, edge_bff AS $fn$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        IF NEW.owner_key IS DISTINCT FROM OLD.owner_key OR NEW.user_id IS DISTINCT FROM OLD.user_id THEN
            RAISE EXCEPTION 'edge_bff.users.owner_key and user_id never change (user %)', OLD.user_id
                USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
    END IF;
    IF NEW.owner_key ~ '^u_[0-9a-f]{24}$' THEN
        RETURN NEW;
    END IF;
    IF NEW.owner_key IN ('default', 'someone-else') OR NEW.owner_key LIKE 'golden-%' OR NEW.owner_key LIKE 'test-%' THEN
        RAISE EXCEPTION 'owner key % is reserved', NEW.owner_key USING ERRCODE = 'check_violation';
    END IF;
    IF EXISTS (SELECT 1 FROM edge_bff.users) THEN
        RAISE EXCEPTION 'only the seed (user #1, the first row) keeps a configured owner key; others are u_ + 24 hex'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END $fn$;
REVOKE ALL ON FUNCTION edge_bff.users_owner_key_rules() FROM PUBLIC;
CREATE TRIGGER users_owner_key_rules BEFORE INSERT OR UPDATE ON edge_bff.users
    FOR EACH ROW EXECUTE FUNCTION edge_bff.users_owner_key_rules();

COMMENT ON TABLE edge_bff.users IS 'EDGE accounts (EXEC-MU-ACCOUNTS Phase 1). owner_key keys every owned row; made by edge-bff, immutable; user #1 (the seed) keeps EDGE_OWNER.';
COMMENT ON COLUMN edge_bff.users.owner_key IS 'u_ + 24 hexadecimal digits made by edge-bff (app/principal.py), immutable (trigger); the seed keeps EDGE_OWNER. Reserved, never issued: default, golden-*, test-*, someone-else, edge-private outside the seed.';
COMMENT ON COLUMN edge_bff.users.username IS 'Lower case a-z 0-9 _, 3 to 30 characters, unique; reserved: admin, root, support, edge, system.';
COMMENT ON COLUMN edge_bff.users.email IS 'Lower-cased, unique; required for every generated account, optional for the seed.';
COMMENT ON COLUMN edge_bff.users.phone_e164 IS 'E.164 (+ country code and number); 08... is stored as +628...; not verified.';
COMMENT ON COLUMN edge_bff.users.role IS 'admin or user. With EDGE_MULTIUSER on, admin holds every capability (Phase 1; the plan catalog follows in Phase 2) and needs MFA for admin routes.';
COMMENT ON COLUMN edge_bff.users.status IS 'pending (email not verified, never signed in; deleted 24 h after creation), active, disabled (every session refused).';

-- ---- identities -------------------------------------------------------------------------------------------------------
CREATE TABLE edge_bff.identities (
    user_id bigint NOT NULL REFERENCES edge_bff.users(user_id) ON DELETE CASCADE,
    provider text NOT NULL CHECK (provider IN ('password', 'google')),
    subject text NOT NULL CHECK (char_length(subject) BETWEEN 1 AND 255),
    verifier text,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (provider, subject),
    UNIQUE (user_id, provider),
    -- a password identity: its subject is the user_id and its verifier the scrypt format of app/security.py
    CONSTRAINT identities_password CHECK (provider <> 'password' OR (subject = user_id::text
        AND verifier ~ '^scrypt\$[0-9a-f]{32}\$[0-9a-f]{64}$'))
);
COMMENT ON TABLE edge_bff.identities IS 'How an EDGE account signs in: password (scrypt verifier, subject = user_id); google later.';

-- ---- email_codes ------------------------------------------------------------------------------------------------------
CREATE TABLE edge_bff.email_codes (
    code_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    purpose text NOT NULL CHECK (purpose IN ('register', 'reset', 'email_change')),
    user_id bigint NOT NULL REFERENCES edge_bff.users(user_id) ON DELETE CASCADE,
    code_hash text NOT NULL CHECK (code_hash ~ '^[0-9a-f]{64}$'),
    -- email_change only: the new address the code was sent to (contract section 1 lists the key columns; this one is
    -- needed to apply an email change once its code is proved)
    target_email text CHECK (target_email = lower(btrim(target_email)) AND char_length(target_email) BETWEEN 3 AND 254),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at timestamptz NOT NULL,
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts BETWEEN 0 AND 5),
    consumed_at timestamptz,
    CONSTRAINT email_codes_five_minutes CHECK (expires_at = created_at + interval '300 seconds'),
    CONSTRAINT email_codes_target CHECK ((purpose = 'email_change') = (target_email IS NOT NULL))
);
-- one live code per (user, purpose): a new code consumes the old one first
CREATE UNIQUE INDEX email_codes_one_live ON edge_bff.email_codes(user_id, purpose) WHERE consumed_at IS NULL;
COMMENT ON TABLE edge_bff.email_codes IS 'Six-digit email codes (register, reset, email_change): HMAC-SHA256 with EDGE_CODE_SECRET, valid 300 s, at most 5 tries, one live code per user and purpose.';

-- ---- sessions (existing) ------------------------------------------------------------------------------------------------
ALTER TABLE edge_bff.sessions
    ADD COLUMN user_id bigint REFERENCES edge_bff.users(user_id) ON DELETE CASCADE,
    ADD COLUMN last_seen_at timestamptz,
    ADD COLUMN mfa_passed_at timestamptz,
    ADD COLUMN created_ip_hash text CHECK (created_ip_hash ~ '^[0-9a-f]{64}$');
COMMENT ON COLUMN edge_bff.sessions.user_id IS 'The account of a session made with EDGE_MULTIUSER on (NULL for a switch-off session, which owner_key keys).';
COMMENT ON COLUMN edge_bff.sessions.last_seen_at IS 'Last request of the session, written at most once per 60 s; idle beyond EDGE_SESSION_IDLE_SECONDS (default 8 h) is refused.';
COMMENT ON COLUMN edge_bff.sessions.mfa_passed_at IS 'When the session proved the admin TOTP (or a recovery code); NULL = not proved.';
COMMENT ON COLUMN edge_bff.sessions.created_ip_hash IS 'HMAC-SHA256 of the client address at sign-in (never the address itself).';

-- ---- MFA --------------------------------------------------------------------------------------------------------------
CREATE TABLE edge_bff.mfa_totp (
    user_id bigint PRIMARY KEY REFERENCES edge_bff.users(user_id) ON DELETE CASCADE,
    nonce bytea NOT NULL CHECK (octet_length(nonce) = 16),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    confirmed_at timestamptz,
    last_step bigint CHECK (last_step >= 0)
);
COMMENT ON TABLE edge_bff.mfa_totp IS 'Admin TOTP (RFC 6238). The secret is HMAC-SHA256(EDGE_MFA_KEY, user_id || nonce)[:20], never stored; last_step refuses a replayed step.';

CREATE TABLE edge_bff.mfa_recovery_codes (
    user_id bigint NOT NULL REFERENCES edge_bff.users(user_id) ON DELETE CASCADE,
    code_hash text NOT NULL CHECK (code_hash ~ '^[0-9a-f]{64}$'),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    used_at timestamptz,
    PRIMARY KEY (user_id, code_hash)
);
COMMENT ON TABLE edge_bff.mfa_recovery_codes IS 'Ten one-time admin recovery codes per enrolment, stored hashed, shown once.';

-- ---- email ------------------------------------------------------------------------------------------------------------
CREATE TABLE edge_bff.email_outbox (
    outbox_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    idempotency_key text NOT NULL UNIQUE CHECK (char_length(idempotency_key) BETWEEN 1 AND 200),
    purpose text NOT NULL CHECK (purpose ~ '^[a-z_]{1,40}$'),
    to_email text NOT NULL CHECK (to_email = lower(btrim(to_email)) AND char_length(to_email) BETWEEN 3 AND 254),
    payload jsonb CHECK (payload IS NULL OR jsonb_typeof(payload) = 'object'),
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'sending', 'sent', 'failed', 'expired', 'suppressed')),
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    next_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    lease_token text,
    lease_expires_at timestamptz,
    provider_id text CHECK (char_length(provider_id) <= 200),
    expires_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    sent_at timestamptz,
    CHECK ((lease_token IS NULL) = (lease_expires_at IS NULL)),
    CHECK ((status = 'sent') = (sent_at IS NOT NULL))
);
COMMENT ON TABLE edge_bff.email_outbox IS 'EDGE emails to send (Resend, Idempotency-Key = idempotency_key). A code email carries expires_at = the code expiry and is never sent after it; payload is nulled once sent.';

CREATE TABLE edge_bff.email_suppression (
    email text PRIMARY KEY CHECK (email = lower(btrim(email)) AND char_length(email) BETWEEN 3 AND 254),
    reason text NOT NULL CHECK (reason IN ('bounce', 'complaint')),
    at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);
COMMENT ON TABLE edge_bff.email_suppression IS 'Addresses EDGE no longer mails (a bounce or complaint from the signed Resend webhook).';

-- ---- admin_audit ------------------------------------------------------------------------------------------------------
CREATE TABLE edge_bff.admin_audit (
    audit_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    actor_user_id bigint REFERENCES edge_bff.users(user_id) ON DELETE SET NULL,
    action text NOT NULL CHECK (action ~ '^[a-z][a-z0-9_.]{0,63}$'),
    target_user_id bigint REFERENCES edge_bff.users(user_id) ON DELETE SET NULL,
    before jsonb,
    after jsonb,
    reason text CHECK (char_length(reason) <= 1000),
    ip_hash text CHECK (ip_hash ~ '^[0-9a-f]{64}$'),
    at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);
COMMENT ON TABLE edge_bff.admin_audit IS 'Every admin action, written in the same transaction as the change. edge_bff_runtime may only read and add rows (no UPDATE, no DELETE).';

-- ---- user_preferences (contract section 4b) ---------------------------------------------------------------------------
-- An account's preferences and saved items that the pages kept only in the browser (My metrics ml.my, indicator
-- favourites, extra series, the model choice, the Screener's extra columns and last screen, the Terminal chart
-- settings), so they come back on any device. One row per (owner, key); version rises by one on every write
-- (optimistic: a stale write answers 409 with the current value). The per-user count and byte limits are in
-- app/preferences.py; the table caps one value at 64 KiB.
CREATE TABLE edge_bff.user_preferences (
    owner_key text NOT NULL,
    pref_key text NOT NULL CHECK (pref_key ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$'),
    value jsonb NOT NULL CHECK (octet_length(value::text) <= 65536),
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version integer NOT NULL DEFAULT 1 CHECK (version > 0),
    PRIMARY KEY (owner_key, pref_key)
);
COMMENT ON TABLE edge_bff.user_preferences IS 'EDGE account preferences restored on any device (EXEC-MU-ACCOUNTS 4b): one JSON value per owner and storage key, optimistic version.';

-- ---- grants: what edge-bff does to each table and no more --------------------------------------------------------------
REVOKE ALL ON edge_bff.users, edge_bff.identities, edge_bff.email_codes, edge_bff.mfa_totp, edge_bff.mfa_recovery_codes,
    edge_bff.email_outbox, edge_bff.email_suppression, edge_bff.admin_audit, edge_bff.user_preferences FROM PUBLIC;
-- users: created (registration, the seed), read, updated (status, names, last sign-in), deleted (a pending user after 24 h)
GRANT SELECT, INSERT, UPDATE, DELETE ON edge_bff.users, edge_bff.identities, edge_bff.email_codes, edge_bff.mfa_totp,
    edge_bff.mfa_recovery_codes, edge_bff.user_preferences TO edge_bff_runtime;
-- the outbox and the suppression list are added to and updated (the sender's lease and status), never deleted
GRANT SELECT, INSERT, UPDATE ON edge_bff.email_outbox, edge_bff.email_suppression TO edge_bff_runtime;
-- the audit is read and added to only
GRANT SELECT, INSERT ON edge_bff.admin_audit TO edge_bff_runtime;
-- the identity columns' sequences: USAGE (nextval through the default) and nothing else
REVOKE ALL ON SEQUENCE edge_bff.users_user_id_seq, edge_bff.email_codes_code_id_seq, edge_bff.email_outbox_outbox_id_seq,
    edge_bff.admin_audit_audit_id_seq FROM PUBLIC;
GRANT USAGE ON SEQUENCE edge_bff.users_user_id_seq, edge_bff.email_codes_code_id_seq, edge_bff.email_outbox_outbox_id_seq,
    edge_bff.admin_audit_audit_id_seq TO edge_bff_runtime;

DO $verify$
DECLARE
    expected constant jsonb := '{"users": ["SELECT","INSERT","UPDATE","DELETE"],
        "identities": ["SELECT","INSERT","UPDATE","DELETE"], "email_codes": ["SELECT","INSERT","UPDATE","DELETE"],
        "mfa_totp": ["SELECT","INSERT","UPDATE","DELETE"], "mfa_recovery_codes": ["SELECT","INSERT","UPDATE","DELETE"],
        "user_preferences": ["SELECT","INSERT","UPDATE","DELETE"], "email_outbox": ["SELECT","INSERT","UPDATE"],
        "email_suppression": ["SELECT","INSERT","UPDATE"], "admin_audit": ["SELECT","INSERT"],
        "sessions": ["SELECT","INSERT","UPDATE","DELETE"]}';
    t text;
    p text;
BEGIN
    FOR t IN SELECT jsonb_object_keys(expected) LOOP
        FOREACH p IN ARRAY ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER'] LOOP
            -- one privilege per call: has_table_privilege with a list is true when any one of them is held
            IF has_table_privilege('edge_bff_runtime', 'edge_bff.' || t, p) <> (expected -> t ? p) THEN
                RAISE EXCEPTION 'edge_bff_runtime % on edge_bff.%: expected %', p, t, (expected -> t ? p);
            END IF;
            IF has_table_privilege('public', 'edge_bff.' || t, p) THEN
                RAISE EXCEPTION 'PUBLIC holds % on edge_bff.%', p, t;
            END IF;
        END LOOP;
    END LOOP;
    FOREACH t IN ARRAY ARRAY['users_user_id_seq', 'email_codes_code_id_seq', 'email_outbox_outbox_id_seq',
                             'admin_audit_audit_id_seq'] LOOP
        IF NOT has_sequence_privilege('edge_bff_runtime', 'edge_bff.' || t, 'USAGE')
           OR has_sequence_privilege('edge_bff_runtime', 'edge_bff.' || t, 'SELECT')
           OR has_sequence_privilege('edge_bff_runtime', 'edge_bff.' || t, 'UPDATE')
           OR has_sequence_privilege('public', 'edge_bff.' || t, 'USAGE, SELECT, UPDATE') THEN
            RAISE EXCEPTION 'sequence edge_bff.% grants differ from USAGE for edge_bff_runtime only', t;
        END IF;
    END LOOP;
    IF EXISTS (SELECT 1 FROM edge_bff.users) THEN
        RAISE EXCEPTION 'edge_bff.users is not empty after its creation';
    END IF;
END $verify$;
COMMIT;

-- Rollback (a new forward migration with this body; deploy the previous edge-bff first, which reads none of these, or
-- keep EDGE_MULTIUSER off and accept the loss of the seed and the saved preferences):
-- BEGIN;
-- DROP TABLE edge_bff.user_preferences, edge_bff.admin_audit, edge_bff.email_suppression, edge_bff.email_outbox,
--     edge_bff.mfa_recovery_codes, edge_bff.mfa_totp, edge_bff.email_codes, edge_bff.identities;
-- ALTER TABLE edge_bff.sessions DROP COLUMN user_id, DROP COLUMN last_seen_at, DROP COLUMN mfa_passed_at,
--     DROP COLUMN created_ip_hash;
-- DROP TABLE edge_bff.users;
-- DROP FUNCTION edge_bff.users_owner_key_rules();
-- COMMIT;
