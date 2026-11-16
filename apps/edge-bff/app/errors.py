"""EDGE multi-user Phase 0 (EXEC-MU-ACCOUNTS; CONTRACT.md section 3, ERRORS M471): one error shape for edge-bff's own
refusals, FastAPI's included: {"error": {"code", "message", "details"}}. The front-end decides by the code, never by
the status alone: UNAUTHENTICATED (401) goes to sign-in, CSRF_INVALID (403) re-reads the session once and retries once,
CAPABILITY_REQUIRED (403) keeps the session and shows that the feature is not open to this account.

Messages are plain English, like every EDGE interface label (EXEC-UI-1019B, user: "Ok 1 aja"), without internal names
(AGENTS.md "Gates and evidence" (d): each names what is wrong and how to go on).
"""
from fastapi.responses import JSONResponse

MESSAGES = {
    'UNAUTHENTICATED': 'Your session has ended or you are not signed in. Please sign in again.',
    'CSRF_INVALID': 'This request could not be verified. Reload the page and try again.',
    'CAPABILITY_REQUIRED': 'This feature is not part of your EDGE plan. Upgrade the plan to use it; you are still signed in.',
    'PLAN_EXPIRED': 'Your EDGE plan has ended. Renew it to use this again; you are still signed in.',
    'MFA_REQUIRED': 'This needs your sign-in code. Enter the code from your authenticator app, then try again.',
    'LIMIT_REACHED': "You have reached your plan's limit. Try again later, or upgrade the plan.",
    'SIGN_IN_RATE_LIMIT': 'Too many sign-in attempts. Wait a minute, then try again.',
    'INVALID_INPUT': 'Some fields are not valid. Check them and try again.',
    'NOT_FOUND': 'The page or item you asked for was not found.',
    'METHOD_NOT_ALLOWED': 'This kind of request is not supported here.',
    'REQUEST_REFUSED': 'This request could not be processed.',
}

# FastAPI's and Starlette's own refusals by status (a route raises HTTPException with one of these codes as its detail)
STATUS_CODES = {400: 'INVALID_INPUT', 401: 'UNAUTHENTICATED', 403: 'CSRF_INVALID', 404: 'NOT_FOUND',
                405: 'METHOD_NOT_ALLOWED', 422: 'INVALID_INPUT'}

# The capabilities a Phase 0 route may require, with the name the person sees (CONTRACT.md section 3 details)
CAPABILITY_NAMES = {'admin.manual': 'Manual agent (troubleshooting)'}


class Refusal(Exception):
    """A refusal in the contract's shape, raised from a dependency or a handler."""

    def __init__(self, status, code, details=None, headers=None):
        self.status, self.code, self.details, self.headers = status, code, details or {}, headers
        super().__init__(code)


def refusal(status, code, details=None, headers=None):
    return JSONResponse(status_code=status, headers=headers, content={'error': {
        'code': code, 'message': MESSAGES.get(code, MESSAGES['REQUEST_REFUSED']), 'details': details or {}}})


def capability_required(capability):
    return Refusal(403, 'CAPABILITY_REQUIRED', {'capability': capability,
                                                'display_name': CAPABILITY_NAMES.get(capability, capability)})


def http_refusal(exc):
    """A FastAPI/Starlette HTTPException: its detail when it is one of our codes, else the code of its status."""
    code = exc.detail if isinstance(exc.detail, str) and exc.detail in MESSAGES else \
        STATUS_CODES.get(exc.status_code, 'REQUEST_REFUSED')
    return refusal(exc.status_code, code, headers=getattr(exc, 'headers', None))


def validation_refusal(exc):
    """A body, query or path value FastAPI could not accept: 422 INVALID_INPUT naming the fields (their API names, as
    the page sends them), never the values."""
    fields = []
    for item in exc.errors():
        loc = [str(p) for p in item.get('loc', ()) if p not in ('body', 'query', 'path', 'header', 'cookie')]
        name = '.'.join(loc)
        if name and name not in fields:
            fields.append(name)
    return refusal(422, 'INVALID_INPUT', {'fields': fields[:20]} if fields else {})
