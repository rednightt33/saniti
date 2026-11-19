"""EDGE multi-user Phase 0 (EXEC-MU-ACCOUNTS; CONTRACT.md section 3, ERRORS M471): one error shape for edge-bff's own
refusals, FastAPI's included: {"error": {"code", "message", "details"}}. The front-end decides by the code, never by
the status alone: UNAUTHENTICATED (401) goes to sign-in, CSRF_INVALID (403) re-reads the session once and retries once,
CAPABILITY_REQUIRED (403) keeps the session and shows that the feature is not open to this account.

Messages are plain English, like every EDGE interface label (EXEC-UI-1019B, user: "Ok 1 aja"), without internal names
(AGENTS.md "Gates and evidence" (d): each names what is wrong and how to go on).
"""
import math

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
    # EXEC-MU-ACCOUNTS Phase 3c (CONTRACT.md 8b "3c in detail"): a header only EDGE itself sets towards the market data
    'HEADER_NOT_ALLOWED': 'This request carries a header that only EDGE itself may set. Reload the page and try again without it.',
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
    'MFA_LOCKED': 'Too many wrong codes, so this way of signing in is locked. Wait 24 hours or reset your password by email; an operator can also unlock it.',
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
# C1 Phase 3a F3: the names the person sees come from the catalog (edge_bff.capabilities.display_name), loaded by
# Auth.refresh_names at start and again at most every NAMES_SECONDS when a route refuses; never the internal key.
# Re-check R2-15: the plans' names too (edge_bff.plans.display_name), for the ended plan of PLAN_EXPIRED
_names = {}
_plan_names = {}
UNNAMED = 'This part of EDGE'


def set_display_names(names, plans=None):
    """Replaces the catalog's names (capability key -> display name) and, when given, the plans' (plan key -> name)."""
    global _names, _plan_names
    _names = dict(names)
    if plans is not None:
        _plan_names = dict(plans)


def display_name(capability):
    """The name the person sees for a capability: the catalog's, an item <family>:<id> as the family's name and the id,
    the Phase 0 table, else a plain phrase (an internal key is never shown)."""
    if capability in _names:
        return _names[capability]
    family, sep, item = capability.partition(':')
    if sep and family in _names:
        return f'{_names[family]}: {item}'
    return CAPABILITY_NAMES.get(capability, UNNAMED)


class Refusal(Exception):
    """A refusal in the contract's shape, raised from a dependency or a handler."""

    def __init__(self, status, code, details=None, headers=None):
        self.status, self.code, self.details, self.headers = status, code, details or {}, headers
        super().__init__(code)


def message_of(code, status):
    """The code's message; a code without one (a code relayed from another service) gets the message of its status
    class, so every refusal carries a message."""
    return MESSAGES.get(code) or MESSAGES['SERVICE_UNAVAILABLE' if status >= 500 else 'REQUEST_REFUSED']


def wait_words(seconds):
    """A wait in words ('30 seconds', '15 minutes', '24 hours'), rounded up; '' when unknown."""
    if not isinstance(seconds, (int, float)) or isinstance(seconds, bool) or seconds < 0:
        return ''
    count, unit = math.ceil(seconds), 'second'
    if count >= 60:
        count, unit = math.ceil(count / 60), 'minute'
        if count >= 60:
            count, unit = math.ceil(count / 60), 'hour'
    return f'{count} {unit}' + ('' if count == 1 else 's')


def named_in(details):
    """The person's name of the capability a refusal names (details.display_name, else the catalog's), or '' when
    only the plain phrase is known."""
    name = details.get('display_name')
    if not isinstance(name, str) or not name.strip():
        capability = details.get('capability')
        name = display_name(capability) if isinstance(capability, str) and capability else ''
    return '' if name == UNNAMED else name.strip()


def is_plan_limit(limit):
    """Whether a LIMIT_REACHED's details.limit is a plan limit: a capability key (<tab>.<name>, the catalog's form;
    its name when the catalog is loaded), else a throttle that no plan decides, such as the email-code and
    authenticator-code tries ('code_tries', 'mfa_tries')."""
    return isinstance(limit, str) and (limit in _names or '.' in limit)


def words(code, status, details=None):
    """The sentence a refusal carries, from its code and its details (re-check R2-15): what the details name reaches
    the person, since every client shows the server's sentence first (shared/edge-session.ts accessText, the shell's
    authText). AGENTS.md "Gates and evidence" (d): it names what is wrong and how to go on.
    - CAPABILITY_REQUIRED names the item (display_name); PLAN_EXPIRED also the ended plan (its name in the catalog);
    - LIMIT_REACHED of a plan limit (is_plan_limit) names it, the account's own number (allowed) and the wait (or, with
      no wait, to remove one); of anything else it names the wait and no plan, since no plan decides it;
    - MFA_REQUIRED says to set the authenticator up when the account has none (details.mfa_enrolled false);
    - every other code: its fixed sentence (message_of)."""
    d = details if isinstance(details, dict) else {}
    if code == 'CAPABILITY_REQUIRED':
        name = named_in(d)
        if name:
            return f'{name} is not part of your EDGE plan. Upgrade the plan to use it; you are still signed in.'
    elif code == 'PLAN_EXPIRED':
        name = named_in(d)
        plan = _plan_names.get(d['expired_plan'], '') if isinstance(d.get('expired_plan'), str) else ''
        ended = f'Your {plan} plan on EDGE has ended' if plan else 'Your EDGE plan has ended'
        if name:
            return f'{ended}, and {name} came with it. Renew the plan to use it again; you are still signed in.'
        return f'{ended}. Renew it to use this again; you are still signed in.'
    elif code == 'LIMIT_REACHED':
        limit, wait = d.get('limit'), wait_words(d.get('retry_after_s'))
        if is_plan_limit(limit):
            allowed = d.get('allowed')
            count = f' ({allowed})' if isinstance(allowed, int) and not isinstance(allowed, bool) else ''
            then = (f'Try again in {wait}, or upgrade the plan.' if wait
                    else 'Remove one you no longer need, or upgrade the plan.')
            what = f' for {_names[limit]}' if limit in _names else ''
            return f"You have reached your plan's limit{what}{count}. {then}"
        return f'Too many attempts. Wait {wait or "a while"}, then try again.'
    elif code == 'MFA_REQUIRED' and d.get('mfa_enrolled') is False:
        return ('This needs two-step sign-in, which is not set up for this account yet. Set up an authenticator app '
                'when EDGE asks for it, then try again.')
    return message_of(code, status)


def plan_cap(capability, allowed, needed):
    """Re-check R2-39 (CONTRACT.md section 3): a saved-item cap of the plan (layouts, presets, places with drawings,
    saved screens and metrics, watchlists and their tickers and indicators) reached. One code for every plan limit,
    LIMIT_REACHED, with details.limit the capability key, allowed the account's own number and needed what the request
    would make; 403, since waiting frees nothing (removing one or a larger plan does; the queue of backtests, which frees
    itself, answers 429 with Retry-After). (code, status, message, details) for a module's failure()."""
    details = {'limit': capability, 'allowed': allowed, 'needed': needed}
    return 'LIMIT_REACHED', 403, words('LIMIT_REACHED', 403, details), details


def refusal(status, code, details=None, headers=None):
    return JSONResponse(status_code=status, headers=headers, content={'error': {
        'code': code, 'message': words(code, status, details), 'details': details or {}}})


def capability_required(capability):
    return Refusal(403, 'CAPABILITY_REQUIRED', {'capability': capability, 'display_name': display_name(capability)})


def plan_expired(capability, plan):
    """EXEC-MU-ACCOUNTS Phase 2 (CONTRACT.md 8a): the capability was held only by the account's plan that has ended.
    (a) the rule is visible before acting: the session answer's access.expired_plan names the ended plan and
    access.capabilities no longer lists what it gave; (b) to pass, renew the plan (the admin extends the subscription);
    (c) right: an account whose paid plan is live runs a backtest; wrong: the same account the second after the plan's
    end gets this refusal, not CAPABILITY_REQUIRED; (d) the message says the plan ended and to renew it, and details
    name the capability and the ended plan."""
    return Refusal(403, 'PLAN_EXPIRED', {'capability': capability,
                                         'display_name': display_name(capability),
                                         'expired_plan': plan})


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
