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
                worker_enabled=os.environ.get('EDGE_WORKER_ENABLED', 'true').lower() == 'true')
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
        if self.orc_timeout_seconds < 3900 or self.session_seconds < 60 or self.heartbeat_seconds <= 0 or self.poll_seconds <= 0 or self.lease_seconds < self.heartbeat_seconds * 2:
            raise ValueError('Invalid EDGE timeout/lease configuration')
