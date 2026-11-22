-- EDGE multi-user, Phase 4 with the contact-support panel (EXEC.md option A item 5; the user, 2026-11-22: "saya minta
-- dibuatkan panel sebelah kiri di live iconnya kotak surat. Kira2 kalau di klik fungsinya sama seperti SS terlampir. Ada
-- yang submit maka langsung ke admin dan telegram dan ke email pribadi saya"; "hanya yang login ... lampiran hanya 2A";
-- "go"). A signed-in account sends a message to EDGE from the rail: an issue type, a subject, a description, the
-- technical details the page adds, and at most three images (PNG, JPG, WebP; 5 MiB each). edge-bff keeps it here, the
-- admin page (the beta) reads it, a Telegram summary and an email to the admins follow (apps/edge-bff/app/support.py).
--
-- The capability support.send (a flag) lets an account send; the free and the paid plan hold it, the guest plan does not
-- (a visitor is asked to sign in), the admin holds it through '*'. An admin may take it from one account with an
-- override (false). Its tab 'support' is released in apps/edge-bff/catalog/releases.json (the user's go).
--
-- The tables hold what the account wrote: a ticket's text and details, and its images. The checks hold every row to
-- what the route accepts: the kinds of the dialog, a subject of 1-120 characters, a description of 1-5000, details of at
-- most 4 KiB, an image's type among three, its length at most 5 MiB and its SHA-256 as stated. A ticket and its images
-- go with the account (ON DELETE CASCADE; CONTRACT 10's deletion table).
--
-- Expand only: a new capability, two plan rows and two new tables; an older edge-bff reads none of them. edge_bff_runtime
-- reads, adds and deletes tickets and images and updates a ticket (its status and delivery; the admin page). Its grants
-- are table-level, as every EDGE grant (re-check R1-41: scripts/provision_edge_bff_login.py refuses a column grant); an
-- image is never updated (no UPDATE on support_attachments). Refuses a second run. Forward-only; rollback block at the
-- end.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';
DO $preflight$
BEGIN
    IF to_regnamespace('edge_bff') IS NULL OR NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'edge_bff_runtime') THEN
        RAISE EXCEPTION 'the schema edge_bff or the role edge_bff_runtime is missing: apply the edge_bff migrations first';
    END IF;
    IF to_regclass('edge_bff.support_tickets') IS NOT NULL
       OR EXISTS (SELECT 1 FROM edge_bff.capabilities WHERE capability_key = 'support.send') THEN
        RAISE EXCEPTION 'edge_bff.support_tickets or support.send exists: this migration ran already';
    END IF;
    IF (SELECT count(*) FROM edge_bff.plans WHERE plan_key IN ('free', 'paid')) <> 2 THEN
        RAISE EXCEPTION 'the plans free and paid are missing: apply 20261117_003 first';
    END IF;
END $preflight$;

INSERT INTO edge_bff.capabilities(capability_key, kind, unit, means, display_name) VALUES
    ('support.send', 'flag', NULL, 'Sends a message to EDGE support from the rail (an issue type, a subject, a description '
     'and up to three images); the admins read it on the admin page and get it by Telegram and email.', 'Contact support');
INSERT INTO edge_bff.plan_capabilities(plan_key, capability_key, value) VALUES
    ('free', 'support.send', 'true'),
    ('paid', 'support.send', 'true');

CREATE TABLE edge_bff.support_tickets (
    ticket_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id bigint NOT NULL REFERENCES edge_bff.users(user_id) ON DELETE CASCADE,
    site text NOT NULL CONSTRAINT support_tickets_site CHECK (site IN ('beta', 'live')),
    kind text NOT NULL CONSTRAINT support_tickets_kind CHECK (kind IN ('bug', 'question', 'account', 'billing', 'feature', 'data')),
    subject text NOT NULL CONSTRAINT support_tickets_subject CHECK (subject = btrim(subject) AND char_length(subject) BETWEEN 1 AND 120),
    body text NOT NULL CONSTRAINT support_tickets_body CHECK (char_length(btrim(body)) >= 1 AND char_length(body) <= 5000),
    details jsonb NOT NULL CONSTRAINT support_tickets_details CHECK (jsonb_typeof(details) = 'object' AND octet_length(details::text) <= 4096),
    images smallint NOT NULL DEFAULT 0 CONSTRAINT support_tickets_images CHECK (images BETWEEN 0 AND 3),
    status text NOT NULL DEFAULT 'new' CONSTRAINT support_tickets_status CHECK (status IN ('new', 'done')),
    created_at timestamptz NOT NULL DEFAULT now(),
    done_at timestamptz,
    done_by_user_id bigint,                          -- who marked it done: a plain number, as every *_by_user_id (R1-42)
    telegram_sent_at timestamptz,
    telegram_attempts smallint NOT NULL DEFAULT 0 CONSTRAINT support_tickets_telegram_attempts CHECK (telegram_attempts >= 0),
    CONSTRAINT support_tickets_done CHECK ((status = 'done') = (done_at IS NOT NULL))
);
CREATE INDEX support_tickets_user_time ON edge_bff.support_tickets(user_id, created_at DESC);
CREATE INDEX support_tickets_status_time ON edge_bff.support_tickets(status, created_at DESC);
COMMENT ON TABLE edge_bff.support_tickets IS
    'Phase 4, the contact-support panel (the user, 2026-11-22): one message an account sent from the rail (support.send); '
    'read on the admin page (the beta), summarised to Telegram and emailed to the admins (apps/edge-bff/app/support.py). '
    'Goes with the account (ON DELETE CASCADE).';
COMMENT ON COLUMN edge_bff.support_tickets.details IS
    'the technical details the page and edge-bff add (the page path, the screen size, the time zone, the browser, the '
    'build, the site, the plan): strings only, at most 4 KiB; never a password, a token or a cookie';
COMMENT ON COLUMN edge_bff.support_tickets.telegram_sent_at IS
    'when telegram-monitor accepted the summary (source EDGE_Support); NULL while not delivered (retried, then shown on the admin page)';

CREATE TABLE edge_bff.support_attachments (
    ticket_id bigint NOT NULL REFERENCES edge_bff.support_tickets(ticket_id) ON DELETE CASCADE,
    position smallint NOT NULL CONSTRAINT support_attachments_position CHECK (position BETWEEN 1 AND 3),
    filename text NOT NULL CONSTRAINT support_attachments_filename CHECK (char_length(filename) BETWEEN 1 AND 120
        AND filename !~ '[/\\[:cntrl:]]'),
    content_type text NOT NULL CONSTRAINT support_attachments_type CHECK (content_type IN ('image/png', 'image/jpeg', 'image/webp')),
    bytes integer NOT NULL CONSTRAINT support_attachments_bytes CHECK (bytes BETWEEN 1 AND 5242880),
    sha256 text NOT NULL CONSTRAINT support_attachments_sha256 CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    body bytea NOT NULL,
    PRIMARY KEY (ticket_id, position),
    CONSTRAINT support_attachments_body CHECK (octet_length(body) = bytes AND encode(sha256(body), 'hex') = sha256)
);
COMMENT ON TABLE edge_bff.support_attachments IS
    'The images of a support ticket (at most 3, PNG, JPG or WebP, 5 MiB each, the type checked from the bytes); read one '
    'by one on the admin page and attached to the admins'' email. Goes with its ticket.';

REVOKE ALL ON edge_bff.support_tickets, edge_bff.support_attachments FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE, DELETE ON edge_bff.support_tickets TO edge_bff_runtime;
GRANT SELECT, INSERT, DELETE ON edge_bff.support_attachments TO edge_bff_runtime;

DO $verify$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM edge_bff.capabilities WHERE capability_key = 'support.send' AND kind = 'flag')
       OR (SELECT count(*) FROM edge_bff.plan_capabilities WHERE capability_key = 'support.send' AND value = 'true'::jsonb
           AND plan_key IN ('free', 'paid')) <> 2
       OR EXISTS (SELECT 1 FROM edge_bff.plan_capabilities AS pc JOIN edge_bff.plans AS p USING (plan_key)
                  WHERE pc.capability_key = 'support.send' AND p.for_guests) THEN
        RAISE EXCEPTION 'verify: support.send is a flag held by the free and the paid plan and by no guest plan';
    END IF;
    -- has_table_privilege with a list is true when ANY is held: each needed privilege is asked on its own
    IF EXISTS (SELECT 1 FROM (VALUES ('edge_bff.support_tickets', 'SELECT'), ('edge_bff.support_tickets', 'INSERT'),
                                     ('edge_bff.support_tickets', 'UPDATE'), ('edge_bff.support_tickets', 'DELETE'),
                                     ('edge_bff.support_attachments', 'SELECT'), ('edge_bff.support_attachments', 'INSERT'),
                                     ('edge_bff.support_attachments', 'DELETE')) AS needed(name, privilege)
               WHERE NOT has_table_privilege('edge_bff_runtime', needed.name, needed.privilege))
       OR has_table_privilege('edge_bff_runtime', 'edge_bff.support_attachments', 'UPDATE')
       OR has_table_privilege('edge_bff_runtime', 'edge_bff.support_tickets', 'TRUNCATE, REFERENCES, TRIGGER')
       OR has_table_privilege('edge_bff_runtime', 'edge_bff.support_attachments', 'TRUNCATE, REFERENCES, TRIGGER')
       OR EXISTS (SELECT 1 FROM pg_attribute WHERE attrelid IN ('edge_bff.support_tickets'::regclass,
                  'edge_bff.support_attachments'::regclass) AND attacl IS NOT NULL) THEN
        RAISE EXCEPTION 'verify: edge_bff_runtime reads, adds and deletes tickets and images, updates a ticket, never an image, and holds no column grant';
    END IF;
END $verify$;
COMMIT;

-- Rollback (a new forward migration with this body, once no edge-bff that reads the tables runs):
-- BEGIN;
-- DROP TABLE edge_bff.support_attachments;
-- DROP TABLE edge_bff.support_tickets;
-- DELETE FROM edge_bff.user_capability_overrides WHERE capability_key = 'support.send';
-- DELETE FROM edge_bff.plan_capabilities WHERE capability_key = 'support.send';
-- DELETE FROM edge_bff.capabilities WHERE capability_key = 'support.send';
-- COMMIT;
