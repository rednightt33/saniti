from dataclasses import dataclass, field
import hashlib
import hmac
import os
import re
from urllib.parse import urlsplit


def admin_owners_of(raw, owner, multiuser=False):
    """EDGE_ADMIN_OWNERS: owners separated by commas, each as EDGE_OWNER is written; unset means the one owner. An empty
    value, a blank entry ("a,,b"), spaces or a repeated owner stop the start (a typo must not turn every right off).
    EXEC-MU-ACCOUNTS Phase 3a (C2/C3 R1): with the switch off an owner the list leaves out holds no capability, so a
    list without EDGE_OWNER would lock the one account out of every tab; that too stops the start and names the fix."""
    if raw is None:
        return (owner,)
    parts = raw.split(',')
    if not raw or any(not p or p != p.strip() or not re.fullmatch(r'[A-Za-z0-9._:@-]{1,128}', p) for p in parts) or len(set(parts)) != len(parts):
        raise ValueError('Invalid EDGE_ADMIN_OWNERS: owners separated by commas, without blanks or spaces')
    if not multiuser and owner not in parts:
        raise ValueError('EDGE_ADMIN_OWNERS must list EDGE_OWNER while EDGE_MULTIUSER is off (unset it to mean '
                         'EDGE_OWNER only): otherwise the configured account loses every tab')
    return tuple(parts)


def switch_of(name, default='false'):
    """A true/false switch, unset = default; any other value stops the start (a typo must not turn accounts on, nor a
    background loop off: ERRORS R2-36)."""
    raw = os.environ.get(name, default).strip().lower()
    if raw not in ('true', 'false'):
        raise ValueError(f'{name} is true or false')
    return raw == 'true'


def optional_switch(name):
    """A true/false switch whose unset value is decided by the site (Settings: None = the site's default)."""
    return switch_of(name) if os.environ.get(name) is not None else None


# EXEC-MU-ACCOUNTS "Production environment" (user decisions 2026-11-19): one Railway environment, two websites on one
# database. EDGE_SITE=beta is the service edge-bff (its Railway address, the admin only, EDGE_MULTIUSER off as today);
# EDGE_SITE=live is the service edge-bff-live (the user's domain, EDGE_MULTIUSER on). Unset = beta, so the running
# service keeps its behaviour.
BETA, LIVE = 'beta', 'live'
SITES = (BETA, LIVE)


@dataclass(frozen=True)
class Settings:
    # secrets never appear in repr(settings) (a traceback, a log line; ERRORS M478 C1 P1-L2)
    database_url: str = field(repr=False)
    orc_url: str
    orc_key: str = field(repr=False)
    owner: str
    login: str
    password_verifier: str = field(repr=False)
    session_secret: str = field(repr=False)
    origin: str
    secure_cookie: bool = True
    session_seconds: int = 86400
    orc_timeout_seconds: int = 3900
    lease_seconds: int = 90
    heartbeat_seconds: float = 20
    poll_seconds: float = 2
    worker_enabled: bool = True
    environment: str = 'dev'
    # EXEC-TERMINAL-API T4 (user 2026-10-25: "edge-bff meneruskan ... --> OK"): the private terminal-api address and the
    # gateway key it accepts for this owner; both empty = the Terminal tab shows its data as unavailable
    terminal_url: str = ''
    terminal_proxy_key: str = field(default='', repr=False)
    # EDGE backtest (CONTRACT.md section 9): the private backtest worker and its shared key; both empty = the feature is
    # off (BACKTEST_DISABLED). The job budget has no default: it is set with the worker (limits measured in the dev E2E,
    # K7b). One running and backtest_queued_per_owner queued jobs per owner. backtest_max_result_bytes: the most JSON a
    # finished job's result may unpack to when edge-bff takes it from the worker (read as it arrives, never past it;
    # over it the job is FAILED LIMIT_EXCEEDED); a limit like the job budget, so no default either (K7b).
    backtest_worker_url: str = ''
    backtest_worker_key: str = field(default='', repr=False)
    backtest_timeout_seconds: float = 0
    backtest_queued_per_owner: int = 3
    backtest_max_result_bytes: int = 0
    # EDGE screener (EXEC-SCREENER, go 2026-10-28; report API CONTRACT 8.1, 8.11): the private screener-worker and its
    # shared key; both empty = the feature is off (SCREENER_DISABLED). screener_timeout_seconds: the worker's deadline
    # (its SCREENER_DEADLINE_MS in seconds), which every relayed call waits for plus one control call; no default, as
    # the worker's limits have none (report 8.9).
    screener_worker_url: str = ''
    screener_worker_key: str = field(default='', repr=False)
    screener_timeout_seconds: float = 0
    # EXEC-BACKTEST-REVAMP P5: the owners with every admin right (app/rights.py), EDGE_ADMIN_OWNERS as a comma list;
    # default the one owner (EDGE_OWNER) until EDGE-MULTIUSER
    admin_owners: tuple = ()
    # EXEC-MU-ACCOUNTS Phase 1 (CONTRACT.md sections 0 and 2): EDGE_MULTIUSER (default false, on only at Phase 6) makes
    # the principal an account of edge_bff.users; off, it is user #1 = EDGE_OWNER and sign-in is as before. The idle
    # timeout of a switch-on session: EDGE_SESSION_IDLE_SECONDS (default 8 h)
    multiuser: bool = False
    session_idle_seconds: int = 28800
    # EXEC-MU-ACCOUNTS Phase 1 auth flows (CONTRACT.md sections 4, 5, 16): needed only with the switch on (a missing value
    # never stops a switch-off start; a value that is set is still checked). code_secret keys the email-code HMAC,
    # mfa_key derives each admin's TOTP secret; email_mode log (the default: the email goes to the outbox row and the
    # log, the code masked outside EDGE_ENVIRONMENT=local) or resend; email_enabled: the sender loop beside the worker
    code_secret: str = field(default='', repr=False)
    mfa_key: str = field(default='', repr=False)
    email_mode: str = 'log'
    # ERRORS R2-26: log mode with the switch on outside EDGE_ENVIRONMENT=local only by this explicit, deliberate switch
    # (EDGE_EMAIL_LOG_ALLOWED, default false): a test of the live site before its Resend key, never with real people
    email_log_allowed: bool = False
    email_enabled: bool = True
    email_from: str = ''
    resend_api_key: str = field(default='', repr=False)
    resend_webhook_secret: str = field(default='', repr=False)
    # EXEC-MU-ACCOUNTS beta/live (ERRORS R2-7, R2-13, R2-23, R2-38): which website this service is (EDGE_SITE, beta or
    # live; see BETA above). Every queued row carries the site that made it, and each site claims only its own.
    site: str = BETA
    # the background loops, each with its own switch (EDGE_WORKER_ENABLED=false still turns every one off: local runs
    # and the tests). None = the site's default (Settings.ai_worker): the AI job loop runs on the beta only (AI is
    # admin-only, decision D1; the live site answers 404 to the Monitor); the backtest loop on both, each claiming its
    # own site's jobs; the hourly housekeeping (sessions, throttle rows, unverified registrations) in its own task; the
    # email sender (email_enabled) only where the switch is on, which is the live site
    ai_worker_enabled: bool | None = None
    backtest_loop_enabled: bool = True
    housekeeping_enabled: bool = True
    # the commit this build runs (Railway's RAILWAY_GIT_COMMIT_SHA), answered by GET /version
    commit_sha: str = ''

    @property
    def ai_worker(self):
        """Whether the AI job loop runs (with the worker): EDGE_AI_WORKER_ENABLED, else the beta only."""
        return self.site == BETA if self.ai_worker_enabled is None else self.ai_worker_enabled

    def shared_key_marks(self):
        """ERRORS R2-8, R2-26: the secrets that key rows of the shared tables (EDGE_SESSION_SECRET: the throttle and CSRF
        HMAC; EDGE_CODE_SECRET: the email codes; EDGE_MFA_KEY: the one TOTP row per user) must be the same on both
        websites, which no process can see of the other. Each start logs, for each, a short HMAC of a fixed label
        under it (never the secret, nothing it can be recovered from), so the two services' start lines (startup_done)
        show at a glance whether they hold the same values; None for an unset one."""
        def mark(value):
            return hmac.new(value.encode(), b'edge_bff.shared_key_check', hashlib.sha256).hexdigest()[:12] if value else None
        return {'EDGE_SESSION_SECRET': mark(self.session_secret), 'EDGE_CODE_SECRET': mark(self.code_secret),
                'EDGE_MFA_KEY': mark(self.mfa_key)}

    @classmethod
    def from_env(cls):
        def required(name):
            value = os.environ.get(name, '').strip()
            if not value:
                raise ValueError(f'{name} is required')
            return value
        s = cls(database_url=required('EDGE_DATABASE_URL'), orc_url=required('EDGE_ORC_URL').rstrip('/'),
                orc_key=required('MARKET_AI_ORC_API_KEY'), owner=required('EDGE_OWNER'),
                login=required('EDGE_LOGIN'), password_verifier=required('EDGE_PASSWORD_VERIFIER'),
                session_secret=required('EDGE_SESSION_SECRET'), origin=required('EDGE_PUBLIC_ORIGIN').rstrip('/'),
                environment=os.environ.get('EDGE_ENVIRONMENT', 'dev'),
                secure_cookie=os.environ.get('EDGE_SECURE_COOKIE', 'true').lower() == 'true',
                orc_timeout_seconds=int(os.environ.get('EDGE_ORC_TIMEOUT_SECONDS', '3900')),
                session_seconds=int(os.environ.get('EDGE_SESSION_SECONDS', '86400')),
                lease_seconds=int(os.environ.get('EDGE_LEASE_SECONDS', '90')),
                heartbeat_seconds=float(os.environ.get('EDGE_HEARTBEAT_SECONDS', '20')),
                poll_seconds=float(os.environ.get('EDGE_POLL_SECONDS', '2')),
                worker_enabled=switch_of('EDGE_WORKER_ENABLED', 'true'),
                terminal_url=os.environ.get('EDGE_TERMINAL_URL', '').strip().rstrip('/'),
                terminal_proxy_key=os.environ.get('TERMINAL_PROXY_KEY', ''),
                backtest_worker_url=os.environ.get('BACKTEST_WORKER_URL', '').strip().rstrip('/'),
                backtest_worker_key=os.environ.get('BACKTEST_WORKER_KEY', ''),
                backtest_timeout_seconds=int(os.environ.get('BACKTEST_TIMEOUT_SECONDS', '0')),
                backtest_queued_per_owner=int(os.environ.get('BACKTEST_QUEUED_PER_OWNER', '3')),
                backtest_max_result_bytes=int(os.environ.get('BACKTEST_MAX_RESULT_BYTES', '0')),
                screener_worker_url=os.environ.get('SCREENER_WORKER_URL', '').strip().rstrip('/'),
                screener_worker_key=os.environ.get('SCREENER_WORKER_KEY', ''),
                screener_timeout_seconds=float(os.environ.get('SCREENER_TIMEOUT_SECONDS', '0')),
                admin_owners=admin_owners_of(os.environ.get('EDGE_ADMIN_OWNERS'), required('EDGE_OWNER'),
                                             switch_of('EDGE_MULTIUSER')),
                multiuser=switch_of('EDGE_MULTIUSER'),
                session_idle_seconds=int(os.environ.get('EDGE_SESSION_IDLE_SECONDS', '28800')),
                code_secret=os.environ.get('EDGE_CODE_SECRET', ''), mfa_key=os.environ.get('EDGE_MFA_KEY', ''),
                email_mode=os.environ.get('EDGE_EMAIL_MODE', 'log').strip().lower(),
                email_enabled=switch_of('EDGE_EMAIL_ENABLED', 'true'),
                email_log_allowed=switch_of('EDGE_EMAIL_LOG_ALLOWED'),
                email_from=os.environ.get('EDGE_EMAIL_FROM', '').strip(),
                resend_api_key=os.environ.get('RESEND_API_KEY', ''),
                resend_webhook_secret=os.environ.get('RESEND_WEBHOOK_SECRET', ''),
                site=os.environ.get('EDGE_SITE', BETA).strip().lower(),
                ai_worker_enabled=optional_switch('EDGE_AI_WORKER_ENABLED'),
                backtest_loop_enabled=switch_of('EDGE_BACKTEST_LOOP_ENABLED', 'true'),
                housekeeping_enabled=switch_of('EDGE_HOUSEKEEPING_ENABLED', 'true'),
                commit_sha=os.environ.get('RAILWAY_GIT_COMMIT_SHA', '').strip())
        s.validate()
        return s

    def validate(self):
        # EXEC-MU-ACCOUNTS Phase 1: log mode keeps each code readable in its outbox row, so it is for a developer
        # machine only; with the switch off nothing is sent, so the default (log) never stops a switch-off start.
        # ERRORS R2-26: no longer by the environment's name (EDGE_ENVIRONMENT=dev is the Railway environment the live
        # site runs in too), but by an explicit switch a copied configuration does not carry by accident
        if self.multiuser and self.email_mode == 'log' and self.environment != 'local' and not self.email_log_allowed:
            raise ValueError('EDGE_EMAIL_MODE=log is for EDGE_ENVIRONMENT=local only (codes stay readable in the '
                             'outbox); set EDGE_EMAIL_MODE=resend with RESEND_API_KEY and EDGE_EMAIL_FROM, or, for a '
                             'test with no real person, EDGE_EMAIL_LOG_ALLOWED=true')
        # the two websites (EXEC-MU-ACCOUNTS "Production environment"): the live site is where accounts sign in, the
        # beta the admin's alone. A beta with the switch on would take registrations, and a live site with it off would
        # be a door to user #1 without the second factor. On a developer machine (local: one process, one database,
        # the tests) the beta may run the switch on.
        if self.site not in SITES:
            raise ValueError('EDGE_SITE is beta (the service edge-bff, the admin only) or live (edge-bff-live, the '
                             'user\'s domain)')
        if self.site == LIVE and not self.multiuser:
            raise ValueError('EDGE_SITE=live needs EDGE_MULTIUSER=true: the live site is where accounts sign in')
        if self.site == BETA and self.multiuser and self.environment != 'local':
            raise ValueError('EDGE_SITE=beta runs with EDGE_MULTIUSER=false (the beta is the admin\'s only); accounts '
                             'sign in on the live site (EDGE_SITE=live)')
        if self.site == LIVE and self.ai_worker_enabled:
            raise ValueError('EDGE_AI_WORKER_ENABLED=true is for the beta only: the live site has no AI (decision D1); '
                             'unset it on the live site')
        if not re.fullmatch(r'scrypt\$[0-9a-f]{32}\$[0-9a-f]{64}', self.password_verifier):
            raise ValueError('Invalid EDGE_PASSWORD_VERIFIER')
        if not re.fullmatch(r'[A-Za-z0-9._:@-]{1,128}', self.owner) or len(self.session_secret) < 32:
            raise ValueError('Invalid EDGE owner/session configuration')
        if not all(isinstance(o, str) and re.fullmatch(r'[A-Za-z0-9._:@-]{1,128}', o) for o in self.admin_owners):
            raise ValueError('Invalid EDGE_ADMIN_OWNERS')
        host = urlsplit(self.orc_url).hostname
        if self.environment != 'local' and (host != 'market-ai-orc.railway.internal' or urlsplit(self.orc_url).scheme != 'http'):
            raise ValueError('EDGE_ORC_URL must use the existing Railway private Orc endpoint')
        if self.environment != 'local' and urlsplit(self.database_url).username != 'edge_bff_login':
            raise ValueError('EDGE_DATABASE_URL requires the dedicated edge_bff_login')
        if urlsplit(self.origin).path not in ('', '/') or not urlsplit(self.origin).hostname:
            raise ValueError('EDGE_PUBLIC_ORIGIN must be an origin')
        if self.environment != 'local' and (not self.secure_cookie or not self.origin.startswith('https://')):
            raise ValueError('Public EDGE requires HTTPS and Secure cookies')
        if bool(self.terminal_url) != bool(self.terminal_proxy_key):
            raise ValueError('EDGE_TERMINAL_URL and TERMINAL_PROXY_KEY are set together or not at all')
        if self.terminal_proxy_key and len(self.terminal_proxy_key) < 32:
            raise ValueError('TERMINAL_PROXY_KEY must be at least 32 characters')
        if self.terminal_url and self.environment != 'local' and (
                urlsplit(self.terminal_url).hostname != 'terminal-api.railway.internal'
                or urlsplit(self.terminal_url).scheme != 'http'):
            raise ValueError('EDGE_TERMINAL_URL must use the Railway private terminal-api endpoint')
        if bool(self.backtest_worker_url) != bool(self.backtest_worker_key):
            raise ValueError('BACKTEST_WORKER_URL and BACKTEST_WORKER_KEY are set together or not at all')
        if self.backtest_worker_key and len(self.backtest_worker_key) < 32:
            raise ValueError('BACKTEST_WORKER_KEY must be at least 32 characters')
        if self.backtest_worker_url and self.environment != 'local' and (
                urlsplit(self.backtest_worker_url).hostname != 'backtest-worker.railway.internal'
                or urlsplit(self.backtest_worker_url).scheme != 'http'):
            raise ValueError('BACKTEST_WORKER_URL must use the Railway private backtest-worker endpoint')
        if self.backtest_worker_url and self.backtest_timeout_seconds <= 0:
            raise ValueError('BACKTEST_TIMEOUT_SECONDS is required with BACKTEST_WORKER_URL')
        if self.backtest_worker_url and self.backtest_max_result_bytes < 1:
            raise ValueError('BACKTEST_MAX_RESULT_BYTES is required with BACKTEST_WORKER_URL')
        if bool(self.screener_worker_url) != bool(self.screener_worker_key):
            raise ValueError('SCREENER_WORKER_URL and SCREENER_WORKER_KEY are set together or not at all')
        if self.screener_worker_key and len(self.screener_worker_key) < 32:
            raise ValueError('SCREENER_WORKER_KEY must be at least 32 characters')
        if self.screener_worker_url and self.environment != 'local' and (
                urlsplit(self.screener_worker_url).hostname != 'screener-worker.railway.internal'
                or urlsplit(self.screener_worker_url).scheme != 'http'):
            raise ValueError('SCREENER_WORKER_URL must use the Railway private screener-worker endpoint')
        if self.screener_worker_url and not 1 <= self.screener_timeout_seconds <= 3600:
            raise ValueError('SCREENER_TIMEOUT_SECONDS is required with SCREENER_WORKER_URL (the worker deadline, 1 s to 3600 s)')
        if self.backtest_queued_per_owner < 1:
            raise ValueError('BACKTEST_QUEUED_PER_OWNER must be at least 1')
        if self.orc_timeout_seconds < 3900 or self.session_seconds < 60 or self.heartbeat_seconds <= 0 or self.poll_seconds <= 0 or self.lease_seconds < self.heartbeat_seconds * 2:
            raise ValueError('Invalid EDGE timeout/lease configuration')
        for name, value in (('EDGE_CODE_SECRET', self.code_secret), ('EDGE_MFA_KEY', self.mfa_key)):
            if (value or self.multiuser) and len(value) < 32:
                raise ValueError(f'{name} must be at least 32 characters (required with EDGE_MULTIUSER=true)')
        if self.email_mode not in ('log', 'resend'):
            raise ValueError('EDGE_EMAIL_MODE is log or resend')
        if self.email_mode == 'resend' and (not self.resend_api_key or '@' not in self.email_from):
            raise ValueError('EDGE_EMAIL_MODE=resend needs RESEND_API_KEY and EDGE_EMAIL_FROM (an address, e.g. '
                             'EDGE <no-reply@mail.example.com>)')
        if self.resend_webhook_secret and not (self.resend_webhook_secret.startswith('whsec_')
                                               and len(self.resend_webhook_secret) >= 30):
            raise ValueError('RESEND_WEBHOOK_SECRET is the whsec_... signing secret of the Resend webhook')
        if self.session_idle_seconds < 60:
            raise ValueError('EDGE_SESSION_IDLE_SECONDS must be at least 60')
