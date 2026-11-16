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
    'FORBIDDEN': 'This request is not allowed for your account.',
    'INVALID_CREDENTIALS': 'The login or password is not correct. Check them and try again.',
    'ORIGIN_REJECTED': 'This request did not come from the EDGE page. Open EDGE again and retry from there.',
    'REQUEST_TOO_LARGE': 'This request is too large. Send less at once and try again.',
    'SERVICE_UNAVAILABLE': 'EDGE cannot answer right now. Wait a moment, then try again.',
    'NOT_READY': 'EDGE is starting. Wait a moment, then try again.',
    'TERMINAL_UNAVAILABLE': 'Market data cannot be reached right now. Wait a moment, then try again.',
    'ORC_UNAVAILABLE': 'The assistant cannot be reached right now. Wait a moment, then try again.',
    'MODELS_UNAVAILABLE': 'The list of models cannot be read right now. Wait a moment, then try again.',
    'RUN_NOT_FOUND': 'This question was not found.',
    'RUN_IN_PROGRESS': 'Another question is still being answered. Wait for it to finish or stop it first.',
    'SUBMISSION_CONFLICT': 'This request was already sent with different content. Send it again as a new request.',
    'QUEUE_FULL': 'Too many requests are waiting. Wait for one to finish, then try again.',
    'BACKTEST_NOT_READY': 'Backtests are not available right now. Wait a moment, then try again.',
    'BACKTEST_NOT_FOUND': 'This backtest was not found.',
    'RESULT_INTEGRITY': 'This result could not be read back correctly. Run the backtest again.',
    'CONVERSATION_NOT_FOUND': 'This conversation was not found.',
    'CONVERSATION_EXPIRED': 'This conversation has expired and can no longer be continued. Start a new one.',
    'CONVERSATION_RUNNING': 'This conversation is still being answered. Wait for it to finish, then try again.',
    'RESPONSE_NOT_AVAILABLE': 'This answer is not available yet. Wait for it to finish, then try again.',
    'EXPORT_NOT_FOUND': 'This download was not found or has expired. Export the table again.',
    'EXPORT_FAILED': 'The table could not be exported. Try again in a moment.',
    'OUTPUT_NOT_FOUND': 'This table was not found in the answer.',
    'PIN_LIMIT': 'Too many answers are pinned in this conversation. Unpin one, then try again.',
    'BRANCH_FAILED': 'A new conversation could not be started from this answer. Try again in a moment.',
    # EXEC-MU-ACCOUNTS Phase 1 (CONTRACT.md section 4b): the account preferences
    'PREFERENCE_CONFLICT': 'This setting was changed on another device. The current value is attached; merge it and save again.',
    # EXEC-MU-ACCOUNTS Phase 1 (CONTRACT.md section 4): registration, codes, passwords and MFA
    'CODE_INVALID_OR_EXPIRED': 'This code is wrong, has expired or was already used. Check the latest EDGE email, or ask for a new code.',
    'USERNAME_TAKEN': 'This username is already taken. Choose another one and send it with the same code.',
    'EMAIL_NOT_VERIFIED': 'Your email address is not verified yet. Enter the code from the EDGE email, or ask for a new code.',
    'PASSWORD_BREACHED': 'This password appears in known data breaches. Choose a different password.',
    'CURRENT_PASSWORD_INVALID': 'Your current password is not correct. Check it and try again.',
    'MFA_CODE_INVALID': 'This sign-in code is not correct or was already used. Enter the current code from your authenticator app, or an unused recovery code.',
    'MFA_NOT_ENROLLED': 'Two-step sign-in is not set up for this account yet. Set it up first, then enter the code.',
    'HOOK_SIGNATURE_INVALID': 'The webhook signature could not be verified. Check the signing secret of the webhook.',
    'PREFERENCE_LIMIT': 'Your account keeps too many settings or too large a setting. Remove some, then save again.',
}

# FastAPI's and Starlette's own refusals by status (a route raises HTTPException with one of these codes as its detail)
# A 403 is FORBIDDEN, which the clients do not retry: only the CSRF check (main.py write) answers CSRF_INVALID, and it
# raises it explicitly, never through an HTTPException
STATUS_CODES = {400: 'INVALID_INPUT', 401: 'UNAUTHENTICATED', 403: 'FORBIDDEN', 404: 'NOT_FOUND',
                405: 'METHOD_NOT_ALLOWED', 422: 'INVALID_INPUT'}

# The capabilities a Phase 0 route may require, with the name the person sees (CONTRACT.md section 3 details)
CAPABILITY_NAMES = {'admin.manual': 'Manual agent (troubleshooting)'}


class Refusal(Exception):
    """A refusal in the contract's shape, raised from a dependency or a handler."""

    def __init__(self, status, code, details=None, headers=None):
        self.status, self.code, self.details, self.headers = status, code, details or {}, headers
        super().__init__(code)


def message_of(code, status):
    """The code's message; a code without one (a code relayed from another service) gets the message of its status
    class, so every refusal carries a message."""
    return MESSAGES.get(code) or MESSAGES['SERVICE_UNAVAILABLE' if status >= 500 else 'REQUEST_REFUSED']


def refusal(status, code, details=None, headers=None):
    return JSONResponse(status_code=status, headers=headers, content={'error': {
        'code': code, 'message': message_of(code, status), 'details': details or {}}})


def capability_required(capability):
    return Refusal(403, 'CAPABILITY_REQUIRED', {'capability': capability,
                                                'display_name': CAPABILITY_NAMES.get(capability, capability)})


def http_refusal(exc):
    """A FastAPI/Starlette HTTPException: its detail when it is one of our codes, else the code of its status."""
    code = exc.detail if isinstance(exc.detail, str) and exc.detail in MESSAGES and exc.detail != 'CSRF_INVALID' else \
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
