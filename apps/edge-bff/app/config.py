from dataclasses import dataclass, field
import os
import re
from urllib.parse import urlsplit


def admin_owners_of(raw, owner):
    """EDGE_ADMIN_OWNERS: owners separated by commas, each as EDGE_OWNER is written; unset means the one owner. An empty
    value, a blank entry ("a,,b"), spaces or a repeated owner stop the start (a typo must not turn every right off)."""
    if raw is None:
        return (owner,)
    parts = raw.split(',')
    if not raw or any(not p or p != p.strip() or not re.fullmatch(r'[A-Za-z0-9._:@-]{1,128}', p) for p in parts) or len(set(parts)) != len(parts):
        raise ValueError('Invalid EDGE_ADMIN_OWNERS: owners separated by commas, without blanks or spaces')
    return tuple(parts)


def switch_of(name):
    """A true/false switch, unset = false; any other value stops the start (a typo must not turn accounts on)."""
    raw = os.environ.get(name, 'false').strip().lower()
    if raw not in ('true', 'false'):
        raise ValueError(f'{name} is true or false')
    return raw == 'true'


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
    email_enabled: bool = True
    email_from: str = ''
    resend_api_key: str = field(default='', repr=False)
    resend_webhook_secret: str = field(default='', repr=False)

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
                worker_enabled=os.environ.get('EDGE_WORKER_ENABLED', 'true').lower() == 'true',
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
                admin_owners=admin_owners_of(os.environ.get('EDGE_ADMIN_OWNERS'), required('EDGE_OWNER')),
                multiuser=switch_of('EDGE_MULTIUSER'),
                session_idle_seconds=int(os.environ.get('EDGE_SESSION_IDLE_SECONDS', '28800')),
                code_secret=os.environ.get('EDGE_CODE_SECRET', ''), mfa_key=os.environ.get('EDGE_MFA_KEY', ''),
                email_mode=os.environ.get('EDGE_EMAIL_MODE', 'log').strip().lower(),
                email_enabled=os.environ.get('EDGE_EMAIL_ENABLED', 'true').strip().lower() == 'true',
                email_from=os.environ.get('EDGE_EMAIL_FROM', '').strip(),
                resend_api_key=os.environ.get('RESEND_API_KEY', ''),
                resend_webhook_secret=os.environ.get('RESEND_WEBHOOK_SECRET', ''))
        s.validate()
        return s

    def validate(self):
        # EXEC-MU-ACCOUNTS Phase 1: log mode keeps each code readable in its outbox row, so it is for dev only; with the
        # switch off nothing is sent, so the default (log) never stops a switch-off start
        if self.multiuser and self.email_mode == 'log' and self.environment not in ('dev', 'local'):
            raise ValueError('EDGE_EMAIL_MODE=log is for EDGE_ENVIRONMENT dev or local only (codes stay readable in the '
                             'outbox); set EDGE_EMAIL_MODE=resend with RESEND_API_KEY and EDGE_EMAIL_FROM')
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
