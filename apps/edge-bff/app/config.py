from dataclasses import dataclass
import os
import re
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Settings:
    database_url: str
    orc_url: str
    orc_key: str
    owner: str
    login: str
    password_verifier: str
    session_secret: str
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
    terminal_proxy_key: str = ''
    # EDGE backtest (CONTRACT.md section 9): the private backtest worker and its shared key; both empty = the feature is
    # off (BACKTEST_DISABLED). The job budget has no default: it is set with the worker (limits measured in the dev E2E,
    # K7b). One running and backtest_queued_per_owner queued jobs per owner.
    backtest_worker_url: str = ''
    backtest_worker_key: str = ''
    backtest_timeout_seconds: float = 0
    backtest_queued_per_owner: int = 3

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
                backtest_queued_per_owner=int(os.environ.get('BACKTEST_QUEUED_PER_OWNER', '3')))
        s.validate()
        return s

    def validate(self):
        if not re.fullmatch(r'scrypt\$[0-9a-f]{32}\$[0-9a-f]{64}', self.password_verifier):
            raise ValueError('Invalid EDGE_PASSWORD_VERIFIER')
        if not re.fullmatch(r'[A-Za-z0-9._:@-]{1,128}', self.owner) or len(self.session_secret) < 32:
            raise ValueError('Invalid EDGE owner/session configuration')
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
        if self.backtest_queued_per_owner < 1:
            raise ValueError('BACKTEST_QUEUED_PER_OWNER must be at least 1')
        if self.orc_timeout_seconds < 3900 or self.session_seconds < 60 or self.heartbeat_seconds <= 0 or self.poll_seconds <= 0 or self.lease_seconds < self.heartbeat_seconds * 2:
            raise ValueError('Invalid EDGE timeout/lease configuration')
