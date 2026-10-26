import asyncio
from collections import defaultdict, deque
from contextlib import asynccontextmanager
import hmac
import json
from pathlib import Path
import re
import secrets
import time
from typing import Annotated, Literal
import httpx

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .client import OrcClient, OrcError, public_data
from .config import Settings
from .security import csrf_token, token_hash, verify_password
from .store import Store, StoreError, TERMINAL
from .worker import Worker

COOKIE = 'edge_session'
STOP_RETRIES = 3  # EXEC-Y Fase 1 (I1): a run dispatched a moment ago is registered at Orc on receipt
STATIC = Path(__file__).resolve().parents[1] / 'static'
SCRIPT_NAME = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*')
# EXEC-TERMINAL-API T4/T5: the built terminal page (apps/edge-bff/terminal -> static/terminal-app) and the terminal-api
# routes the page may reach through this gateway (sign-in, password and admin routes stay on terminal-api only)
TERMINAL_APP = STATIC / 'terminal-app'
TERMINAL_ASSET = re.compile(r'[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*\.(?:js|css|woff2|svg|png)')
TERMINAL_ROUTES = {'GET': re.compile(r'manifest/[A-Z0-9]{1,12}|reference/(?:tickers|brokers|logos)|history/(?:price|broker)'
                                      r'|logo/[A-Z0-9]{1,12}'),   # logo: EXEC-TERMINAL-LOGO
                   'POST': re.compile(r'files|bundle')}   # bundle: every file of one ticker in one call (EXEC-TERMINAL-UI-1026 U6)
# The terminal page has no inline script; it downloads its files from the private bucket by presigned URL (virtual-host
# addressing, https://<bucket>.t3.storageapi.dev). Inline style attributes are kept: the reference page builds them.
TERMINAL_CSP = ("default-src 'self'; script-src 'self'; worker-src 'self'; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; "
                "img-src 'self' data: blob:; connect-src 'self' https://*.t3.storageapi.dev; object-src 'none'; "
                "base-uri 'self'; frame-ancestors 'self'")
CONV = r'^conv_[0-9a-f]{32}$'
CHOICES = r'^(QUICK_SUMMARY|ANALYSIS|RESEARCH|EXPLORE|FACT|CLARIFY|INSIGHT|CONTINUE|APPROVE|NEW_TOPIC)$'
# EXEC-MODELS: the shape of a model id and the reasoning levels; Orc checks the choice against its offered models
MODEL_ID = r'^[a-z0-9][a-z0-9._-]*/[a-z0-9][a-z0-9._:-]*$'
LEVELS = r'^(low|medium|high|max|off|on)$'  # EXEC-LOGOS: max (DeepSeek, GLM); Orc checks each model's own
MODELS_CACHE_SECONDS = 600  # Orc reads OpenRouter's prices every hour; the page sees them within ten minutes


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Login(Strict):
    login: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=1, max_length=1024)


class PlanReply(Strict):
    plan_id: str = Field(pattern=r'^rp_[0-9a-f]{24}$')
    action: str = Field(pattern=r'^(APPROVE|REVISE|CANCEL)$')
    revision_instruction: str | None = Field(default=None, max_length=2000)

    @model_validator(mode='after')
    def check_revision(self):
        if self.revision_instruction is not None and self.action != 'REVISE':
            raise ValueError('Only REVISE takes an instruction')
        return self


class AttachedSelection(Strict):
    """EXEC-IMPL-1016 Fase 4.2 (EDGE-CTX A): part of an earlier answer's table attached to the question (Orc checks
    the same bounds)."""
    kind: Literal['TABLE'] = 'TABLE'
    ref: str = Field(pattern=r'^out\.[A-Za-z0-9_]{1,40}$')
    output_id: str | None = Field(default=None, max_length=100)
    title: str | None = Field(default=None, max_length=200)
    columns: list[str] = Field(default_factory=list, max_length=12)
    rows: list[int] = Field(default_factory=list, max_length=50)
    shown_values: list[list[str]] = Field(default_factory=list, max_length=50)
    # EXEC-UI-1024 2c: the user's comment on this attachment (Orc checks the same bound)
    comment: str | None = Field(default=None, max_length=500)

    @model_validator(mode='after')
    def check_bounds(self):
        if any(not 1 <= len(c) <= 100 for c in self.columns) or any(r < 0 for r in self.rows) \
                or any(len(row) > 12 or any(len(cell) > 80 for cell in row) for row in self.shown_values):
            raise ValueError('Selection out of bounds')
        return self


class AttachedFigure(Strict):
    """EXEC-IMPL-1017 Fase 3: one figure inside an attached passage, with the value reference EDGE read from Orc's
    answer_figures or answer_tables (Orc checks the same bounds and reads the figure again from it)."""
    ref: str = Field(min_length=3, max_length=200, pattern=r'^[A-Za-z][A-Za-z0-9_]*\.[^{}|\n]+$')
    shown: str = Field(min_length=1, max_length=40)


class AttachedText(Strict):
    """EXEC-IMPL-1017 Fase 3: a passage of an earlier answer the user selected and attached."""
    kind: Literal['TEXT']
    request_id: str | None = Field(default=None, max_length=100)
    section: Literal['ANSWER', 'ASSUMPTIONS', 'LIMITATIONS', 'FINDINGS', 'PLAN', 'OTHER'] = 'ANSWER'
    quote: str = Field(min_length=1, max_length=1000)
    figures: list[AttachedFigure] = Field(default_factory=list, max_length=20)
    comment: str | None = Field(default=None, max_length=500)  # EXEC-UI-1024 2c


class RunInput(Strict):
    submission_key: str = Field(min_length=1, max_length=100, pattern=r'^[A-Za-z0-9._:-]+$')
    message: str = Field(min_length=1, max_length=16000)
    conversation_id: str | None = Field(default=None, pattern=CONV)
    chosen_option: str | None = Field(default=None, pattern=CHOICES)
    plan_reply: PlanReply | None = None
    model: str | None = Field(default=None, max_length=100, pattern=MODEL_ID)
    reasoning_level: str | None = Field(default=None, pattern=LEVELS)
    # EXEC-FASTLANE: the lane of this message (Orc refuses "fast" while its switch is off)
    lane: str | None = Field(default=None, pattern=r'^(standard|fast)$')
    # EXEC-Y Fase 1 (S3): sent while a run is active = stop that run and run this message next
    after_stop: bool = False
    attached_selection: AttachedSelection | None = None
    # EXEC-IMPL-1017 Fase 3: selections attached anywhere in earlier answers (at most 5)
    attachments: list[AttachedSelection | AttachedText] = Field(default_factory=list, max_length=5)

    @model_validator(mode='after')
    def check_message(self):
        if not self.message.strip():
            raise ValueError('Blank message')
        return self


class ConversationPreferences(Strict):
    bookmarked: bool | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)


class TableExport(Strict):
    columns: list[Annotated[str, Field(max_length=120)]] = Field(default_factory=list, max_length=60)
    titles: list[Annotated[str, Field(max_length=200)]] = Field(default_factory=list, max_length=60)


class Pin(Strict):
    pinned: bool


class BranchInput(Strict):
    """EXEC-ASK-BRANCH (user 2026-10-24): continue an answer in a new conversation: BRANCH (a new tab, listed) or SIDE
    (the answer's side chat, one per answer, not listed). The title is EDGE's wording (edge-labels.js)."""
    kind: Literal['BRANCH', 'SIDE']
    title: str = Field(min_length=1, max_length=200)


def create_app(settings=None, store=None, orc=None):
    settings = settings or Settings.from_env()
    settings.validate()
    store = store or Store(settings.database_url)
    orc = orc or OrcClient(settings)
    worker = Worker(settings, store, orc)
    ready = {'value': False}
    failures = defaultdict(deque)
    # EXEC-TERMINAL-SPEED step 5: one pooled HTTP client to terminal-api, made on first use and closed at shutdown
    # (a client per request opened a new connection every time)
    terminal_http = {'client': None}

    @asynccontextmanager
    async def lifespan(app):
        try:
            await asyncio.to_thread(store.ready)
            ready['value'] = True
        except Exception:
            ready['value'] = False
        task = asyncio.create_task(worker.run()) if settings.worker_enabled and ready['value'] else None
        yield
        worker.stop()
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        orc.close()
        if terminal_http['client'] is not None and hasattr(terminal_http['client'], 'aclose'):
            await terminal_http['client'].aclose()

    app = FastAPI(title='EDGE private gateway', docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.worker, app.state.store = worker, store

    def error(code, status):
        return JSONResponse(status_code=status, content={'error': {'code': code}})

    @app.exception_handler(StoreError)
    async def store_error(_, exc):
        return error(exc.code, exc.status)

    @app.exception_handler(OrcError)
    async def orc_error(_, exc):
        return error(exc.code, exc.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_, exc):
        return error('INVALID_INPUT', 422)

    @app.exception_handler(Exception)
    async def unexpected(_, exc):
        # Deliberately no exception body/traceback: database/http errors may contain secrets.
        return error('SERVICE_UNAVAILABLE', 503)

    @app.middleware('http')
    async def protections(request, call_next):
        if request.method in ('POST', 'PATCH', 'PUT', 'DELETE'):
            # Same-origin writes, including login, cannot be driven by cross-site forms.
            if request.headers.get('origin') != settings.origin:
                return error('ORIGIN_REJECTED', 403)
            total, chunks = 0, []
            async for chunk in request.stream():
                total += len(chunk)
                if total > 131072:
                    return error('REQUEST_TOO_LARGE', 413)
                chunks.append(chunk)
            request._body = b''.join(chunks)
        response = await call_next(request)
        response.headers.setdefault('Cache-Control', 'no-store')
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        # a terminal logo keeps terminal-api's stricter, script-free policy (EXEC-TERMINAL-LOGO); every other answer gets EDGE's
        if request.url.path.startswith('/api/terminal/v1/logo/') and 'sandbox' in response.headers.get('Content-Security-Policy', ''):
            return response
        # EXEC-ASK-BRANCH: the side chat frames EDGE inside EDGE, so only EDGE's own pages may frame it (another site
        # still cannot; frame-ancestors 'self' keeps the clickjacking guard)
        response.headers['Content-Security-Policy'] = TERMINAL_CSP if request.url.path.startswith('/terminal-app/') else "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data: blob:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'self'"
        return response

    async def session(request: Request):
        token = request.cookies.get(COOKIE, '')
        found = await asyncio.to_thread(store.session, token_hash(token)) if re.fullmatch(r'[0-9a-f]{64}', token) else None
        if not found or found['owner_key'] != settings.owner:
            raise HTTPException(status_code=401, detail='Authentication required')
        return token

    async def write(request: Request, token=Depends(session)):
        if not hmac.compare_digest(request.headers.get('x-csrf-token', ''), csrf_token(token, settings.session_secret)):
            raise HTTPException(status_code=403, detail='Invalid CSRF token')
        return token

    async def snapshot(request_id):
        row = await asyncio.to_thread(store.job, settings.owner, request_id)
        data = {k: row[k] for k in ('request_id','conversation_id','state','state_version','run_status','error_code','created_at','updated_at','completed_at')}
        data['message'] = row['input']['message']
        if row['state'] in TERMINAL and row['conversation_id']:
            found = await asyncio.to_thread(orc.request, settings.owner, request_id)
            data['response'] = found.get('response') if found else None
            data['expired'] = found is None
        return jsonable_encoder(data)

    @app.get('/health')
    async def health():
        return {'status': 'ok'}

    @app.get('/ready')
    async def readiness():
        try:
            await asyncio.to_thread(store.ready)
        except Exception:
            return error('NOT_READY', 503)
        return {'status': 'ready'}

    # The page builds its links as <page>#/<route> (index.html staticUrl); opened at "/" that page is index.html, so
    # /index.html is served too (user 2026-10-24: a Branch tab and the side chat showed {"detail":"Not Found"})
    @app.get('/')
    @app.get('/index.html')
    @app.get('/monitor')
    @app.get('/terminal')
    @app.get('/login')
    async def index():
        return FileResponse(STATIC / 'index.html', media_type='text/html')

    # EXEC-CHAT-URL (user 2026-10-24: "B saja ya"): every conversation has its own address, /c/<conversation_id>, like
    # ChatGPT and Claude; the page reads the id from it. Any other id is not a page.
    @app.get('/c/{conversation_id}')
    async def conversation_page(conversation_id: str):
        if not re.fullmatch(CONV, conversation_id):
            return error('NOT_FOUND', 404)
        return FileResponse(STATIC / 'index.html', media_type='text/html')

    # EXEC-X: every page script in static/ (edge-client.js, edge-view.js, edge-labels.js, ...) by its name; a new
    # front-end file needs no route. The name pattern keeps the request inside static/.
    @app.get('/{name}.js')
    async def frontend_script(name: str):
        target = STATIC / f'{name}.js'
        if not SCRIPT_NAME.fullmatch(name) or not target.is_file():
            return error('NOT_FOUND', 404)
        return FileResponse(target, media_type='text/javascript')

    # EXEC-LOGOS (user 2026-10-13, "kasih logo untuk setiap model ya di HP"): the model brand logos (LobeHub icons,
    # MIT, static/model-logos/LICENSE) served from this origin, as the page CSP allows images from 'self' only.
    @app.get('/model-logos/{name}.svg')
    async def model_logo(name: str):
        target = STATIC / 'model-logos' / f'{name}.svg'
        if not SCRIPT_NAME.fullmatch(name) or not target.is_file():
            return error('NOT_FOUND', 404)
        return FileResponse(target, media_type='image/svg+xml', headers={'Cache-Control': 'public, max-age=86400'})

    # EXEC-UI-1015C (user 2026-10-15, "Please also add Favicon"): the EDGE "E" mark for the browser tab and the phone
    # home screen. Public like the page itself, so the login screen shows it too.
    # EXEC-UI-1019B (user 2026-10-19: "Favicon dan PNG dan PDF. Sudah bagus"): the round "E" mark and the EDGE logo of
    # the shared card
    @app.get('/favicon.svg')
    @app.get('/favicon-32.png')
    @app.get('/apple-touch-icon.png')
    @app.get('/edge-logo.svg')
    async def favicon(request: Request):
        name = request.url.path.lstrip('/')
        media = 'image/svg+xml' if name.endswith('.svg') else 'image/png'
        return FileResponse(STATIC / name, media_type=media, headers={'Cache-Control': 'public, max-age=86400'})

    # EXEC-TERMINAL-API T5: the terminal page itself carries no data (the page asks /api/terminal for it), so it is
    # served like EDGE's own page; its hashed assets never change and are cached.
    @app.get('/terminal-app/')
    async def terminal_page():
        target = TERMINAL_APP / 'index.html'
        if not target.is_file():
            return error('NOT_FOUND', 404)
        return FileResponse(target, media_type='text/html')

    @app.get('/terminal-app/assets/{name}')
    async def terminal_asset(name: str):
        target = TERMINAL_APP / 'assets' / name
        if not TERMINAL_ASSET.fullmatch(name) or not target.is_file():
            return error('NOT_FOUND', 404)
        return FileResponse(target, headers={'Cache-Control': 'public, max-age=31536000, immutable'})

    # EXEC-TERMINAL-API T4 (user 2026-10-25: "edge-bff meneruskan /api/terminal/... ke terminal-api --> OK"): the owner's
    # EDGE session reaches terminal-api as its one terminal account (quotas and audit there); writes keep EDGE's
    # same-origin and CSRF checks. Only the data routes are forwarded.
    async def forward_terminal(method: str, path: str, request: Request):
        if not settings.terminal_url:
            return error('TERMINAL_UNAVAILABLE', 503)
        if not TERMINAL_ROUTES[method].fullmatch(path):
            return error('NOT_FOUND', 404)
        body = await request.body() if method == 'POST' else None
        if terminal_http['client'] is None:
            terminal_http['client'] = httpx.AsyncClient(timeout=30)
        try:
            answer = await terminal_http['client'].request(
                method, f'{settings.terminal_url}/api/terminal/v1/{path}', params=request.query_params,
                content=body, headers={'content-type': 'application/json', 'x-terminal-proxy-key': settings.terminal_proxy_key})
        except httpx.HTTPError:
            return error('TERMINAL_UNAVAILABLE', 503)
        if answer.status_code == 200 and answer.headers.get('content-type', '').startswith('image/'):
            # a ticker's logo passes through as it is, with terminal-api's caching and its no-script CSP
            return Response(answer.content, media_type=answer.headers['content-type'], headers={
                k: answer.headers[k] for k in ('cache-control', 'etag', 'content-security-policy') if k in answer.headers})
        try:
            data = answer.json()
        except ValueError:
            return error('TERMINAL_UNAVAILABLE', 503)
        return JSONResponse(status_code=answer.status_code, content=data)

    @app.get('/api/terminal/v1/{path:path}')
    async def terminal_read(path: str, request: Request, _=Depends(session)):
        return await forward_terminal('GET', path, request)

    @app.post('/api/terminal/v1/{path:path}')
    async def terminal_write(path: str, request: Request, _=Depends(write)):
        return await forward_terminal('POST', path, request)

    @app.post('/api/v1/auth/sign-in')
    async def sign_in(body: Login, request: Request):
        ip = request.client.host if request.client else 'unknown'
        # Bounded in-process attempt limiter; this deployment intentionally uses one uvicorn process.
        if len(failures) > 1024:
            failures.clear()
        attempts = failures[ip]
        now = time.monotonic()
        while attempts and attempts[0] < now - 60:
            attempts.popleft()
        if len(attempts) >= 5:
            return error('SIGN_IN_RATE_LIMIT', 429)
        password_ok = await asyncio.to_thread(verify_password, body.password, settings.password_verifier)
        if not hmac.compare_digest(body.login.casefold().encode(), settings.login.casefold().encode()) or not password_ok:
            attempts.append(now)
            return error('INVALID_CREDENTIALS', 401)
        attempts.clear()
        old = request.cookies.get(COOKIE)
        if old:
            await asyncio.to_thread(store.revoke, token_hash(old))
        token = secrets.token_hex(32)
        await asyncio.to_thread(store.session_create, token_hash(token), settings.owner, settings.session_seconds)
        response = JSONResponse({'authenticated': True, 'login': settings.login, 'csrf_token': csrf_token(token, settings.session_secret)})
        response.set_cookie(COOKIE, token, max_age=settings.session_seconds, httponly=True,
                            secure=settings.secure_cookie, samesite='strict', path='/')
        return response

    @app.get('/api/v1/auth/session')
    async def get_session(token=Depends(session)):
        return {'authenticated': True, 'login': settings.login, 'csrf_token': csrf_token(token, settings.session_secret),
                'capabilities': {'deep_research': False, 'model_selection': True, 'cancel': True, 'tool_progress': False,
                                 'retention_days_default': 30}}

    @app.post('/api/v1/auth/sign-out')
    async def sign_out(token=Depends(write)):
        await asyncio.to_thread(store.revoke, token_hash(token))
        response = JSONResponse({'authenticated': False})
        response.delete_cookie(COOKIE, path='/')
        return response

    @app.post('/api/v1/runs', status_code=202)
    async def submit(body: RunInput, _=Depends(write)):
        payload = body.model_dump(exclude_none=True, exclude={'submission_key', 'after_stop'})
        if body.conversation_id:
            await asyncio.to_thread(store.conversation, settings.owner, body.conversation_id)
            if not await asyncio.to_thread(orc.messages, settings.owner, body.conversation_id):
                raise StoreError('CONVERSATION_EXPIRED', 410)
        row, created = await asyncio.to_thread(store.submit, settings.owner, body.submission_key, payload,
                                               body.after_stop)
        after = (row['input'] or {}).get('after_request_id')
        before = await asyncio.to_thread(store.job, settings.owner, after) if after else None
        if before is not None and created:  # S3: the run this message follows is stopped; this one waits for it
            await stop_job(before)
        return {'request_id': row['request_id'], 'conversation_id': row['conversation_id'],
                'state': row['state'], 'state_version': row['state_version'], 'created': created,
                **({'after_request_id': before['request_id']} if before is not None else {})}

    async def stop_job(row):
        """The stop button (EXEC-X, EXEC-Y Fase 1): a queued run ends here and never reaches Orc; a running one is
        marked (the worker never dispatches a marked run) and flagged at Orc, which stops before its next model call
        while the run's answer still arrives through the worker. NOT_RUNNING when there is nothing to stop."""
        if row['state'] == 'QUEUED' and await asyncio.to_thread(store.stop_queued, settings.owner, row['request_id']):
            return 'STOPPED'
        if row['state'] not in ('QUEUED', 'RUNNING', 'RECOVERING'):
            return 'NOT_RUNNING'
        marked = await asyncio.to_thread(store.request_stop, settings.owner, row['request_id'])
        for attempt in range(STOP_RETRIES):
            status = await asyncio.to_thread(orc.stop, settings.owner, row['request_id'])
            if status != 'NOT_RUNNING':
                return status
            if marked and not marked['attempt_count']:
                return 'STOPPING'  # not dispatched yet: the worker ends it before it reaches Orc
            if attempt + 1 < STOP_RETRIES:
                await asyncio.sleep(settings.poll_seconds)  # dispatched a moment ago: Orc registers it on receipt
        if marked and marked['attempt_count']:
            # V5 (C): dispatched, yet Orc runs nothing (a restart ended it); unless Orc stored its answer, the run ends
            # here and the composer opens again
            try:
                found = await asyncio.to_thread(orc.request, settings.owner, row['request_id'])
            except OrcError:
                return 'NOT_RUNNING'
            if (found or {}).get('turn_status') != 'COMPLETED' and \
                    await asyncio.to_thread(store.interrupt_not_running, settings.owner, row['request_id']):
                return 'STOPPED'
        return 'NOT_RUNNING'

    @app.post('/api/v1/runs/{request_id}/stop')
    async def stop_run(request_id: str, _=Depends(write)):
        row = await asyncio.to_thread(store.job, settings.owner, request_id)
        status = await stop_job(row)
        return JSONResponse({'status': status}, status_code=409 if status == 'NOT_RUNNING' else 202)

    @app.get('/api/v1/runs/{request_id}')
    async def run_status(request_id: str, _=Depends(session)):
        return await snapshot(request_id)

    @app.get('/api/v1/runs/{request_id}/progress')
    async def run_progress(request_id: str, _=Depends(session)):
        """EXEC-IMPL-1016 Fase 4.3 (UI-1015B): what the run is doing now, read from Orc while it runs (labels and
        times only; nothing is stored). NOT_RUNNING before Orc starts it, after it ends, or when Orc cannot answer."""
        await asyncio.to_thread(store.job, settings.owner, request_id)  # the owner's run, or 404
        try:
            found = await asyncio.to_thread(orc.progress, settings.owner, request_id)
        except OrcError:
            found = None
        return found or {'status': 'NOT_RUNNING', 'steps': []}

    @app.get('/api/v1/runs')
    async def active_run(_=Depends(session)):
        row = await asyncio.to_thread(store.active, settings.owner)
        return {'active': await snapshot(row['request_id']) if row else None}

    @app.get('/api/v1/runs/{request_id}/events')
    async def events(request_id: str, request: Request, token=Depends(session)):
        await asyncio.to_thread(store.job, settings.owner, request_id)
        try:
            last = max(0, int(request.headers.get('last-event-id', '0')))
        except ValueError:
            raise HTTPException(400, 'Invalid event cursor')
        async def stream():
            version = last
            started = time.monotonic()
            # Short bounded connections; reconnect to snapshots rather than holding a 60-minute edge request.
            while time.monotonic() - started < 240:
                if await request.is_disconnected() or not await asyncio.to_thread(store.session, token_hash(token)):
                    break
                data = await snapshot(request_id)
                terminal = data['state'] in TERMINAL
                if data['state_version'] > version or terminal or version > data['state_version']:
                    version = data['state_version']
                    yield f'id: {version}\nevent: snapshot\ndata: {json.dumps(data,ensure_ascii=False)}\n\n'
                else:
                    # M153 (EXEC-UI-1013B): a named event, not an SSE comment, so the page sees the stream is alive
                    # (iOS 18 resumes a backgrounded page with a dead EventSource and no error event)
                    yield 'event: ping\ndata: {}\n\n'
                if terminal:
                    break
                await asyncio.sleep(settings.poll_seconds)
        return StreamingResponse(stream(), media_type='text/event-stream', headers={
            'Cache-Control':'no-store, no-transform', 'X-Accel-Buffering':'no', 'Content-Encoding':'identity'})

    # EXEC-MANUAL (user 2026-10-17, troubleshooting only): Claude reads the waiting model calls of a run that chose
    # the manual model and posts its reply; Orc decides (404 while its switch is off)
    @app.get('/api/v1/dev/manual/steps')
    async def manual_steps(_=Depends(session)):
        code, data = await asyncio.to_thread(orc.manual, settings.owner, 'GET', '')
        return JSONResponse(data, status_code=code)

    @app.post('/api/v1/dev/manual/steps/{step_id}')
    async def manual_answer(step_id: str, request: Request, _=Depends(session)):
        try:
            body = await request.json()
        except ValueError:
            raise HTTPException(400, 'Invalid JSON')
        code, data = await asyncio.to_thread(orc.manual, settings.owner, 'POST', '/' + step_id[:64], body)
        return JSONResponse(data, status_code=code)

    models_cache = {'at': None, 'data': None}

    @app.get('/api/v1/models')
    async def models(_=Depends(session)):
        """EXEC-MODELS: the models a message may choose, with their levels and prices, cached for ten minutes; when Orc
        cannot answer, the last list is kept (none yet: the page hides the choice and sends none)."""
        now = time.monotonic()
        if models_cache['data'] is None or now - models_cache['at'] >= MODELS_CACHE_SECONDS:
            try:
                data = await asyncio.to_thread(orc.models, settings.owner)
            except OrcError:
                data = None
            if data:
                models_cache.update(at=now, data=data)
            elif models_cache['data'] is None:
                raise OrcError('MODELS_UNAVAILABLE', 503)
        return jsonable_encoder(models_cache['data'])

    @app.get('/api/v1/conversations')
    async def conversations(q: str = Query(default='', max_length=200), bookmarked: bool = False,
                            offset: int = Query(default=0, ge=0), limit: int = Query(default=30, ge=1, le=100), _=Depends(session)):
        items = await asyncio.to_thread(store.list_conversations, settings.owner, q, bookmarked, offset, limit+1)
        return jsonable_encoder({'items': items[:limit], 'next_offset':offset+limit if len(items)>limit else None})

    @app.get('/api/v1/conversations/{conversation_id}/messages')
    async def messages(conversation_id: str, after: int = Query(default=-1, ge=-1),
                       limit: int = Query(default=20, ge=1, le=50), through: int | None = Query(default=None, ge=0),
                       _=Depends(session)):
        ui = await asyncio.to_thread(store.conversation, settings.owner, conversation_id)
        data = await asyncio.to_thread(orc.messages, settings.owner, conversation_id, after, limit, through)
        if data is None:
            raise StoreError('CONVERSATION_EXPIRED', 410)
        # EXEC-ASK-BRANCH Q2: each answer's side chat (not in the list), for the link under the answer
        sides = await asyncio.to_thread(store.side_chats, settings.owner,
                                        [m.get('request_id') for m in data.get('messages') or [] if m.get('request_id')])
        return jsonable_encoder({'conversation':ui, **data, 'side_chats':sides})

    @app.post('/api/v1/runs/{request_id}/branch')
    async def branch(request_id: str, body: BranchInput, _=Depends(write)):
        """EXEC-ASK-BRANCH (user 2026-10-24): a new conversation continuing this answer (Orc keeps the history it
        continues; nothing is copied). A side chat is made once per answer and then opened again."""
        if body.kind == 'SIDE' and (existing := await asyncio.to_thread(store.side_chat, settings.owner, request_id)):
            return jsonable_encoder(existing)
        found = await asyncio.to_thread(orc.request, settings.owner, request_id)
        if not found or found.get('turn_status') != 'COMPLETED':
            raise StoreError('RESPONSE_NOT_AVAILABLE', 409)
        await asyncio.to_thread(store.conversation, settings.owner, found['conversation_id'])
        made = await asyncio.to_thread(orc.branch, settings.owner, found['conversation_id'], found['turn_index'])
        return jsonable_encoder(await asyncio.to_thread(store.add_branch, settings.owner, made['conversation_id'],
                                                        body.title, body.kind, found['conversation_id'], request_id))

    @app.delete('/api/v1/conversations/{conversation_id}')
    async def hide_conversation(conversation_id: str, _=Depends(write)):
        """EXEC-DELETE: hide a conversation from the list; a running one is refused (its answer is still coming)."""
        if await asyncio.to_thread(store.active_conversation, settings.owner, conversation_id):
            raise StoreError('CONVERSATION_RUNNING', 409)
        return jsonable_encoder(await asyncio.to_thread(store.hide, settings.owner, conversation_id))

    @app.patch('/api/v1/conversations/{conversation_id}/preferences')
    async def preferences(conversation_id: str, body: ConversationPreferences, _=Depends(write)):
        await asyncio.to_thread(store.conversation, settings.owner, conversation_id)
        if await asyncio.to_thread(orc.messages, settings.owner, conversation_id) is None:
            raise StoreError('CONVERSATION_EXPIRED', 410)
        return jsonable_encoder(await asyncio.to_thread(store.preferences, settings.owner, conversation_id,
                                                        **body.model_dump(exclude_none=True)))

    @app.patch('/api/v1/runs/{request_id}/preferences')
    async def pin(request_id: str, body: Pin, _=Depends(write)):
        row = await asyncio.to_thread(store.job, settings.owner, request_id)
        found = await asyncio.to_thread(orc.request, settings.owner, request_id)
        if not found or not found.get('response'):
            raise StoreError('RESPONSE_NOT_AVAILABLE', 409)
        return jsonable_encoder(await asyncio.to_thread(store.preferences, settings.owner, found['conversation_id'],
                                                        request_id=request_id, pinned=body.pinned))

    @app.post('/api/v1/conversations/{conversation_id}/outputs/{output_id}/export')
    async def export_table(conversation_id: str, output_id: str, body: TableExport, _=Depends(write)):
        """The table download (user 2026-10-20): every row of an answer table as Excel; Orc writes the file (no model
        call) and the page then downloads it through the export route below."""
        if not re.fullmatch(r'out_[0-9a-f]{24}', output_id):
            raise StoreError('OUTPUT_NOT_FOUND', 404)
        await asyncio.to_thread(store.conversation, settings.owner, conversation_id)
        data = await asyncio.to_thread(orc.export_table, settings.owner, conversation_id, output_id,
                                       body.columns, body.titles)
        if not re.fullmatch(r'exp_[0-9a-f]{24}', str(data.get('export_id') or '')):
            raise OrcError('EXPORT_FAILED')
        return jsonable_encoder(data)

    @app.get('/api/v1/exports/{export_id}')
    async def download(export_id: str, _=Depends(session)):
        if not re.fullmatch(r'exp_[0-9a-f]{24}', export_id):
            raise StoreError('EXPORT_NOT_FOUND', 404)
        # Orc enforces owner; use streaming transport so file size does not become a BFF response copy.
        client = httpx.AsyncClient(base_url=settings.orc_url, timeout=60, trust_env=False, follow_redirects=False)
        req = client.build_request('GET', f'/v1/exports/{export_id}/download', headers={
            'Authorization': f'Bearer {settings.orc_key}', 'X-Saniti-Owner':settings.owner})
        try:
            response = await client.send(req, stream=True)
        except Exception:
            await client.aclose()
            raise OrcError()
        if response.status_code != 200:
            await response.aclose(); await client.aclose()
            raise StoreError('EXPORT_NOT_FOUND', 404)
        async def chunks():
            try:
                async for chunk in response.aiter_bytes():
                    yield chunk
            finally:
                await response.aclose(); await client.aclose()
        headers = {k:v for k,v in response.headers.items() if k in ('content-disposition','content-length','x-saniti-sha256')}
        return StreamingResponse(chunks(), media_type=response.headers.get('content-type','application/octet-stream'), headers=headers)

    return app
