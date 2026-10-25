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
                cookie_samesite=os.environ.get('TERMINAL_COOKIE_SAMESITE', 'lax').lower())
        s.validate()
        return s

    def validate(self):
        if len(self.admin_key) < 32:
            raise ValueError('TERMINAL_ADMIN_KEY must be at least 32 characters')
        if 'terminal_api_login' not in self.database_url:
            raise ValueError('TERMINAL_DATABASE_URL requires the dedicated terminal_api_login')
        if self.cookie_samesite not in ('lax', 'strict', 'none'):
            raise ValueError('TERMINAL_COOKIE_SAMESITE must be lax, strict or none')
        if not self.allowed_origins:
            raise ValueError('TERMINAL_ALLOWED_ORIGINS or RAILWAY_PUBLIC_DOMAIN is required')
