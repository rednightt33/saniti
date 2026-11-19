-- EDGE multi-user, fix round of the ultracode re-check (EXEC-MU-ACCOUNTS; verification/edge_multiuser/fix_round/auth.md;
-- contract verification/edge_multiuser/access_tiers/CONTRACT.md sections 1, 4 and 5), behind the switch EDGE_MULTIUSER
-- (off until Phase 6; with it off nothing is written to the outbox, so both reads and the purge find no row).
-- 1. ERRORS R2-35: the hot reads of edge_bff.email_outbox scanned every email ever sent: the 60-second gap between code
--    emails of an address (app/auth_flows.py _may_send, on every register, resend, forgot and sign-in restart, by
--    to_email and created_at) and the sender's claim every 5 s (app/mailer.py OutboxStore.claim: the expired and
--    suppressed UPDATEs and the SELECT ... FOR UPDATE SKIP LOCKED, all on rows still pending or sending). Two indexes:
--      email_outbox_to_email_created  (to_email, created_at)          _may_send; the purge by address
--      email_outbox_unsent            (next_at) WHERE pending/sending  the claim (a handful of rows, whatever the size)
--    Measured (EXPLAIN, 20 000 sent rows, tests/test_c2_ops_recheck.py): without them all four statements are Seq Scans;
--    with them none is (the finder's control and this migration's run, fix_round/auth.md).
-- 2. ERRORS R2-24: the hourly purge deleted a registration never verified 24 h after it was made (CONTRACT 4), but every
--    outbox row naming its address stayed for ever, and edge_bff_runtime holds no DELETE on the outbox (20261116_003:
--    "never deleted"). The rule here follows CONTRACT 4's: an address that has no row in edge_bff.users (no account and
--    no pending registration: never verified and purged, or never registered) keeps no sent, failed, expired or
--    suppressed outbox row older than 24 h. The function edge_bff.purge_email_outbox(max_rows) deletes exactly those, at
--    most max_rows per call (NULL: 10 000, and never more; the hourly housekeeping passes its batch, store.PURGE_BATCH,
--    each batch in its own transaction); edge_bff_runtime may execute it and still holds no DELETE on the table, so the
--    rule is the only delete edge-bff can make.
-- 3. Retention (EXEC-MU-ACCOUNTS "Decisions from the fix round" item 2, user 2026-11-19: "a", deleted after 30 days, with
--    used codes and webhook events; verification/edge_multiuser/fix_round/decisions.md): besides rule 2, every sent,
--    failed, expired or suppressed outbox row of every address (an account's included) is deleted 30 days after it was
--    made, by the same function; a row still pending or sending is never deleted. The handled webhook deliveries
--    (edge_bff.email_hook_events, kept so a repeated svix-id changes nothing; Svix retries for days, and its timestamp
--    tolerance is 5 minutes) are deleted 30 days after they were received by edge_bff.purge_email_hook_events(max_rows),
--    the same way (edge_bff_runtime holds SELECT and INSERT on that table, 20261117_001, and no DELETE). The used email
--    codes go with them, by edge-bff itself (edge_bff_runtime holds DELETE on edge_bff.email_codes since 20261116_003;
--    store.py PURGES 'codes'). email_suppression is not touched: an address that bounced or complained stays suppressed
--    (CONTRACT section 10, "Account deletion": its address and reason are kept).
-- Forward-only; refuses a second run; rollback block at the end (comment).
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';
DO $preflight$
BEGIN
    IF to_regclass('edge_bff.email_outbox') IS NULL OR to_regclass('edge_bff.users') IS NULL THEN
        RAISE EXCEPTION 'edge_bff.email_outbox or edge_bff.users is missing: apply 20261116_003 first';
    END IF;
    IF to_regclass('edge_bff.email_hook_events') IS NULL THEN
        RAISE EXCEPTION 'edge_bff.email_hook_events is missing: apply 20261117_001 first';
    END IF;
    IF to_regclass('edge_bff.email_outbox_to_email_created') IS NOT NULL OR to_regclass('edge_bff.email_outbox_unsent') IS NOT NULL
       OR EXISTS (SELECT 1 FROM pg_proc WHERE proname IN ('purge_email_outbox', 'purge_email_hook_events')
                  AND pronamespace = 'edge_bff'::regnamespace) THEN
        RAISE EXCEPTION 'an index or a function of this migration exists: reconcile before applying';
    END IF;
END $preflight$;

CREATE INDEX email_outbox_to_email_created ON edge_bff.email_outbox (to_email, created_at);
CREATE INDEX email_outbox_unsent ON edge_bff.email_outbox (next_at) WHERE status IN ('pending', 'sending');

CREATE FUNCTION edge_bff.purge_email_outbox(max_rows integer) RETURNS integer LANGUAGE sql SECURITY DEFINER
SET search_path = pg_catalog, edge_bff AS $fn$
    WITH gone AS (
        SELECT o.outbox_id FROM edge_bff.email_outbox o
        WHERE o.status IN ('sent', 'failed', 'expired', 'suppressed')
          AND (o.created_at < now() - interval '30 days'
               OR (o.created_at < now() - interval '24 hours'
                   AND NOT EXISTS (SELECT 1 FROM edge_bff.users u WHERE u.email = o.to_email)))
        ORDER BY o.outbox_id LIMIT greatest(1, least(coalesce(max_rows, 10000), 10000))),
    deleted AS (DELETE FROM edge_bff.email_outbox o USING gone WHERE o.outbox_id = gone.outbox_id RETURNING 1)
    SELECT count(*)::integer FROM deleted
$fn$;
COMMENT ON FUNCTION edge_bff.purge_email_outbox(integer) IS 'ERRORS R2-24 and the retention decided 2026-11-19 ("a", 30 days): deletes (at most max_rows per call, NULL or more than 10 000 = 10 000) the sent, failed, expired or suppressed outbox rows made more than 30 days ago, and those made more than 24 h ago of addresses with no row in edge_bff.users; never a pending or sending row; called hourly by edge-bff (store.py PURGES outbox, worker.Housekeeping).';
REVOKE ALL ON FUNCTION edge_bff.purge_email_outbox(integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION edge_bff.purge_email_outbox(integer) TO edge_bff_runtime;
COMMENT ON TABLE edge_bff.email_outbox IS 'EDGE emails to send (Resend, Idempotency-Key = idempotency_key). A code email carries expires_at = the code expiry and is never sent after it; payload is nulled once sent. A sent, failed, expired or suppressed row is deleted 30 days after it was made, or 24 h after for an address with no account (purge_email_outbox); edge_bff_runtime holds no DELETE.';

CREATE FUNCTION edge_bff.purge_email_hook_events(max_rows integer) RETURNS integer LANGUAGE sql SECURITY DEFINER
SET search_path = pg_catalog, edge_bff AS $fn$
    WITH gone AS (
        SELECT e.svix_id FROM edge_bff.email_hook_events e
        WHERE e.received_at < now() - interval '30 days'
        ORDER BY e.received_at, e.svix_id LIMIT greatest(1, least(coalesce(max_rows, 10000), 10000))),
    deleted AS (DELETE FROM edge_bff.email_hook_events e USING gone WHERE e.svix_id = gone.svix_id RETURNING 1)
    SELECT count(*)::integer FROM deleted
$fn$;
COMMENT ON FUNCTION edge_bff.purge_email_hook_events(integer) IS 'The retention decided 2026-11-19 ("a", 30 days): deletes (at most max_rows per call, NULL or more than 10 000 = 10 000) the webhook deliveries received more than 30 days ago; called hourly by edge-bff (store.py PURGES hook_events, worker.Housekeeping).';
REVOKE ALL ON FUNCTION edge_bff.purge_email_hook_events(integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION edge_bff.purge_email_hook_events(integer) TO edge_bff_runtime;
COMMENT ON TABLE edge_bff.email_hook_events IS 'Each signed Resend webhook delivery (svix-id) once; a repeated delivery changes nothing. Deleted 30 days after it was received (purge_email_hook_events); edge_bff_runtime holds no DELETE.';

DO $verify$
DECLARE
    fn text;
BEGIN
    -- the runtime still cannot delete from the outbox itself (20261116_003), and may run the purge only
    IF has_table_privilege('edge_bff_runtime', 'edge_bff.email_outbox', 'DELETE')
       OR has_table_privilege('edge_bff_runtime', 'edge_bff.email_outbox', 'TRUNCATE') THEN
        RAISE EXCEPTION 'edge_bff_runtime may delete from edge_bff.email_outbox';
    END IF;
    IF has_table_privilege('edge_bff_runtime', 'edge_bff.email_hook_events', 'DELETE')
       OR has_table_privilege('edge_bff_runtime', 'edge_bff.email_hook_events', 'TRUNCATE') THEN
        RAISE EXCEPTION 'edge_bff_runtime may delete from edge_bff.email_hook_events';
    END IF;
    FOR fn IN SELECT unnest(ARRAY['edge_bff.purge_email_outbox(integer)', 'edge_bff.purge_email_hook_events(integer)']) LOOP
        IF NOT has_function_privilege('edge_bff_runtime', fn, 'EXECUTE') OR has_function_privilege('public', fn, 'EXECUTE') THEN
            RAISE EXCEPTION '% is not for edge_bff_runtime only', fn;
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_proc WHERE oid = fn::regprocedure AND prosecdef
                       AND proconfig @> ARRAY['search_path=pg_catalog, edge_bff']) THEN
            RAISE EXCEPTION '% must be SECURITY DEFINER with a fixed search_path', fn;
        END IF;
    END LOOP;
    IF (SELECT count(*) FROM pg_indexes WHERE schemaname = 'edge_bff' AND tablename = 'email_outbox'
        AND indexname IN ('email_outbox_to_email_created', 'email_outbox_unsent')) <> 2 THEN
        RAISE EXCEPTION 'an index of edge_bff.email_outbox is missing';
    END IF;
END $verify$;
COMMIT;

-- Rollback (a new forward migration with this body; deploy an edge-bff that does not call the purge first):
-- BEGIN;
-- DROP FUNCTION edge_bff.purge_email_hook_events(integer);
-- DROP FUNCTION edge_bff.purge_email_outbox(integer);
-- DROP INDEX edge_bff.email_outbox_unsent, edge_bff.email_outbox_to_email_created;
-- COMMIT;
