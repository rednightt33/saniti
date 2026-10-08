import asyncio
from collections import defaultdict, deque
from contextlib import asynccontextmanager
import hmac
import json
from pathlib import Path
import re
import secrets
import time
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
STATIC = Path(__file__).resolve().parents[1] / 'static'
SCRIPT_NAME = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*')
CONV = r'^conv_[0-9a-f]{32}$'
CHOICES = r'^(QUICK_SUMMARY|ANALYSIS|RESEARCH|EXPLORE|FACT|CLARIFY|INSIGHT|CONTINUE|APPROVE|NEW_TOPIC)$'


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


class RunInput(Strict):
    submission_key: str = Field(min_length=1, max_length=100, pattern=r'^[A-Za-z0-9._:-]+$')
    message: str = Field(min_length=1, max_length=16000)
    conversation_id: str | None = Field(default=None, pattern=CONV)
    chosen_option: str | None = Field(default=None, pattern=CHOICES)
    plan_reply: PlanReply | None = None

    @model_validator(mode='after')
    def check_message(self):
        if not self.message.strip():
            raise ValueError('Blank message')
        return self


class ConversationPreferences(Strict):
    bookmarked: bool | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)


class Pin(Strict):
    pinned: bool


def create_app(settings=None, store=None, orc=None):
    settings = settings or Settings.from_env()
    settings.validate()
    store = store or Store(settings.database_url)
    orc = orc or OrcClient(settings)
    worker = Worker(settings, store, orc)
    ready = {'value': False}
    failures = defaultdict(deque)

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
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data: blob:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
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

    @app.get('/')
    @app.get('/monitor')
    @app.get('/login')
    async def index():
        return FileResponse(STATIC / 'index.html', media_type='text/html')

    # EXEC-X: every page script in static/ (edge-client.js, edge-view.js, edge-labels.js, ...) by its name; a new
    # front-end file needs no route. The name pattern keeps the request inside static/.
    @app.get('/{name}.js')
    async def frontend_script(name: str):
        target = STATIC / f'{name}.js'
        if not SCRIPT_NAME.fullmatch(name) or not target.is_file():
            return error('NOT_FOUND', 404)
        return FileResponse(target, media_type='text/javascript')

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
                'capabilities': {'deep_research': False, 'model_selection': False, 'cancel': False, 'tool_progress': False,
                                 'retention_days_default': 30}}

    @app.post('/api/v1/auth/sign-out')
    async def sign_out(token=Depends(write)):
        await asyncio.to_thread(store.revoke, token_hash(token))
        response = JSONResponse({'authenticated': False})
        response.delete_cookie(COOKIE, path='/')
        return response

    @app.post('/api/v1/runs', status_code=202)
    async def submit(body: RunInput, _=Depends(write)):
        payload = body.model_dump(exclude_none=True, exclude={'submission_key'})
        if body.conversation_id:
            await asyncio.to_thread(store.conversation, settings.owner, body.conversation_id)
            if not await asyncio.to_thread(orc.messages, settings.owner, body.conversation_id):
                raise StoreError('CONVERSATION_EXPIRED', 410)
        row, created = await asyncio.to_thread(store.submit, settings.owner, body.submission_key, payload)
        return {'request_id': row['request_id'], 'conversation_id': row['conversation_id'],
                'state': row['state'], 'state_version': row['state_version'], 'created': created}

    @app.get('/api/v1/runs/{request_id}')
    async def run_status(request_id: str, _=Depends(session)):
        return await snapshot(request_id)

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
                    yield ': heartbeat\n\n'
                if terminal:
                    break
                await asyncio.sleep(settings.poll_seconds)
        return StreamingResponse(stream(), media_type='text/event-stream', headers={
            'Cache-Control':'no-store, no-transform', 'X-Accel-Buffering':'no', 'Content-Encoding':'identity'})

    @app.get('/api/v1/conversations')
    async def conversations(q: str = Query(default='', max_length=200), bookmarked: bool = False,
                            offset: int = Query(default=0, ge=0), limit: int = Query(default=30, ge=1, le=100), _=Depends(session)):
        items = await asyncio.to_thread(store.list_conversations, settings.owner, q, bookmarked, offset, limit+1)
        return jsonable_encoder({'items': items[:limit], 'next_offset':offset+limit if len(items)>limit else None})

    @app.get('/api/v1/conversations/{conversation_id}/messages')
    async def messages(conversation_id: str, after: int = Query(default=-1, ge=-1),
                       limit: int = Query(default=20, ge=1, le=50), _=Depends(session)):
        ui = await asyncio.to_thread(store.conversation, settings.owner, conversation_id)
        data = await asyncio.to_thread(orc.messages, settings.owner, conversation_id, after, limit)
        if data is None:
            raise StoreError('CONVERSATION_EXPIRED', 410)
        return jsonable_encoder({'conversation':ui, **data})

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
