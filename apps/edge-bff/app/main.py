import asyncio
from contextlib import asynccontextmanager
import functools
import hmac
import json
import logging
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
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .backtest import Backtests
from . import catalog, logs, releases, terminal_access
from .client import OrcClient, OrcError, public_data
from .config import LIVE, Settings
from .errors import Refusal, UnexpectedErrors, http_refusal, refusal, set_registration_open, validation_refusal
from .hooks import is_hook_path
from .layouts import Layouts
from .monitor import ModelCatalog, run_refusal, visible as visible_models
from .auth_flows import AuthFlows
from .mailer import EmailSender
from .preferences import Preferences
from .presets import Presets
from .accounts import EMAIL_MAX, PENDING_CHECKED
from .passwords import PasswordWork
from .principal import BETA_ONLY_TABS, Auth, Principal
from .drawings import Drawings
from .overview import Overview
from .watchlist import Watchlist
from .radar import Radar
from .examples import Examples
from . import support as support_module
from .admin import Admin
from .screener import MESSAGES as SCREENER_MESSAGES, Screeners
from .security import SESSION_COOKIE, cookie_name, csrf_token, needs_rehash, password_verifier, token_hash, verify_password
from .store import Store, StoreError, TERMINAL
from .throttle import (DEVICE_SIGNIN, GUEST_TOTAL_KEY, SIGNIN_IP, SIGNIN_LOGIN, Throttle, client_address, guest_total,
                       normal_login)
from .worker import Housekeeping, Worker

COOKIE = SESSION_COOKIE                     # its name on an https origin: cookie_name (__Host-, re-check R2-22)
# the start-up's lines (startup_not_ready, startup_done, email_sender_off): INFO included, written as app/backtest.py's
# are when nothing set up a handler (uvicorn configures only its own loggers; lastResort writes WARNING and above)
startup_log = logging.getLogger('edge_bff.startup')
if not startup_log.hasHandlers():
    _handler = logs.handler()                # Railway's level on each JSON line (app/logs.py, live checker F3)
    startup_log.addHandler(_handler)
    startup_log.setLevel(logging.INFO)
STOP_RETRIES = 3  # EXEC-Y Fase 1 (I1): a run dispatched a moment ago is registered at Orc on receipt
SUPPORT_RETRY_SECONDS = 600  # Phase 4: how often a support ticket's Telegram summary not accepted yet is sent again
WRITE_BYTES = 131072  # the body of a write, but the support upload's (app/support.py REQUEST_BYTES)
STATIC = Path(__file__).resolve().parents[1] / 'static'
SCRIPT_NAME = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*')
# EXEC-MU-ACCOUNTS re-check R2-28 (user 2026-11-19: "5a pakai inter"): EDGE's own copy of the Inter font (static/fonts: the
# woff2 files, the two stylesheets the pages link, OFL.txt), so no page asks Google Fonts and every policy keeps
# font-src 'self' (no visitor's address reaches Google)
FONTS = STATIC / 'fonts'
FONT_NAME = re.compile(r'[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*\.(?:woff2|css|txt)')
FONT_TYPES = {'.woff2': 'font/woff2', '.css': 'text/css; charset=utf-8', '.txt': 'text/plain; charset=utf-8'}
# EXEC-TERMINAL-API T4/T5: the built terminal page (apps/edge-bff/terminal -> static/terminal-app) and the terminal-api
# routes the page may reach through this gateway (sign-in, password and admin routes stay on terminal-api only)
TERMINAL_APP = STATIC / 'terminal-app'
TERMINAL_ASSET = re.compile(r'[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*\.(?:js|css|woff2|svg|png)')
# reference/<name>: the gateway checks only the name's shape (terminal-api's REF_NAME); terminal-api owns the list of
# reference files and answers 404 unknown_reference for any other name, so a new reference file (fixed_income,
# EXEC-FI-TERMINAL, M327) needs no change here
# EXEC-MU-ACCOUNTS Phase 3c (CONTRACT.md 8b "3c in detail"): cut/<TICKER>/<dataset>, the last N days of a dataset that
# terminal-api cuts for a principal with terminal.history_days (decision D2 = A), relayed byte for byte (relay_cut);
# its datasets and /history's come from app/terminal_access.py (terminal-api's own names)
# EXEC-MU-ACCOUNTS re-check R2-32: reference/<name>/cut, the plan's own copy of a reference file (terminal-api refcut.py),
# relayed byte for byte like a cut (TERMINAL_BYTES)
TERMINAL_BYTES = re.compile(rf'cut/[A-Z0-9]{{1,12}}/(?:{"|".join(terminal_access.CUT_DATASETS)})'
                            r'|reference/[a-z0-9][a-z0-9_-]{0,31}/cut')
TERMINAL_ROUTES = {'GET': re.compile(r'manifest/[A-Z0-9]{1,12}|reference/[a-z0-9][a-z0-9_-]{0,31}'
                                      rf'|history/(?:{"|".join(terminal_access.HISTORY_DATASETS)})'
                                      r'|logo/[A-Z0-9]{1,12}'   # logo: EXEC-TERMINAL-LOGO
                                      rf'|{TERMINAL_BYTES.pattern}'),
                   'POST': re.compile(r'files|bundle')}   # bundle: every file of one ticker in one call (EXEC-TERMINAL-UI-1026 U6)
# the cut's answer: its gzip bytes exactly (no JSON parse, no decoding, no Content-Encoding, so the page's sha256 check
# holds), with only these headers of terminal-api's, at most TERMINAL_CUT_BYTES
TERMINAL_CUT_HEADERS = ('content-type', 'etag', 'x-terminal-cut-sha256', 'cache-control')
TERMINAL_CUT_BYTES = 64 * 1024 * 1024
# The terminal page has no inline script; it downloads its files from the private bucket by presigned URL (virtual-host
# addressing, https://<bucket>.t3.storageapi.dev). Inline style attributes are kept: the reference page builds them.
TERMINAL_CSP = ("default-src 'self'; script-src 'self'; worker-src 'self'; "
                "style-src 'self' 'unsafe-inline'; font-src 'self'; "
                "img-src 'self' data: blob:; connect-src 'self' https://*.t3.storageapi.dev; object-src 'none'; "
                "base-uri 'self'; form-action 'self'; frame-ancestors 'self'")
# EDGE backtest (CONTRACT.md section 10): the built backtest page (apps/edge-bff/backtest -> static/backtest-app), shown in
# the Backtest tab's frame. It loads what the terminal page loads (its own script and stylesheet, EDGE's own Inter from
# /fonts/, inline style attributes) and, for the signal preview, the ticker files the /api/terminal/v1/bundle answer
# presigns on the bucket, so it takes the terminal page's policy.
BACKTEST_APP = STATIC / 'backtest-app'
# 3f (EXEC option A item 4; CONTRACT.md 8 "Lab code"): the lab builds of the pages that carry definitions and formulas
# (every item, the lab formulas of terminal/src/lab), served at /<app>/lab/ only to the admin on the beta who holds every
# item (auth.lab_admin and catalog.holds_every_item, page_app below)
TERMINAL_LAB_APP = STATIC / 'terminal-app-lab'
BACKTEST_LAB_APP = STATIC / 'backtest-app-lab'
BACKTEST_CSP = TERMINAL_CSP
# EDGE screener (EXEC-SCREENER; report FRONTEND INTEGRATION 9.1, 9.7): the built screener page (apps/edge-bff/screener ->
# static/screener-app), shown in the Screener tab's frame. It loads what the backtest page loads except the bucket: its
# preview is computed by the screener-worker and every answer comes from /api/v1/screener on this origin, so it reads no
# rack file and connect-src is 'self' only.
SCREENER_APP = STATIC / 'screener-app'
# EXEC-RADAR R6 (user go 2026-11-14): the built Radar page (apps/edge-bff/radar -> static/radar-app), the Radar tab's
# frame. Its data comes from /api/v1/radar on this origin (the bytes are relayed, app/radar.py), so it takes the
# Screener page's policy (connect-src 'self').
RADAR_APP = STATIC / 'radar-app'
# EXEC-OVERVIEW O4 (user go 2026-11-15): the built Market Overview page (apps/edge-bff/overview -> static/overview-app),
# the Overview tab's frame; its data comes from /api/v1/overview on this origin, so the same policy as the Radar's
OVERVIEW_APP = STATIC / 'overview-app'
# EXEC-WATCHLIST L5 (user go 2026-11-16): the built Watchlist page (apps/edge-bff/watchlist -> static/watchlist-app), the
# Watchlist tab's frame; its lists come from /api/v1/watchlist/lists and its figures from /api/v1/watchlist (file)
WATCHLIST_APP = STATIC / 'watchlist-app'
SCREENER_CSP = ("default-src 'self'; script-src 'self'; worker-src 'self'; "
                "style-src 'self' 'unsafe-inline'; font-src 'self'; "
                "img-src 'self' data: blob:; connect-src 'self'; object-src 'none'; "
                "base-uri 'self'; form-action 'self'; frame-ancestors 'self'")
# EXEC-WATCHLIST L5: the Watchlist page shows the Terminal's issuer logos; their list is the Terminal's reference file
# (GET /api/terminal/v1/reference/logos answers a presigned URL on the bucket), so the page takes the Terminal page's
# policy: the Screener's plus connect-src to the bucket (a host EDGE already uses; no new one). The images come from
# /api/terminal/v1/logo/<T> on this origin.
WATCHLIST_CSP = TERMINAL_CSP
CONV = r'^conv_[0-9a-f]{32}$'
CHOICES = r'^(QUICK_SUMMARY|ANALYSIS|RESEARCH|EXPLORE|FACT|CLARIFY|INSIGHT|CONTINUE|APPROVE|NEW_TOPIC)$'
# EXEC-MODELS: the shape of a model id and the reasoning levels; Orc checks the choice against its offered models
MODEL_ID = r'^[a-z0-9][a-z0-9._-]*/[a-z0-9][a-z0-9._:-]*$'
LEVELS = r'^(low|medium|high|max|off|on)$'  # EXEC-LOGOS: max (DeepSeek, GLM); Orc checks each model's own
# EXEC-MODELS: the model list is cached ten minutes (app/monitor.py MODELS_CACHE_SECONDS)
# EXEC-MU-ACCOUNTS Phase 3a (CONTRACT.md 8b, decisions D1 and D5): the Monitor (AI) routes read with monitor.view and
# write with monitor.chat; the Terminal proxy needs terminal.view (tests/test_phase3a_monitor_pages.py ROUTE_CAPS)
MONITOR_VIEW, MONITOR_CHAT, TERMINAL_VIEW = 'monitor.view', 'monitor.chat', 'terminal.view'


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Login(Strict):
    # ERRORS R1-14: as long as the longest email an account may have (the login is a username or an email)
    login: str = Field(min_length=1, max_length=EMAIL_MAX)
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
    # live checker G3: a visitor's refusal offers "create one" only while registration is open (errors.words)
    set_registration_open(not settings.prelaunch)
    store = store or Store(settings.database_url)
    orc = orc or OrcClient(settings)
    # EXEC-MODELS: Orc's model list, shared by the models route, the submit's model rule and the worker's dispatch check
    model_catalog = ModelCatalog(orc)
    worker = Worker(settings, store, orc, model_catalog)
    backtests = Backtests(settings, store)
    screeners = Screeners(settings, store)
    layouts = Layouts(settings, store)
    presets = Presets(settings, store)
    drawings = Drawings(settings, store)
    radar = Radar(settings)
    overview = Overview(settings)                       # EXEC-OVERVIEW O4
    watchlist = Watchlist(settings, store)              # EXEC-WATCHLIST L3
    examples = Examples(store, overview, watchlist.files)   # 3e, the example mode (ERRORS M527)
    support = support_module.Support(settings, store)   # Phase 4, the contact-support panel (the user, 2026-11-22)
    # EXEC-MU-ACCOUNTS beta/live: the AI loop claims only the runs this site queued (config.py EDGE_SITE)
    worker.claim = functools.partial(store.claim, site=settings.site)
    housekeeping = Housekeeping(settings, store)        # ERRORS R2-33: the hourly purges, their own task
    # ERRORS R2-3, R2-36: the start-up steps (readiness, the seeds, the catalog names) and then the loops, retried until
    # they ran; /ready answers 503 until then. lock: one attempt at a time; serving: the app's lifespan has started
    started = {'done': False, 'serving': False, 'failures': 0, 'lock': None, 'stopping': None, 'tasks': []}
    # EXEC-MU-ACCOUNTS Phase 0: the sign-in throttle lives in PostgreSQL (app/throttle.py), shared by every instance
    throttle = Throttle(store, settings.session_secret)
    # EXEC-MU-ACCOUNTS Phase 1: the principal of every request (app/principal.py) and the account preferences
    auth = Auth(settings, store)
    session_cookie = cookie_name(COOKIE, settings.secure_cookie)      # re-check R2-22
    # Phase 3a: the worker re-checks the owner's principal when it dispatches a queued run (monitor.chat, the model)
    worker.access = auth.owner_principal
    preferences = Preferences(store)
    # the email outbox's sender loop and the auth flows (registration, codes, MFA; CONTRACT.md sections 4 and 5)
    sender = EmailSender(settings, store)
    # ERRORS R2-37: every password derivation and Pwned Passwords call runs on this pool, apart from the database's
    password_work = PasswordWork()
    flows = AuthFlows(settings, store, auth, throttle, sender, password_work=password_work)
    # Phase 4, the admin page (CONTRACT 10; the user, 2026-11-22: "1A 2A 3A", "1A, 2B, 3A"): the beta only, the code step
    admin = Admin(settings, store, flows, support, session_cookie)
    # EXEC-TERMINAL-SPEED step 5: one pooled HTTP client to terminal-api, made on first use and closed at shutdown
    # (a client per request opened a new connection every time)
    terminal_http = {'client': None}

    def start_loops():
        """The background loops (EXEC-MU-ACCOUNTS beta/live: each with its own switch, config.py; EDGE_WORKER_ENABLED=false
        starts none): the AI job loop (the beta only, Settings.ai_worker), the backtest loop (each site claims its own
        jobs), the hourly housekeeping and the email sender (its own task, never behind an AI run or a backtest; only
        with the switch on, so only on the live site)."""
        if settings.multiuser and settings.email_mode == 'log' and settings.environment != 'local':
            # EDGE_EMAIL_LOG_ALLOWED: every code stays readable in the outbox; said at every start while it is on
            startup_log.error(json.dumps({'event': 'email_log_mode_allowed', 'site': settings.site}))
        if settings.multiuser and not (settings.worker_enabled and settings.email_enabled):
            # no registration or reset code leaves this instance; visible, as an intended sender-less one must be
            startup_log.error(json.dumps({'event': 'email_sender_off', 'site': settings.site}))
        if not settings.worker_enabled:
            return
        if settings.ai_worker:
            started['tasks'].append(asyncio.create_task(worker.run()))
        if settings.backtest_loop_enabled and backtests.loop:
            started['tasks'].append(asyncio.create_task(backtests.loop.run()))
        if settings.housekeeping_enabled:
            started['tasks'].append(asyncio.create_task(housekeeping.run()))
            # Phase 4: a support ticket's Telegram summary not accepted yet is sent again (app/support.py), by the
            # instance that runs the housekeeping (the live site; one shared table, telegram-monitor drops a repeat)
            started['tasks'].append(asyncio.create_task(support_retry_loop()))
        if settings.multiuser and settings.email_enabled:
            started['tasks'].append(asyncio.create_task(sender.run()))

    async def support_retry_loop():
        while True:
            await asyncio.sleep(SUPPORT_RETRY_SECONDS)
            try:
                await support.retry_telegram()
            except Exception as e:                          # noqa: BLE001 - logged by its class; the loop goes on
                logging.getLogger('edge_bff.support').warning(json.dumps({'event': 'support_retry_failed',
                                                                          'error': type(e).__name__}))

    async def start_up():
        """One attempt at the start-up steps (ERRORS R2-3, R2-36); True once they ran, and then always. Readiness first
        (the tables and columns this build reads; a database being restarted, a migration not applied yet), then user
        #1 and its plan, the catalog's names, then the loops. A seed failure keeps the switch-off sign-in working (the
        loops start); with the switch on nothing can sign in without accounts, so the attempt fails and is made again.
        While no attempt succeeded /ready answers 503 and no loop runs: a build that is not ready never claims a job."""
        async with started['lock']:
            if started['done']:
                return True
            try:
                await asyncio.to_thread(store.ready, settings.multiuser)
                # EXEC-MU-ACCOUNTS Phase 1: user #1 (the configured owner) when the accounts table holds none;
                # idempotent across replicas and attempts
                try:
                    await asyncio.to_thread(auth.seed_user)
                except Exception as e:                 # noqa: BLE001 - logged by its class only (no secret in it)
                    logging.getLogger('edge_bff.accounts').warning(json.dumps({'event': 'account_seed_failed',
                                                                               'error': type(e).__name__}))
                    if settings.multiuser:
                        raise
                # EXEC-MU-ACCOUNTS Phase 2 (CONTRACT.md 8a): user #1's subscription to the plan holding every
                # capability, found by data (account_seed_plan_ambiguous otherwise); idempotent. A failure (the catalog
                # migration not applied yet) changes nothing with the switch off; with it on nothing resolves without
                # the catalog
                try:
                    await asyncio.to_thread(auth.refresh_names)  # Phase 3a (C1 F3): refusals name what the person sees
                except Exception as e:                 # noqa: BLE001 - the plain phrase stays until the next read
                    logging.getLogger('edge_bff.accounts').warning(json.dumps({'event': 'capability_names_failed',
                                                                               'error': type(e).__name__}))
                try:
                    await asyncio.to_thread(auth.seed_plan)
                except Exception as e:                 # noqa: BLE001 - logged by its class only (no secret in it)
                    logging.getLogger('edge_bff.accounts').warning(json.dumps({'event': 'account_seed_plan_failed',
                                                                               'error': type(e).__name__}))
                    if settings.multiuser:
                        raise
            except Exception as e:                     # noqa: BLE001 - its class only (no secret in the log)
                started['failures'] += 1
                if started['failures'] == 1 or started['failures'] % 30 == 0:
                    startup_log.error(json.dumps({'event': 'startup_not_ready', 'error': type(e).__name__,
                                                  'attempts': started['failures']}))
                return False
            start_loops()
            started['done'] = True
            startup_log.info(json.dumps({'event': 'startup_done', 'site': settings.site, 'attempts': started['failures'] + 1,
                                         'loops': len(started['tasks']), 'commit': settings.commit_sha or None,
                                         'shared_keys': settings.shared_key_marks()}))
            return True

    @asynccontextmanager
    async def lifespan(app):
        # made here, in the loop that serves (a lifespan begins with nothing started)
        started.update(done=False, serving=True, failures=0, tasks=[], lock=asyncio.Lock(), stopping=asyncio.Event())
        stopping = started['stopping']

        async def keep_starting():
            while not stopping.is_set() and not await start_up():
                try:
                    await asyncio.wait_for(stopping.wait(), timeout=settings.poll_seconds)
                except asyncio.TimeoutError:
                    pass
        # the first attempt before the first request, as before; while it fails it is made again in the background
        starter = None if await start_up() else asyncio.create_task(keep_starting())
        yield
        stopping.set()
        started['serving'] = False
        worker.stop()
        sender.stop()
        housekeeping.stop()
        if backtests.loop:
            backtests.loop.stop()
        for running in [starter, *started['tasks']]:
            if running:
                running.cancel()
                await asyncio.gather(running, return_exceptions=True)
        orc.close()
        await backtests.aclose()
        await screeners.aclose()
        if hasattr(store, 'close'):                          # EXEC-BACKTEST-LOAD: the connection pool
            await asyncio.to_thread(store.close)
        if terminal_http['client'] is not None and hasattr(terminal_http['client'], 'aclose'):
            await terminal_http['client'].aclose()
        await radar.aclose()                          # EXEC-RADAR R6 (QA 2026-11-14): its client too
        await overview.aclose()
        await watchlist.aclose()
        await support.aclose()
        await sender.aclose()
        password_work.close()

    app = FastAPI(title='EDGE private gateway', docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.worker, app.state.store, app.state.backtests = worker, store, backtests
    app.state.screeners = screeners
    app.state.auth_flows, app.state.email_sender = flows, sender
    app.state.auth = auth                                 # EXEC-MU-ACCOUNTS Phase 1 (tests add routes with need and admin)
    app.state.support = support                           # Phase 4 (tests give its Telegram client a fake transport)

    def error(code, status):
        # EXEC-MU-ACCOUNTS Phase 0 (CONTRACT.md section 3): every refusal in the full shape {code, message, details}
        return refusal(status, code)

    @app.exception_handler(StoreError)
    async def store_error(_, exc):
        return error(exc.code, exc.status)

    @app.exception_handler(OrcError)
    async def orc_error(_, exc):
        return error(exc.code, exc.status)

    # EXEC-MU-ACCOUNTS Phase 0 (CONTRACT.md section 3, M471): FastAPI's own refusals in the one error shape
    @app.exception_handler(RequestValidationError)
    async def validation_error(_, exc):
        return validation_refusal(exc)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_, exc):
        return http_refusal(exc)

    @app.exception_handler(Refusal)
    async def refused(_, exc):
        return refusal(exc.status, exc.code, exc.details, exc.headers)

    @app.exception_handler(Exception)
    async def unexpected(_, exc):
        # Deliberately no exception body/traceback: database/http errors may contain secrets.
        return error('SERVICE_UNAVAILABLE', 503)

    async def support_precheck(request):
        """The support upload's refusal before its body is read (app/support.py), or None: a stated length within
        REQUEST_BYTES, and a session of an account holding support.send that passed its second factor. A request that
        states no length (a proxy may forward a body chunked) is read only up to REQUEST_BYTES, after the same checks."""
        raw = request.headers.get('content-length', '').strip()
        if raw and (not raw.isdigit() or int(raw) > support_module.REQUEST_BYTES):
            return refusal(413, 'REQUEST_TOO_LARGE', {'limit': 'support_request', 'allowed': support_module.REQUEST_BYTES})
        token = request.cookies.get(auth.session_cookie, '')
        if not token and auth.session_cookie != COOKIE and not settings.multiuser:
            token = request.cookies.get(COOKIE, '')
        try:
            p = await auth.resolve(token)
        except Exception:                                   # noqa: BLE001 - fail closed: nothing is read
            return error('SERVICE_UNAVAILABLE', 503)
        if p is None:
            return refusal(401, 'UNAUTHENTICATED')
        if not p.mfa_ok:
            return refusal(403, 'MFA_REQUIRED', {'mfa_enrolled': p.mfa_enrolled})
        if not p.can(support_module.CAPABILITY):
            r = p.refusal(support_module.CAPABILITY)
            return refusal(r.status, r.code, r.details, r.headers)
        return None

    @app.middleware('http')
    async def protections(request, call_next):
        if request.method in ('POST', 'PATCH', 'PUT', 'DELETE'):
            # Same-origin writes, including login, cannot be driven by cross-site forms. EXEC-MU-ACCOUNTS (CONTRACT.md
            # section 6): a hook (/api/v1/hooks/, app/hooks.py) comes from a provider, not a browser, and proves itself
            # by a signature over the body instead; the size cap below and the headers still apply to it.
            if not is_hook_path(request.url.path) and request.headers.get('origin') != settings.origin:
                return error('ORIGIN_REJECTED', 403)
            cap = WRITE_BYTES
            if request.method == 'POST' and request.url.path == support_module.PATH:
                # Phase 4 (app/support.py): the support upload may be large, so its body is read only for a session
                # that may send, and only up to its stated length; a visitor's or a stranger's large body never is
                refused = await support_precheck(request)
                if refused is not None:
                    return refused
                cap = support_module.REQUEST_BYTES
            total, chunks = 0, []
            async for chunk in request.stream():
                total += len(chunk)
                if total > cap:
                    if request.url.path.startswith('/api/v1/screener/'):
                        # report 8.8: the screener's refusals name the fix (AGENTS.md "Gates and evidence" (d))
                        return JSONResponse(status_code=413, content={'error': {
                            'code': 'REQUEST_TOO_LARGE', 'message': SCREENER_MESSAGES['REQUEST_TOO_LARGE'],
                            'details': {'limit': 'request_bytes', 'allowed': 131072}}})
                    return error('REQUEST_TOO_LARGE', 413)
                chunks.append(chunk)
            request._body = b''.join(chunks)
        state = request.state                      # made before the routes run, so the principal they set is seen here
        response = await call_next(request)
        # EXEC-MU-ACCOUNTS Phase 2 (CONTRACT.md 8a): every answer made for a principal (refusals included; /api/v1, the
        # Terminal's /api/terminal/v1 data calls and any later surface: C2 Phase 2 F1) carries the principal's access
        # fingerprint; the shared session module re-reads the session when it changes. Switch off: always 'env'
        principal = getattr(state, 'principal', None)
        if principal is not None:
            response.headers['X-Edge-Entitlements'] = principal.version
            # re-check R2-22: the switch-off owner's session read under the old cookie name moves to the new one
            # (never over a route's own cookie answer: a sign-in or a sign-out sets or deletes it itself)
            if (session_cookie != COOKIE and not settings.multiuser and principal.token
                    and not request.cookies.get(session_cookie) and request.cookies.get(COOKIE) == principal.token
                    and not any(h.startswith(session_cookie + '=') for h in response.headers.getlist('set-cookie'))):
                response.set_cookie(session_cookie, principal.token, max_age=settings.session_seconds, httponly=True,
                                    secure=True, samesite='strict', path='/')
                response.delete_cookie(COOKIE, path='/')
        # re-check R2-21: on an https origin the browser keeps to https for this host (no includeSubDomains: the domain's
        # other hosts are not EDGE's; no preload, which is the user's decision on the domain)
        if settings.origin.startswith('https://'):
            response.headers['Strict-Transport-Security'] = 'max-age=31536000'
        response.headers.setdefault('Cache-Control', 'no-store')
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        # a file answered with its own policy that loads nothing and runs nothing (default-src 'none' and sandbox: a
        # terminal logo, EXEC-TERMINAL-LOGO; a support image of the admin page, Phase 4) keeps it; every other answer
        # gets EDGE's
        own = response.headers.get('Content-Security-Policy', '')
        if own.startswith("default-src 'none'") and re.search(r"(^|;)\s*sandbox\s*(;|$)", own):
            return response
        # EXEC-ASK-BRANCH: the side chat frames EDGE inside EDGE, so only EDGE's own pages may frame it (another site
        # still cannot; frame-ancestors 'self' keeps the clickjacking guard). Re-check R2-19: the shell has no inline
        # script (static/edge-boot.js, static/edge-app.js), so script-src is 'self' alone, and form-action is 'self'
        response.headers['Content-Security-Policy'] = TERMINAL_CSP if request.url.path.startswith('/terminal-app/') else BACKTEST_CSP if request.url.path.startswith('/backtest-app/') else WATCHLIST_CSP if request.url.path.startswith('/watchlist-app/') else SCREENER_CSP if request.url.path.startswith(('/screener-app/', '/radar-app/', '/overview-app/')) else "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self' data: blob:; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'self'"
        return response

    # ERRORS R2-25: added last, so it is the outermost middleware: an exception no handler expected is answered 503
    # here and logged by its class and SQLSTATE only, and never reaches Starlette's ServerErrorMiddleware, which
    # re-raises it to the server, whose log line would carry the exception's text (a failing row's personal data)
    app.add_middleware(UnexpectedErrors)

    # EXEC-MU-ACCOUNTS Phase 1 (CONTRACT.md section 2): the principal of every request (app/principal.py); auth.principal
    # replaces the session dependency and auth.writer the write (CSRF) one. The route-table test
    # (tests/test_route_table.py, CONTRACT.md 13.1) finds these in every /api route's dependencies.
    app.state.session_dependency, app.state.write_dependency = auth.principal, auth.writer
    # track guest: the visitor dependencies (the guest plan's principal without a session; tests/test_route_table.py GUEST_OPEN)
    app.state.visitor_dependency, app.state.visitor_write_dependency = auth.visitor, auth.visitor_writer

    async def still_signed_in(p):
        """The SSE stream re-checks the principal (and, Phase 3a, its monitor.view) on each loop (CONTRACT.md 4, 8b)."""
        found = await auth.resolve(p.token)
        return found is not None and found.owner_key == p.owner_key and found.can(MONITOR_VIEW)  # Phase 3a, D5

    async def snapshot(owner, request_id):
        row = await asyncio.to_thread(store.job, owner, request_id)
        data = {k: row[k] for k in ('request_id','conversation_id','state','state_version','run_status','error_code','created_at','updated_at','completed_at')}
        data['message'] = row['input']['message']
        if row['state'] in TERMINAL and row['conversation_id']:
            found = await asyncio.to_thread(orc.request, owner, request_id)
            data['response'] = found.get('response') if found else None
            data['expired'] = found is None
        return jsonable_encoder(data)

    @app.get('/health')
    async def health():
        return {'status': 'ok'}

    @app.get('/ready')
    async def readiness():
        # ERRORS R2-3, R2-36: ready once the start-up steps ran and the loops started (an attempt is made here while
        # they have not: Railway's healthcheck passes only then), and while the database answers
        if started['serving'] and not await start_up():
            return error('NOT_READY', 503)
        try:
            await asyncio.to_thread(store.ready, settings.multiuser)
        except Exception:
            return error('NOT_READY', 503)
        return {'status': 'ready'}

    @app.get('/version')
    async def version():
        """EXEC-MU-ACCOUNTS beta/live: which website this is and the commit it runs (Railway's RAILWAY_GIT_COMMIT_SHA;
        null when unset, as on a developer machine), read before and after a push to live."""
        return {'site': settings.site, 'commit': settings.commit_sha or None}

    # The page builds its links as <page>#/<route> (index.html staticUrl); opened at "/" that page is index.html, so
    # /index.html is served too (user 2026-10-24: a Branch tab and the side chat showed {"detail":"Not Found"})
    @app.get('/')
    @app.get('/index.html')
    @app.get('/terminal')
    @app.get('/backtest')
    @app.get('/screener')
    @app.get('/radar')
    @app.get('/overview')
    @app.get('/watchlist')
    @app.get('/login')
    @app.get('/register')                   # EXEC-MU-ACCOUNTS Phase 1: the account pages of the shell (contract 12)
    @app.get('/verify')
    @app.get('/forgot')
    @app.get('/reset')
    @app.get('/mfa')
    async def index():
        return FileResponse(STATIC / 'index.html', media_type='text/html')

    def on_this_site(tab):
        """Whether this site serves a tab's pages: the live site has none of the beta-only tabs (principal.py)."""
        return not (settings.site == LIVE and tab in BETA_ONLY_TABS)

    @app.get('/monitor')
    async def monitor_page():
        if not on_this_site('monitor'):
            return error('NOT_FOUND', 404)
        return FileResponse(STATIC / 'index.html', media_type='text/html')

    # EXEC-CHAT-URL (user 2026-10-24: "B saja ya"): every conversation has its own address, /c/<conversation_id>, like
    # ChatGPT and Claude; the page reads the id from it. Any other id is not a page. A conversation is the Monitor's.
    @app.get('/c/{conversation_id}')
    async def conversation_page(conversation_id: str):
        if not re.fullmatch(CONV, conversation_id) or not on_this_site('monitor'):
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

    # EXEC-MU-ACCOUNTS re-check R2-28 (user 2026-11-19: "5a pakai inter"): the Inter font every page uses, served from
    # this origin (FONTS); public like the sign-in page that needs it. The name pattern keeps the request inside fonts/.
    @app.get('/fonts/{name}')
    async def font(name: str):
        target = FONTS / name
        if not FONT_NAME.fullmatch(name) or not target.is_file():
            return error('NOT_FOUND', 404)
        return FileResponse(target, media_type=FONT_TYPES[target.suffix], headers={'Cache-Control': 'public, max-age=86400'})

    # EXEC-UI-1015C (user 2026-10-15, "Please also add Favicon"): the EDGE "E" mark for the browser tab and the phone
    # home screen. Public like the page itself, so the login screen shows it too.
    # EXEC-UI-1019B (user 2026-10-19: "Favicon dan PNG dan PDF. Sudah bagus"): the round "E" mark and the EDGE logo of
    # the shared card
    # User 2026-11-02 ("update favicon dengan logo terlampir"): the three tab and home-screen icons are the square
    # dark-gradient "E" the user sent; edge-logo.svg (the shared card) is unchanged
    @app.get('/favicon.svg')
    @app.get('/favicon-32.png')
    @app.get('/apple-touch-icon.png')
    @app.get('/edge-logo.svg')
    async def favicon(request: Request):
        name = request.url.path.lstrip('/')
        media = 'image/svg+xml' if name.endswith('.svg') else 'image/png'
        return FileResponse(STATIC / name, media_type=media, headers={'Cache-Control': 'public, max-age=86400'})

    # EXEC-TERMINAL-API T5: the terminal page itself carries no data (the page asks /api/terminal for it), so it is
    # served like EDGE's own page; its hashed assets never change and are cached. The same for the backtest page (EDGE
    # backtest, CONTRACT.md section 10: it asks /api/v1/backtests and /api/terminal for its data), the screener page
    # (report FRONTEND INTEGRATION 9.1), and the Radar, Market Overview and Watchlist pages (EXEC-RADAR R6, EXEC-OVERVIEW
    # O4, EXEC-WATCHLIST).
    # 3f (EXEC option A item 4; CONTRACT.md 8 "Lab code"):
    # - a page with a lab build (`lab`) is served from it to the admin on the beta (auth.lab_admin) who holds every item
    #   (catalog.holds_every_item: the build carries them all, so it goes only to a principal every catalog lists each
    #   one to; 3f round 2 CS-1): its index refers to its own assets under /<app>/lab/assets/, which answer 404 to
    #   everyone else and on the live site, and are cached by the admin's browser only (private);
    # - a tab at the lab stage (releases.tab_stage) is served to the admin on the beta who holds the tab's own
    #   <tab>.view: its page and assets answer 404 to everyone else and on the live site, so a lab tab's code is in no
    #   file a visitor downloads.
    # (the folders are this module's names, read when a request comes, so a test can point one elsewhere)
    def page_app(prefix, folder_name, tab, lab_name=None):
        async def shown(request):
            # a lab tab's page carries the tab's code: the admin holding the tab (its own <tab>.view)
            if releases.tab_stage(tab) == releases.LAB:
                p = await auth.lab_admin(request)
                return p is not None and p.can(f'{tab}.view')
            return True

        async def lab_build(request):
            # a lab build carries every item: the admin holding every item (catalog.holds_every_item, the catalogs' rule)
            p = await auth.lab_admin(request)
            return p is not None and catalog.holds_every_item(p)

        async def page(request: Request):
            if not await shown(request):
                return error('NOT_FOUND', 404)
            target = globals()[folder_name] / 'index.html'
            lab = globals()[lab_name] if lab_name else None
            # a lab build that is whole (its index and its assets: 3f checker SERVE-8) is the admin's on the beta
            if (lab is not None and (lab / 'index.html').is_file() and (lab / 'assets').is_dir()
                    and await lab_build(request)):
                target = lab / 'index.html'
            if not target.is_file():
                return error('NOT_FOUND', 404)
            return FileResponse(target, media_type='text/html')

        async def asset(request: Request, name: str):
            target = globals()[folder_name] / 'assets' / name
            if not await shown(request) or not TERMINAL_ASSET.fullmatch(name) or not target.is_file():
                return error('NOT_FOUND', 404)
            # a lab tab's assets are the admin's only, so no shared cache keeps them (3f checker SERVE-1)
            scope = 'private' if releases.tab_stage(tab) == releases.LAB else 'public'
            return FileResponse(target, headers={'Cache-Control': f'{scope}, max-age=31536000, immutable'})

        async def lab_asset(request: Request, name: str):
            target = globals()[lab_name] / 'assets' / name
            if (not TERMINAL_ASSET.fullmatch(name) or not await shown(request) or not await lab_build(request)
                    or not target.is_file()):
                return error('NOT_FOUND', 404)
            return FileResponse(target, headers={'Cache-Control': 'private, max-age=31536000, immutable'})

        app.get(f'/{prefix}/', name=f'{prefix}_page')(page)
        app.get(f'/{prefix}/assets/{{name}}', name=f'{prefix}_asset')(asset)
        if lab_name:
            app.get(f'/{prefix}/lab/assets/{{name}}', name=f'{prefix}_lab_asset')(lab_asset)

    page_app('terminal-app', 'TERMINAL_APP', 'terminal', 'TERMINAL_LAB_APP')
    page_app('backtest-app', 'BACKTEST_APP', 'backtest', 'BACKTEST_LAB_APP')
    page_app('screener-app', 'SCREENER_APP', 'screener')
    page_app('radar-app', 'RADAR_APP', 'radar')
    page_app('overview-app', 'OVERVIEW_APP', 'overview')
    page_app('watchlist-app', 'WATCHLIST_APP', 'watchlist')

    # EXEC-TERMINAL-API T4 (user 2026-10-25: "edge-bff meneruskan /api/terminal/... ke terminal-api --> OK"): the owner's
    # EDGE session reaches terminal-api as its one terminal account (quotas and audit there); writes keep EDGE's
    # same-origin and CSRF checks. Only the data routes are forwarded.
    # EXEC-MU-ACCOUNTS Phase 3c (CONTRACT.md 8b "3c in detail", app/terminal_access.py): every call carries the
    # principal's x-terminal-proxy-owner and x-terminal-capabilities (built from the principal only; a page-sent one is
    # refused by the route's terminal_access.guard), and a ticker or dataset the plan lacks is refused 403
    # CAPABILITY_REQUIRED before terminal-api is asked (terminal_access.check). With the switch off the configured owner
    # holds '*': admin, the body forwarded unchanged.
    # Re-check R1-1, R1-26, R2-4: every answer goes through terminal_access.relayed, the one rule for what reaches the
    # page: an acknowledged 2xx, its JSON through client.public_data (ERRORS M260); a refusal in the contract's shape (a
    # terminal-api 401 or 403 about its own account or key is 503 TERMINAL_UNAVAILABLE, never the EDGE sign-in; a 429
    # LIMIT_REACHED with Retry-After).
    guest_ceiling = guest_total(settings.guest_calls_per_hour) if settings.guest_calls_per_hour else None

    async def forward_terminal(method: str, path: str, request: Request, p: Principal):
        if not settings.terminal_url:
            return error('TERMINAL_UNAVAILABLE', 503)
        if not TERMINAL_ROUTES[method].fullmatch(path):
            return error('NOT_FOUND', 404)
        if p.guest and guest_ceiling is not None:
            # one ceiling for every visitor together (EDGE_GUEST_CALLS_PER_HOUR; the user's "2A ... di set dibackend
            # variable", 2026-11-19), before terminal-api is asked; unset, nothing is counted
            wait = await asyncio.to_thread(throttle.attempt, guest_ceiling, GUEST_TOTAL_KEY)
            if wait:
                await refuse(p, Refusal(429, 'LIMIT_REACHED', {'limit': 'guest_total', 'retry_after_s': wait,
                                                               'visitor': True}, {'Retry-After': str(wait)}))
        body = await request.body() if method == 'POST' else None
        try:
            body = terminal_access.check(p, method, path, request.query_params, body)
        except Refusal as refused:
            await refuse(p, refused)
        headers = terminal_access.headers(settings, p)
        if terminal_http['client'] is None:
            terminal_http['client'] = httpx.AsyncClient(timeout=30)
        url = f'{settings.terminal_url}/api/terminal/v1/{path}'
        if TERMINAL_BYTES.fullmatch(path):
            return await relay_cut(url, request, headers, p, path)
        try:
            answer = await terminal_http['client'].request(method, url, params=request.query_params, content=body,
                                                           headers=headers)
        except httpx.HTTPError:
            return error('TERMINAL_UNAVAILABLE', 503)
        image = 200 <= answer.status_code < 300 and answer.headers.get('content-type', '').startswith('image/')
        try:
            data = None if image else answer.json()
        except ValueError:
            data = None
        refused, data = terminal_access.relayed(p, answer.status_code, data, answer.headers, path)
        if refused is not None:
            await refuse(p, refused)
        if image:
            # a ticker's logo passes through as it is, with terminal-api's caching and its no-script CSP
            return Response(answer.content, media_type=answer.headers['content-type'], headers={
                k: answer.headers[k] for k in ('cache-control', 'etag', 'content-security-policy') if k in answer.headers})
        if data is None:
            return error('TERMINAL_UNAVAILABLE', 503)                 # a 2xx that is not JSON: never relayed on a guess
        return JSONResponse(status_code=answer.status_code, content=data)

    async def refuse(p, refused):
        """Raise a refusal of the Terminal path; a CAPABILITY_REQUIRED with the catalog's name (refuse_capability)."""
        if refused.code == 'CAPABILITY_REQUIRED':
            await refuse_capability(p, refused.details['capability'])
        raise refused

    async def refuse_capability(p, capability):
        try:
            await asyncio.to_thread(auth.refresh_names, False)        # the catalog's name, as auth.need does
        except Exception:                                             # noqa: BLE001 - the plain phrase stays
            pass
        raise p.refusal(capability)

    async def relay_cut(url, request, headers, p, path):
        """Phase 3c (decision D2 = A): terminal-api's cut of the last N days (application/gzip), its bytes exactly as sent
        (read raw, never decoded or parsed, no Content-Encoding added or relayed; the page checks their sha256 against
        /bundle's), with TERMINAL_CUT_HEADERS and always Cache-Control private (the bytes are this principal's). The
        query (the page's ?sha256=) is forwarded. Re-check R2-32: the plan's own copy of a reference file
        (reference/<name>/cut) the same way. Every answer goes through terminal_access.relayed (R1-1, R2-4): a refusal
        in the contract's shape, an unacknowledged answer 503."""
        try:
            async with terminal_http['client'].stream('GET', url, params=request.query_params, headers=headers) as answer:
                if answer.status_code != 200:
                    await answer.aread()
                    try:
                        data = answer.json()
                    except ValueError:
                        data = None
                    refused, _ = terminal_access.relayed(p, answer.status_code, data, answer.headers, path)
                    await refuse(p, refused or Refusal(503, 'TERMINAL_UNAVAILABLE'))
                if (refused := terminal_access.relayed(p, 200, None, answer.headers, path)[0]) is not None:
                    await refuse(p, refused)
                raw = bytearray()
                async for chunk in answer.aiter_raw():
                    raw += chunk
                    if len(raw) > TERMINAL_CUT_BYTES:
                        return error('TERMINAL_UNAVAILABLE', 503)
                sent = {k: answer.headers[k] for k in TERMINAL_CUT_HEADERS if k in answer.headers}
                length = answer.headers.get('content-length')
        except httpx.HTTPError:
            return error('TERMINAL_UNAVAILABLE', 503)
        if length is not None and length != str(len(raw)):
            return error('TERMINAL_UNAVAILABLE', 503)                # cut short on the way: never relayed as whole
        cache = [t.strip() for t in sent.pop('cache-control', '').split(',')
                 if t.strip() and t.strip().lower() not in ('public', 'private')]
        sent['cache-control'] = ', '.join(['private', *(cache or ['no-cache'])])
        media = sent.pop('content-type', 'application/octet-stream')
        return Response(bytes(raw), media_type=media, headers={**sent, 'content-length': str(len(raw))})

    # track guest (decision 1 of 2026-11-19, "1a"; principal.py): the Terminal's data relay is the one route family a
    # visitor without an account reaches (guests=True: the guest plan's principal, 401 where guests are off)
    terminal_read_gate = terminal_access.guard(auth.need(TERMINAL_VIEW, guests=True))
    terminal_write_gate = terminal_access.guard(auth.need(TERMINAL_VIEW, write=True, guests=True))

    @app.get('/api/terminal/v1/{path:path}')
    async def terminal_read(path: str, request: Request, p: Principal = Depends(terminal_read_gate)):
        return await forward_terminal('GET', path, request, p)

    @app.post('/api/terminal/v1/{path:path}')
    async def terminal_write(path: str, request: Request, p: Principal = Depends(terminal_write_gate)):
        return await forward_terminal('POST', path, request, p)

    # EDGE backtest (CONTRACT.md section 9): /api/v1/backtests... with this session (writes with CSRF, as /api/v1/runs)
    # EXEC-MU-ACCOUNTS Phase 1: every router takes routes(app, auth) (auth.principal, auth.writer, auth.need, auth.admin)
    backtests.routes(app, auth)
    # EDGE screener (report API CONTRACT 8.2): /api/v1/screener... with this session (writes with CSRF, as the backtest)
    screeners.routes(app, auth)
    # EXEC-TERMINAL-LAYOUTS (user 2026-11-06: "di akun edge"): the Terminal's saved chart layouts, /api/v1/terminal/layouts
    layouts.routes(app, auth)
    # EXEC-IND-PRESETS (user 2026-11-06: "Q1 A"): the Terminal's indicator presets, /api/v1/terminal/presets
    presets.routes(app, auth)
    # EXEC-DRAW-PANES (user 2026-11-07: "semua gambar harus di simpan di akun EDGE"): the Terminal's drawings, /api/v1/terminal/drawings
    drawings.routes(app, auth)
    # EXEC-RADAR R6, EXEC-OVERVIEW O4: /api/v1/radar and /api/v1/overview (index and files), the owner's only
    radar.routes(app, auth)
    overview.routes(app, auth)
    watchlist.routes(app, auth)              # EXEC-WATCHLIST L3: the lists and the daily file
    # 3e, the example mode (user 2026-11-21; ERRORS M527): /api/v1/examples/<tab>, for <tab>.example, visitors too
    examples.routes(app, auth)
    support.routes(app, auth)                # Phase 4: POST /api/v1/support (support.send)
    admin.routes(app, auth)                  # Phase 4: /api/v1/admin/* (auth.admin_page; 404 on the live site)
    # EXEC-MU-ACCOUNTS Phase 1 (CONTRACT.md section 4b): the account's preferences, /api/v1/preferences
    preferences.routes(app, auth)
    catalog.routes(app, auth)                # EXEC-MU-ACCOUNTS Phase 2 (CONTRACT.md 8a): /api/v1/catalog/{kind}

    @app.post('/api/v1/auth/sign-in')
    async def sign_in(body: Login, request: Request):
        # EXEC-MU-ACCOUNTS Phase 0 (CONTRACT.md section 4 "Throttle"): 10 failures per login and client address in 15
        # minutes, counted in PostgreSQL for every login typed (known or not, so a refusal says nothing about the
        # account; ERRORS R1-9: keyed by the login alone, anyone who typed it could keep its owner out). The try is
        # decided and counted in one locked step before the password check (C1 H1: a concurrent burst cannot pass the
        # limit); a success clears the count. The client address alone is counted on failure but not enforced until
        # Railway's forwarded address is proved.
        address = client_address(request)
        login_key = (normal_login(body.login), address)
        # ERRORS R2-37: the password work of a sign-in runs on its own pool (passwords.PasswordWork), never on the
        # default executor every database call uses; a request over its limit is answered 503 before any try counts
        async with password_work.admitted_request():
            account = restart = rehash = device = None
            if settings.multiuser:
                # EXEC-MU-ACCOUNTS Phase 1 (switch on): the active account named by its username or email
                account = await asyncio.to_thread(auth.accounts.find_login, body.login)
                # the A2 fix (ERRORS M517, NIST SP 800-63B 5.2.2): a browser where this account's password was proved
                # before (its device cookie, security.device_of) tries under its own failure limit (DEVICE_SIGNIN,
                # decided and counted in one step before the check), and neither the per-login limit of its client
                # address nor the account's lock holds it: a stranger who fills either, even from the owner's own
                # network (A2 checker ATK-1), does not lock the owner out of its own browser
                device = await asyncio.to_thread(flows.store.device_try, account['user_id'],
                                                 request.cookies.get(flows.device_cookie)) if account else None
            if not device:
                wait = await asyncio.to_thread(throttle.attempt, SIGNIN_LOGIN, login_key)
                if wait:
                    return refusal(429, 'SIGN_IN_RATE_LIMIT', {'retry_after_s': wait}, {'Retry-After': str(wait)})
            if settings.multiuser:
                # the password identity, and the pending registrations of that address (the newest PENDING_CHECKED).
                # Every sign-in runs exactly 1 + PENDING_CHECKED password derivations, padded with the configured
                # verifier, whatever the address holds (ERRORS M478 re-check: the time tells nothing; OWASP)
                pending = list(await asyncio.to_thread(auth.accounts.pending_logins, body.login))[:PENDING_CHECKED]
                # ERRORS R1-16: the account's consecutive failures, decided and counted before the check (a locked
                # account answers as a wrong password); the same statement runs for a login that names no account
                checked = True if device else await asyncio.to_thread(auth.accounts.sign_in_try,
                                                                      account['user_id'] if account else None)
                known = await password_work.run(verify_password, body.password,
                                                account['verifier'] if account else settings.password_verifier)
                known = known and account is not None and checked
                for row in pending + [None] * (PENDING_CHECKED - len(pending)):
                    matched = await password_work.run(verify_password, body.password,
                                                      row['verifier'] if row else settings.password_verifier)
                    if matched and row is not None and account is None:
                        restart = restart or row
                if known and needs_rehash(account['verifier']):
                    # ERRORS R2-29: a verifier of the cost before R2-29 is replaced by one at the current cost
                    rehash = await password_work.run(password_verifier, body.password)
            else:
                # the password is checked before the login is compared (against the one verifier, so an unknown login
                # runs the same scrypt as a known one): a wrong login costs the same time as a wrong password
                password_ok = await password_work.run(verify_password, body.password, settings.password_verifier)
                known = hmac.compare_digest(body.login.casefold().encode(), settings.login.casefold().encode()) and password_ok
        if not known:
            await asyncio.to_thread(throttle.count, (SIGNIN_IP, address))     # a known browser's try is counted already
            response = error('INVALID_CREDENTIALS', 401)
            # track guest: in the pre-launch mode registration is closed, so no pending registration is restarted (every
            # 401 there answers alike, without a registration cookie)
            if settings.multiuser and not settings.prelaunch:
                # ERRORS M478 (C1 P1-M1): a pending registration with the right password answers the same 401 (no
                # enumeration); within the send limits a fresh code is mailed and this browser gets that registration's
                # cookie, so the person finishes on /verify. Every switch-on 401 sets a registration cookie, so the
                # answers do not differ by a header either
                await flows.restart_registration(response, restart, address, request)
            return response
        # track guest (the pre-launch mode of the live site; the user, 2026-11-19: "Dan hanya admin yang bisa login
        # (saya)", then "A": the admin and the accounts marked as test accounts): only an account whose grants make it
        # the admin ('*' or admin.access, the catalog's, as the second factor is decided) or one marked test_account
        # (migration 20261119_070, set only by an audited step) signs in; every other account is refused with a plain
        # sentence, after its password was checked like any other, and no session is made
        needs_mfa = await asyncio.to_thread(auth.needs_mfa, account['owner_key']) if account is not None else False
        if account is not None and settings.prelaunch and not (needs_mfa or account.get('test_account')):
            logging.getLogger('edge_bff.accounts').info(json.dumps({'event': 'sign_in_closed',
                                                                   'user_id': account['user_id']}))
            # the live checker after the switch-on (ACC-5): the password was right, so the try is not a failure: the
            # account's consecutive failures and this login's tries are cleared as a success clears them (the password
            # work stays bounded by its pool, R2-37)
            if device:                        # a known browser's try left the account's count as it was (A2)
                await asyncio.to_thread(throttle.clear, DEVICE_SIGNIN, (str(account['user_id']), device))
            else:
                await asyncio.to_thread(auth.accounts.sign_in_proved, account['user_id'])
            await asyncio.to_thread(throttle.clear, SIGNIN_LOGIN, login_key)
            return error('SIGN_IN_CLOSED', 403)
        old = request.cookies.get(session_cookie) or (None if settings.multiuser else request.cookies.get(COOKIE))
        if old:
            await asyncio.to_thread(store.revoke, token_hash(old))
        token = secrets.token_hex(32)
        if account is not None:
            # at most MAX_SESSIONS per account (the oldest revoked); the address only as its HMAC. ERRORS R2-9: made
            # only while the verifier this sign-in proved is still the account's (a reset or change landed during the
            # check refuses it, as a wrong password)
            made = await asyncio.to_thread(auth.accounts.create_session, token_hash(token), account,
                                           settings.session_seconds, throttle.key_hash(SIGNIN_IP, address), False,
                                           # Phase 2: MFA by the account's resolved capabilities ('*' or admin.access)
                                           needs_mfa,
                                           account['verifier'], None, rehash, keep_failures=bool(device))
            if made is None:
                return error('INVALID_CREDENTIALS', 401)
            await asyncio.to_thread(auth.accounts.signed_in, account['user_id'])
            if device:
                await asyncio.to_thread(throttle.clear, DEVICE_SIGNIN, (str(account['user_id']), device))
        else:
            await asyncio.to_thread(store.session_create, token_hash(token), auth.configured_owner(), settings.session_seconds)
        await asyncio.to_thread(throttle.clear, SIGNIN_LOGIN, login_key)
        p = await auth.resolve(token)
        if p is None:                              # an account disabled at this very moment
            return error('INVALID_CREDENTIALS', 401)
        request.state.principal = p                # its X-Edge-Entitlements on the sign-in answer too

        # EXEC-RADAR R7: the capabilities come with the sign-in too, so the shell's menu is right before any reload.
        # An admin whose session has not passed MFA (switch on) gets the pending session's cookie and 403 MFA_REQUIRED
        # with its CSRF token, for the MFA page's enrol or verify call
        response = JSONResponse(session_answer(p)) if p.mfa_ok else refusal(
            403, 'MFA_REQUIRED', {'csrf_token': csrf_token(token, settings.session_secret),
                                  'mfa_enrolled': p.mfa_enrolled})
        response.set_cookie(session_cookie, token, max_age=settings.session_seconds, httponly=True,
                            secure=settings.secure_cookie, samesite='strict', path='/')
        if session_cookie != COOKIE:
            response.delete_cookie(COOKIE, path='/')
        if account is not None:
            # the A2 fix: this browser proved the account's password; its device token follows the verifier it now has
            flows.set_device(response, account['user_id'], rehash or account['verifier'])
        return response

    def session_answer(p):
        """GET /api/v1/auth/session (and the sign-in answer): today's keys unchanged, plus username and access
        (CONTRACT.md sections 4 and 15). login: the configured login with the switch off, the username with it on."""
        return {'authenticated': True, 'login': p.username if settings.multiuser else settings.login,
                'owner_key': p.owner_key,
                'csrf_token': csrf_token(p.token, settings.session_secret), 'capabilities': capabilities(),
                'username': p.username, 'access': jsonable_encoder(p.access(ceilings=auth.ceilings))}

    def capabilities():
        return {'deep_research': False, 'model_selection': True, 'cancel': True, 'tool_progress': False,
                'retention_days_default': 30,
                # EXEC-RADAR R6, EXEC-OVERVIEW O4: the Radar and Overview tabs show only when their data can be read
                'radar': bool(settings.terminal_url), 'overview': bool(settings.terminal_url),
                'watchlist': bool(settings.terminal_url)}

    @app.get('/api/v1/auth/session')
    async def get_session(p: Principal = Depends(auth.principal)):
        return session_answer(p)

    # track guest (decision 1 of 2026-11-19, "1a"; principal.py): what the Terminal holds for this request when it has no
    # session: the guest plan's access, in the session answer's shape with `visitor` true (no login, no owner key, no
    # CSRF token: a guest writes without one). A signed-in principal gets its own session answer with `visitor` false.
    # Where guests are off (the beta, EDGE_GUESTS=false) or the client address cannot be read, 401 UNAUTHENTICATED: the
    # page goes to sign-in.
    @app.get('/api/v1/auth/guest')
    async def get_guest(p: Principal = Depends(auth.visitor)):
        if not p.guest:
            return {**session_answer(p), 'visitor': False}
        return {'authenticated': False, 'visitor': True, 'login': '', 'owner_key': None, 'csrf_token': '',
                'capabilities': capabilities(), 'username': None,
                'access': {**jsonable_encoder(p.access(ceilings=auth.ceilings)), 'owner_key': None}}

    # EXEC-MU-ACCOUNTS Phase 1 (CONTRACT.md sections 4-6): registration, codes, reset and change, sign-out everywhere,
    # admin MFA, the Resend webhook (app/auth_flows.py); every one answers 404 with the switch off, except auth/config
    flows.routes(app, session_answer)

    @app.post('/api/v1/auth/sign-out')
    async def sign_out(p: Principal = Depends(auth.writer)):
        await asyncio.to_thread(store.revoke, token_hash(p.token))
        response = JSONResponse({'authenticated': False})
        response.delete_cookie(session_cookie, path='/', secure=settings.secure_cookie)
        if session_cookie != COOKIE:
            response.delete_cookie(COOKIE, path='/')
        return response

    @app.post('/api/v1/runs', status_code=202)
    async def submit(body: RunInput, p: Principal = Depends(auth.need(MONITOR_CHAT, write=True))):
        # Phase 3a: the run's model (the request's, else Orc's server default) must be one the principal holds, and the
        # manual model needs admin.manual (app/monitor.py); refused before anything is stored or sent to Orc
        refused = await run_refusal(p, body.model, model_catalog)
        if refused is not None:
            raise refused
        payload = body.model_dump(exclude_none=True, exclude={'submission_key', 'after_stop'})
        if body.conversation_id:
            await asyncio.to_thread(store.conversation, p.owner_key, body.conversation_id)
            if not await asyncio.to_thread(orc.messages, p.owner_key, body.conversation_id):
                raise StoreError('CONVERSATION_EXPIRED', 410)
        row, created = await asyncio.to_thread(functools.partial(store.submit, site=settings.site), p.owner_key,
                                               body.submission_key, payload, body.after_stop)
        after = (row['input'] or {}).get('after_request_id')
        before = await asyncio.to_thread(store.job, p.owner_key, after) if after else None
        if before is not None and created:  # S3: the run this message follows is stopped; this one waits for it
            await stop_job(p.owner_key, before)
        return {'request_id': row['request_id'], 'conversation_id': row['conversation_id'],
                'state': row['state'], 'state_version': row['state_version'], 'created': created,
                **({'after_request_id': before['request_id']} if before is not None else {})}

    async def stop_job(owner, row):
        """The stop button (EXEC-X, EXEC-Y Fase 1): a queued run ends here and never reaches Orc; a running one is
        marked (the worker never dispatches a marked run) and flagged at Orc, which stops before its next model call
        while the run's answer still arrives through the worker. NOT_RUNNING when there is nothing to stop."""
        if row['state'] == 'QUEUED' and await asyncio.to_thread(store.stop_queued, owner, row['request_id']):
            return 'STOPPED'
        if row['state'] not in ('QUEUED', 'RUNNING', 'RECOVERING'):
            return 'NOT_RUNNING'
        marked = await asyncio.to_thread(store.request_stop, owner, row['request_id'])
        for attempt in range(STOP_RETRIES):
            status = await asyncio.to_thread(orc.stop, owner, row['request_id'])
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
                found = await asyncio.to_thread(orc.request, owner, row['request_id'])
            except OrcError:
                return 'NOT_RUNNING'
            if (found or {}).get('turn_status') != 'COMPLETED' and \
                    await asyncio.to_thread(store.interrupt_not_running, owner, row['request_id']):
                return 'STOPPED'
        return 'NOT_RUNNING'

    @app.post('/api/v1/runs/{request_id}/stop')
    async def stop_run(request_id: str, p: Principal = Depends(auth.need(MONITOR_CHAT, write=True))):
        row = await asyncio.to_thread(store.job, p.owner_key, request_id)
        status = await stop_job(p.owner_key, row)
        return JSONResponse({'status': status}, status_code=409 if status == 'NOT_RUNNING' else 202)

    @app.get('/api/v1/runs/{request_id}')
    async def run_status(request_id: str, p: Principal = Depends(auth.need(MONITOR_VIEW))):
        return await snapshot(p.owner_key, request_id)

    @app.get('/api/v1/runs/{request_id}/progress')
    async def run_progress(request_id: str, p: Principal = Depends(auth.need(MONITOR_VIEW))):
        """EXEC-IMPL-1016 Fase 4.3 (UI-1015B): what the run is doing now, read from Orc while it runs (labels and
        times only; nothing is stored). NOT_RUNNING before Orc starts it, after it ends, or when Orc cannot answer."""
        await asyncio.to_thread(store.job, p.owner_key, request_id)  # the owner's run, or 404
        try:
            found = await asyncio.to_thread(orc.progress, p.owner_key, request_id)
        except OrcError:
            found = None
        return found or {'status': 'NOT_RUNNING', 'steps': []}

    @app.get('/api/v1/runs')
    async def active_run(p: Principal = Depends(auth.need(MONITOR_VIEW))):
        row = await asyncio.to_thread(store.active, p.owner_key)
        return {'active': await snapshot(p.owner_key, row["request_id"]) if row else None}

    @app.get('/api/v1/runs/{request_id}/events')
    async def events(request_id: str, request: Request, p: Principal = Depends(auth.need(MONITOR_VIEW))):
        await asyncio.to_thread(store.job, p.owner_key, request_id)
        try:
            last = max(0, int(request.headers.get('last-event-id', '0')))
        except ValueError:
            raise HTTPException(400, 'INVALID_INPUT')
        async def stream():
            version = last
            started = time.monotonic()
            # Short bounded connections; reconnect to snapshots rather than holding a 60-minute edge request.
            while time.monotonic() - started < 240:
                if await request.is_disconnected() or not await still_signed_in(p):
                    break
                data = await snapshot(p.owner_key, request_id)
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
    # the manual model and posts its reply; Orc decides (404 while its switch is off). EXEC-MU-ACCOUNTS Phase 0 (M259,
    # M474): an admin owner's only (403 CAPABILITY_REQUIRED admin.manual), and the reply is a write (CSRF)
    @app.get('/api/v1/dev/manual/steps')
    async def manual_steps(p: Principal = Depends(auth.admin(capability='admin.manual'))):
        code, data = await asyncio.to_thread(orc.manual, p.owner_key, 'GET', '')
        return JSONResponse(data, status_code=code)

    @app.post('/api/v1/dev/manual/steps/{step_id}')
    async def manual_answer(step_id: str, request: Request, p: Principal = Depends(auth.admin(write=True, capability='admin.manual'))):
        try:
            body = await request.json()
        except ValueError:
            raise HTTPException(400, 'INVALID_INPUT')
        code, data = await asyncio.to_thread(orc.manual, p.owner_key, 'POST', '/' + step_id[:64], body)
        return JSONResponse(data, status_code=code)

    @app.get('/api/v1/models')
    async def models(p: Principal = Depends(auth.need(MONITOR_VIEW))):
        """EXEC-MODELS: the models a message may choose, with their levels and prices, cached for ten minutes; when Orc
        cannot answer, the last list is kept (none yet: the page hides the choice and sends none). Phase 3a: the shared
        list is filtered per principal after the cache (only the models it holds; each default only when held)."""
        return jsonable_encoder(visible_models(p, await model_catalog.read(p.owner_key)))

    @app.get('/api/v1/conversations')
    async def conversations(q: str = Query(default='', max_length=200), bookmarked: bool = False,
                            offset: int = Query(default=0, ge=0), limit: int = Query(default=30, ge=1, le=100), p: Principal = Depends(auth.need(MONITOR_VIEW))):
        items = await asyncio.to_thread(store.list_conversations, p.owner_key, q, bookmarked, offset, limit+1)
        return jsonable_encoder({'items': items[:limit], 'next_offset':offset+limit if len(items)>limit else None})

    @app.get('/api/v1/conversations/{conversation_id}/messages')
    async def messages(conversation_id: str, after: int = Query(default=-1, ge=-1),
                       limit: int = Query(default=20, ge=1, le=50), through: int | None = Query(default=None, ge=0),
                       p: Principal = Depends(auth.need(MONITOR_VIEW))):
        ui = await asyncio.to_thread(store.conversation, p.owner_key, conversation_id)
        data = await asyncio.to_thread(orc.messages, p.owner_key, conversation_id, after, limit, through)
        if data is None:
            raise StoreError('CONVERSATION_EXPIRED', 410)
        # EXEC-ASK-BRANCH Q2: each answer's side chat (not in the list), for the link under the answer
        sides = await asyncio.to_thread(store.side_chats, p.owner_key,
                                        [m.get('request_id') for m in data.get('messages') or [] if m.get('request_id')])
        return jsonable_encoder({'conversation':ui, **data, 'side_chats':sides})

    @app.post('/api/v1/runs/{request_id}/branch')
    async def branch(request_id: str, body: BranchInput, p: Principal = Depends(auth.need(MONITOR_CHAT, write=True))):
        """EXEC-ASK-BRANCH (user 2026-10-24): a new conversation continuing this answer (Orc keeps the history it
        continues; nothing is copied). A side chat is made once per answer and then opened again."""
        if body.kind == 'SIDE' and (existing := await asyncio.to_thread(store.side_chat, p.owner_key, request_id)):
            return jsonable_encoder(existing)
        found = await asyncio.to_thread(orc.request, p.owner_key, request_id)
        if not found or found.get('turn_status') != 'COMPLETED':
            raise StoreError('RESPONSE_NOT_AVAILABLE', 409)
        await asyncio.to_thread(store.conversation, p.owner_key, found['conversation_id'])
        made = await asyncio.to_thread(orc.branch, p.owner_key, found['conversation_id'], found['turn_index'])
        return jsonable_encoder(await asyncio.to_thread(store.add_branch, p.owner_key, made['conversation_id'],
                                                        body.title, body.kind, found['conversation_id'], request_id))

    @app.delete('/api/v1/conversations/{conversation_id}')
    async def hide_conversation(conversation_id: str, p: Principal = Depends(auth.need(MONITOR_CHAT, write=True))):
        """EXEC-DELETE: hide a conversation from the list; a running one is refused (its answer is still coming)."""
        if await asyncio.to_thread(store.active_conversation, p.owner_key, conversation_id):
            raise StoreError('CONVERSATION_RUNNING', 409)
        return jsonable_encoder(await asyncio.to_thread(store.hide, p.owner_key, conversation_id))

    @app.patch('/api/v1/conversations/{conversation_id}/preferences')
    async def preferences(conversation_id: str, body: ConversationPreferences, p: Principal = Depends(auth.need(MONITOR_CHAT, write=True))):
        await asyncio.to_thread(store.conversation, p.owner_key, conversation_id)
        if await asyncio.to_thread(orc.messages, p.owner_key, conversation_id) is None:
            raise StoreError('CONVERSATION_EXPIRED', 410)
        return jsonable_encoder(await asyncio.to_thread(store.preferences, p.owner_key, conversation_id,
                                                        **body.model_dump(exclude_none=True)))

    @app.patch('/api/v1/runs/{request_id}/preferences')
    async def pin(request_id: str, body: Pin, p: Principal = Depends(auth.need(MONITOR_CHAT, write=True))):
        row = await asyncio.to_thread(store.job, p.owner_key, request_id)
        found = await asyncio.to_thread(orc.request, p.owner_key, request_id)
        if not found or not found.get('response'):
            raise StoreError('RESPONSE_NOT_AVAILABLE', 409)
        return jsonable_encoder(await asyncio.to_thread(store.preferences, p.owner_key, found['conversation_id'],
                                                        request_id=request_id, pinned=body.pinned))

    @app.post('/api/v1/conversations/{conversation_id}/outputs/{output_id}/export')
    async def export_table(conversation_id: str, output_id: str, body: TableExport, p: Principal = Depends(auth.need(MONITOR_CHAT, write=True))):
        """The table download (user 2026-10-20): every row of an answer table as Excel; Orc writes the file (no model
        call) and the page then downloads it through the export route below."""
        if not re.fullmatch(r'out_[0-9a-f]{24}', output_id):
            raise StoreError('OUTPUT_NOT_FOUND', 404)
        await asyncio.to_thread(store.conversation, p.owner_key, conversation_id)
        data = await asyncio.to_thread(orc.export_table, p.owner_key, conversation_id, output_id,
                                       body.columns, body.titles)
        if not re.fullmatch(r'exp_[0-9a-f]{24}', str(data.get('export_id') or '')):
            raise OrcError('EXPORT_FAILED')
        return jsonable_encoder(data)

    @app.get('/api/v1/exports/{export_id}')
    async def download(export_id: str, p: Principal = Depends(auth.need(MONITOR_VIEW))):
        if not re.fullmatch(r'exp_[0-9a-f]{24}', export_id):
            raise StoreError('EXPORT_NOT_FOUND', 404)
        # Orc enforces owner; use streaming transport so file size does not become a BFF response copy.
        client = httpx.AsyncClient(base_url=settings.orc_url, timeout=60, trust_env=False, follow_redirects=False)
        req = client.build_request('GET', f'/v1/exports/{export_id}/download', headers={
            'Authorization': f'Bearer {settings.orc_key}', 'X-Saniti-Owner':p.owner_key})
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
