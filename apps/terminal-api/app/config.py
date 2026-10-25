import os
from dataclasses import dataclass, field


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
                proxy_subscriber=os.environ.get('TERMINAL_PROXY_SUBSCRIBER', '').strip().lower())
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
