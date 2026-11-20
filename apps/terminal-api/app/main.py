"""Subscriber terminal API (EXEC-TERMINAL-API, verification/terminal_api/DESIGN.md section 3).

Subscribers sign in, read a ticker's manifest and receive short-lived presigned URLs for the pre-published files in
the private bucket terminal-display; data older than the published window comes from PostgreSQL. Every URL and query
is logged and counted against the subscriber's quotas (terminal.quota). Accounts are managed by the administrator
through /admin (option A, user 2026-10-25).

EXEC-MU-RUNTIME Phase 1b (user 2026-10-28, option A; verification/edge_multiuser/runtime/terminal.md T1, T3, T5, T9):
service accounts for the workers (accounts.py, config.py TERMINAL_SERVICE_KEY_<NAME>), the account read inside each
grant's transaction after its lock and cached 60 s for the routes that grant nothing, the reference file index
(bucket.py refs_index) and TERMINAL_POOL_MAX.

EXEC-MU-ACCOUNTS Phase 0 (verification/edge_multiuser/access_tiers/CONTRACT.md section 7; ERRORS M470):
- private-only mode: with no browser origin configured (config.py Settings.private_only, the state once the public
  domain is removed) the direct cookie sign-in and every cookie route answer 403 direct_access_closed; the gateway key,
  the service keys and the admin key keep working;
- every key (the EDGE gateway key, a service key, the admin key) is accepted only on a request addressed to the private
  host (Host exactly terminal-api.railway.internal with an optional :port, any letter case) that did not pass Railway's
  public edge (none of EDGE_HEADERS). Otherwise the answer is 403 gateway_host_not_allowed with one generic message,
  the same whether the key is valid, wrong or absent (C1 M3, L2): the public answer never says a key is real nor names
  the private host or a variable; the detailed reason goes to the server log only (never the key).

EXEC-MU-ACCOUNTS Phase 3c (T2; CONTRACT.md section 8b "3c in detail"): beside the gateway key edge-bff may name the EDGE
owner and its plan (x-terminal-proxy-owner, x-terminal-capabilities; entitlements.py). Without both headers nothing
changes. With them:
- the owner has its own terminal.subscriber row (kind 'owner', edge_owner_key; made on first use), and the caller's
  credential is ('gateway', owner): the account cache, the usage and the audit rows (with the header's version) are the
  owner's;
- quotas (decision D6): an `admin` owner (holding *) gets the gateway subscriber's own limits (its overrides included),
  counted on the owner's own row; any other owner the terminal.quota defaults overlaid by the header's `quota`;
- every data route passes the owner's plan (ROUTE_ACCESS lists how each route is gated; tests/test_phase3c.py walks the
  routes): tickers (terminal.tickers), datasets (terminal.dataset:<id>, with `intraday` and `reference`) and the history
  window (terminal.history_days). A refusal is 403 capability_required with the `capability` it lacks;
- a capped owner (history_days N) gets each dated dataset of /bundle as one cut file (cut.py: exactly the rows dated
  after data_through - N days, deterministic gzip), served by GET /cut/{ticker}/{dataset} and counted there.

Re-check fix round (track terminal; verification/edge_multiuser/fix_round/terminal.md): every 429 names its quota and
when to try again (retry_after_s, Retry-After; R1-1, R1-26); an owner's answers carry x-terminal-capabilities-applied
(R2-4); an unknown dataset id of the header is left out (R2-5); history_days 0 is the empty window (R1-22); an owner
without the dataset `reference` gets its own copy of each reference file (refcut.py, GET /reference/{name}/cut; R2-32);
/ready reports the state of the gateway's own account (R1-4).

Track guest (decision 1 of 2026-11-19, "1a"; verification/edge_multiuser/fix_round/guest.md): the visitors of EDGE's
guest plan reach terminal-api under one owner row; edge-bff adds x-terminal-client (the visitor's opaque key) and the
quotas of that owner are then counted per visitor: the usage, its lock and the audit rows carry the key
(terminal.access_log.client_key, migration 20261119_170; meter()). A call without it is counted on the owner's row as
a whole (stricter, never wider). Every plan that holds terminal.view, and the guest, reads the whole ticker list
(refcut.py names_only).
"""
import datetime as dt
import json
import math
import re
import time
from contextlib import asynccontextmanager
import logging
from typing import Annotated, Literal, get_args

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from . import quota
from .accounts import AccountCache, Caller
from .bucket import PAGE_FAMILIES, REF_NAME, SHA256, XSECTION_NAME, radar_index, refs_index, xsection_index
from .config import PRIVATE_HOST, Settings, service_email, service_variable
from .cut import CutCache, CutError, make_cut
from .refcut import RefError, make_copy
from .entitlements import (APPLIED_HEADER, CAPS_HEADER, CLIENT_EXAMPLE, CLIENT_HEADER, EXAMPLE as CAPS_EXAMPLE,
                           EXTRA_DATASETS, OWNER_HEADER, HeaderError, applied, parse_capabilities, parse_client,
                           parse_owner, window_after)
from .security import client_ip, new_token, password_verifier, same_secret, token_hash, verify_password

COOKIE = 'terminal_session'
PROXY_HEADER = 'x-terminal-proxy-key'
# T2 (EXEC-MU-ACCOUNTS Phase 3c): the gateway names the EDGE owner in OWNER_HEADER and its plan in CAPS_HEADER
# (entitlements.py). A service key acts as its own account and may never name one (T1).
# T1: the services that may be granted cross-sectional files (one file holds every ticker); the gateway key keeps its
# access until a later, separate step removes it (compatibility with the deployed screener-worker build)
XSECTION_SERVICES = frozenset({'screener-worker'})
# M470: headers Railway's public edge adds to every request it forwards; a call over the private network (edge-bff's
# httpx client, which sends only content-type and the key) carries none of them. The gateway key is refused with any.
EDGE_HEADERS = ('x-forwarded-for', 'x-forwarded-host', 'x-real-ip', 'forwarded', 'x-railway-edge')
PRIVATE_URL = f'http://{PRIVATE_HOST}:8080'
# RFC 9110 7.2: Host = uri-host [":" port]. Only a plain name and an optional port of digits; userinfo, a path, a query,
# a fragment, a trailing dot or anything else is not a private host (C1 L2). No trailing dot: Railway does not rewrite
# Host on the private network, it is the name in the caller's URL, and every caller uses the name without one.
HOST = re.compile(r'([A-Za-z0-9.-]+)(?::[0-9]{1,5})?')
NOT_HERE = ('This address does not accept keyed requests. Fix: call terminal-api from inside its own network, where '
            'your service is configured to reach it; a person opens the Terminal in EDGE.')
log = logging.getLogger('terminal-api')
TICKER = re.compile(r'^[A-Z0-9]{1,12}$')
BROKER = r'^[A-Z0-9]{2}$'
API = '/api/terminal/v1'
MAX_YEARS_PER_CALL = 6
MAX_PRICE_HISTORY_DAYS = 3660
MAX_BROKER_HISTORY_DAYS = 366
REF_FILES = {'tickers': 'v1/ref/tickers.json.gz', 'brokers': 'v1/ref/brokers.json.gz', 'logos': 'v1/ref/logos.json.gz',
             'fixed_income': 'v1/ref/fixed_income.json.gz', 'stock_lists': 'v1/ref/stock_lists.json.gz'}
LOGO_CACHE_SECONDS = 7 * 24 * 3600
ACCESS_LOG_DAYS = 90            # EXEC-TERMINAL-SPEED (user 2026-10-26): audit rows are kept 90 days
PRUNE_EVERY_SECONDS = 6 * 3600
MAX_XSECTION_NAMES = 16         # EXEC-SCREENER: names per /xsection call (Phase 1 indexes 2, Phase 2 about 5)
SIGN_IN_WAIT = 15 * 60          # the failed sign-ins are counted over 15 minutes (store.failed_sign_ins)
GATEWAY_WARN_DAYS = 30          # R1-4: /ready says 'expiring' this long before the gateway's account ends


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class SignIn(Strict):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=1024)


class ChangePassword(Strict):
    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=12, max_length=1024)


class FilesRequest(Strict):
    ticker: str = Field(pattern=TICKER.pattern)
    dataset: Literal['price', 'broker', 'events']
    years: list[int] = Field(default_factory=list, max_length=MAX_YEARS_PER_CALL)

    @model_validator(mode='after')
    def years_fit_dataset(self):
        if self.dataset == 'events' and self.years:
            raise ValueError('events is one file per ticker with every date: send no years')
        if self.dataset != 'events' and not self.years:
            raise ValueError(f'{self.dataset} files are per year: send 1-{MAX_YEARS_PER_CALL} years')
        return self


BUNDLE_DATASET = Literal['price', 'broker', 'events', 'yield']
# EXEC-MU-ACCOUNTS Phase 3c: the dataset ids a plan grants (terminal.dataset:<id>): every per-ticker file dataset of
# /bundle, each one dated (its files carry the date column `d`, so a capped owner gets it as a cut, cut.py), plus the
# intraday bars and the reference files (entitlements.EXTRA_DATASETS), which are not cut
DATED = tuple(get_args(BUNDLE_DATASET))
DATASETS = DATED + EXTRA_DATASETS
HISTORY_DATASET = {'history_price': 'price', 'history_broker': 'broker'}
# how each API route is gated for an EDGE owner (tests/test_phase3c.py fails on a route under API without an entry):
# 'owner': tickers, datasets and the window of the owner's plan (the gate functions below); 'filtered': answers only
# what the plan may see (no refusal); 'no-owner': refuses an owner header; 'no-data': carries no data file (decided,
# README); 'page': EDGE pages edge-bff gates itself, the owner only audited; 'account': sign-in and password routes
# (no gateway); 'admin': the administrator key
ROUTE_ACCESS = {'/reference/{name}': 'filtered', '/reference/{name}/cut': 'filtered', '/files': 'owner', '/bundle': 'owner', '/manifest/{ticker}': 'owner',
                '/history/price': 'owner', '/history/broker': 'owner', '/cut/{ticker}/{dataset}': 'owner',
                '/state': 'filtered', '/xsection': 'no-owner', '/logo/{ticker}': 'no-data',
                **{f'/{family}': 'page' for family in PAGE_FAMILIES},
                '/auth/sign-in': 'account', '/auth/sign-out': 'account', '/auth/session': 'account',
                '/auth/change-password': 'account', '/admin/subscribers': 'admin', '/admin/subscribers/{sid}': 'admin'}


class BundleRequest(Strict):
    """EXEC-TERMINAL-UI-1026 U6 (user 2026-10-26: "Satu panggilan API per saham ... sesuai dengan ticker yang di display"):
    every published file of the chosen datasets of one ticker in one answer."""
    ticker: str = Field(pattern=TICKER.pattern)
    # EXEC-FI-TERMINAL (user go 2026-11-01): `yield`, a government bond's yield rows (its `price` is the bond price). The
    # list is at most every dataset once (the answer reads each once): the bound is derived from BUNDLE_DATASET, so a new
    # dataset needs no second edit (M327: a fixed 3 refused the page's 4-dataset request)
    datasets: list[BUNDLE_DATASET] = Field(default=['price', 'broker', 'events'], min_length=1,
                                           max_length=len(get_args(BUNDLE_DATASET)))
    # EXEC-TERMINAL-SPEED: the packs instead of yearly files where the manifest has them (price: one file for every
    # year; broker: the archive pack plus the last two yearly files)
    packs: bool = False
    # EXEC-INTRADAY-FEATURES C2 (user 2026-11-01): the intraday files of one timeframe as well (its archive and its
    # current period, manifest `intraday`); which timeframes exist is the manifest's, never a list here
    timeframe: str | None = Field(default=None, pattern=r'^[0-9]{1,3}[mh]$')


class XsectionRequest(Strict):
    """EXEC-SCREENER (P1 a, user 2026-10-28): cross-sectional files of the current publication by their index names
    (state.json `xsection`, shown on /state); a client never names a key."""
    names: list[Annotated[str, Field(pattern=XSECTION_NAME.pattern)]] = Field(min_length=1,
                                                                              max_length=MAX_XSECTION_NAMES)


class PageRequest(Strict):
    """EXEC-RADAR R5, EXEC-OVERVIEW: a page's files of the current publication by their index names (GET /<family>
    lists them)."""
    names: list[Annotated[str, Field(pattern=XSECTION_NAME.pattern)]] = Field(min_length=1,
                                                                              max_length=MAX_XSECTION_NAMES)


RadarRequest = PageRequest
# the page's name in the messages, and where the owner opens it (edge-bff)
PAGE_LABELS = {'radar': 'the Radar', 'overview': 'the Market Overview', 'watchlist': 'the Watchlist'}


class NewSubscriber(Strict):
    email: str = Field(min_length=3, max_length=254)
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=12, max_length=1024)
    expires_at: dt.datetime

    @field_validator('email')
    @classmethod
    def normal_email(cls, v):
        v = v.strip().lower()
        if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', v):
            raise ValueError('not an email address')
        return v


class SubscriberChange(Strict):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    active: bool | None = None
    expires_at: dt.datetime | None = None
    disabled_reason: str | None = Field(default=None, max_length=500)
    password: str | None = Field(default=None, min_length=12, max_length=1024)


def error(status, code, message, headers=None, **extra):
    raise HTTPException(status, detail={'error': code, 'message': message, **extra}, headers=headers)


def wait_error(code, message, wait, **extra):
    """EXEC-MU-ACCOUNTS re-check R1-1/R1-26: every 429 says when to try again, as a body field `retry_after_s` (whole
    seconds, at least 1) and as the Retry-After header; edge-bff relays it as 429 LIMIT_REACHED."""
    error(429, code, message, headers={'Retry-After': str(wait)}, retry_after_s=wait, **extra)


def lacks(capability, what, fix):
    """EXEC-MU-ACCOUNTS Phase 3c: 403 capability_required, the existing error shape with the capability the owner's plan
    lacks (edge-bff names it to the person with its display_name and refuses most of these before calling here)."""
    error(403, 'capability_required', f"{what} is not in the plan of this EDGE account ({capability}). Fix: {fix}",
          capability=capability)


def create_app(settings: Settings | None = None, store=None, bucket=None):
    settings = settings or Settings.from_env()
    if store is None:
        from .store import Store
        store = Store(settings.database_url, settings.pool_max)
    if bucket is None:
        from .bucket import Bucket
        bucket = Bucket(settings)

    @asynccontextmanager
    async def lifespan(_app):
        if hasattr(store, 'open'):
            store.open()
        yield
        if hasattr(store, 'close'):
            store.close()

    app = FastAPI(title='terminal-api', docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    if settings.allowed_origins:                             # private-only: no browser origin, no CORS answer at all
        app.add_middleware(CORSMiddleware, allow_origins=list(settings.allowed_origins), allow_credentials=True,
                           allow_methods=['GET', 'POST'], allow_headers=['Content-Type'])

    @app.middleware('http')
    async def headers(request: Request, call_next):
        response = await call_next(request)
        caller = getattr(request.state, 'caller', None)
        if caller is not None and caller.owner is not None:
            # R2-4: the owner's header was parsed and is what this answer applied (refusals included), so edge-bff can
            # tell this answer from one of a terminal-api that ignores the owner headers
            response.headers[APPLIED_HEADER] = applied(caller.caps)
        response.headers.setdefault('Cache-Control', 'no-store')   # only a logo sets its own (EXEC-TERMINAL-LOGO)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        return response

    @app.exception_handler(HTTPException)
    async def http_error(_request, exc: HTTPException):
        detail = exc.detail if isinstance(exc.detail, dict) else {'error': 'error', 'message': str(exc.detail)}
        return JSONResponse(detail, status_code=exc.status_code, headers=getattr(exc, 'headers', None))

    @app.exception_handler(RequestValidationError)
    async def invalid(_request, exc: RequestValidationError):
        problems = [{'field': '.'.join(str(p) for p in e['loc'][1:]), 'problem': e['msg']} for e in exc.errors()]
        return JSONResponse({'error': 'invalid_request', 'message': 'Check the listed fields.', 'fields': problems},
                            status_code=400)

    def ip_of(request: Request):
        return client_ip(request.headers.get('x-forwarded-for'), request.client.host if request.client else None)

    services = tuple((name, key, service_email(name)) for name, key in settings.service_keys)
    accounts = AccountCache()

    def direct_closed(what):
        """Private-only mode (Settings.private_only): no browser can reach this service, so a sign-in or a session
        cookie is refused before any database read."""
        error(403, 'direct_access_closed',
              f'{what} is closed: this terminal-api runs private-only (no public domain; TERMINAL_ALLOWED_ORIGINS and '
              f'RAILWAY_PUBLIC_DOMAIN are unset), so a direct sign-in or a session cookie is refused. Fix: open the '
              f'Terminal in EDGE (/terminal), which reaches terminal-api through its gateway; a service calls '
              f'{PRIVATE_URL} with its key in {PROXY_HEADER}. Example: GET {PRIVATE_URL}{API}/state with '
              f'{PROXY_HEADER}: <the value of TERMINAL_SERVICE_KEY_<NAME>>.')

    def private_call(request: Request):
        """None when the request was addressed to a private host (settings.proxy_hosts, exactly, with an optional
        :port; HOST) and did not pass the public edge; else what is wrong, for the server log only."""
        host = request.headers.get('host', '')
        m = HOST.fullmatch(host)
        if not m or m.group(1).lower() not in settings.proxy_hosts:
            return f'Host {host[:100]!r} is not a private host'
        edge = [h for h in EDGE_HEADERS if h in request.headers]
        if edge:
            return f'the request passed the public edge (it carries {", ".join(edge)})'
        return None

    def key_kind(request: Request):
        """For the log only: which credential a refused request carried (every key compared; never the key)."""
        key, admin_key = request.headers.get(PROXY_HEADER), request.headers.get('x-terminal-admin-key')
        kinds = []
        if key is not None:
            kinds.append('gateway' if settings.proxy_key and same_secret(key, settings.proxy_key) else
                         next((f'service {n}' for n, k, _ in services if same_secret(key, k)), 'unknown proxy key'))
        if admin_key is not None:
            kinds.append('admin' if same_secret(admin_key, settings.admin_key) else 'unknown admin key')
        return ', '.join(kinds) or 'no key'

    def private_only_keys(request: Request):
        """C1 M3: every key counts only on the private host. Off it, one generic refusal for a valid, a wrong or no
        key alike, so the public answer tells nothing; the reason is logged."""
        wrong = private_call(request)
        if wrong:
            log.warning('keyed request refused off the private host: %r; credential: %s; path %r', wrong,   # %r: C1 log forging
                        key_kind(request), request.scope.get('path'))   # not request.url: a malformed Host breaks it
            error(403, 'gateway_host_not_allowed', NOT_HERE)

    def identify(request: Request) -> Caller:
        """Who is calling, from the request alone (no database), decided once per request (request.state)."""
        caller = getattr(request.state, 'caller', None)
        if caller is None:
            caller = request.state.caller = identify_now(request)
        return caller

    def owner_of(request: Request):
        """EXEC-MU-ACCOUNTS Phase 3c: (owner, Capabilities, client) of a gateway call that names an EDGE owner,
        (None, None, None) when it sends neither header (the gateway's one account, as before). One header without the
        other, or a header that breaks its rule, is 400 naming the header or field, the rule and a right example.
        Track guest: `client` is the visitor key of x-terminal-client, allowed only beside both owner headers of an
        owner that does not hold * (a visitor of the guest plan), else None."""
        owner, caps = request.headers.get(OWNER_HEADER), request.headers.get(CAPS_HEADER)
        client = request.headers.get(CLIENT_HEADER)
        if owner is None and caps is None:
            if client is not None:
                error(400, 'invalid_owner_headers',
                      f'{CLIENT_HEADER} was sent without {OWNER_HEADER} and {CAPS_HEADER}: a visitor key counts only '
                      f'for an EDGE owner. Fix: send it beside both owner headers of the guest plan, or not at all. '
                      f'Example: {OWNER_HEADER}: edge-guest, {CAPS_HEADER}: {CAPS_EXAMPLE}, {CLIENT_HEADER}: '
                      f'{CLIENT_EXAMPLE}.', field=CLIENT_HEADER)
            return None, None, None
        if owner is None or caps is None:
            missing, sent = (OWNER_HEADER, CAPS_HEADER) if owner is None else (CAPS_HEADER, OWNER_HEADER)
            error(400, 'invalid_owner_headers',
                  f'{sent} was sent without {missing}: the EDGE gateway names an owner with both headers or with '
                  f'neither. Fix: send both, built from the principal. Example: {OWNER_HEADER}: '
                  f'u_0123456789abcdef01234567 and {CAPS_HEADER}: {CAPS_EXAMPLE}.', field=missing)
        try:
            found = parse_owner(owner), parse_capabilities(caps, DATASETS), (
                parse_client(client) if client is not None else None)
        except HeaderError as e:
            error(400, 'invalid_owner_headers', str(e), field=e.field)
        if found[2] is not None and found[1].admin:
            error(400, 'invalid_owner_headers',
                  f'{CLIENT_HEADER} was sent for an owner holding * ("admin": true): a visitor key belongs to the '
                  f'guest plan only. Fix: send no {CLIENT_HEADER} for a signed-in principal. Example: '
                  f'{CAPS_HEADER}: {CAPS_EXAMPLE} with {CLIENT_HEADER}: {CLIENT_EXAMPLE}.', field=CLIENT_HEADER)
        if found[1].ignored:
            # R2-5: an edge-bff that knows more datasets than this terminal-api (a deploy in between): not served anyway
            log.warning(json.dumps({'event': 'owner_datasets_ignored', 'datasets': list(found[1].ignored),
                                    'known': list(DATASETS)}))
        return found

    def identify_now(request: Request) -> Caller:
        """Who is calling, from the request alone (no database): the gateway key, a service key or a session cookie.
        A key in x-terminal-proxy-key that is neither is refused, never ignored. Every key counts only on the private
        host (private_only_keys, M470, C1 M3); a cookie only while a browser origin is configured (private_only).
        Phase 3c: the owner headers count only beside the gateway key (owner_of)."""
        key = request.headers.get(PROXY_HEADER)
        if key is None:
            if OWNER_HEADER in request.headers or CAPS_HEADER in request.headers or CLIENT_HEADER in request.headers:
                if settings.private_only:
                    direct_closed('A request without a key')
                error(400, 'owner_not_allowed',
                      f'{OWNER_HEADER} and {CAPS_HEADER} count only beside the EDGE gateway key in {PROXY_HEADER}; a '
                      f'session never names an owner. Fix: send no owner header with a session cookie. Example: GET '
                      f'{API}/manifest/BBCA with only the cookie.')
            if settings.private_only:
                direct_closed('A session cookie')
            token = request.cookies.get(COOKIE)
            if not token:
                error(401, 'not_signed_in', 'Sign in first.')
            return Caller('session', token_hash=token_hash(token))
        private_only_keys(request)                           # before any key is judged (C1 M3)
        gateway_ok = bool(settings.proxy_key) and same_secret(key, settings.proxy_key)
        matched = [(name, email) for name, k, email in services if same_secret(key, k)]   # every key compared
        if gateway_ok:
            owner, caps, client = owner_of(request)
            return Caller('gateway', email=settings.proxy_subscriber, owner=owner, caps=caps, client=client)
        if not matched:
            error(401, 'proxy_key_rejected',
                  f'The {PROXY_HEADER} header holds no key this terminal-api knows: neither the EDGE gateway key '
                  'nor a service key. Send the value of your own TERMINAL_PROXY_KEY variable, which references '
                  "terminal-api's TERMINAL_PROXY_KEY (edge-bff) or its TERMINAL_SERVICE_KEY_<NAME> (a worker). "
                  'Example: TERMINAL_PROXY_KEY=${{terminal-api.TERMINAL_SERVICE_KEY_BACKTEST_WORKER}} on '
                  'backtest-worker.')
        name, email = matched[0]
        if OWNER_HEADER in request.headers or CAPS_HEADER in request.headers or CLIENT_HEADER in request.headers:
            error(400, 'owner_not_allowed',
                  f'{OWNER_HEADER} or {CAPS_HEADER} was sent with the service key of {name}. A service key acts as its own account '
                  f'({email}) and can never name an owner; only the EDGE gateway names one. Fix: send '
                  f'{PROXY_HEADER} alone. Example: GET {API}/state with only {PROXY_HEADER}: <the value of '
                  f'{service_variable(name)}>.')
        return Caller('service', name=name, email=email)

    def proxied(request: Request):
        """True for a request with a valid gateway or service key; a wrong key is refused, never ignored."""
        return PROXY_HEADER in request.headers and identify(request).proxied

    def same_origin_post(request: Request):
        """Cookie-authenticated writes must come from an allowed origin (no cross-site form posts). The gateway checks
        its own page's origin and CSRF token before forwarding; a service calls from the private network."""
        if proxied(request):
            return
        if settings.private_only:
            direct_closed(f'{request.method} {request.scope.get("path")} from a browser')
        if request.headers.get('origin', '').rstrip('/') not in settings.allowed_origins:
            error(403, 'origin_not_allowed', 'This request must come from the terminal page.')

    def lookup(c, caller: Caller):
        """The caller's account row as it is now, or None: missing, inactive, expired, or a session that ended."""
        if caller.kind == 'session':
            return store.session_subscriber(c, caller.token_hash)
        row = store.account(c, caller.email, 'service' if caller.kind == 'service' else 'person')
        if row is None or caller.owner is None:
            return row
        # Phase 3c: an owner acts through the gateway, so both the gateway's account and the owner's own row must be
        # active; the owner's row is the one counted and audited, the gateway's id gives an admin owner its limits
        mine = store.owner_account(c, caller.owner)
        return {**mine, 'gateway_id': row['subscriber_id']} if mine else None

    def refuse(caller: Caller):
        if caller.kind == 'gateway' and caller.owner is not None:
            error(401, 'session_ended', f'The terminal account of this gateway, or the row of the EDGE owner '
                                        f'{caller.owner} (terminal.subscriber kind owner), is not active. Fix: the '
                                        f'administrator sets both active (POST {API}/admin/subscribers/<id>).')
        if caller.kind == 'gateway':
            error(401, 'session_ended', 'The terminal account of this gateway is not active.')
        if caller.kind == 'service':
            error(401, 'service_account_inactive',
                  f'The service account of {caller.name} ({caller.email}, kind service) is missing, inactive or '
                  f'expired in terminal.subscriber, so its key is refused. Fix: apply migration '
                  f'20261028_100_terminal_service_accounts.sql, or let the administrator set it active with a later '
                  f'expires_at (POST {API}/admin/subscribers/<id>). Example: {{"active": true, "expires_at": '
                  f'"2100-01-01T00:00:00Z"}}.')
        error(401, 'session_ended', 'Your session ended or your subscription is not active. Sign in again.')

    def subscriber(request: Request):
        """The caller's account, read now in its own transaction (routes that change or show the account)."""
        caller = identify(request)
        with store.tx() as c:
            row = lookup(c, caller)
        if not row:
            accounts.drop(caller)
            refuse(caller)
        return row

    def known(request: Request):
        """(caller, account row) for a route that may use this process's last check of the account (accounts.py, at
        most 60 s old); the database is read only when that check is older or absent. A caller without an active
        account is refused here, before any bucket read."""
        caller = identify(request)
        row = accounts.get(caller)
        if row is None:
            with store.tx() as c:
                row = lookup(c, caller)
            if not row:
                accounts.drop(caller)
                refuse(caller)
            accounts.put(caller, row)
        return caller, row

    def reader(request: Request):
        """T3: /manifest, /state and /logo grant nothing: the account of the last check (known), no transaction while
        it is at most 60 s old."""
        return known(request)[1]

    def granted(request: Request) -> Caller:
        """A grant's caller, known as reader() knows it (so a stranger is refused before the bucket is read); the grant
        then reads the account again inside its own transaction, after its lock (admit)."""
        return known(request)[0]

    def admit(c, caller: Caller):
        """T3: the account checked inside the grant's own transaction, after its lock: one transaction per grant, and an
        account deactivated or expired while the grant waited for the lock is refused. The lock key is the account's
        subscriber id, from the cache when this process knows it (else one lookup first); a cached id that is no longer
        the credential's account (a replaced row) takes that account's lock and reads it again."""
        sid = accounts.sid(caller)
        if sid is None:
            row = lookup(c, caller)
            if not row:
                refuse(caller)
            sid = row['subscriber_id']
        store.lock_subscriber(c, sid, **meter(caller))
        row = lookup(c, caller)                              # after the lock
        if row and row['subscriber_id'] != sid:
            sid = row['subscriber_id']
            store.lock_subscriber(c, sid, **meter(caller))
            row = lookup(c, caller)
        if not row or row['subscriber_id'] != sid:
            accounts.drop(caller)
            refuse(caller)
        accounts.put(caller, row)
        return row

    def xsection_caller(request: Request) -> Caller:
        """EXEC-SCREENER: one cross-sectional file holds every ticker, so it is granted only to the screener-worker's
        service account (EXEC-MU-RUNTIME T1) and, until a later step removes it, to the EDGE gateway key; a subscriber
        session or another service is refused. Signing in would not help, so the refusal is 403, not 401; a wrong key
        is 401 proxy_key_rejected as on every route."""
        caller = identify(request) if PROXY_HEADER in request.headers else None
        if caller and caller.owner is not None:
            # Phase 3c: one file holds every ticker, so no EDGE owner's plan can be applied to it
            error(403, 'gateway_only', f'POST {API}/xsection grants cross-sectional files (every ticker in one file), '
                                       f'which no EDGE owner\'s plan can be applied to, so the gateway key is refused '
                                       f'with {OWNER_HEADER}. Fix: the screener-worker reads them with its own '
                                       f'service key ({service_variable("screener-worker")}); one ticker\'s files: '
                                       f'POST {API}/bundle. Example: {PROXY_HEADER}: '
                                       f'${{{{terminal-api.{service_variable("screener-worker")}}}}}.')
        if caller and (caller.kind == 'gateway' or (caller.kind == 'service' and caller.name in XSECTION_SERVICES)):
            return known(request)[0]
        who = f'the service key of {caller.name}' if caller else 'a subscriber session'
        error(403, 'gateway_only', f'POST {API}/xsection grants cross-sectional files only to the screener-worker '
                                   f'service key or the EDGE gateway key, sent in the {PROXY_HEADER} header; '
                                   f'{who} cannot ask for them. Fix: call with the screener-worker key '
                                   f'({service_variable("screener-worker")}). One ticker\'s files: POST '
                                   f'{API}/bundle. Example: {PROXY_HEADER}: '
                                   f'${{{{terminal-api.{service_variable("screener-worker")}}}}}.')

    def page_caller(family):
        """EXEC-RADAR R5 (user 2026-11-14: the Radar is an admin page, the owner's only), EXEC-OVERVIEW (decision 7, the
        same): a page's files go to the EDGE gateway key only (edge-bff relays them to the owner's session); a
        subscriber session or any service key is refused with 403, a wrong key 401 as on every route."""
        def check(request: Request) -> Caller:
            caller = identify(request) if PROXY_HEADER in request.headers else None
            if caller and caller.kind == 'gateway':
                return known(request)[0]
            who = f'the service key of {caller.name}' if caller else 'a subscriber session'
            label = PAGE_LABELS[family]
            error(403, 'gateway_only', f'{API}/{family} serves {label}\'s files to the EDGE gateway key only, sent in '
                                       f'the {PROXY_HEADER} header; {who} cannot ask for them. Fix: open {label} in '
                                       f'EDGE (edge-bff /api/v1/{family}). Example: {PROXY_HEADER}: '
                                       f'${{{{terminal-api.TERMINAL_PROXY_KEY}}}} from edge-bff.')
        return check


    def service_only_files(caller: Caller, route: str):
        """T1: a service account reads published files; the PostgreSQL fallback and password routes are a person's."""
        if caller.kind == 'service':
            error(403, 'not_for_service_accounts',
                  f'{route} is for a subscriber or the EDGE gateway; the service account of {caller.name} reads '
                  f'published files only. Fix: ask POST {API}/bundle for a ticker\'s files (or {API}/xsection, '
                  f'{API}/reference). Example: POST {API}/bundle {{"ticker": "BBCA", "datasets": ["price"], '
                  f'"packs": true}}.')

    def admin(request: Request):
        private_only_keys(request)                           # C1 M3: the admin key only on the private network
        if not same_secret(request.headers.get('x-terminal-admin-key'), settings.admin_key):
            error(401, 'admin_key_required', 'A valid X-Terminal-Admin-Key header is required.')

    def ticker_manifest(ticker):
        if not TICKER.fullmatch(ticker):
            error(400, 'invalid_ticker', 'A ticker is 1-12 capital letters or digits, for example BBCA.')
        m = bucket.manifest(ticker)
        if not m:
            error(404, 'unknown_ticker', f'No published data for {ticker}.')
        return m

    def meter(caller: Caller):
        """Track guest: the keyword that makes the store count a visitor of the guest plan on its own (its usage, the
        lock its quota check takes, its audit rows): {'client': key} beside the owner headers, else {} (every row of
        the account, exactly as before; a store without visitor keys is never asked for one)."""
        return {'client': caller.client} if caller.client is not None else {}

    def take(c, sid, refusal, caller: Caller | None = None):
        """A quota refusal (quota.check) as 429 quota_exceeded with the quota's name, its limit, its window and when the
        refused request fits (Store.frees_in; the window's length when the store cannot tell), so a relay can name the
        limit and the wait without reading the message (re-check R1-1/R1-26)."""
        if refusal:
            found = (store.frees_in(c, sid, refusal, **(meter(caller) if caller else {}))
                     if hasattr(store, 'frees_in') else None)
            wait = min(found or refusal.longest_wait, refusal.longest_wait)
            wait_error('quota_exceeded', refusal.message(wait), wait, quota=refusal.quota, limit=refusal.limit,
                       window=refusal.window)

    # ---- EXEC-MU-ACCOUNTS Phase 3c: the owner's plan (every data route; ROUTE_ACCESS) -------------------------------
    def plan(caller: Caller):
        """The Capabilities that limit this caller, or None (no owner header, or an owner holding *: no filter)."""
        caps = caller.caps if caller.owner is not None else None
        return None if caps is None or caps.admin else caps

    def need_ticker(caller: Caller, ticker):
        caps = plan(caller)
        if caps and not caps.ticker_ok(ticker):
            some = ', '.join(sorted(caps.tickers)[:10]) or 'none'
            lacks('terminal.tickers', f'The ticker {ticker}',
                  f'open a ticker the plan includes ({some}), or raise the plan. Example: POST {API}/bundle '
                  f'{{"ticker": "{min(caps.tickers) if caps.tickers else "BBCA"}", "datasets": ["price"]}}.')

    def need_dataset(caller: Caller, dataset):
        caps = plan(caller)
        if caps and not caps.dataset_ok(dataset):
            some = ', '.join(sorted(caps.datasets)) or 'none'
            lacks(f'terminal.dataset:{dataset}', f'The data set {dataset}',
                  f'ask only for the data sets the plan includes ({some}), or raise the plan.')

    def window(caller: Caller, m, dataset):
        """The last date NOT served to a capped owner for `dataset` (entitlements.window_after), else None."""
        caps = plan(caller)
        if not caps or caps.history_days is None:
            return None
        after = window_after(((m.get('datasets') or {}).get(dataset) or {}).get('data_through'), caps.history_days)
        if after is None:
            lacks('terminal.history_days', f'{dataset} history (no data_through to count the window from)',
                  'nothing of this data set can be served inside the plan\'s window; ask for another data set.')
        return after

    def beyond(caller: Caller, dataset, what, after):
        caps = plan(caller)
        lacks('terminal.history_days', what,
              f'the plan shows the last {caps.history_days} calendar days of {dataset} (rows dated after '
              f'{after.isoformat()}); a capped account reads them as one cut from POST {API}/bundle, which answers '
              f'each dated data set with one file. Example: POST {API}/bundle {{"ticker": "BBCA", "datasets": '
              f'["{dataset}"], "packs": true}}.')

    def limits_of(c, caller: Caller, row):
        """Decision D6. No owner header: the account's own limits (terminal.quota with its overrides), as before. An
        owner holding * (admin): the gateway subscriber's own limits, overrides included (today's 1e9), never copied to
        another row; the usage they are checked against is the owner's own row. Any other owner: the terminal.quota
        defaults (no override of any row) overlaid by the header's `quota`; a key it leaves out keeps the default."""
        if caller.owner is None:
            return store.limits(c, row['subscriber_id'])
        if caller.caps.admin:
            return store.limits(c, row['gateway_id'])
        return {**store.limits(c, 0), **dict(caller.caps.quota)}

    def version_of(caller: Caller):
        return caller.caps.version if caller.owner is not None else None

    def audit(c, sid, caller, *args, **kwargs):
        """store.log_access with the entitlements version of an owner's call (a keyword only then, so the audit row of
        a call without the headers is written exactly as before)."""
        version = version_of(caller)
        store.log_access(c, sid, *args, **kwargs, **({'version': version} if version is not None else {}),
                         **meter(caller))

    # ---- health ----------------------------------------------------------------------------------------------
    @app.get('/health')
    def health():
        return {'status': 'ok'}

    def gateway_account():
        """Re-check R1-4: the state of the EDGE gateway's own account (TERMINAL_PROXY_SUBSCRIBER, kind person), on which
        every EDGE call depends (every owner's lookup reads it first): ok, expiring (within GATEWAY_WARN_DAYS), expired,
        inactive or missing, with the whole days left; None without a gateway. Reported by /ready and logged as a warning
        unless ok; it never makes the service unready (the workers' service accounts keep working without it)."""
        if not settings.proxy_key or not hasattr(store, 'gateway_state'):
            return None
        try:
            with store.tx() as c:
                row = store.gateway_state(c, settings.proxy_subscriber)
        except Exception:  # noqa: BLE001 - readiness only reports, never leaks the driver error
            return {'state': 'unknown'}
        if row is None:
            out = {'state': 'missing'}
        else:
            days = math.floor(row['seconds_left'] / 86400)
            state = ('inactive' if not row['active'] else 'expired' if row['seconds_left'] <= 0 else
                     'expiring' if days < GATEWAY_WARN_DAYS else 'ok')
            out = {'state': state, 'days_left': max(days, 0)}
        if out['state'] != 'ok':
            log.warning(json.dumps({'event': 'gateway_account_' + out['state'], **out,
                                    'fix': 'the administrator sets the gateway subscriber active with a later '
                                           'expires_at (POST /api/terminal/v1/admin/subscribers/<id>)'}))
        return out

    @app.get('/ready')
    def ready():
        try:
            store.ready()
        except Exception:  # noqa: BLE001 - readiness only reports, never leaks the driver error
            return JSONResponse({'status': 'not_ready'}, status_code=503)
        account = gateway_account()
        return {'status': 'ready', **({'gateway_account': account} if account is not None else {})}

    # ---- auth ------------------------------------------------------------------------------------------------
    @app.post(f'{API}/auth/sign-in')
    def sign_in(body: SignIn, request: Request, response: Response):
        if settings.private_only:                            # with or without a key: no browser can hold the cookie
            direct_closed('The direct sign-in')
        same_origin_post(request)
        email, ip = body.email.strip().lower(), ip_of(request)
        outcome, token = 'failed', None
        with store.tx() as c:
            limits = store.limits(c, 0)
            by_email, by_ip = store.failed_sign_ins(c, email, ip)
            if by_email >= limits['failed_sign_ins_per_email'] or by_ip >= limits['failed_sign_ins_per_ip']:
                outcome = 'throttled'
            else:
                row = store.subscriber_by_email(c, email)
                # T1: a service account never signs in; it is checked like an unknown email (same work, same answer)
                row = row if row and row.get('kind', 'person') == 'person' else None
                ok = verify_password(body.password, row['password_hash'] if row else None)
                if ok and row['active'] and row['current']:
                    outcome, token = 'ok', new_token()
                    limits = store.limits(c, row['subscriber_id'])
                    store.open_session(c, row['subscriber_id'], token_hash(token), ip, limits['session_hours'],
                                       limits['sessions_per_subscriber'])
                elif ok:
                    outcome = 'inactive'
                store.record_sign_in(c, email, ip, outcome == 'ok')
        if outcome == 'throttled':
            wait_error('too_many_attempts', 'Too many failed sign-ins. Wait 15 minutes and try again.', SIGN_IN_WAIT)
        if outcome == 'inactive':
            error(403, 'subscription_inactive', 'Your subscription is not active. Contact the administrator.')
        allowed = outcome == 'ok'
        if not allowed:
            error(401, 'sign_in_failed', 'Email or password is not correct.')
        response.set_cookie(COOKIE, token, max_age=limits['session_hours'] * 3600, httponly=True,
                            secure=settings.secure_cookie, samesite=settings.cookie_samesite, path='/')
        return {'status': 'signed_in'}

    @app.post(f'{API}/auth/sign-out')
    def sign_out(request: Request, response: Response):
        same_origin_post(request)
        token = request.cookies.get(COOKIE)
        if token:
            with store.tx() as c:
                store.revoke_session(c, token_hash(token))
            accounts.drop(Caller('session', token_hash=token_hash(token)))
        response.delete_cookie(COOKIE, path='/')
        return {'status': 'signed_out'}

    @app.get(f'{API}/auth/session')
    def session(who=Depends(subscriber)):
        return {'email': who['email'], 'display_name': who['display_name'],
                'subscription_expires_at': who['expires_at'].isoformat()}

    @app.post(f'{API}/auth/change-password')
    def change_password(body: ChangePassword, request: Request, who=Depends(subscriber)):
        same_origin_post(request)
        service_only_files(identify(request), f'POST {API}/auth/change-password')
        with store.tx() as c:
            if not verify_password(body.current_password, store.password_hash(c, who['subscriber_id'])):
                error(403, 'wrong_password', 'The current password is not correct.')
            store.set_password(c, who['subscriber_id'], password_verifier(body.new_password),
                               token_hash(request.cookies.get(COOKIE)))
        accounts.clear()                                     # the other sessions ended: no cached read for them here
        return {'status': 'password_changed', 'other_sessions': 'signed out'}

    # ---- data ------------------------------------------------------------------------------------------------
    def reference_source(name):
        """(index entry or None, the entry to read) of a reference file of the current publication; 404 when the
        publication has no such file."""
        state = bucket.state()
        index = refs_index((state or {}).get('refs')) or {}
        entry = index.get(name) if REF_NAME.fullmatch(name) else None
        if entry is None and name not in REF_FILES:
            error(404, 'unknown_reference', f'Reference files: {", ".join(sorted(set(REF_FILES) | set(index)))}.')
        return entry, entry or {'key': REF_FILES[name], 'bytes': 0}

    refcopies = CutCache()

    def own_copy(caller, name):
        """Re-check R2-32: the Cut of the plan's own copy of a reference file (refcut.py) for an owner whose plan does
        not hold the dataset `reference`; None for every other caller (the published file)."""
        caps = plan(caller)
        if not caps or caps.dataset_ok('reference'):
            return None
        _, source = reference_source(name)
        try:
            return make_copy(bucket.read, name, source, caps, refcopies, DATASETS)
        except RefError as e:
            error(503, 'reference_unavailable', f'The reference file {name} cannot be filtered to the plan: {e.reason}. '
                                                'It is not served whole; try again after the next publication.')

    @app.get(f'{API}/reference/{{name}}')
    def reference(name: str, request: Request, caller=Depends(granted)):
        """One reference file, counted against the quota under the REF pseudo-ticker (never an opened ticker), one audit
        row. EXEC-MU-RUNTIME T5: the publication's content key when state.json's `refs` index names the file (the
        answer then carries its sha256, bytes and rows, and its bytes count); otherwise, for a publication before the
        index, the fixed key REF_FILES, with sha256, bytes and rows null. A client never names a key.

        Phase 3c, re-check R2-32: an owner whose plan holds the dataset `reference` gets the published file (the
        reference lists in full); any other owner the plan's own copy (refcut.py: its tickers' rows, the broker list
        only with `broker`), answered in the shape of a cut: {"url": "/api/terminal/v1/reference/NAME/cut?sha256=HEX"
        (relative: edge-bff relays it), "expires_in_seconds": 0, "sha256", "bytes", "rows"}, counted when GET
        /reference/NAME/cut serves it (nothing is granted here)."""
        copy = own_copy(caller, name)
        if copy is not None:
            return {'url': f'{API}/reference/{name}/cut?sha256={copy.sha256}', 'expires_in_seconds': 0,
                    'encoding': 'gzip json', 'sha256': copy.sha256, 'bytes': copy.bytes, 'rows': copy.rows}
        entry, f = reference_source(name)
        ttl = grant(request, caller, quota.REF, [('reference', None, f)])
        return {'url': bucket.presign(f['key'], ttl), 'expires_in_seconds': ttl, 'encoding': 'gzip json',
                **{k: entry[k] if entry else None for k in ('sha256', 'bytes', 'rows')}}

    @app.get(f'{API}/reference/{{name}}/cut')
    def reference_cut(name: str, request: Request, sha256: str = Query(pattern=SHA256.pattern),
                      caller=Depends(granted)):
        """Re-check R2-32: the plan's own copy of a reference file (GET /reference/NAME announced its sha256), its gzip
        bytes as they are (application/gzip, no Content-Encoding: the page checks the sha256 of these bytes), counted as
        one file of its bytes under REF with one audit row (object_key refcut/NAME/SHA256). When the publication
        changed since the announcement the current copy is served: the page's check fails and it asks again."""
        copy = own_copy(caller, name)
        if copy is None:
            error(404, 'no_cut', f'GET {API}/reference/{name}/cut serves the plan\'s own copy of a reference file to an '
                                 f'EDGE owner whose plan does not hold the reference lists; this caller reads the file '
                                 f'itself. Fix: ask GET {API}/reference/{name}, whose answer names the file to read. '
                                 f'Example: GET {API}/reference/tickers.')
        grant(request, caller, quota.REF, [('reference', None, {'key': f'refcut/{name}/{copy.sha256}',
                                                                'bytes': copy.bytes})])
        return Response(copy.body, media_type='application/gzip',
                        headers={'ETag': f'"{copy.sha256}"', 'X-Terminal-Cut-Sha256': copy.sha256,
                                 'X-Terminal-Cut-Rows': str(copy.rows)})

    @app.get(f'{API}/logo/{{ticker}}')
    def logo(ticker: str, request: Request, who=Depends(reader)):
        """EXEC-TERMINAL-LOGO: the ticker's logo image. Not a data file: no quota and no audit row; the browser keeps it
        a week (the page asks with ?v=<sha256>, so a new logo is a new URL). An SVG is served with a CSP that runs nothing."""
        if not TICKER.fullmatch(ticker):
            error(400, 'invalid_ticker', 'A ticker is 1-12 capital letters or digits, for example BBCA.')
        found = bucket.logo(ticker)
        if not found:
            error(404, 'no_logo', f'No logo is published for {ticker}; the page shows its monogram.')
        body, ctype, sha = found
        return Response(body, media_type=ctype, headers={
            'Cache-Control': f'private, max-age={LOGO_CACHE_SECONDS}', 'ETag': f'"{sha[:32]}"',
            'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; sandbox"})

    @app.get(f'{API}/state')
    def publication(who=Depends(known)):
        """EXEC-BACKTEST-LOAD (user 2026-10-27, K1): the publication the files belong to (state.json, read for the manifest
        cache, at most manifest_cache_seconds old). No file is granted: no quota, no audit row. A reader keeps what it
        derives from the files (the backtest catalog) until finished_at changes. EXEC-SCREENER: `xsection` is the
        run's cross-sectional file index ({name: {key, sha256, bytes, rows, as_of}}, null before the publisher writes
        one); it names keys and hashes but grants nothing (the bucket is private), so a reader with the file cached by
        sha256 asks POST /xsection only for the files it lacks. EXEC-MU-RUNTIME T5: `refs` is the reference file index
        ({name: {key, sha256, bytes, rows}}, null before the publisher writes one), which /reference grants from.
        Phase 3c: no data file, so no refusal; for an owner whose plan is not * `xsection` is null (it is never granted
        to an owner) and so is `refs` without the dataset `reference`."""
        caller = who[0]
        state = bucket.state()
        if not state:
            error(503, 'state_unavailable', 'The publication state could not be read; try again shortly.')
        if plan(caller):
            state = {**state, 'xsection': None,
                     'refs': state.get('refs') if plan(caller).dataset_ok('reference') else None}
        return state

    @app.get(f'{API}/manifest/{{ticker}}')
    def manifest(ticker: str, who=Depends(known)):
        """Phase 3c: for an owner, a ticker outside its plan is refused, a data set outside it answers {locked,
        capability}, and with a history cap only the files /files would grant are listed (each entirely after the
        window start), with `cut` {history_days, after}."""
        caller = who[0]
        need_ticker(caller, ticker)
        m = ticker_manifest(ticker)
        caps, out = plan(caller), {}
        for name, ds in m.get('datasets', {}).items():
            if caps and not caps.dataset_ok(name):
                out[name] = {'locked': True, 'capability': f'terminal.dataset:{name}'}
                continue
            files = sorted(ds.get('files', {}).items())
            entry = {'data_through': ds.get('data_through')}
            if caps and caps.history_days is not None:
                after = window_after(ds.get('data_through'), caps.history_days)
                files = [(y, f) for y, f in files if after and str(f.get('first') or '')[:10] > after.isoformat()]
                entry['cut'] = {'history_days': caps.history_days, 'after': after.isoformat() if after else None}
            out[name] = {**entry, 'years': {y: {k: f[k] for k in ('bytes', 'rows', 'first', 'last', 'sha256')}
                                            for y, f in files}}
        return {'ticker': ticker, 'window': m.get('window'), 'generated_at': m.get('generated_at'), 'datasets': out}

    pruned = {'at': None}                                    # the first grant of a worker prunes once

    def grant(request, caller, ticker, chosen, one_row=False, row_dataset='bundle'):
        """Quota and audit for a set of files of one ticker, in one transaction under the account's lock: the same
        counting for /files, /bundle, /xsection and /reference. chosen = [(dataset, year or None, file entry)]. one_row
        (/bundle, EXEC-TERMINAL-SPEED; /xsection under quota.REF, EXEC-SCREENER): one audit row, dataset row_dataset,
        that counts every file; quotas sum file_count either way. EXEC-MU-RUNTIME: the account is read after the lock
        (admit, T3); a service account is counted per clock hour against its ceilings instead of a person's rolling
        quotas (store.meter, quota.check_service, T1) and keeps its own audit rows."""
        size = sum(f['bytes'] for _, _, f in chosen)
        ip = ip_of(request)
        with store.tx() as c:
            row = admit(c, caller)
            sid = row['subscriber_id']
            limits = limits_of(c, caller, row)
            if caller.kind == 'service':
                refusal = quota.check_service(caller.name, limits, store.meter(c, sid, len(chosen), size))
                if refusal:
                    wait_error('service_ceiling_reached', refusal.message(), refusal.seconds_left(),
                               quota=refusal.quota, limit=refusal.limit)
            else:
                take(c, sid, quota.check(limits, store.usage(c, sid, **meter(caller)), files=len(chosen),
                                         ticker=ticker, bytes_=size), caller)
            ttl = limits['url_ttl_seconds']
            if one_row:
                audit(c, sid, caller, 'file', ticker, ip, dataset=row_dataset, bytes_=size, keys=[f['key'] for _, _, f in chosen])
            else:
                for dataset, y, f in chosen:
                    audit(c, sid, caller, 'file', ticker, ip, dataset=dataset, year=y, key=f['key'], bytes_=f['bytes'])
        if (pruned['at'] is None or time.monotonic() - pruned['at'] > PRUNE_EVERY_SECONDS) and hasattr(store, 'prune'):
            pruned['at'] = time.monotonic()                  # at most once per worker per 6 hours, outside the quota lock
            with store.tx() as c:
                store.prune(c, ACCESS_LOG_DAYS)
        return ttl

    def ticker_quota(caller: Caller, ticker):
        """Phase 3c: a capped owner's /bundle grants no presigned file (its cuts are counted when GET /cut serves them),
        but it is still held to the ticker quotas before any cut is built (no audit row: nothing is granted yet)."""
        with store.tx() as c:
            row = admit(c, caller)
            take(c, row['subscriber_id'], quota.check(limits_of(c, caller, row),
                                                      store.usage(c, row['subscriber_id'], **meter(caller)),
                                                      ticker=ticker), caller)

    def file_answer(y, f, ttl):
        return {'year': y, 'url': bucket.presign(f['key'], ttl), 'sha256': f['sha256'], 'bytes': f['bytes'],
                'rows': f['rows']}

    @app.post(f'{API}/files')
    def files(body: FilesRequest, request: Request, caller=Depends(granted)):
        """Phase 3c: an owner needs the ticker and the data set; with a history cap only a file entirely after the window
        start (its manifest `first`) is granted, any other is refused (terminal.history_days)."""
        same_origin_post(request)
        need_ticker(caller, body.ticker)
        need_dataset(caller, body.dataset)
        m = ticker_manifest(body.ticker)
        published = m.get('datasets', {}).get(body.dataset, {}).get('files', {})
        if body.dataset == 'events':
            if 'all' not in published:
                error(404, 'no_events', f'No corporate action or insider event is published for {body.ticker}.')
            years, ids = [None], ['all']
        else:
            years = sorted(set(body.years))
            ids = [str(y) for y in years]
            missing = [y for y in years if str(y) not in published]
            if missing:
                error(404, 'year_not_published', f'{body.dataset} {body.ticker} has no file for {missing}; published '
                                                 f'years: {sorted(int(y) for y in published if y.isdigit())}. '
                                                 'Older data: /history.')
        chosen = [(body.dataset, y, published[i]) for y, i in zip(years, ids)]
        after = window(caller, m, body.dataset)
        if after is not None:
            old = [i for (_, _, f), i in zip(chosen, ids) if not str(f.get('first') or '')[:10] > after.isoformat()]
            if old:
                beyond(caller, body.dataset, f'The {body.dataset} file(s) {", ".join(old)} of {body.ticker} (rows on or '
                                             f'before {after.isoformat()})', after)
        ttl = grant(request, caller, body.ticker, chosen)
        return {'ticker': body.ticker, 'dataset': body.dataset, 'expires_in_seconds': ttl, 'encoding': 'gzip json',
                'files': [file_answer(y, f, ttl) for _, y, f in chosen]}

    cuts = CutCache()

    def cut_of(m, ticker, dataset, days):
        """The Cut (cut.py) of a dated dataset, None when no row is in the window; CutError when it cannot be cut."""
        return make_cut(bucket.read, m, ticker, dataset, days, cuts)

    def cut_url(ticker, dataset, sha):
        return f'{API}/cut/{ticker}/{dataset}?sha256={sha}'

    @app.post(f'{API}/bundle')
    def bundle(body: BundleRequest, request: Request, caller=Depends(granted)):
        """The manifest and every published file of the asked datasets of one ticker (oldest year first); a dataset the
        ticker does not have (broker for an index, events for a ticker without events) answers with no files.

        Phase 3c, for an owner whose plan is not *: a ticker outside the plan is refused (terminal.tickers); a dataset
        outside it answers {"locked": true, "capability": "terminal.dataset:<id>"} with no URL, sha or rows (the asked
        intraday timeframe likewise, dataset `intraday`). With a history cap N every dated dataset answers one file,
        its cut (cut.py), in the pack shape the page reads: {"year": null, "pack": "cut", "url":
        "/api/terminal/v1/cut/<TICKER>/<dataset>?sha256=<hex>" (relative: edge-bff relays it), "sha256", "bytes",
        "rows"}; `packs` makes no difference, intraday bars are not cut ({locked, capability terminal.history_days,
        reason}) and a dataset that cannot be cut answers {locked, capability terminal.history_days, reason}, never
        its whole files."""
        same_origin_post(request)
        need_ticker(caller, body.ticker)
        m = ticker_manifest(body.ticker)
        caps = plan(caller)
        names = list(dict.fromkeys(body.datasets))
        locked = {n: {'locked': True, 'capability': f'terminal.dataset:{n}'}
                  for n in names if caps and not caps.dataset_ok(n)}
        # a dataset the ticker does not have (no datasets.<name> in its manifest) is answered with no files, as for an
        # uncapped owner, never as a history lock (3c check C3-4): only a dataset that exists is cut
        capped = [n for n in names if n not in locked and caps and caps.history_days is not None
                  and n in (m.get('datasets') or {})]
        packs = m.get('packs', {}) if body.packs else {}
        chosen = []
        for name in names:
            if name in locked or name in capped:
                continue
            published = m.get('datasets', {}).get(name, {}).get('files', {})
            ids = ['all'] if name == 'events' else sorted((y for y in published if y.isdigit()), key=int)
            if name in ('price', 'yield') and name in packs:
                chosen.append((name, name, packs[name]))
                continue
            if name == 'broker' and 'broker-archive' in packs:
                last = packs['broker-archive'].get('years', [0, 0])[1]
                chosen.append(('broker', 'broker-archive', packs['broker-archive']))    # older years first, then yearly
                ids = [y for y in ids if int(y) > last]
            chosen += [(name, None if i == 'all' else int(i), published[i]) for i in ids if i in published]
        intraday = m.get('intraday') or {}
        series = intraday.get(body.timeframe) if body.timeframe else None
        intraday_lock = None
        if body.timeframe and caps and not caps.dataset_ok('intraday'):
            intraday_lock = {'locked': True, 'capability': 'terminal.dataset:intraday'}
        elif body.timeframe and caps and caps.history_days is not None:
            intraday_lock = {'locked': True, 'capability': 'terminal.history_days',
                             'reason': 'intraday bars are not cut to a window of days, so a plan with a history '
                                       'limit is not served them'}
        if series and not intraday_lock:
            chosen += [('intraday', part, series['files'][part]) for part in ('archive', 'current')
                       if part in series.get('files', {})]
        made = {}
        if capped:
            ticker_quota(caller, body.ticker)                # before any bucket read of a cut
            for name in capped:
                try:
                    made[name] = cut_of(m, body.ticker, name, caps.history_days)
                except CutError as e:
                    locked[name] = {'locked': True, 'capability': 'terminal.history_days',
                                    'reason': f'{name} cannot be cut to the plan\'s window: {e.reason}'}
        ttl = grant(request, caller, body.ticker, chosen, one_row=True) if chosen else 0
        out = {}
        for name in names:
            if name in locked:
                out[name] = locked[name]
                continue
            ds = m.get('datasets', {}).get(name, {})
            out[name] = {'data_through': ds.get('data_through'), 'first_year': ds.get('first_year'),
                         'files': [{**file_answer(None if isinstance(y, str) else y, f, ttl), **({'pack': y} if isinstance(y, str) else {})}
                                   for n, y, f in chosen if n == name]}
            if name in made:
                cut = made[name]
                out[name]['files'] = [] if cut is None else [
                    {'year': None, 'url': cut_url(body.ticker, name, cut.sha256), 'sha256': cut.sha256,
                     'bytes': cut.bytes, 'rows': cut.rows, 'pack': 'cut'}]
                out[name]['cut'] = {'history_days': caps.history_days,
                                    'after': window_after(ds.get('data_through'), caps.history_days).isoformat()}
        if body.timeframe:
            # the asked timeframe: its files (archive first, then the current period) and how to read them; no files
            # when the ticker has none of it
            out['intraday'] = {'timeframe': body.timeframe, **intraday_lock} if intraday_lock else {
                'timeframe': body.timeframe, 'files': [
                    {**file_answer(None, f, ttl), 'part': part} for n, part, f in chosen if n == 'intraday'],
                **{k: (series or {}).get(k) for k in ('first', 'last', 'rows', 'bars_per_year', 'timezone',
                                                      'utc_offset_seconds', 'period', 'current')}}
        # every intraday timeframe of the ticker, so a page knows which it can offer before asking for one
        timeframes = {tf: {k: s.get(k) for k in ('first', 'last', 'rows', 'bars_per_year')} for tf, s in intraday.items()}
        # EXEC-FI-TERMINAL: a government bond's manifest says so (`kind` fixed_income, `instrument` name, country, units)
        return {'ticker': body.ticker, 'window': m.get('window'), 'generated_at': m.get('generated_at'),
                'expires_in_seconds': ttl, 'encoding': 'gzip json', 'datasets': out, 'timeframes': timeframes,
                'kind': m.get('kind', 'equity'), 'instrument': m.get('instrument')}

    @app.get(f'{API}/cut/{{ticker}}/{{dataset}}')
    def cut_file(ticker: str, dataset: str, request: Request,
                 sha256: str = Query(pattern=SHA256.pattern), caller=Depends(granted)):
        """Phase 3c (decision D2 = A): the cut of one dated dataset of one ticker for the owner whose plan caps the
        history at N days, N read from x-terminal-capabilities only (never from the query). The answer is the cut's
        gzip bytes as they are (application/gzip, no Content-Encoding: the page checks the sha256 of these very
        bytes), with ETag and X-Terminal-Cut-Sha256. It is counted as one file of its bytes, with one audit row
        (object_key cut/<TICKER>/<dataset>/<N>/<sha256>). `sha256` is the one /bundle announced: when the publication
        changed since, the current cut is served, the page's check fails and it asks a new /bundle (rack.ts)."""
        caps = plan(caller)
        if not caps or caps.history_days is None:
            error(404, 'no_cut', f'GET {API}/cut serves a cut only to an EDGE owner whose plan limits the history '
                                 f'(x-terminal-capabilities "history_days": N); this caller has no limit. Fix: ask POST '
                                 f'{API}/bundle, whose answer names every file to read. Example: POST {API}/bundle '
                                 f'{{"ticker": "BBCA", "datasets": ["price"], "packs": true}}.')
        if dataset not in DATED:
            error(404, 'unknown_dataset', f'A cut is made of a dated data set: {", ".join(DATED)}; {dataset[:32]!r} is '
                                          f'not one. Example: GET {API}/cut/BBCA/price?sha256=<the hex /bundle gave>.')
        need_ticker(caller, ticker)
        need_dataset(caller, dataset)
        m = ticker_manifest(ticker)
        if dataset not in (m.get('datasets') or {}):
            # the ticker has no such dataset: nothing to cut (3c check C3-4), as /bundle answers it with no file
            error(404, 'no_rows_in_window', f'{ticker} has no {dataset} data set; POST {API}/bundle answers it with no '
                                            'file.')
        try:
            cut = cut_of(m, ticker, dataset, caps.history_days)
        except CutError as e:
            error(503, 'cut_unavailable', f'{dataset} of {ticker} cannot be cut to the plan\'s window: {e.reason}. It is '
                                          'not served whole; try again after the next publication.')
        if cut is None:
            error(404, 'no_rows_in_window', f'{dataset} of {ticker} has no row in the plan\'s last '
                                            f'{caps.history_days} days; POST {API}/bundle answers it with no file.')
        grant(request, caller, ticker, [(dataset, None, {'key': f'cut/{ticker}/{dataset}/{caps.history_days}/{cut.sha256}',
                                                          'bytes': cut.bytes})])
        return Response(cut.body, media_type='application/gzip',
                        headers={'ETag': f'"{cut.sha256}"', 'X-Terminal-Cut-Sha256': cut.sha256,
                                 'X-Terminal-Cut-Rows': str(cut.rows)})

    @app.post(f'{API}/xsection')
    def xsection(body: XsectionRequest, request: Request, caller=Depends(xsection_caller)):
        """EXEC-SCREENER (P1 a, user 2026-10-28): presigned URLs for cross-sectional files of the current publication,
        named by their /state index names; the screener-worker's service key (EXEC-MU-RUNTIME T1) or, until a later
        step removes it, the gateway key (xsection_caller; both on the private network). Only
        index keys are presigned (xsection_index). One file per name and their bytes count against the quota under the
        REF pseudo-ticker (never an opened ticker), with one audit row (dataset 'xsection') listing every key. The
        answer names its publication (finished_at) and each file's sha256: during the first manifest_cache_seconds
        after a run another process may still serve the previous one, whose files stay in the bucket."""
        state = bucket.state()
        if not state:
            error(503, 'state_unavailable', 'The publication state could not be read; try again shortly.')
        index = xsection_index(state.get('xsection')) or {}
        names = list(dict.fromkeys(body.names))
        missing = [n for n in names if n not in index]
        if missing:
            error(404, 'xsection_not_published', f'No cross-sectional file {missing} in the publication of '
                                                 f'{state.get("finished_at")}; indexed: {sorted(index) or "none"}. '
                                                 f'GET {API}/state lists the index.')
        chosen = [('xsection', n, index[n]) for n in names]
        ttl = grant(request, caller, quota.REF, chosen, one_row=True, row_dataset='xsection')
        return {'finished_at': state.get('finished_at'), 'expires_in_seconds': ttl, 'encoding': 'gzip json',
                'files': [{'name': n, 'url': bucket.presign(f['key'], ttl), 'sha256': f['sha256'], 'bytes': f['bytes'],
                           'rows': f['rows'], 'as_of': f['as_of']} for _, n, f in chosen]}

    def page_routes(family):
        """EXEC-RADAR R5, EXEC-OVERVIEW: GET /<family> lists the page's file index of the current publication ({name:
        {sha256, bytes, rows, as_of}}; no key, nothing granted); POST /<family> presigns files of it by their index
        names. Both for the EDGE gateway only (page_caller); a grant is counted under the REF pseudo-ticker with one
        audit row (dataset = the family), as /xsection."""
        label = PAGE_LABELS[family]

        def files(request: Request, caller=Depends(page_caller(family))):
            finished, index = bucket.page(family)
            if finished is None:
                error(503, 'state_unavailable', 'The publication state could not be read; try again shortly.')
            return {'finished_at': finished, 'files': {n: {k: e[k] for k in ('sha256', 'bytes', 'rows', 'as_of')}
                                                       for n, e in sorted((index or {}).items())}}

        def grant_files(body: PageRequest, request: Request, caller=Depends(page_caller(family))):
            finished, index = bucket.page(family)
            if finished is None:
                error(503, 'state_unavailable', 'The publication state could not be read; try again shortly.')
            index = index or {}
            names = list(dict.fromkeys(body.names))
            missing = [n for n in names if n not in index]
            if missing:
                error(404, f'{family}_not_published', f'No file {missing} of {label} in the publication of {finished}; '
                                                      f'GET {API}/{family} lists the published ones.')
            chosen = [(family, n, index[n]) for n in names]
            ttl = grant(request, caller, quota.REF, chosen, one_row=True, row_dataset=family)
            return {'finished_at': finished, 'expires_in_seconds': ttl, 'encoding': 'gzip json',
                    'files': [{'name': n, 'url': bucket.presign(f['key'], ttl), 'sha256': f['sha256'],
                               'bytes': f['bytes'], 'rows': f['rows'], 'as_of': f['as_of']} for _, n, f in chosen]}

        app.get(f'{API}/{family}', name=f'{family}_files')(files)
        app.post(f'{API}/{family}', name=f'{family}_grant')(grant_files)

    for family in PAGE_FAMILIES:
        page_routes(family)

    def history_range(m, dataset, lo: dt.date, hi: dt.date, max_days: int):
        first_year = (m.get('datasets', {}).get(dataset, {}).get('first_year')
                      or (m.get('window') or {}).get('first_year'))
        if hi < lo:
            error(400, 'invalid_range', '`from` must be on or before `to`.')
        if (hi - lo).days + 1 > max_days:
            error(400, 'range_too_long', f'At most {max_days} days per request; split the range.')
        if first_year and hi >= dt.date(first_year, 1, 1):
            error(400, 'use_published_files', f'Dates from {first_year}-01-01 are published as files; '
                                              f'request them with POST {API}/files. History serves older dates only.')

    def run_history(request, caller, ticker, kind, fetch, cols, max_days, lo, hi):
        """Phase 3c: an owner needs the ticker and the data set (price or broker); with a history cap a range that
        starts on or before the window start is refused (terminal.history_days), so /history never serves older rows."""
        service_only_files(caller, f'GET {API}/history/{kind.removeprefix("history_")}')
        dataset = HISTORY_DATASET[kind]
        need_ticker(caller, ticker)
        need_dataset(caller, dataset)
        m = ticker_manifest(ticker)
        after = window(caller, m, dataset)
        if after is not None and lo <= after:
            beyond(caller, dataset, f'{dataset} history from {lo.isoformat()}', after)
        history_range(m, dataset, lo, hi, max_days)
        with store.tx() as c:
            row = admit(c, caller)
            sid = row['subscriber_id']
            limits = limits_of(c, caller, row)
            take(c, sid, quota.check(limits, store.usage(c, sid, **meter(caller)), history=1, ticker=ticker), caller)
            rows = fetch(c)
            data = ({n: [r[k] for r in rows] for n, k in zip(cols, rows[0].keys())} if rows
                    else {n: [] for n in cols})
            body = {'ticker': ticker, 'from': lo.isoformat(), 'to': hi.isoformat(), 'columns': cols, **data}
            size = len(json.dumps(body, separators=(',', ':')))
            take(c, sid, quota.check(limits, store.usage(c, sid, **meter(caller)), bytes_=size), caller)
            audit(c, sid, caller, kind, ticker, ip_of(request), bytes_=size)
        return body

    @app.get(f'{API}/history/price')
    def history_price(request: Request, ticker: str = Query(pattern=TICKER.pattern),
                      date_from: dt.date = Query(alias='from'), date_to: dt.date = Query(alias='to'),
                      caller=Depends(granted)):
        return run_history(request, caller, ticker, 'history_price',
                           lambda c: store.price_history(c, ticker, date_from, date_to),
                           ['d', 'o', 'h', 'l', 'c', 'v'], MAX_PRICE_HISTORY_DAYS, date_from, date_to)

    @app.get(f'{API}/history/broker')
    def history_broker(request: Request, ticker: str = Query(pattern=TICKER.pattern),
                       date_from: dt.date = Query(alias='from'), date_to: dt.date = Query(alias='to'),
                       brokers: list[str] | None = Query(default=None, max_length=20),
                       investor_type: Literal['Foreign', 'Domestic'] | None = None,
                       market_board: Literal['Regular', 'Nego', 'Tunai'] | None = None,
                       caller=Depends(granted)):
        if brokers and not all(re.fullmatch(BROKER, b) for b in brokers):
            error(400, 'invalid_broker', 'A broker code is two capital letters or digits, for example YP.')
        return run_history(request, caller, ticker, 'history_broker',
                           lambda c: store.broker_history(c, ticker, date_from, date_to, brokers or None,
                                                          investor_type, market_board),
                           ['d', 'b', 'i', 'm', 'bv', 'sv', 'bl', 'sl', 'gap'], MAX_BROKER_HISTORY_DAYS,
                           date_from, date_to)

    # ---- admin (option A: accounts managed by the administrator) ---------------------------------------------
    @app.get(f'{API}/admin/subscribers', dependencies=[Depends(admin)])
    def list_subscribers():
        with store.tx() as c:
            rows = store.list_subscribers(c)
        return {'subscribers': [{k: (v.isoformat() if isinstance(v, dt.datetime) else v) for k, v in r.items()}
                                for r in rows]}

    @app.post(f'{API}/admin/subscribers', status_code=201, dependencies=[Depends(admin)])
    def add_subscriber(body: NewSubscriber, request: Request):
        with store.tx() as c:
            if store.subscriber_by_email(c, body.email):
                error(409, 'email_exists', f'{body.email} already has an account.')
            sid = store.add_subscriber(c, body.email, body.display_name.strip(), password_verifier(body.password),
                                       body.expires_at)
            store.admin_log(c, 'add', sid, {'email': body.email, 'expires_at': body.expires_at.isoformat()},
                            ip_of(request))
        return {'subscriber_id': sid, 'email': body.email}

    @app.post(f'{API}/admin/subscribers/{{sid}}', dependencies=[Depends(admin)])
    def change_subscriber(sid: int, body: SubscriberChange, request: Request):
        fields = body.model_dump(exclude_none=True)
        if 'password' in fields:
            fields['password_hash'] = password_verifier(fields.pop('password'))
        if not fields:
            error(400, 'nothing_to_change', 'Send at least one field to change.')
        with store.tx() as c:
            if not store.update_subscriber(c, sid, fields):
                error(404, 'unknown_subscriber', f'No subscriber {sid}.')
            store.admin_log(c, 'change', sid, {k: (v.isoformat() if isinstance(v, dt.datetime) else v)
                                               for k, v in fields.items() if k != 'password_hash'}
                            | ({'password': 'reset'} if 'password_hash' in fields else {}), ip_of(request))
        accounts.clear()                                     # this process reads the changed account at once
        return {'subscriber_id': sid, 'changed': sorted(k if k != 'password_hash' else 'password' for k in fields)}

    return app
