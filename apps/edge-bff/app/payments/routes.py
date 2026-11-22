"""POST /api/v1/hooks/payments/<provider> (CONTRACT.md sections 6 and 11): a provider's notification of a payment.

One route per provider that sends notifications (adapters.VERIFIERS: test, midtrans), each registered in
app/hooks.py HOOK_ROUTES and carrying `hooks.signed` for its own path and verifier, so the raw body's signature is
checked with EDGE_PAYMENTS_SECRET before the handler reads it (401 HOOK_SIGNATURE_INVALID otherwise).

Off unless switched on: a route answers 404 NOT_FOUND, and logs `payments_hook_off` with the reason, while the accounts
switch is off or EDGE_PAYMENTS_PROVIDER does not name its provider (unset by default; config.validate refuses
'midtrans' until its phase and 'test' on the live site). How to turn it on: EDGE_PAYMENTS_PROVIDER=test and
EDGE_PAYMENTS_SECRET (at least 32 characters) on the beta.

A verified notification answers 200 with what it did ({"status": applied | duplicate | no_change | older |
amount_mismatch | unknown_order | held | ended}), so the provider does not send it again; one the shell cannot read
answers 400 INVALID_INPUT naming the field. A provider that confirms with its own record first (Midtrans' Get Status)
answers 503 SERVICE_UNAVAILABLE while that call is not built, so the provider retries later and nothing is applied
unconfirmed.
"""
import asyncio
import json
import logging

from fastapi import Depends
from fastapi.encoders import jsonable_encoder

from .. import hooks
from ..errors import Refusal
from .adapters import VERIFIERS, PaymentNotConfigured, PaymentRefused, adapter_for, body_of
from .orders import PaymentStore

logger = logging.getLogger('edge_bff.payments')


def hook_path(provider):
    return f'/api/v1/hooks/payments/{provider}'


def install(app, settings, store):
    payments = PaymentStore(store)

    def active(provider):
        async def on():
            why = ('accounts_off' if not settings.multiuser else
                   'provider_unset' if not settings.payments_provider else
                   'another_provider' if settings.payments_provider != provider else None)
            if why:
                logger.info(json.dumps({'event': 'payments_hook_off', 'provider': provider, 'why': why,
                                        'how': 'EDGE_PAYMENTS_PROVIDER and EDGE_PAYMENTS_SECRET (app/payments/routes.py)'}))
                raise Refusal(404, 'NOT_FOUND')
        return on

    def route(provider):
        path = hook_path(provider)

        async def notification(_on=Depends(active(provider)),
                               raw=Depends(hooks.signed(path, lambda: settings.payments_secret))):
            adapter = adapter_for(provider, settings.payments_secret)
            try:
                event = adapter.event_of(body_of(raw))       # the signature was checked by hooks.signed
            except PaymentRefused as refused:
                raise Refusal(400, 'INVALID_INPUT', {'fields': [refused.field]}) from None
            if adapter.confirms:
                try:
                    record = await asyncio.to_thread(adapter.fetch_status, event.order_id)
                except PaymentNotConfigured as missing:
                    logger.warning(json.dumps({'event': 'payment_not_confirmed', 'provider': provider,
                                               'order_id': event.order_id, 'why': str(missing)}))
                    raise Refusal(503, 'SERVICE_UNAVAILABLE') from None
                if record is None or record.status != event.status:
                    logger.warning(json.dumps({'event': 'payment_not_confirmed', 'provider': provider,
                                               'order_id': event.order_id, 'notified': event.status,
                                               'record': None if record is None else record.status}))
                    raise Refusal(503, 'SERVICE_UNAVAILABLE')
            result = await asyncio.to_thread(payments.apply_event, provider, event)
            return jsonable_encoder({'status': result.outcome})

        notification.__name__ = f'payment_hook_{provider}'
        app.post(path)(notification)

    for provider in VERIFIERS:
        route(provider)
    return payments
