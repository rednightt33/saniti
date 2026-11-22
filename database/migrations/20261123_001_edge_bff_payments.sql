-- EDGE multi-user, step 7: the payment shell (EXEC.md EXEC-MU-ACCOUNTS option A item 6; CONTRACT.md sections 6 and 11).
-- The user, 2026-11-20: "Kerangka pembayaran nanti saya. Siapkan dulu shellnya."; 2026-11-22: "Untuk kerangka
-- pembayaran, rencananya kita akan pakai Mitrans. Dengan pembayaran QRIS atau virtual account"; "1A 2A 3A" (the admin
-- page on the beta only; the plans read-only; Snap by redirect); and the go of the same day: "langkah 7 berkaitan dengan
-- pembuatan kerangka pembayaran, harap disiapkan saja infrastrukturnya. Untuk tesnya nanti kita buat fase tersendiri
-- karena akun Mitrans belum siap."
--
-- What it holds: one row per payment attempt (payment_orders: our own order number, new for every attempt, the
-- account, the plan, the period and the amount expected in rupiah) and every verified notification a provider sent
-- about it (payment_events, unique per provider and event). Midtrans' notification carries no user id of ours: the
-- order number we wrote links a payment to the account (verification/edge_multiuser/payments/MIDTRANS_RESEARCH.md
-- section 2). apps/edge-bff/app/payments/ applies an event in one transaction: the order, the event and the
-- subscription it starts or extends (FINDINGS.md section 4: a duplicate changes nothing, an older event is ignored, a
-- paid order never goes back, the amount and the currency must equal the order's).
--
-- No price, no plan and no provider account here: the prices, the periods, the grace period and Midtrans' keys are the
-- user's, in the Midtrans phase. Nothing writes these tables until a provider is switched on (EDGE_PAYMENTS_PROVIDER);
-- the shell's own provider for the tests is `test`.
--
-- Expand only: two new tables, and subscriptions.provider also allows 'midtrans' (its CHECK dropped and added again
-- with the wider list); an older edge-bff reads none of the new tables and writes only 'manual' and 'test'.
-- edge_bff_runtime reads, adds and updates an order (its status and its event time) and reads and adds an event; an
-- event is never changed or deleted (no UPDATE or DELETE), and an order is never deleted (bookkeeping). Grants are
-- table-level, as every EDGE grant (re-check R1-41). Refuses a second run. Forward-only; rollback block at the end.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';
DO $preflight$
BEGIN
    IF to_regnamespace('edge_bff') IS NULL OR NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'edge_bff_runtime') THEN
        RAISE EXCEPTION 'the schema edge_bff or the role edge_bff_runtime is missing: apply the edge_bff migrations first';
    END IF;
    IF to_regclass('edge_bff.subscriptions') IS NULL OR to_regclass('edge_bff.plans') IS NULL THEN
        RAISE EXCEPTION 'edge_bff.subscriptions or edge_bff.plans is missing: apply 20261117_003 first';
    END IF;
    IF to_regclass('edge_bff.payment_orders') IS NOT NULL OR to_regclass('edge_bff.payment_events') IS NOT NULL THEN
        RAISE EXCEPTION 'edge_bff.payment_orders or edge_bff.payment_events exists: this migration ran already';
    END IF;
END $preflight$;

-- ---- subscriptions.provider: 'midtrans' as well -----------------------------------------------------------------------
DO $provider$
DECLARE
    found text;
BEGIN
    -- the CHECK of 20261117_003 has no name of its own: find it by its definition
    SELECT conname INTO found FROM pg_constraint
     WHERE conrelid = 'edge_bff.subscriptions'::regclass AND contype = 'c'
       AND pg_get_constraintdef(oid) LIKE '%provider%' AND pg_get_constraintdef(oid) LIKE '%manual%';
    IF found IS NULL THEN
        RAISE EXCEPTION 'the CHECK on edge_bff.subscriptions.provider was not found';
    END IF;
    EXECUTE format('ALTER TABLE edge_bff.subscriptions DROP CONSTRAINT %I', found);
END $provider$;
ALTER TABLE edge_bff.subscriptions ADD CONSTRAINT subscriptions_provider
    CHECK (provider IN ('manual', 'test', 'midtrans'));
COMMENT ON COLUMN edge_bff.subscriptions.provider IS
    'Who made the subscription: manual (the admin page or a script), test (the tests), midtrans (a payment applied by '
    'apps/edge-bff/app/payments, the order number in provider_ref).';

-- ---- payment_orders ----------------------------------------------------------------------------------------------------
CREATE TABLE edge_bff.payment_orders (
    order_id text PRIMARY KEY CONSTRAINT payment_orders_order_id CHECK (order_id ~ '^[A-Za-z0-9_~.-]{1,50}$'),
    user_id bigint NOT NULL REFERENCES edge_bff.users(user_id) ON DELETE RESTRICT,
    plan_key text NOT NULL REFERENCES edge_bff.plans(plan_key),
    period_days integer NOT NULL CONSTRAINT payment_orders_period CHECK (period_days BETWEEN 1 AND 3660),
    amount_idr bigint NOT NULL CONSTRAINT payment_orders_amount CHECK (amount_idr BETWEEN 1 AND 1000000000000),
    currency text NOT NULL DEFAULT 'IDR' CONSTRAINT payment_orders_currency CHECK (currency = 'IDR'),
    provider text NOT NULL CONSTRAINT payment_orders_provider CHECK (provider IN ('manual', 'test', 'midtrans')),
    status text NOT NULL DEFAULT 'pending'
        CONSTRAINT payment_orders_status CHECK (status IN ('pending', 'settled', 'failed', 'expired', 'cancelled', 'refunded')),
    held_reason text CONSTRAINT payment_orders_held CHECK (held_reason IN ('plan_conflict', 'settled_after_end', 'refund_review')),
    expires_at timestamptz NOT NULL,
    paid_at timestamptz,
    subscription_id bigint REFERENCES edge_bff.subscriptions(subscription_id) ON DELETE SET NULL,
    last_event_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT payment_orders_paid CHECK ((status IN ('settled', 'refunded')) = (paid_at IS NOT NULL)),
    CONSTRAINT payment_orders_expiry CHECK (expires_at > created_at)
);
CREATE INDEX payment_orders_user_time ON edge_bff.payment_orders(user_id, created_at DESC);
-- the orders the reconciliation asks the provider about: still pending, oldest expiry first
CREATE INDEX payment_orders_pending ON edge_bff.payment_orders(expires_at) WHERE status = 'pending';
COMMENT ON TABLE edge_bff.payment_orders IS
    'Step 7, the payment shell: one payment attempt of an account (a new order number for every attempt, as Midtrans '
    'uses an order number once). apps/edge-bff/app/payments applies its provider''s notifications (payment_events) in '
    'one transaction with the subscription it starts or extends. Kept for bookkeeping: never deleted, and an account '
    'with orders is not deleted by a cascade.';
COMMENT ON COLUMN edge_bff.payment_orders.order_id IS
    'Our own opaque order number, sent to the provider and returned in its notification (Midtrans: at most 50 '
    'characters, letters, digits and - _ ~ .); never a user id, a username or an email';
COMMENT ON COLUMN edge_bff.payment_orders.user_id IS 'The account that pays; the notification is linked to it only through this row';
COMMENT ON COLUMN edge_bff.payment_orders.plan_key IS 'The plan the payment buys';
COMMENT ON COLUMN edge_bff.payment_orders.period_days IS 'How many days of the plan the payment buys (a renewal adds them to a live subscription of the same plan)';
COMMENT ON COLUMN edge_bff.payment_orders.amount_idr IS 'The amount expected, in whole rupiah; a notification with another amount changes nothing';
COMMENT ON COLUMN edge_bff.payment_orders.currency IS 'Always IDR (Midtrans QRIS and VA)';
COMMENT ON COLUMN edge_bff.payment_orders.provider IS 'manual (the admin activates the plan), test (the tests), midtrans';
COMMENT ON COLUMN edge_bff.payment_orders.status IS
    'pending (waiting), settled (paid, applied once), failed, expired, cancelled (ended unpaid), refunded; a settled '
    'order never goes back to pending, failed or expired';
COMMENT ON COLUMN edge_bff.payment_orders.held_reason IS
    'Why a settled or refunded order was not applied to the subscription and waits for the admin: plan_conflict (the '
    'account holds another live plan), settled_after_end (paid after it had ended), refund_review (a refund)';
COMMENT ON COLUMN edge_bff.payment_orders.expires_at IS 'When the attempt lapses unpaid (Midtrans: a VA 24 h, QRIS 15 minutes by default)';
COMMENT ON COLUMN edge_bff.payment_orders.paid_at IS 'When the paid notification was applied';
COMMENT ON COLUMN edge_bff.payment_orders.subscription_id IS 'The subscription the payment started or extended';
COMMENT ON COLUMN edge_bff.payment_orders.last_event_at IS 'The provider''s time of the newest event applied; an older event is ignored';
COMMENT ON COLUMN edge_bff.payment_orders.created_at IS 'When the order was made';
COMMENT ON COLUMN edge_bff.payment_orders.updated_at IS 'When the order last changed';

-- ---- payment_events ----------------------------------------------------------------------------------------------------
CREATE TABLE edge_bff.payment_events (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    provider text NOT NULL CONSTRAINT payment_events_provider CHECK (provider IN ('test', 'midtrans')),
    event_key text NOT NULL CONSTRAINT payment_events_key CHECK (char_length(event_key) BETWEEN 1 AND 200),
    order_id text NOT NULL CONSTRAINT payment_events_order_id CHECK (order_id ~ '^[A-Za-z0-9_~.-]{1,50}$'),
    status text NOT NULL
        CONSTRAINT payment_events_status CHECK (status IN ('pending', 'settled', 'failed', 'expired', 'cancelled', 'refunded')),
    amount_idr bigint,
    currency text,
    event_at timestamptz,
    payload jsonb NOT NULL CONSTRAINT payment_events_payload CHECK (jsonb_typeof(payload) = 'object' AND octet_length(payload::text) <= 16384),
    applied boolean NOT NULL,
    outcome text NOT NULL CONSTRAINT payment_events_outcome
        CHECK (outcome IN ('applied', 'no_change', 'older', 'amount_mismatch', 'unknown_order', 'held', 'ended')),
    received_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT payment_events_unique UNIQUE (provider, event_key),
    CONSTRAINT payment_events_applied CHECK (applied = (outcome = 'applied'))
);
CREATE INDEX payment_events_order ON edge_bff.payment_events(order_id, received_at);
COMMENT ON TABLE edge_bff.payment_events IS
    'Step 7, the payment shell: every verified notification of a payment provider, once (unique per provider and '
    'event key, so a resent notification changes nothing), with what it did to its order (outcome). Never changed or '
    'deleted.';
COMMENT ON COLUMN edge_bff.payment_events.provider IS 'test or midtrans (manual has no notifications)';
COMMENT ON COLUMN edge_bff.payment_events.event_key IS
    'The provider''s identity of the event: the test provider''s event id; for Midtrans, which sends no event id, the '
    'order, the transaction status and the status code';
COMMENT ON COLUMN edge_bff.payment_events.order_id IS 'Our order number the event names (an event for an order we do not know is kept, outcome unknown_order)';
COMMENT ON COLUMN edge_bff.payment_events.status IS 'The event read in our words: pending, settled (paid), failed, expired, cancelled, refunded';
COMMENT ON COLUMN edge_bff.payment_events.amount_idr IS 'The amount the event states, in whole rupiah';
COMMENT ON COLUMN edge_bff.payment_events.currency IS 'The currency the event states';
COMMENT ON COLUMN edge_bff.payment_events.event_at IS 'The provider''s time of the event, when it states one';
COMMENT ON COLUMN edge_bff.payment_events.payload IS
    'The notification as verified, without its signature; never a key or a secret (the provider''s notification holds none)';
COMMENT ON COLUMN edge_bff.payment_events.applied IS 'Whether the event changed its order (outcome applied)';
COMMENT ON COLUMN edge_bff.payment_events.outcome IS
    'applied; no_change (it repeats the order''s state); older (older than the order''s last event); amount_mismatch '
    '(another amount or currency than the order''s); unknown_order; held (left to the admin, the order''s held_reason); '
    'ended (the order had ended before)';
COMMENT ON COLUMN edge_bff.payment_events.received_at IS 'When edge-bff received it';

GRANT SELECT, INSERT, UPDATE ON edge_bff.payment_orders TO edge_bff_runtime;
GRANT SELECT, INSERT ON edge_bff.payment_events TO edge_bff_runtime;
GRANT USAGE ON SEQUENCE edge_bff.payment_events_event_id_seq TO edge_bff_runtime;

DO $verify$
BEGIN
    IF EXISTS (SELECT 1 FROM (VALUES ('edge_bff.payment_orders', 'SELECT'), ('edge_bff.payment_orders', 'INSERT'),
                                     ('edge_bff.payment_orders', 'UPDATE'), ('edge_bff.payment_events', 'SELECT'),
                                     ('edge_bff.payment_events', 'INSERT')) AS needed(name, privilege)
               WHERE NOT has_table_privilege('edge_bff_runtime', needed.name, needed.privilege))
       OR has_table_privilege('edge_bff_runtime', 'edge_bff.payment_orders', 'DELETE')
       OR has_table_privilege('edge_bff_runtime', 'edge_bff.payment_events', 'UPDATE')
       OR has_table_privilege('edge_bff_runtime', 'edge_bff.payment_events', 'DELETE')
       OR has_table_privilege('edge_bff_runtime', 'edge_bff.payment_orders', 'TRUNCATE, REFERENCES, TRIGGER')
       OR has_table_privilege('edge_bff_runtime', 'edge_bff.payment_events', 'TRUNCATE, REFERENCES, TRIGGER')
       OR EXISTS (SELECT 1 FROM pg_attribute WHERE attrelid IN ('edge_bff.payment_orders'::regclass,
                  'edge_bff.payment_events'::regclass) AND attacl IS NOT NULL) THEN
        RAISE EXCEPTION 'verify: edge_bff_runtime reads, adds and updates orders, reads and adds events, deletes neither, and holds no column grant';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'edge_bff.subscriptions'::regclass
                   AND conname = 'subscriptions_provider' AND pg_get_constraintdef(oid) LIKE '%midtrans%') THEN
        RAISE EXCEPTION 'verify: subscriptions.provider does not allow midtrans';
    END IF;
END $verify$;
COMMIT;

-- Rollback (a new forward migration with this body, once no edge-bff that reads the tables runs and no subscription
-- names midtrans):
-- BEGIN;
-- DROP TABLE edge_bff.payment_events;
-- DROP TABLE edge_bff.payment_orders;
-- ALTER TABLE edge_bff.subscriptions DROP CONSTRAINT subscriptions_provider;
-- ALTER TABLE edge_bff.subscriptions ADD CONSTRAINT subscriptions_provider CHECK (provider IN ('manual', 'test'));
-- COMMIT;
