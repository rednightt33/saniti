"""Subscriber terminal API (EXEC-TERMINAL-API, verification/terminal_api/DESIGN.md section 3).

Subscribers sign in, read a ticker's manifest and receive short-lived presigned URLs for the pre-published files in
the private bucket terminal-display; data older than the published window comes from PostgreSQL. Every URL and query
is logged and counted against the subscriber's quotas (terminal.quota). Accounts are managed by the administrator
through /admin (option A, user 2026-10-25).

EXEC-MU-RUNTIME Phase 1b (user 2026-10-28, option A; verification/edge_multiuser/runtime/terminal.md T1, T3, T5, T9):
service accounts for the workers (accounts.py, config.py TERMINAL_SERVICE_KEY_<NAME>), the account read inside each
grant's transaction after its lock and cached 60 s for the routes that grant nothing, the reference file index
(bucket.py refs_index) and TERMINAL_POOL_MAX.
"""
import datetime as dt
import json
import re
import time
from contextlib import asynccontextmanager
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from . import quota
from .accounts import AccountCache, Caller
from .bucket import REF_NAME, XSECTION_NAME, refs_index, xsection_index
from .config import Settings, service_email, service_variable
from .security import client_ip, new_token, password_verifier, same_secret, token_hash, verify_password

COOKIE = 'terminal_session'
PROXY_HEADER = 'x-terminal-proxy-key'
# T2 (EXEC-MU-RUNTIME Phase 4, not built): the gateway will name the EDGE owner in this header. A service key acts as
# its own account and may never name one (T1); the gateway's header is ignored until T2, as before.
OWNER_HEADER = 'x-terminal-proxy-owner'
# T1: the services that may be granted cross-sectional files (one file holds every ticker); the gateway key keeps its
# access until a later, separate step removes it (compatibility with the deployed screener-worker build)
XSECTION_SERVICES = frozenset({'screener-worker'})
TICKER = re.compile(r'^[A-Z0-9]{1,12}$')
BROKER = r'^[A-Z0-9]{2}$'
API = '/api/terminal/v1'
MAX_YEARS_PER_CALL = 6
MAX_PRICE_HISTORY_DAYS = 3660
MAX_BROKER_HISTORY_DAYS = 366
REF_FILES = {'tickers': 'v1/ref/tickers.json.gz', 'brokers': 'v1/ref/brokers.json.gz', 'logos': 'v1/ref/logos.json.gz'}
LOGO_CACHE_SECONDS = 7 * 24 * 3600
ACCESS_LOG_DAYS = 90            # EXEC-TERMINAL-SPEED (user 2026-10-26): audit rows are kept 90 days
PRUNE_EVERY_SECONDS = 6 * 3600
MAX_XSECTION_NAMES = 16         # EXEC-SCREENER: names per /xsection call (Phase 1 indexes 2, Phase 2 about 5)


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


class BundleRequest(Strict):
    """EXEC-TERMINAL-UI-1026 U6 (user 2026-10-26: "Satu panggilan API per saham ... sesuai dengan ticker yang di display"):
    every published file of the chosen datasets of one ticker in one answer."""
    ticker: str = Field(pattern=TICKER.pattern)
    datasets: list[Literal['price', 'broker', 'events']] = Field(default=['price', 'broker', 'events'], min_length=1,
                                                                 max_length=3)
    # EXEC-TERMINAL-SPEED: the packs instead of yearly files where the manifest has them (price: one file for every
    # year; broker: the archive pack plus the last two yearly files)
    packs: bool = False


class XsectionRequest(Strict):
    """EXEC-SCREENER (P1 a, user 2026-10-28): cross-sectional files of the current publication by their index names
    (state.json `xsection`, shown on /state); a client never names a key."""
    names: list[Annotated[str, Field(pattern=XSECTION_NAME.pattern)]] = Field(min_length=1,
                                                                              max_length=MAX_XSECTION_NAMES)


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


def error(status, code, message):
    raise HTTPException(status, detail={'error': code, 'message': message})


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
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.allowed_origins), allow_credentials=True,
                       allow_methods=['GET', 'POST'], allow_headers=['Content-Type'])

    @app.middleware('http')
    async def headers(request: Request, call_next):
        response = await call_next(request)
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

    def identify(request: Request) -> Caller:
        """Who is calling, from the request alone (no database): the gateway key, a service key or a session cookie.
        A key in x-terminal-proxy-key that is neither is refused, never ignored."""
        key = request.headers.get(PROXY_HEADER)
        if key is None:
            token = request.cookies.get(COOKIE)
            if not token:
                error(401, 'not_signed_in', 'Sign in first.')
            return Caller('session', token_hash=token_hash(token))
        gateway_ok = bool(settings.proxy_key) and same_secret(key, settings.proxy_key)
        matched = [(name, email) for name, k, email in services if same_secret(key, k)]   # every key compared
        if gateway_ok:
            return Caller('gateway', email=settings.proxy_subscriber)
        if not matched:
            error(401, 'proxy_key_rejected',
                  f'The {PROXY_HEADER} header holds no key this terminal-api knows: neither the EDGE gateway key '
                  'nor a service key. Send the value of your own TERMINAL_PROXY_KEY variable, which references '
                  "terminal-api's TERMINAL_PROXY_KEY (edge-bff) or its TERMINAL_SERVICE_KEY_<NAME> (a worker). "
                  'Example: TERMINAL_PROXY_KEY=${{terminal-api.TERMINAL_SERVICE_KEY_BACKTEST_WORKER}} on '
                  'backtest-worker.')
        name, email = matched[0]
        if OWNER_HEADER in request.headers:
            error(400, 'owner_not_allowed',
                  f'{OWNER_HEADER} was sent with the service key of {name}. A service key acts as its own account '
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
        if request.headers.get('origin', '').rstrip('/') not in settings.allowed_origins:
            error(403, 'origin_not_allowed', 'This request must come from the terminal page.')

    def lookup(c, caller: Caller):
        """The caller's account row as it is now, or None: missing, inactive, expired, or a session that ended."""
        if caller.kind == 'session':
            return store.session_subscriber(c, caller.token_hash)
        return store.account(c, caller.email, 'service' if caller.kind == 'service' else 'person')

    def refuse(caller: Caller):
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
        store.lock_subscriber(c, sid)
        row = lookup(c, caller)                              # after the lock
        if row and row['subscriber_id'] != sid:
            sid = row['subscriber_id']
            store.lock_subscriber(c, sid)
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
        if caller and (caller.kind == 'gateway' or (caller.kind == 'service' and caller.name in XSECTION_SERVICES)):
            return known(request)[0]
        who = f'the service key of {caller.name}' if caller else 'a subscriber session'
        error(403, 'gateway_only', f'POST {API}/xsection grants cross-sectional files only to the screener-worker '
                                   f'service key or the EDGE gateway key, sent in the {PROXY_HEADER} header; '
                                   f'{who} cannot ask for them. Fix: call with the screener-worker key '
                                   f'({service_variable("screener-worker")}). One ticker\'s files: POST '
                                   f'{API}/bundle. Example: {PROXY_HEADER}: '
                                   f'${{{{terminal-api.{service_variable("screener-worker")}}}}}.')

    def service_only_files(caller: Caller, route: str):
        """T1: a service account reads published files; the PostgreSQL fallback and password routes are a person's."""
        if caller.kind == 'service':
            error(403, 'not_for_service_accounts',
                  f'{route} is for a subscriber or the EDGE gateway; the service account of {caller.name} reads '
                  f'published files only. Fix: ask POST {API}/bundle for a ticker\'s files (or {API}/xsection, '
                  f'{API}/reference). Example: POST {API}/bundle {{"ticker": "BBCA", "datasets": ["price"], '
                  f'"packs": true}}.')

    def admin(request: Request):
        if not same_secret(request.headers.get('x-terminal-admin-key'), settings.admin_key):
            error(401, 'admin_key_required', 'A valid X-Terminal-Admin-Key header is required.')

    def ticker_manifest(ticker):
        if not TICKER.fullmatch(ticker):
            error(400, 'invalid_ticker', 'A ticker is 1-12 capital letters or digits, for example BBCA.')
        m = bucket.manifest(ticker)
        if not m:
            error(404, 'unknown_ticker', f'No published data for {ticker}.')
        return m

    def take(c, sid, refusal):
        if refusal:
            error(429, 'quota_exceeded', refusal.message())

    # ---- health ----------------------------------------------------------------------------------------------
    @app.get('/health')
    def health():
        return {'status': 'ok'}

    @app.get('/ready')
    def ready():
        try:
            store.ready()
        except Exception:  # noqa: BLE001 - readiness only reports, never leaks the driver error
            return JSONResponse({'status': 'not_ready'}, status_code=503)
        return {'status': 'ready'}

    # ---- auth ------------------------------------------------------------------------------------------------
    @app.post(f'{API}/auth/sign-in')
    def sign_in(body: SignIn, request: Request, response: Response):
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
            error(429, 'too_many_attempts', 'Too many failed sign-ins. Wait 15 minutes and try again.')
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
    @app.get(f'{API}/reference/{{name}}')
    def reference(name: str, request: Request, caller=Depends(granted)):
        """One reference file, counted against the quota under the REF pseudo-ticker (never an opened ticker), one audit
        row. EXEC-MU-RUNTIME T5: the publication's content key when state.json's `refs` index names the file (the
        answer then carries its sha256, bytes and rows, and its bytes count); otherwise, for a publication before the
        index, the fixed key REF_FILES, with sha256, bytes and rows null. A client never names a key."""
        state = bucket.state()
        index = refs_index((state or {}).get('refs')) or {}
        entry = index.get(name) if REF_NAME.fullmatch(name) else None
        if entry is None and name not in REF_FILES:
            error(404, 'unknown_reference', f'Reference files: {", ".join(sorted(set(REF_FILES) | set(index)))}.')
        f = entry or {'key': REF_FILES[name], 'bytes': 0}
        ttl = grant(request, caller, quota.REF, [('reference', None, f)])
        return {'url': bucket.presign(f['key'], ttl), 'expires_in_seconds': ttl, 'encoding': 'gzip json',
                **{k: entry[k] if entry else None for k in ('sha256', 'bytes', 'rows')}}

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
    def publication(who=Depends(reader)):
        """EXEC-BACKTEST-LOAD (user 2026-10-27, K1): the publication the files belong to (state.json, read for the manifest
        cache, at most manifest_cache_seconds old). No file is granted: no quota, no audit row. A reader keeps what it
        derives from the files (the backtest catalog) until finished_at changes. EXEC-SCREENER: `xsection` is the
        run's cross-sectional file index ({name: {key, sha256, bytes, rows, as_of}}, null before the publisher writes
        one); it names keys and hashes but grants nothing (the bucket is private), so a reader with the file cached by
        sha256 asks POST /xsection only for the files it lacks. EXEC-MU-RUNTIME T5: `refs` is the reference file index
        ({name: {key, sha256, bytes, rows}}, null before the publisher writes one), which /reference grants from."""
        state = bucket.state()
        if not state:
            error(503, 'state_unavailable', 'The publication state could not be read; try again shortly.')
        return state

    @app.get(f'{API}/manifest/{{ticker}}')
    def manifest(ticker: str, who=Depends(reader)):
        m = ticker_manifest(ticker)
        return {'ticker': ticker, 'window': m.get('window'), 'generated_at': m.get('generated_at'),
                'datasets': {name: {'data_through': ds.get('data_through'),
                                    'years': {y: {k: f[k] for k in ('bytes', 'rows', 'first', 'last', 'sha256')}
                                              for y, f in sorted(ds.get('files', {}).items())}}
                             for name, ds in m.get('datasets', {}).items()}}

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
            sid = admit(c, caller)['subscriber_id']
            limits = store.limits(c, sid)
            if caller.kind == 'service':
                refusal = quota.check_service(caller.name, limits, store.meter(c, sid, len(chosen), size))
                if refusal:
                    error(429, 'service_ceiling_reached', refusal.message())
            else:
                take(c, sid, quota.check(limits, store.usage(c, sid), files=len(chosen), ticker=ticker, bytes_=size))
            ttl = limits['url_ttl_seconds']
            if one_row:
                store.log_access(c, sid, 'file', ticker, ip, dataset=row_dataset, bytes_=size, keys=[f['key'] for _, _, f in chosen])
            else:
                for dataset, y, f in chosen:
                    store.log_access(c, sid, 'file', ticker, ip, dataset=dataset, year=y, key=f['key'], bytes_=f['bytes'])
        if (pruned['at'] is None or time.monotonic() - pruned['at'] > PRUNE_EVERY_SECONDS) and hasattr(store, 'prune'):
            pruned['at'] = time.monotonic()                  # at most once per worker per 6 hours, outside the quota lock
            with store.tx() as c:
                store.prune(c, ACCESS_LOG_DAYS)
        return ttl

    def file_answer(y, f, ttl):
        return {'year': y, 'url': bucket.presign(f['key'], ttl), 'sha256': f['sha256'], 'bytes': f['bytes'],
                'rows': f['rows']}

    @app.post(f'{API}/files')
    def files(body: FilesRequest, request: Request, caller=Depends(granted)):
        same_origin_post(request)
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
        ttl = grant(request, caller, body.ticker, chosen)
        return {'ticker': body.ticker, 'dataset': body.dataset, 'expires_in_seconds': ttl, 'encoding': 'gzip json',
                'files': [file_answer(y, f, ttl) for _, y, f in chosen]}

    @app.post(f'{API}/bundle')
    def bundle(body: BundleRequest, request: Request, caller=Depends(granted)):
        """The manifest and every published file of the asked datasets of one ticker (oldest year first); a dataset the
        ticker does not have (broker for an index, events for a ticker without events) answers with no files."""
        same_origin_post(request)
        m = ticker_manifest(body.ticker)
        packs = m.get('packs', {}) if body.packs else {}
        chosen = []
        for name in dict.fromkeys(body.datasets):
            published = m.get('datasets', {}).get(name, {}).get('files', {})
            ids = ['all'] if name == 'events' else sorted((y for y in published if y.isdigit()), key=int)
            if name == 'price' and 'price' in packs:
                chosen.append(('price', 'price', packs['price']))
                continue
            if name == 'broker' and 'broker-archive' in packs:
                last = packs['broker-archive'].get('years', [0, 0])[1]
                chosen.append(('broker', 'broker-archive', packs['broker-archive']))    # older years first, then yearly
                ids = [y for y in ids if int(y) > last]
            chosen += [(name, None if i == 'all' else int(i), published[i]) for i in ids if i in published]
        ttl = grant(request, caller, body.ticker, chosen, one_row=True) if chosen else 0
        out = {}
        for name in dict.fromkeys(body.datasets):
            ds = m.get('datasets', {}).get(name, {})
            out[name] = {'data_through': ds.get('data_through'), 'first_year': ds.get('first_year'),
                         'files': [{**file_answer(None if isinstance(y, str) else y, f, ttl), **({'pack': y} if isinstance(y, str) else {})}
                                   for n, y, f in chosen if n == name]}
        return {'ticker': body.ticker, 'window': m.get('window'), 'generated_at': m.get('generated_at'),
                'expires_in_seconds': ttl, 'encoding': 'gzip json', 'datasets': out}

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
        service_only_files(caller, f'GET {API}/history/{kind.removeprefix("history_")}')
        m = ticker_manifest(ticker)
        history_range(m, 'price' if kind == 'history_price' else 'broker', lo, hi, max_days)
        with store.tx() as c:
            sid = admit(c, caller)['subscriber_id']
            limits = store.limits(c, sid)
            take(c, sid, quota.check(limits, store.usage(c, sid), history=1, ticker=ticker))
            rows = fetch(c)
            data = ({n: [r[k] for r in rows] for n, k in zip(cols, rows[0].keys())} if rows
                    else {n: [] for n in cols})
            body = {'ticker': ticker, 'from': lo.isoformat(), 'to': hi.isoformat(), 'columns': cols, **data}
            size = len(json.dumps(body, separators=(',', ':')))
            take(c, sid, quota.check(limits, store.usage(c, sid), bytes_=size))
            store.log_access(c, sid, kind, ticker, ip_of(request), bytes_=size)
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
