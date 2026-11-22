"""The payment providers behind one interface (CONTRACT.md 11):

    create_checkout(order, user, return_urls) -> {'provider', 'order_id', 'redirect_url' | None}
    verify_webhook(headers, raw) -> Event            (PaymentRefused when the signature or the body is not right)
    fetch_status(order_id) -> Event | None           (the provider's own record of the order)

and, for the hook registry (app/hooks.py HOOK_ROUTES), each provider's signature check as a plain function
verify(headers, raw, secret) -> bool, which `hooks.signed` runs before the handler reads the body.

`midtrans` is built only in its offline parts (verification/edge_multiuser/payments/MIDTRANS_RESEARCH.md sections 1-2):
the notification's signature_key (SHA512 of order_id + status_code + gross_amount + the Server Key), its status words,
its amount and its order number. Creating a Snap transaction and Get Status need the Midtrans account (the user's, in
the Midtrans phase): they raise PaymentNotConfigured, and nothing here opens a connection.
"""
import hashlib
import hmac
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

STATUSES = ('pending', 'settled', 'failed', 'expired', 'cancelled', 'refunded')
ORDER_ID = re.compile(r'[A-Za-z0-9_~.-]{1,50}')
TEST_SIGNATURE_HEADER = 'x-edge-test-signature'
WIB = timezone(timedelta(hours=7))   # Midtrans states its times in Jakarta time, without an offset
# the payload kept with an event (payment_events.payload) leaves these out: a signature is not part of what was paid
NOT_KEPT = ('signature_key', 'signature')
PAYLOAD_BYTES = 16384


class PaymentRefused(Exception):
    """A notification or a request the shell does not take: `field` names what is wrong, the message how to fix it."""

    def __init__(self, field_name, message):
        super().__init__(message)
        self.field = field_name


class PaymentNotConfigured(Exception):
    """A provider call the shell does not make yet (the Midtrans phase), or a provider not switched on."""


@dataclass(frozen=True)
class Event:
    """A provider's notification read in EDGE's words (payment_events)."""
    order_id: str
    event_key: str
    status: str
    amount_idr: int | None
    currency: str | None
    event_at: datetime | None
    payload: dict = field(default_factory=dict)


def valid_order_id(value):
    return isinstance(value, str) and ORDER_ID.fullmatch(value) is not None


def kept_payload(data):
    """The notification as kept: its own fields without a signature, at most PAYLOAD_BYTES (a larger one keeps its
    order fields only)."""
    kept = {k: v for k, v in data.items() if k not in NOT_KEPT}
    if len(json.dumps(kept, default=str).encode()) > PAYLOAD_BYTES:
        kept = {k: kept[k] for k in ('order_id', 'transaction_status', 'status_code', 'gross_amount', 'currency',
                                     'event_id', 'status', 'amount_idr') if k in kept}
    return kept


def body_of(raw):
    try:
        data = json.loads(raw or b'')
    except (ValueError, UnicodeDecodeError):
        raise PaymentRefused('body', 'The notification is not JSON. Send the provider\'s JSON body as it is.') from None
    if not isinstance(data, dict):
        raise PaymentRefused('body', 'The notification is not a JSON object. Send the provider\'s JSON body as it is.')
    return data


class Adapter:
    """One provider. `webhook`: it sends notifications to a hook route; `confirms`: a notification is applied only after
    the provider's own record (fetch_status) agrees with it (Midtrans' advice: MIDTRANS_RESEARCH.md section 2)."""
    name = ''
    webhook = False
    confirms = False

    def __init__(self, secret=''):
        self.secret = secret

    def create_checkout(self, order, user, return_urls):
        raise NotImplementedError

    def verify_webhook(self, headers, raw):
        raise PaymentRefused('provider', f'{self.name or "This provider"} sends no notifications.')

    def fetch_status(self, order_id):
        raise PaymentNotConfigured(f'{self.name or "This provider"} keeps no record EDGE can ask.')


# ---- manual: the admin activates the plan (the admin page) ---------------------------------------------------------------

class ManualAdapter(Adapter):
    name = 'manual'

    def create_checkout(self, order, user, return_urls):
        """No page to pay on: the admin activates the plan once the money has arrived (the admin page's plan action)."""
        return {'provider': self.name, 'order_id': order['order_id'], 'redirect_url': None}


# ---- test: signed fake notifications, for the tests ------------------------------------------------------------------------

def sign_test_provider(raw, secret):
    return hmac.new(secret.encode(), raw or b'', hashlib.sha256).hexdigest()


def verify_test_provider(headers, raw, secret):
    """The test provider's signature: HMAC-SHA256 of the raw body with EDGE_PAYMENTS_SECRET, hex, in
    X-Edge-Test-Signature."""
    given = headers.get(TEST_SIGNATURE_HEADER) or ''
    return bool(secret) and given.isascii() and hmac.compare_digest(given.lower(), sign_test_provider(raw, secret))


def iso_time(value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise PaymentRefused('event_at', 'event_at is an ISO 8601 time with its offset, e.g. 2026-11-23T10:00:00+07:00.')
    try:
        stamp = datetime.fromisoformat(value)
    except ValueError:
        raise PaymentRefused('event_at', 'event_at is an ISO 8601 time with its offset, e.g. 2026-11-23T10:00:00+07:00.') from None
    if stamp.tzinfo is None:
        raise PaymentRefused('event_at', 'event_at needs its offset, e.g. 2026-11-23T10:00:00+07:00, not 2026-11-23T10:00:00.')
    return stamp


class TestAdapter(Adapter):
    """The shell's own provider for the tests: a notification is {event_id, order_id, status (EDGE's words), amount_idr,
    currency, event_at}, signed with the secret; `records` stands in for the provider's own record (fetch_status), so a
    missed notification is reconciled."""
    name = 'test'
    webhook = True
    __test__ = False                  # not a pytest class

    def __init__(self, secret='', records=None):
        super().__init__(secret)
        self.records = {} if records is None else records

    def create_checkout(self, order, user, return_urls):
        return {'provider': self.name, 'order_id': order['order_id'],
                'redirect_url': f"{return_urls['finish']}?order_id={order['order_id']}"}

    def event_of(self, data):
        order_id, status = data.get('order_id'), data.get('status')
        if not valid_order_id(order_id):
            raise PaymentRefused('order_id', 'order_id is the order number EDGE made: 1-50 letters, digits or - _ ~ .')
        if status not in STATUSES:
            raise PaymentRefused('status', f'status is one of {", ".join(STATUSES)}.')
        amount = data.get('amount_idr')
        if amount is not None and (not isinstance(amount, int) or isinstance(amount, bool) or amount < 0):
            raise PaymentRefused('amount_idr', 'amount_idr is a whole number of rupiah, e.g. 50000.')
        key = data.get('event_id')
        if not isinstance(key, str) or not 1 <= len(key) <= 200:
            raise PaymentRefused('event_id', 'event_id is the provider\'s id of the event, 1-200 characters.')
        return Event(order_id, key, status, amount, data.get('currency'), iso_time(data.get('event_at')), kept_payload(data))

    def verify_webhook(self, headers, raw):
        if not verify_test_provider(headers, raw, self.secret):
            raise PaymentRefused('signature', 'The signature does not match. Sign the raw body with EDGE_PAYMENTS_SECRET.')
        return self.event_of(body_of(raw))

    def fetch_status(self, order_id):
        record = self.records.get(order_id)
        return None if record is None else self.event_of({'order_id': order_id, **record})


# ---- midtrans: the offline parts only -------------------------------------------------------------------------------------

# Midtrans' transaction_status in EDGE's words (MIDTRANS_RESEARCH.md section 2: success is settlement, or capture with
# fraud_status accept; a card's capture under review is still pending)
MIDTRANS_STATUS = {'pending': 'pending', 'settlement': 'settled', 'capture': 'settled', 'deny': 'failed', 'failure': 'failed',
                   'cancel': 'cancelled', 'expire': 'expired', 'refund': 'refunded', 'partial_refund': 'refunded'}


def midtrans_signature(order_id, status_code, gross_amount, server_key):
    """SHA512(order_id + status_code + gross_amount + ServerKey), hex, as Midtrans signs a notification."""
    return hashlib.sha512(f'{order_id}{status_code}{gross_amount}{server_key}'.encode()).hexdigest()


def midtrans_verify(headers, raw, secret):
    """A Midtrans notification's signature_key against the Server Key (EDGE_PAYMENTS_SECRET); the body's own fields are
    signed, so the raw body is read as JSON first."""
    if not secret:
        return False
    try:
        data = body_of(raw)
    except PaymentRefused:
        return False
    parts = [data.get(k) for k in ('order_id', 'status_code', 'gross_amount', 'signature_key')]
    if not all(isinstance(x, str) and x.isascii() for x in parts):
        return False
    return hmac.compare_digest(parts[3].lower(), midtrans_signature(*parts[:3], secret))


def midtrans_status(transaction_status, fraud_status=None):
    """EDGE's word for a Midtrans status, or None for one it does not know."""
    word = MIDTRANS_STATUS.get(transaction_status)
    if word == 'settled' and fraud_status not in (None, '', 'accept'):
        return 'failed' if fraud_status == 'deny' else 'pending'
    return word


def rupiah(gross_amount):
    """Midtrans' gross_amount ("10000.00", a string) as whole rupiah, or None when it is not a whole, non-negative amount."""
    if not isinstance(gross_amount, str):
        return None
    try:
        value = Decimal(gross_amount)
    except InvalidOperation:
        return None
    if not value.is_finite() or value < 0 or value != value.to_integral_value():
        return None
    return int(value)


def midtrans_time(value):
    """'2026-11-23 10:11:12' (Jakarta time) as an aware time, or None."""
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, '%Y-%m-%d %H:%M:%S').replace(tzinfo=WIB)
    except ValueError:
        return None


class MidtransAdapter(Adapter):
    name = 'midtrans'
    webhook = True
    confirms = True
    NOT_BUILT = ('Midtrans is not connected yet: creating a Snap payment and asking Get Status are built in the Midtrans '
                 'phase, with the account\'s Server Key (EXEC.md EXEC-MU-ACCOUNTS, step 7).')

    def event_of(self, data):
        order_id = data.get('order_id')
        if not valid_order_id(order_id):
            raise PaymentRefused('order_id', 'order_id is the order number EDGE made: 1-50 letters, digits or - _ ~ .')
        status = midtrans_status(data.get('transaction_status'), data.get('fraud_status'))
        if status is None:
            raise PaymentRefused('transaction_status', 'transaction_status is one Midtrans documents, e.g. settlement.')
        amount = rupiah(data.get('gross_amount'))
        # Midtrans sends no event id: the order, its status and the status code name the event (a resent one is the same)
        key = f"{order_id}:{data.get('transaction_status')}:{data.get('status_code')}"
        when = midtrans_time(data.get('settlement_time')) or midtrans_time(data.get('transaction_time'))
        return Event(order_id, key, status, amount, data.get('currency') or 'IDR', when, kept_payload(data))

    def verify_webhook(self, headers, raw):
        if not midtrans_verify(headers, raw, self.secret):
            raise PaymentRefused('signature_key', 'The signature_key does not match the Server Key of this environment.')
        return self.event_of(body_of(raw))

    def create_checkout(self, order, user, return_urls):
        raise PaymentNotConfigured(self.NOT_BUILT)

    def fetch_status(self, order_id):
        raise PaymentNotConfigured(self.NOT_BUILT)


ADAPTERS = {'manual': ManualAdapter, 'test': TestAdapter, 'midtrans': MidtransAdapter}
# the providers that send notifications, with their signature checks (app/hooks.py HOOK_ROUTES)
VERIFIERS = {'test': verify_test_provider, 'midtrans': midtrans_verify}


def adapter_for(provider, secret=''):
    if provider not in ADAPTERS:
        raise PaymentNotConfigured(f'{provider!r} is not a payment provider EDGE knows ({", ".join(ADAPTERS)}).')
    return ADAPTERS[provider](secret)
