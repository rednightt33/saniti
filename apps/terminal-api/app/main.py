"""Subscriber terminal API (EXEC-TERMINAL-API, verification/terminal_api/DESIGN.md section 3).

Subscribers sign in, read a ticker's manifest and receive short-lived presigned URLs for the pre-published files in
the private bucket terminal-display; data older than the published window comes from PostgreSQL. Every URL and query
is logged and counted against the subscriber's quotas (terminal.quota). Accounts are managed by the administrator
through /admin (option A, user 2026-10-25).
"""
import datetime as dt
import json
import re
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from . import quota
from .config import Settings
from .security import client_ip, new_token, password_verifier, same_secret, token_hash, verify_password

COOKIE = 'terminal_session'
PROXY_HEADER = 'x-terminal-proxy-key'
TICKER = re.compile(r'^[A-Z0-9]{1,12}$')
BROKER = r'^[A-Z0-9]{2}$'
API = '/api/terminal/v1'
MAX_YEARS_PER_CALL = 6
MAX_PRICE_HISTORY_DAYS = 3660
MAX_BROKER_HISTORY_DAYS = 366
REF_FILES = {'tickers': 'v1/ref/tickers.json.gz', 'brokers': 'v1/ref/brokers.json.gz', 'logos': 'v1/ref/logos.json.gz'}
LOGO_CACHE_SECONDS = 7 * 24 * 3600


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
        store = Store(settings.database_url)
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

    def proxied(request: Request):
        """True for a request forwarded by edge-bff with the proxy key; a wrong key is refused, never ignored."""
        key = request.headers.get(PROXY_HEADER)
        if key is None:
            return False
        if not settings.proxy_key or not same_secret(key, settings.proxy_key):
            error(401, 'proxy_key_rejected', 'The gateway key is not valid.')
        return True

    def same_origin_post(request: Request):
        """Cookie-authenticated writes must come from an allowed origin (no cross-site form posts). The gateway checks
        its own page's origin and CSRF token before forwarding."""
        if proxied(request):
            return
        if request.headers.get('origin', '').rstrip('/') not in settings.allowed_origins:
            error(403, 'origin_not_allowed', 'This request must come from the terminal page.')

    def subscriber(request: Request):
        if proxied(request):
            with store.tx() as c:
                row = store.proxied_subscriber(c, settings.proxy_subscriber)
            if not row:
                error(401, 'session_ended', 'The terminal account of this gateway is not active.')
            return row
        token = request.cookies.get(COOKIE)
        if not token:
            error(401, 'not_signed_in', 'Sign in first.')
        with store.tx() as c:
            row = store.session_subscriber(c, token_hash(token))
        if not row:
            error(401, 'session_ended', 'Your session ended or your subscription is not active. Sign in again.')
        return row

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
        response.delete_cookie(COOKIE, path='/')
        return {'status': 'signed_out'}

    @app.get(f'{API}/auth/session')
    def session(who=Depends(subscriber)):
        return {'email': who['email'], 'display_name': who['display_name'],
                'subscription_expires_at': who['expires_at'].isoformat()}

    @app.post(f'{API}/auth/change-password')
    def change_password(body: ChangePassword, request: Request, who=Depends(subscriber)):
        same_origin_post(request)
        with store.tx() as c:
            if not verify_password(body.current_password, store.password_hash(c, who['subscriber_id'])):
                error(403, 'wrong_password', 'The current password is not correct.')
            store.set_password(c, who['subscriber_id'], password_verifier(body.new_password),
                               token_hash(request.cookies.get(COOKIE)))
        return {'status': 'password_changed', 'other_sessions': 'signed out'}

    # ---- data ------------------------------------------------------------------------------------------------
    @app.get(f'{API}/reference/{{name}}')
    def reference(name: str, request: Request, who=Depends(subscriber)):
        key = REF_FILES.get(name)
        if not key:
            error(404, 'unknown_reference', f'Reference files: {", ".join(REF_FILES)}.')
        sid = who['subscriber_id']
        with store.tx() as c:
            store.lock_subscriber(c, sid)
            limits = store.limits(c, sid)
            take(c, sid, quota.check(limits, store.usage(c, sid), files=1, ticker=quota.REF))
            ttl = limits['url_ttl_seconds']
            store.log_access(c, sid, 'file', quota.REF, ip_of(request), dataset='reference', key=key)
        return {'url': bucket.presign(key, ttl), 'expires_in_seconds': ttl, 'encoding': 'gzip json'}

    @app.get(f'{API}/logo/{{ticker}}')
    def logo(ticker: str, request: Request, who=Depends(subscriber)):
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

    @app.get(f'{API}/manifest/{{ticker}}')
    def manifest(ticker: str, who=Depends(subscriber)):
        m = ticker_manifest(ticker)
        return {'ticker': ticker, 'window': m.get('window'), 'generated_at': m.get('generated_at'),
                'datasets': {name: {'data_through': ds.get('data_through'),
                                    'years': {y: {k: f[k] for k in ('bytes', 'rows', 'first', 'last', 'sha256')}
                                              for y, f in sorted(ds.get('files', {}).items())}}
                             for name, ds in m.get('datasets', {}).items()}}

    def grant(request, who, ticker, chosen):
        """Quota and audit for a set of files of one ticker, under one lock: the same counting for /files and /bundle.
        chosen = [(dataset, year or None, manifest file entry)]."""
        size = sum(f['bytes'] for _, _, f in chosen)
        sid, ip = who['subscriber_id'], ip_of(request)
        with store.tx() as c:
            store.lock_subscriber(c, sid)
            limits = store.limits(c, sid)
            take(c, sid, quota.check(limits, store.usage(c, sid), files=len(chosen), ticker=ticker, bytes_=size))
            ttl = limits['url_ttl_seconds']
            for dataset, y, f in chosen:
                store.log_access(c, sid, 'file', ticker, ip, dataset=dataset, year=y, key=f['key'], bytes_=f['bytes'])
        return ttl

    def file_answer(y, f, ttl):
        return {'year': y, 'url': bucket.presign(f['key'], ttl), 'sha256': f['sha256'], 'bytes': f['bytes'],
                'rows': f['rows']}

    @app.post(f'{API}/files')
    def files(body: FilesRequest, request: Request, who=Depends(subscriber)):
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
        ttl = grant(request, who, body.ticker, chosen)
        return {'ticker': body.ticker, 'dataset': body.dataset, 'expires_in_seconds': ttl, 'encoding': 'gzip json',
                'files': [file_answer(y, f, ttl) for _, y, f in chosen]}

    @app.post(f'{API}/bundle')
    def bundle(body: BundleRequest, request: Request, who=Depends(subscriber)):
        """The manifest and every published file of the asked datasets of one ticker (oldest year first); a dataset the
        ticker does not have (broker for an index, events for a ticker without events) answers with no files."""
        same_origin_post(request)
        m = ticker_manifest(body.ticker)
        chosen = []
        for name in dict.fromkeys(body.datasets):
            published = m.get('datasets', {}).get(name, {}).get('files', {})
            ids = ['all'] if name == 'events' else sorted((y for y in published if y.isdigit()), key=int)
            chosen += [(name, None if i == 'all' else int(i), published[i]) for i in ids if i in published]
        ttl = grant(request, who, body.ticker, chosen) if chosen else 0
        out = {}
        for name in dict.fromkeys(body.datasets):
            ds = m.get('datasets', {}).get(name, {})
            out[name] = {'data_through': ds.get('data_through'), 'first_year': ds.get('first_year'),
                         'files': [file_answer(y, f, ttl) for n, y, f in chosen if n == name]}
        return {'ticker': body.ticker, 'window': m.get('window'), 'generated_at': m.get('generated_at'),
                'expires_in_seconds': ttl, 'encoding': 'gzip json', 'datasets': out}

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

    def run_history(request, who, ticker, kind, fetch, cols, max_days, lo, hi):
        m = ticker_manifest(ticker)
        history_range(m, 'price' if kind == 'history_price' else 'broker', lo, hi, max_days)
        sid = who['subscriber_id']
        with store.tx() as c:
            store.lock_subscriber(c, sid)
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
                      who=Depends(subscriber)):
        return run_history(request, who, ticker, 'history_price',
                           lambda c: store.price_history(c, ticker, date_from, date_to),
                           ['d', 'o', 'h', 'l', 'c', 'v'], MAX_PRICE_HISTORY_DAYS, date_from, date_to)

    @app.get(f'{API}/history/broker')
    def history_broker(request: Request, ticker: str = Query(pattern=TICKER.pattern),
                       date_from: dt.date = Query(alias='from'), date_to: dt.date = Query(alias='to'),
                       brokers: list[str] | None = Query(default=None, max_length=20),
                       investor_type: Literal['Foreign', 'Domestic'] | None = None,
                       market_board: Literal['Regular', 'Nego', 'Tunai'] | None = None,
                       who=Depends(subscriber)):
        if brokers and not all(re.fullmatch(BROKER, b) for b in brokers):
            error(400, 'invalid_broker', 'A broker code is two capital letters or digits, for example YP.')
        return run_history(request, who, ticker, 'history_broker',
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
        return {'subscriber_id': sid, 'changed': sorted(k if k != 'password_hash' else 'password' for k in fields)}

    return app
