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
    max_inline_rows: int
    max_inline_output_bytes: int
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
            max_inline_rows=_integer(env, "SQL_MAX_INLINE_ROWS", 200, maximum=2000),
            max_inline_output_bytes=_integer(env, "SQL_MAX_INLINE_OUTPUT_BYTES", 24000, minimum=1024, maximum=131072),
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
        )
        if settings.max_unfiltered_date_range_days > settings.max_date_range_days:
            raise ConfigError("SQL_MAX_UNFILTERED_DATE_RANGE_DAYS must not exceed SQL_MAX_DATE_RANGE_DAYS")
        if settings.max_inline_rows > settings.max_dataset_rows:
            raise ConfigError("SQL_MAX_INLINE_ROWS must not exceed SQL_MAX_DATASET_ROWS")
        if settings.statement_timeout_seconds > settings.max_execution_seconds:
            raise ConfigError("SQL_STATEMENT_TIMEOUT_SECONDS must not exceed SQL_MAX_EXECUTION_SECONDS")
        if settings.max_joins >= settings.max_tables:
            raise ConfigError("SQL_MAX_JOINS must be below SQL_MAX_TABLES")
        if settings.bucket_name and not (
            settings.bucket_endpoint and settings.bucket_access_key_id and settings.bucket_secret_access_key
        ):
            raise ConfigError("SQL_DATASET_BUCKET_NAME requires endpoint, access key id, and secret access key")
        if settings.bucket_name and settings.dataset_local_dir:
            raise ConfigError("Configure either a dataset bucket or SQL_DATASET_LOCAL_DIR, not both")
        return settings
