"""Orders, events and the state machine (FINDINGS.md section 4, "Payments"; migration 20261123_001).

An order is one payment attempt: its own opaque number (new for every attempt), the account, the plan, the period and
the amount in rupiah. A provider's notification is applied in ONE transaction with the order locked:

    pending  -> settled    (paid) the subscription is started, or extended when the account holds the same plan live
             -> failed | expired | cancelled         (ended unpaid)
    settled  -> refunded   held for the admin (refund_review): the subscription is not changed by a refund
    an ended order told it was paid                  held for the admin (settled_after_end); its status stays
    paid while the account holds another live plan  settled, held for the admin (plan_conflict), the subscription unchanged

and never otherwise: a notification already received (the same provider and event key) changes nothing; one older than
the order's last applied event is ignored; a settled order never goes back to pending, failed or expired; an amount or a
currency other than the order's changes nothing (logged as refused). Every notification is kept once in payment_events
with what it did (its outcome). The admin's decision on a held order is the admin page's plan action, as today.

`reconcile()` asks the provider's own record (Adapter.fetch_status) about the pending orders a notification may have
missed, and ends a pending order past its expiry that the provider has no record of. It runs when called; the loop that
calls it waits for the Midtrans phase (with Get Status).
"""
import json
import logging
import secrets
from dataclasses import dataclass

from psycopg.types.json import Jsonb

from .adapters import PaymentNotConfigured, valid_order_id

logger = logging.getLogger('edge_bff.payments')

ENDED = ('failed', 'expired', 'cancelled')


@dataclass(frozen=True)
class Outcome:
    outcome: str                  # applied, duplicate, no_change, older, amount_mismatch, unknown_order, held, ended
    order_id: str
    status: str | None = None     # the order's status afterwards
    held_reason: str | None = None


class Duplicate(Exception):
    pass


def new_order_id():
    """An opaque order number: 'edge-' and 24 hex digits (29 characters; Midtrans takes at most 50, letters, digits and
    - _ ~ .). It names no account."""
    return 'edge-' + secrets.token_hex(12)


class PaymentStore:
    def __init__(self, store):
        self.store = store

    def create_order(self, user_id, plan_key, period_days, amount_idr, provider, ttl_seconds=86400):
        """A pending order of `amount_idr` rupiah for `period_days` of `plan_key`, lapsing after `ttl_seconds` unpaid.
        The prices and periods are the user's (the Midtrans phase): this only records what the caller names."""
        order_id = new_order_id()
        with self.store.connect() as c:
            return c.execute('''INSERT INTO edge_bff.payment_orders(order_id, user_id, plan_key, period_days, amount_idr,
                    provider, expires_at) VALUES (%s, %s, %s, %s, %s, %s, now() + make_interval(secs => %s))
                RETURNING *''', (order_id, user_id, plan_key, period_days, amount_idr, provider, ttl_seconds)).fetchone()

    def order(self, order_id):
        with self.store.connect() as c:
            return c.execute('SELECT * FROM edge_bff.payment_orders WHERE order_id = %s', (order_id,)).fetchone()

    def events(self, order_id):
        with self.store.connect() as c:
            return c.execute('SELECT * FROM edge_bff.payment_events WHERE order_id = %s ORDER BY event_id',
                             (order_id,)).fetchall()

    # ---- the state machine --------------------------------------------------------------------------------------------

    def apply_event(self, provider, event):
        """Apply one verified event of `provider` (adapters.Event); returns an Outcome. One transaction: the order
        locked, the change, the subscription, the event row; a duplicate rolls all of it back."""
        if not valid_order_id(event.order_id):
            return Outcome('unknown_order', str(event.order_id))
        try:
            with self.store.connect() as c:
                result = self._apply(c, provider, event)
                kept = c.execute('''INSERT INTO edge_bff.payment_events(provider, event_key, order_id, status, amount_idr,
                        currency, event_at, payload, applied, outcome) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (provider, event_key) DO NOTHING RETURNING event_id''',
                    (provider, event.event_key, event.order_id, event.status, event.amount_idr, event.currency,
                     event.event_at, Jsonb(event.payload), result.outcome == 'applied', result.outcome)).fetchone()
                if kept is None:
                    raise Duplicate()
        except Duplicate:
            result = Outcome('duplicate', event.order_id)
        level = logging.WARNING if result.outcome in ('amount_mismatch', 'unknown_order', 'held') else logging.INFO
        logger.log(level, json.dumps({'event': 'payment_event', 'provider': provider, 'order_id': event.order_id,
                                      'status': event.status, 'outcome': result.outcome, 'order_status': result.status,
                                      'held_reason': result.held_reason}))
        return result

    def _apply(self, c, provider, event):
        # a notification seen before changes nothing, whatever it says now (checked under the order's lock, so two
        # copies arriving together are applied once; the unique key catches an unknown order's copies)
        order = c.execute('SELECT * FROM edge_bff.payment_orders WHERE order_id = %s FOR UPDATE',
                          (event.order_id,)).fetchone()
        if c.execute('SELECT 1 FROM edge_bff.payment_events WHERE provider = %s AND event_key = %s',
                     (provider, event.event_key)).fetchone():
            raise Duplicate()
        if order is None or order['provider'] != provider:
            return Outcome('unknown_order', event.order_id)
        current = order['status']
        if event.status in ('pending', 'settled') and (event.amount_idr != order['amount_idr']
                                                    or (event.currency or 'IDR') != order['currency']):
            return Outcome('amount_mismatch', event.order_id, current)
        if event.event_at is not None and order['last_event_at'] is not None and event.event_at < order['last_event_at']:
            return Outcome('older', event.order_id, current)
        stamp = event.event_at

        def update(status, **more):
            sets = ', '.join(f'{k} = %s' for k in more)
            c.execute(f'''UPDATE edge_bff.payment_orders SET status = %s, updated_at = now(),
                    last_event_at = greatest(last_event_at, coalesce(%s, now())){", " + sets if sets else ""}
                WHERE order_id = %s''', (status, stamp, *more.values(), event.order_id))

        if current == 'pending':
            if event.status == 'pending':
                return Outcome('no_change', event.order_id, current)
            if event.status in ENDED:
                update(event.status)
                return Outcome('applied', event.order_id, event.status)
            if event.status == 'settled':
                subscription, held = self._subscribe(c, order)
                # one statement: the status and paid_at change together (CHECK payment_orders_paid)
                c.execute('''UPDATE edge_bff.payment_orders SET status = 'settled', paid_at = now(), subscription_id = %s,
                        held_reason = %s, updated_at = now(), last_event_at = greatest(last_event_at, coalesce(%s, now()))
                    WHERE order_id = %s''', (subscription, held, stamp, event.order_id))
                return Outcome('held' if held else 'applied', event.order_id, 'settled', held)
            return Outcome('no_change', event.order_id, current)          # a refund of an order never paid
        if current == 'settled':
            if event.status == 'refunded':
                update('refunded', held_reason='refund_review')
                return Outcome('held', event.order_id, 'refunded', 'refund_review')
            return Outcome('no_change', event.order_id, current)          # a paid order never goes back
        if current in ENDED and event.status == 'settled':
            update(current, held_reason='settled_after_end')
            return Outcome('held', event.order_id, current, 'settled_after_end')
        return Outcome('ended', event.order_id, current)

    def _subscribe(self, c, order):
        """Start or extend the account's subscription for a paid order: (subscription_id, held_reason). The same plan
        live is extended by the period from its end; no live plan starts one now; another live plan (or one without an
        end) is left to the admin (plan_conflict)."""
        live = c.execute('''SELECT subscription_id, plan_key, expires_at, expires_at IS NULL OR expires_at > now() AS live
            FROM edge_bff.subscriptions WHERE user_id = %s AND status = 'active' FOR UPDATE''',
                         (order['user_id'],)).fetchone()
        if live is not None and live['live']:
            if live['plan_key'] != order['plan_key'] or live['expires_at'] is None:
                return None, 'plan_conflict'
            c.execute('''UPDATE edge_bff.subscriptions SET expires_at = expires_at + make_interval(days => %s),
                    last_event_at = now() WHERE subscription_id = %s''', (order['period_days'], live['subscription_id']))
            return live['subscription_id'], None
        if live is not None:                                   # an active row whose end has passed
            c.execute("UPDATE edge_bff.subscriptions SET status = 'expired', last_event_at = now() WHERE subscription_id = %s",
                      (live['subscription_id'],))
        row = c.execute('''INSERT INTO edge_bff.subscriptions(user_id, plan_key, status, expires_at, provider, provider_ref,
                last_event_at) VALUES (%s, %s, 'active', now() + make_interval(days => %s), %s, %s, now())
            RETURNING subscription_id''', (order['user_id'], order['plan_key'], order['period_days'], order['provider'],
                                           order['order_id'])).fetchone()
        return row['subscription_id'], None

    # ---- reconciliation -----------------------------------------------------------------------------------------------

    def reconcile(self, provider, adapter, limit=50):
        """The pending orders of `provider`, oldest expiry first: the provider's own record applied as an event (key
        'reconcile:<order>:<status>'), and a pending order past its expiry that the provider has no record of ended
        (expired). Returns {order_id: outcome}."""
        with self.store.connect() as c:
            pending = c.execute('''SELECT order_id, expires_at <= now() AS lapsed FROM edge_bff.payment_orders
                WHERE status = 'pending' AND provider = %s ORDER BY expires_at LIMIT %s''', (provider, limit)).fetchall()
        done = {}
        for row in pending:
            try:
                record = adapter.fetch_status(row['order_id'])
            except PaymentNotConfigured:
                record = None
            if record is not None and record.status != 'pending':
                found = record.__class__(record.order_id, f"reconcile:{record.order_id}:{record.status}", record.status,
                                         record.amount_idr, record.currency, record.event_at,
                                         {**record.payload, 'reconciled': True})
                done[row['order_id']] = self.apply_event(provider, found).outcome
            elif row['lapsed']:
                with self.store.connect() as c:
                    ended = c.execute('''UPDATE edge_bff.payment_orders SET status = 'expired', updated_at = now()
                        WHERE order_id = %s AND status = 'pending' RETURNING order_id''', (row['order_id'],)).fetchone()
                done[row['order_id']] = 'expired' if ended else 'no_change'
        return done
