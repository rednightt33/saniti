from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field


class ConfigError(RuntimeError):
    pass


def _integer(env: Mapping[str, str], name: str, default: int, minimum: int = 1, maximum: int | None = None) -> int:
    raw = env.get(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc
    if value < minimum or (maximum is not None and value > maximum):
        bound = f"between {minimum} and {maximum}" if maximum is not None else f"at least {minimum}"
        raise ConfigError(f"{name} must be {bound}")
    return value


def _optional(env: Mapping[str, str], name: str) -> str | None:
    value = env.get(name, "").strip()
    return value or None


def _flag(env: Mapping[str, str], name: str, default: bool) -> bool:
    raw = env.get(name, "").strip().lower()
    if not raw:
        return default
    if raw not in {"true", "false"}:
        raise ConfigError(f"{name} must be true or false")
    return raw == "true"


@dataclass(frozen=True)
class Settings:
    """market-audit-store configuration. Keys and URLs are never logged (repr=False).

    Three bearer keys with disjoint purposes; each identifies its caller:
    - AUDIT_STORE_GOVERNOR_KEY (market-sql-governor) and AUDIT_STORE_SANDBOX_KEY (market-python-sandbox): the
      internal producer endpoints only, recorded as that producer;
    - AUDIT_STORE_READER_KEY (an operator): the query, access, hold and retention-report endpoints only.
    market-ai-orc has no key: it writes to ai_audit.ingest_outbox, which this service consumes."""

    database_url: str = field(repr=False)
    governor_key: str | None = field(repr=False)
    sandbox_key: str | None = field(repr=False)
    reader_key: str | None = field(repr=False)
    bucket_name: str | None
    bucket_endpoint: str | None
    bucket_region: str | None
    bucket_access_key_id: str | None = field(repr=False)
    bucket_secret_access_key: str | None = field(repr=False)
    local_object_dir: str | None
    local_signing_key: str | None = field(repr=False)
    public_base_url: str | None
    connect_timeout_seconds: int
    statement_timeout_seconds: int
    upload_url_ttl_seconds: int
    access_url_ttl_seconds: int
    max_artifact_bytes: int
    max_events_per_call: int
    retention_standard_days: int
    retention_pinned_days: int
    outbox_enabled: bool
    outbox_poll_seconds: int
    outbox_batch: int
    outbox_max_attempts: int
    reevaluate_hours: int

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if env is None else env
        database_url = env.get("AUDIT_DATABASE_URL", "").strip()
        if not database_url.startswith(("postgresql://", "postgres://")):
            raise ConfigError("AUDIT_DATABASE_URL must be a postgresql:// connection URL")
        settings = cls(
            database_url=database_url,
            governor_key=_optional(env, "AUDIT_STORE_GOVERNOR_KEY"),
            sandbox_key=_optional(env, "AUDIT_STORE_SANDBOX_KEY"),
            reader_key=_optional(env, "AUDIT_STORE_READER_KEY"),
            bucket_name=_optional(env, "AUDIT_BUCKET_NAME"),
            bucket_endpoint=_optional(env, "AUDIT_BUCKET_ENDPOINT"),
            bucket_region=_optional(env, "AUDIT_BUCKET_REGION"),
            bucket_access_key_id=_optional(env, "AUDIT_BUCKET_ACCESS_KEY_ID"),
            bucket_secret_access_key=_optional(env, "AUDIT_BUCKET_SECRET_ACCESS_KEY"),
            local_object_dir=_optional(env, "AUDIT_LOCAL_OBJECT_DIR"),
            local_signing_key=_optional(env, "AUDIT_LOCAL_SIGNING_KEY"),
            public_base_url=_optional(env, "AUDIT_PUBLIC_BASE_URL"),
            connect_timeout_seconds=_integer(env, "AUDIT_CONNECT_TIMEOUT_SECONDS", 5, maximum=30),
            statement_timeout_seconds=_integer(env, "AUDIT_STATEMENT_TIMEOUT_SECONDS", 15, maximum=120),
            upload_url_ttl_seconds=_integer(env, "AUDIT_UPLOAD_URL_TTL_SECONDS", 300, minimum=30, maximum=900),
            access_url_ttl_seconds=_integer(env, "AUDIT_ACCESS_URL_TTL_SECONDS", 120, minimum=30, maximum=900),
            max_artifact_bytes=_integer(env, "AUDIT_MAX_ARTIFACT_BYTES", 268_435_456, minimum=1,
                                        maximum=2_147_483_648),
            max_events_per_call=_integer(env, "AUDIT_MAX_EVENTS_PER_CALL", 200, maximum=1000),
            retention_standard_days=_integer(env, "AUDIT_RETENTION_STANDARD_DAYS", 90, maximum=3650),
            retention_pinned_days=_integer(env, "AUDIT_RETENTION_PINNED_DAYS", 365, maximum=3650),
            outbox_enabled=_flag(env, "AUDIT_OUTBOX_ENABLED", True),
            outbox_poll_seconds=_integer(env, "AUDIT_OUTBOX_POLL_SECONDS", 10, maximum=3600),
            outbox_batch=_integer(env, "AUDIT_OUTBOX_BATCH", 20, maximum=200),
            outbox_max_attempts=_integer(env, "AUDIT_OUTBOX_MAX_ATTEMPTS", 12, maximum=100),
            reevaluate_hours=_integer(env, "AUDIT_REEVALUATE_HOURS", 48, maximum=720),
        )
        keys = [k for k in (settings.governor_key, settings.sandbox_key, settings.reader_key) if k is not None]
        if not keys:
            raise ConfigError("Configure at least one of AUDIT_STORE_GOVERNOR_KEY, AUDIT_STORE_SANDBOX_KEY, "
                              "AUDIT_STORE_READER_KEY")
        if any(len(k) < 32 for k in keys):
            raise ConfigError("Every AUDIT_STORE_*_KEY must be at least 32 characters")
        if len(set(keys)) != len(keys):
            raise ConfigError("AUDIT_STORE_GOVERNOR_KEY, AUDIT_STORE_SANDBOX_KEY and AUDIT_STORE_READER_KEY must "
                              "differ")
        if settings.bucket_name and settings.local_object_dir:
            raise ConfigError("Configure either AUDIT_BUCKET_NAME or AUDIT_LOCAL_OBJECT_DIR, not both")
        if not (settings.bucket_name or settings.local_object_dir):
            raise ConfigError("AUDIT_BUCKET_NAME (or AUDIT_LOCAL_OBJECT_DIR for development) is required")
        if settings.bucket_name and not (settings.bucket_endpoint and settings.bucket_access_key_id
                                         and settings.bucket_secret_access_key):
            raise ConfigError("AUDIT_BUCKET_NAME requires endpoint, access key id and secret access key")
        if settings.local_object_dir and not (settings.local_signing_key and len(settings.local_signing_key) >= 32
                                              and settings.public_base_url):
            raise ConfigError("AUDIT_LOCAL_OBJECT_DIR requires AUDIT_LOCAL_SIGNING_KEY (32+ characters) and "
                              "AUDIT_PUBLIC_BASE_URL")
        if settings.retention_pinned_days < settings.retention_standard_days:
            raise ConfigError("AUDIT_RETENTION_PINNED_DAYS must not be below AUDIT_RETENTION_STANDARD_DAYS")
        return settings
