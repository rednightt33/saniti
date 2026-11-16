-- EDGE multi-user Phase 1, auth flows (EXEC-MU-ACCOUNTS; contract verification/edge_multiuser/access_tiers/CONTRACT.md
-- sections 4 and 5). Two needs of the flows that the Phase 1 tables (20261116_003) cannot hold:
-- 1. Registration: "Username taken: the conflict is decided at verify time" (section 4). A pending registration must
--    therefore exist without holding its username (users.username is UNIQUE), so a pending user keeps the requested
--    name in requested_username and username stays NULL until the email code is proved; an active or disabled user
--    always has a username.
-- 2. The Resend webhook: "UNIQUE svix-id" (section 5). edge_bff.email_hook_events keeps each delivered svix-id once, so
--    a repeated delivery changes nothing.
-- Forward-only; rollback block at the end (comment).
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';
DO $preflight$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'edge_bff' AND table_name = 'users') THEN
        RAISE EXCEPTION 'edge_bff.users is missing: apply 20261116_003 first';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'edge_bff' AND table_name = 'users'
               AND column_name = 'requested_username')
       OR EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'edge_bff' AND table_name = 'email_hook_events') THEN
        RAISE EXCEPTION 'edge_bff.users.requested_username or edge_bff.email_hook_events exists: reconcile before applying';
    END IF;
END $preflight$;

ALTER TABLE edge_bff.users
    ALTER COLUMN username DROP NOT NULL,
    ADD COLUMN requested_username text CHECK (requested_username ~ '^[a-z0-9_]{3,30}$'
        AND requested_username NOT IN ('admin', 'root', 'support', 'edge', 'system')),
    -- a user without a username is a pending registration that names the one it asked for
    ADD CONSTRAINT users_username_or_pending CHECK (username IS NOT NULL
        OR (status = 'pending' AND requested_username IS NOT NULL));
COMMENT ON COLUMN edge_bff.users.requested_username IS 'The username a pending registration asked for; it becomes username when the email code is proved (USERNAME_TAKEN then if another account holds it). NULL once active.';
COMMENT ON COLUMN edge_bff.users.username IS 'Lower case a-z 0-9 _, 3 to 30 characters, unique; reserved: admin, root, support, edge, system. NULL only for a pending registration (requested_username).';

CREATE TABLE edge_bff.email_hook_events (
    svix_id text PRIMARY KEY CHECK (char_length(svix_id) BETWEEN 1 AND 200),
    event_type text CHECK (char_length(event_type) <= 100),
    received_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);
COMMENT ON TABLE edge_bff.email_hook_events IS 'Each signed Resend webhook delivery (svix-id) once; a repeated delivery changes nothing.';

REVOKE ALL ON edge_bff.email_hook_events FROM PUBLIC;
GRANT SELECT, INSERT ON edge_bff.email_hook_events TO edge_bff_runtime;
DO $verify$
DECLARE
    p text;
BEGIN
    FOREACH p IN ARRAY ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER'] LOOP
        IF has_table_privilege('edge_bff_runtime', 'edge_bff.email_hook_events', p) <> (p IN ('SELECT', 'INSERT')) THEN
            RAISE EXCEPTION 'edge_bff_runtime % on edge_bff.email_hook_events differs from SELECT, INSERT', p;
        END IF;
        IF has_table_privilege('public', 'edge_bff.email_hook_events', p) THEN
            RAISE EXCEPTION 'PUBLIC holds % on edge_bff.email_hook_events', p;
        END IF;
    END LOOP;
    IF EXISTS (SELECT 1 FROM edge_bff.users WHERE username IS NULL) THEN
        RAISE EXCEPTION 'a user has no username after the change';
    END IF;
END $verify$;
COMMIT;

-- Rollback (a new forward migration with this body; deploy the previous edge-bff first; pending registrations are
-- deleted, they hold no username):
-- BEGIN;
-- DELETE FROM edge_bff.users WHERE username IS NULL;
-- ALTER TABLE edge_bff.users DROP CONSTRAINT users_username_or_pending, DROP COLUMN requested_username,
--     ALTER COLUMN username SET NOT NULL;
-- DROP TABLE edge_bff.email_hook_events;
-- COMMIT;
