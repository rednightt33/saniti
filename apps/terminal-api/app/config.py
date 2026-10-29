import os
import re
from dataclasses import dataclass, field

# EXEC-MU-RUNTIME T1 (user 2026-10-28, option A): one variable per service account, so a worker's own variable can
# reference it (${{terminal-api.TERMINAL_SERVICE_KEY_BACKTEST_WORKER}}); the name after the prefix, lower case with '-'
# for '_', is the service (backtest-worker), and its account is the terminal.subscriber row <service>@terminal.local of
# kind 'service' (migration 20261028_100). Values are Railway secrets; only the names appear in code and documents.
SERVICE_KEY_PREFIX = 'TERMINAL_SERVICE_KEY_'
SERVICE_NAME = re.compile(r'^[a-z0-9][a-z0-9-]{0,30}$')
SERVICE_DOMAIN = 'terminal.local'
# T9: connections per process; 8 is the value before this variable existed (2 uvicorn workers x 8 = 16 of the 20 the
# login terminal_api_login may hold, scripts/provision_terminal_logins.py). The 20 are shared by every process, and a
# replica runs PROCESSES_PER_REPLICA of them (apps/terminal-api/Dockerfile --workers), so one process may hold at most
# POOL_MAX_LIMIT = 20 // 2 = 10. With R replicas keep R x 2 x value <= 20 (4 with two replicas).
POOL_MAX_DEFAULT = 8
ROLE_CONNECTION_LIMIT = 20
PROCESSES_PER_REPLICA = 2
POOL_MAX_LIMIT = ROLE_CONNECTION_LIMIT // PROCESSES_PER_REPLICA


def service_variable(name):
    """backtest-worker -> TERMINAL_SERVICE_KEY_BACKTEST_WORKER"""
    return SERVICE_KEY_PREFIX + name.upper().replace('-', '_')


def service_email(name):
    """backtest-worker -> backtest-worker@terminal.local, the account row of the service"""
    return f'{name}@{SERVICE_DOMAIN}'


def _service_keys(environ):
    """(service, key) for every non-empty TERMINAL_SERVICE_KEY_<NAME>, sorted by service."""
    out = []
    for var, value in environ.items():
        if var.startswith(SERVICE_KEY_PREFIX) and value:
            out.append((var[len(SERVICE_KEY_PREFIX):].lower().replace('_', '-'), value))
    return tuple(sorted(out))


def _pool_max(environ):
    raw = environ.get('TERMINAL_POOL_MAX', '').strip()
    if not raw:
        return POOL_MAX_DEFAULT
    try:
        return int(raw)
    except ValueError:
        raise ValueError(f'TERMINAL_POOL_MAX must be a whole number of connections (1-{POOL_MAX_LIMIT}), '
                         f'for example {POOL_MAX_DEFAULT}') from None


def _required(name):
    value = os.environ.get(name, '')
    if not value:
        raise ValueError(f'{name} is required')
    return value


@dataclass(frozen=True)
class Settings:
    database_url: str
    admin_key: str
    bucket_name: str
    bucket_endpoint: str
    bucket_region: str
    bucket_access_key_id: str
    bucket_secret_access_key: str
    allowed_origins: tuple = field(default_factory=tuple)
    secure_cookie: bool = True
    cookie_samesite: str = 'lax'
    manifest_cache_seconds: int = 60
    # T4 (user 2026-10-25): edge-bff forwards /api/terminal/... for its signed-in owner with this key; the requests
    # count against the one named subscriber account (quotas and audit as for a direct sign-in)
    proxy_key: str = ''
    proxy_subscriber: str = ''
    # T1: ((service, key), ...) from TERMINAL_SERVICE_KEY_<NAME>; each key acts as the service's own account
    service_keys: tuple = ()
    # T9: TERMINAL_POOL_MAX, PostgreSQL connections per process
    pool_max: int = POOL_MAX_DEFAULT

    @classmethod
    def from_env(cls):
        origins = [o.strip().rstrip('/') for o in os.environ.get('TERMINAL_ALLOWED_ORIGINS', '').split(',') if o.strip()]
        domain = os.environ.get('RAILWAY_PUBLIC_DOMAIN', '')
        if domain:
            origins.append(f'https://{domain}')
        s = cls(database_url=_required('TERMINAL_DATABASE_URL'), admin_key=_required('TERMINAL_ADMIN_KEY'),
                bucket_name=_required('TERMINAL_BUCKET_NAME'), bucket_endpoint=_required('TERMINAL_BUCKET_ENDPOINT'),
                bucket_region=_required('TERMINAL_BUCKET_REGION'),
                bucket_access_key_id=_required('TERMINAL_BUCKET_ACCESS_KEY_ID'),
                bucket_secret_access_key=_required('TERMINAL_BUCKET_SECRET_ACCESS_KEY'),
                allowed_origins=tuple(dict.fromkeys(origins)),
                secure_cookie=os.environ.get('TERMINAL_SECURE_COOKIE', 'true').lower() == 'true',
                cookie_samesite=os.environ.get('TERMINAL_COOKIE_SAMESITE', 'lax').lower(),
                proxy_key=os.environ.get('TERMINAL_PROXY_KEY', ''),
                proxy_subscriber=os.environ.get('TERMINAL_PROXY_SUBSCRIBER', '').strip().lower(),
                service_keys=_service_keys(os.environ), pool_max=_pool_max(os.environ))
        s.validate()
        return s

    def validate(self):
        if len(self.admin_key) < 32:
            raise ValueError('TERMINAL_ADMIN_KEY must be at least 32 characters')
        if 'terminal_api_login' not in self.database_url:
            raise ValueError('TERMINAL_DATABASE_URL requires the dedicated terminal_api_login')
        if self.cookie_samesite not in ('lax', 'strict', 'none'):
            raise ValueError('TERMINAL_COOKIE_SAMESITE must be lax, strict or none')
        if bool(self.proxy_key) != bool(self.proxy_subscriber):
            raise ValueError('TERMINAL_PROXY_KEY and TERMINAL_PROXY_SUBSCRIBER are set together or not at all')
        if self.proxy_key and len(self.proxy_key) < 32:
            raise ValueError('TERMINAL_PROXY_KEY must be at least 32 characters')
        if not self.allowed_origins:
            raise ValueError('TERMINAL_ALLOWED_ORIGINS or RAILWAY_PUBLIC_DOMAIN is required')
        if not 1 <= self.pool_max <= POOL_MAX_LIMIT:
            raise ValueError(f'TERMINAL_POOL_MAX must be 1-{POOL_MAX_LIMIT} connections per process: '
                             f'terminal_api_login holds at most {ROLE_CONNECTION_LIMIT} for all processes together and '
                             f'each replica runs {PROCESSES_PER_REPLICA} (Dockerfile --workers); {self.pool_max} was '
                             f'given. Fix: unset it (default {POOL_MAX_DEFAULT}) or lower it; with two replicas use at '
                             f'most {POOL_MAX_LIMIT // 2}, for example TERMINAL_POOL_MAX=4')
        seen = {self.admin_key, self.proxy_key} - {''}
        names = [name for name, _ in self.service_keys]
        for name, key in self.service_keys:
            var = service_variable(name)
            if not SERVICE_NAME.fullmatch(name):
                raise ValueError(f'{var}: a service name is lower-case letters, digits and "_" in the variable name, '
                                 'for example TERMINAL_SERVICE_KEY_BACKTEST_WORKER')
            if names.count(name) > 1:
                raise ValueError(f'{names.count(name)} variables name the service {name} (they differ only in case '
                                 f'or in "-" and "_"): one service account, one key. Fix: keep only {var}')
            if len(key) < 32:
                raise ValueError(f'{var} must be at least 32 characters')
            if key in seen:
                raise ValueError(f'{var} must differ from TERMINAL_ADMIN_KEY, TERMINAL_PROXY_KEY and every other '
                                 'service key: one key, one account')
            seen.add(key)
