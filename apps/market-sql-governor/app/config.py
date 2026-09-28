from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field, replace


class ConfigError(RuntimeError):
    pass


def _flag(env: Mapping[str, str], name: str) -> bool:
    raw = env.get(name, "").strip().lower()
    if raw not in {"", "true", "false"}:
        raise ConfigError(f"{name} must be true or false")
    return raw == "true"


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


@dataclass(frozen=True)
class Settings:
    """Hard limits are backend configuration only; no request field can raise them."""

    api_key: str = field(repr=False)
    database_url: str = field(repr=False)
    connect_timeout_seconds: int
    statement_timeout_seconds: int
    lock_timeout_seconds: int
    max_tables: int
    max_joins: int
    max_columns: int
    max_filters: int
    max_in_values: int
    max_estimated_scan_rows: int
    max_plan_cost: int
    max_execution_seconds: int
    max_date_range_days: int
    max_unfiltered_date_range_days: int
    max_dataset_rows: int
    max_dataset_bytes: int
    dataset_retention_hours: int
    dataset_cleanup_interval_seconds: int
    bucket_name: str | None
    bucket_endpoint: str | None
    bucket_region: str | None
    bucket_access_key_id: str | None = field(repr=False)
    bucket_secret_access_key: str | None = field(repr=False)
    dataset_local_dir: str | None
    # market-python-sandbox only: reads manifests and obtains a short-lived read URL for one
    # dataset. It can never call /v1/query.
    dataset_access_key: str | None = field(default=None, repr=False)
    dataset_access_url_ttl_seconds: int = 120
    dataset_tombstone_retention_hours: int = 720
    # POST /v1/extract (DataNeed extractions planned by market-ai-orc's backend)
    extract_max_parts: int = 64
    extract_max_in_values: int = 500
    extract_max_columns: int = 60
    extract_max_window_days: int = 3660
    # IP2 solution 2 (SQL_GOVERNOR_AUDIT_STORE_ENABLED, off by default): archive each dataset's raw Parquet and
    # extraction manifest to market-audit-store through an outbox in the dataset bucket (app/audit_archive.py)
    audit_store_enabled: bool = False
    audit_store_url: str | None = None
    audit_store_key: str | None = field(default=None, repr=False)
    audit_poll_seconds: int = 30
    audit_max_attempts: int = 12
    audit_timeout_seconds: int = 60

    @property
    def dataset_storage_configured(self) -> bool:
        return bool(self.bucket_name or self.dataset_local_dir)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if env is None else env
        secrets = {
            "SQL_GOVERNOR_API_KEY": env.get("SQL_GOVERNOR_API_KEY", "").strip(),
            "GOVERNOR_DATABASE_URL": env.get("GOVERNOR_DATABASE_URL", "").strip(),
        }
        missing = [name for name, value in secrets.items() if not value]
        if missing:
            raise ConfigError(f"Missing required variables: {', '.join(missing)}")
        if not secrets["GOVERNOR_DATABASE_URL"].startswith(("postgresql://", "postgres://")):
            raise ConfigError("GOVERNOR_DATABASE_URL must be a postgresql:// connection URL")
        if len(secrets["SQL_GOVERNOR_API_KEY"]) < 32:
            raise ConfigError("SQL_GOVERNOR_API_KEY must be at least 32 characters")

        settings = cls(
            api_key=secrets["SQL_GOVERNOR_API_KEY"],
            database_url=secrets["GOVERNOR_DATABASE_URL"],
            connect_timeout_seconds=_integer(env, "SQL_CONNECT_TIMEOUT_SECONDS", 5, maximum=30),
            statement_timeout_seconds=_integer(env, "SQL_STATEMENT_TIMEOUT_SECONDS", 20, maximum=120),
            lock_timeout_seconds=_integer(env, "SQL_LOCK_TIMEOUT_SECONDS", 2, maximum=30),
            max_tables=_integer(env, "SQL_MAX_TABLES", 3, maximum=5),
            max_joins=_integer(env, "SQL_MAX_JOINS", 2, minimum=0, maximum=4),
            max_columns=_integer(env, "SQL_MAX_COLUMNS", 20, maximum=50),
            max_filters=_integer(env, "SQL_MAX_FILTERS", 10, maximum=30),
            max_in_values=_integer(env, "SQL_MAX_IN_VALUES", 100, maximum=500),
            max_estimated_scan_rows=_integer(env, "SQL_MAX_ESTIMATED_SCAN_ROWS", 2_000_000),
            max_plan_cost=_integer(env, "SQL_MAX_PLAN_COST", 600_000),
            max_execution_seconds=_integer(env, "SQL_MAX_EXECUTION_SECONDS", 60, maximum=300),
            max_date_range_days=_integer(env, "SQL_MAX_DATE_RANGE_DAYS", 3660),
            max_unfiltered_date_range_days=_integer(env, "SQL_MAX_UNFILTERED_DATE_RANGE_DAYS", 400),
            max_dataset_rows=_integer(env, "SQL_MAX_DATASET_ROWS", 500_000, maximum=5_000_000),
            max_dataset_bytes=_integer(env, "SQL_MAX_DATASET_BYTES", 134_217_728, minimum=65536, maximum=1_073_741_824),
            dataset_retention_hours=_integer(env, "SQL_DATASET_RETENTION_HOURS", 168, maximum=720),
            dataset_cleanup_interval_seconds=_integer(env, "SQL_DATASET_CLEANUP_INTERVAL_SECONDS", 3600,
                                                      minimum=0, maximum=86400),
            bucket_name=_optional(env, "SQL_DATASET_BUCKET_NAME"),
            bucket_endpoint=_optional(env, "SQL_DATASET_BUCKET_ENDPOINT"),
            bucket_region=_optional(env, "SQL_DATASET_BUCKET_REGION"),
            bucket_access_key_id=_optional(env, "SQL_DATASET_BUCKET_ACCESS_KEY_ID"),
            bucket_secret_access_key=_optional(env, "SQL_DATASET_BUCKET_SECRET_ACCESS_KEY"),
            dataset_local_dir=_optional(env, "SQL_DATASET_LOCAL_DIR"),
            dataset_access_key=_optional(env, "SQL_GOVERNOR_DATASET_ACCESS_KEY"),
            dataset_access_url_ttl_seconds=_integer(env, "SQL_DATASET_ACCESS_URL_TTL_SECONDS", 120,
                                                    minimum=30, maximum=900),
            dataset_tombstone_retention_hours=_integer(env, "SQL_DATASET_TOMBSTONE_RETENTION_HOURS", 720,
                                                       minimum=0, maximum=8760),
            extract_max_parts=_integer(env, "SQL_EXTRACT_MAX_PARTS", 64, maximum=256),
            extract_max_in_values=_integer(env, "SQL_EXTRACT_MAX_IN_VALUES", 500, maximum=1000),
            extract_max_columns=_integer(env, "SQL_EXTRACT_MAX_COLUMNS", 60, maximum=60),
            extract_max_window_days=_integer(env, "SQL_EXTRACT_MAX_WINDOW_DAYS", 3660, maximum=7400),
        )
        if settings.max_unfiltered_date_range_days > settings.max_date_range_days:
            raise ConfigError("SQL_MAX_UNFILTERED_DATE_RANGE_DAYS must not exceed SQL_MAX_DATE_RANGE_DAYS")
        if settings.statement_timeout_seconds > settings.max_execution_seconds:
            raise ConfigError("SQL_STATEMENT_TIMEOUT_SECONDS must not exceed SQL_MAX_EXECUTION_SECONDS")
        if settings.max_joins >= settings.max_tables:
            raise ConfigError("SQL_MAX_JOINS must be below SQL_MAX_TABLES")
        if settings.bucket_name and not (
            settings.bucket_endpoint and settings.bucket_access_key_id and settings.bucket_secret_access_key
        ):
            raise ConfigError("SQL_DATASET_BUCKET_NAME requires endpoint, access key id, and secret access key")
        if settings.dataset_access_key is not None:
            if len(settings.dataset_access_key) < 32:
                raise ConfigError("SQL_GOVERNOR_DATASET_ACCESS_KEY must be at least 32 characters")
            if settings.dataset_access_key == settings.api_key:
                raise ConfigError("SQL_GOVERNOR_DATASET_ACCESS_KEY must differ from SQL_GOVERNOR_API_KEY")
        if settings.bucket_name and settings.dataset_local_dir:
            raise ConfigError("Configure either a dataset bucket or SQL_DATASET_LOCAL_DIR, not both")
        audit = {
            "audit_store_enabled": _flag(env, "SQL_GOVERNOR_AUDIT_STORE_ENABLED"),
            "audit_store_url": (_optional(env, "AUDIT_STORE_URL") or "").rstrip("/") or None,
            "audit_store_key": _optional(env, "AUDIT_STORE_GOVERNOR_KEY"),
            "audit_poll_seconds": _integer(env, "SQL_GOVERNOR_AUDIT_POLL_SECONDS", 30, maximum=3600),
            "audit_max_attempts": _integer(env, "SQL_GOVERNOR_AUDIT_MAX_ATTEMPTS", 12, maximum=100),
            "audit_timeout_seconds": _integer(env, "SQL_GOVERNOR_AUDIT_TIMEOUT_SECONDS", 60, maximum=600),
        }
        if audit["audit_store_enabled"]:
            # the Audit Store variables are required only while the feature is on
            if not (audit["audit_store_url"] or "").startswith(("https://", "http://")):
                raise ConfigError("SQL_GOVERNOR_AUDIT_STORE_ENABLED needs AUDIT_STORE_URL (http:// or https://)")
            if len(audit["audit_store_key"] or "") < 32:
                raise ConfigError("SQL_GOVERNOR_AUDIT_STORE_ENABLED needs AUDIT_STORE_GOVERNOR_KEY (32+ characters)")
            if not (settings.bucket_name or settings.dataset_local_dir):
                raise ConfigError("SQL_GOVERNOR_AUDIT_STORE_ENABLED needs dataset storage (its audit outbox)")
        return replace(settings, **audit)
