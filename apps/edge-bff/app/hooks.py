"""EDGE multi-user Phase 0 (EXEC-MU-ACCOUNTS; CONTRACT.md section 6): the hooks route exemption.

A caller outside the browser (a payment provider, the email provider's bounce webhook) cannot send EDGE's Origin, so
the Origin check of main.py `protections` skips exactly the path prefix HOOK_PREFIX; the body size cap and the security
headers stay. A hook route has no session and no CSRF token: it must verify a signature over the raw body
(`request._body`, buffered by `protections`) before it reads or changes anything.

Every route under HOOK_PREFIX is registered in HOOK_ROUTES, path -> the function that verifies its signature
(verify(headers, raw_body) -> bool). tests/test_route_table.py fails on a route under the prefix that is missing here.
No hook route exists in Phase 0.
"""
HOOK_PREFIX = '/api/v1/hooks/'

from .mailer import svix_verify  # noqa: E402

# Phase 1: the Resend webhook (bounces and complaints), verified by its Svix signature with RESEND_WEBHOOK_SECRET
# (verify(headers, raw_body, secret))
HOOK_ROUTES = {'/api/v1/hooks/email/resend': svix_verify}


def is_hook_path(path):
    return path.startswith(HOOK_PREFIX)
