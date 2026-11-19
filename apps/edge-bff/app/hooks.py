"""EDGE multi-user Phase 0 (EXEC-MU-ACCOUNTS; CONTRACT.md section 6): the hooks route exemption.

A caller outside the browser (a payment provider, the email provider's bounce webhook) cannot send EDGE's Origin, so
the Origin check of main.py `protections` skips exactly the path prefix HOOK_PREFIX; the body size cap and the security
headers stay. A hook route has no session and no CSRF token: it must verify a signature over the raw body
(`request._body`, buffered by `protections`) before it reads or changes anything.

Every route under HOOK_PREFIX is registered in HOOK_ROUTES, path -> the function that verifies its signature
(verify(headers, raw_body, secret) -> bool), and carries the dependency `signed(path, secret)` built from that entry:
it verifies the raw body before the handler runs, refuses 401 HOOK_SIGNATURE_INVALID otherwise, and hands the handler
the verified bytes. A registry entry therefore means verification, whatever the handler does (fix round, re-check
R1-15): tests/test_route_table.py fails on a route under the prefix that is missing here or does not carry `signed`
for its own path and verifier.
"""
from fastapi import Request

from .errors import Refusal

HOOK_PREFIX = '/api/v1/hooks/'

from .mailer import svix_verify  # noqa: E402

# Phase 1: the Resend webhook (bounces and complaints), verified by its Svix signature with RESEND_WEBHOOK_SECRET
# (verify(headers, raw_body, secret))
HOOK_ROUTES = {'/api/v1/hooks/email/resend': svix_verify}


def is_hook_path(path):
    return path.startswith(HOOK_PREFIX)


def signed(path, secret, registry=None):
    """The dependency of the hook route `path`: the raw body, once its signature verifies with `secret` (a value, or a
    function returning it at request time) by the route's verifier in the registry. A path without an entry fails when
    the route is built, not when a request comes."""
    verify = (HOOK_ROUTES if registry is None else registry)[path]

    async def signature(request: Request):
        raw = getattr(request, '_body', None) or await request.body()
        if not verify(request.headers, raw, secret() if callable(secret) else secret):
            raise Refusal(401, 'HOOK_SIGNATURE_INVALID')
        return raw
    signature.hook_path, signature.verifier = path, verify
    return signature
