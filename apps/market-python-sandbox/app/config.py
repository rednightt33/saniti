from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path


class ConfigError(RuntimeError):
    pass


def _integer(env: Mapping[str, str], name: str, default: int, minimum: int = 1, maximum: int | None = None) -> int:
    raw = env.get(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc
    if value < minimum or (maximum is not None and value > maximum):
        bound = f"between {minimum} and {maximum}" if maximum is not None else f"at least {minimum}"
        raise ConfigError(f"{name} must be {bound}")
    return value


def _boolean(env: Mapping[str, str], name: str, default: bool) -> bool:
    raw = env.get(name, "true" if default else "false").strip().lower()
    if raw not in {"true", "false", "1", "0"}:
        raise ConfigError(f"{name} must be true or false")
    return raw in {"true", "1"}


@dataclass(frozen=True)
class Settings:
    """All limits are backend configuration. No request field can raise them."""

    api_key: str = field(repr=False)
    governor_url: str
    governor_access_key: str = field(repr=False)
    data_dir: str
    jobs_dir: str
    cache_dir: str
    runtime_dir: str
    python_executable: str
    mpl_cache_dir: str
    dataset_url_schemes: tuple[str, ...]
    # inputs
    max_logical_datasets: int
    max_input_files: int
    max_input_rows: int
    max_input_bytes: int
    max_code_chars: int
    download_timeout_seconds: int
    dataset_cache_bytes: int
    # execution
    max_runtime_seconds: int
    max_memory_mb: int
    max_virtual_memory_mb: int
    cpus_per_job: int
    threads_per_job: int
    max_threads: int
    max_intermediate_bytes: int
    max_output_dir_bytes: int
    duckdb_memory_mb: int
    max_materialize_rows: int
    concurrency: int
    max_queued: int
    slot_uid_base: int
    random_seed: int
    require_isolation: bool
    # validation
    validator_uid: int
    validator_runtime_seconds: int
    validator_memory_mb: int
    # request-level budgets (all run_python_analysis calls of one orchestrator request together)
    max_analyses_per_request: int
    max_cpu_seconds_per_request: int
    max_input_bytes_per_request: int
    max_specs_per_request: int
    # research governor (experiments of one orchestrator request) and the evidence thresholds
    research_max_hypotheses: int
    research_max_experiments: int
    research_max_followups_per_hypothesis: int
    research_max_pairwise_candidates: int
    research_max_candidates: int
    research_min_events: int
    research_min_baseline_observations: int
    research_min_coverage_pct: int
    research_min_holdout_pct: int
    leakage_check: bool
    # DataNeed flow (DataNeedSpec, governed bundles, analysis sessions); off until the orchestrator switches over
    dataneed_enabled: bool
    bundle_dir: str
    bundle_retention_hours: int
    bundle_max_rows: int
    bundle_max_bytes: int
    bundle_max_parts: int
    bundle_store_bytes: int
    session_uid_base: int
    max_sessions: int
    session_execution_seconds: int
    session_cpu_seconds: int
    session_idle_seconds: int
    session_max_seconds: int
    session_max_executions: int
    session_max_failed: int
    session_max_outputs: int
    # outputs
    max_tables: int
    max_table_output_rows: int
    max_table_preview_rows: int
    max_metrics: int
    max_metrics_bytes: int
    max_output_bytes: int
    max_artifact_bytes: int
    max_charts: int
    max_artifacts: int
    diagnostics_chars: int
    # lifecycle
    submit_wait_seconds: int
    max_poll_wait_seconds: int
    retry_after_seconds: int
    result_retention_hours: int
    record_retention_days: int
    cleanup_interval_seconds: int
    retain_code: bool
    failed_workspace_ttl_hours: int
    failed_workspace_max_bytes: int

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if env is None else env
        secrets = {name: env.get(name, "").strip() for name in
                   ("PY_SANDBOX_API_KEY", "SQL_GOVERNOR_URL", "SQL_GOVERNOR_DATASET_ACCESS_KEY")}
        missing = [name for name, value in secrets.items() if not value]
        if missing:
            raise ConfigError(f"Missing required variables: {', '.join(missing)}")
        for name in ("PY_SANDBOX_API_KEY", "SQL_GOVERNOR_DATASET_ACCESS_KEY"):
            if len(secrets[name]) < 32:
                raise ConfigError(f"{name} must be at least 32 characters")
        if secrets["PY_SANDBOX_API_KEY"] == secrets["SQL_GOVERNOR_DATASET_ACCESS_KEY"]:
            raise ConfigError("PY_SANDBOX_API_KEY must differ from SQL_GOVERNOR_DATASET_ACCESS_KEY")
        if not secrets["SQL_GOVERNOR_URL"].startswith(("http://", "https://")):
            raise ConfigError("SQL_GOVERNOR_URL must be an http(s) URL")
        schemes = tuple(s.strip().lower() for s in env.get("PY_SANDBOX_DATASET_URL_SCHEMES", "https").split(",")
                        if s.strip())
        if not schemes or not set(schemes) <= {"https", "http", "file"}:
            raise ConfigError("PY_SANDBOX_DATASET_URL_SCHEMES must be a subset of https,http,file")

        memory = _integer(env, "PY_SANDBOX_MAX_MEMORY_MB", 2048, minimum=256, maximum=16384)
        settings = cls(
            api_key=secrets["PY_SANDBOX_API_KEY"],
            governor_url=secrets["SQL_GOVERNOR_URL"].rstrip("/"),
            governor_access_key=secrets["SQL_GOVERNOR_DATASET_ACCESS_KEY"],
            data_dir=env.get("PY_SANDBOX_DATA_DIR", "/data").strip(),
            jobs_dir=env.get("PY_SANDBOX_JOBS_DIR", "/sandbox/jobs").strip(),
            cache_dir=env.get("PY_SANDBOX_CACHE_DIR", "/sandbox/cache").strip(),
            runtime_dir=env.get("PY_SANDBOX_RUNTIME_DIR",
                                os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                             "runtime")).strip(),
            python_executable=env.get("PY_SANDBOX_PYTHON", "/usr/local/bin/python").strip(),
            mpl_cache_dir=env.get("PY_SANDBOX_MPL_CACHE_DIR", "/opt/mplcache").strip(),
            dataset_url_schemes=schemes,
            max_logical_datasets=_integer(env, "PY_SANDBOX_MAX_LOGICAL_DATASETS", 4, maximum=4),
            max_input_files=_integer(env, "PY_SANDBOX_MAX_INPUT_FILES", 8, maximum=64),
            max_input_rows=_integer(env, "PY_SANDBOX_MAX_INPUT_ROWS", 2_000_000, maximum=20_000_000),
            max_input_bytes=_integer(env, "PY_SANDBOX_MAX_INPUT_BYTES", 268_435_456, minimum=1024,
                                     maximum=4_294_967_296),
            max_code_chars=_integer(env, "PY_SANDBOX_MAX_CODE_CHARS", 20000, minimum=100, maximum=20000),
            download_timeout_seconds=_integer(env, "PY_SANDBOX_DOWNLOAD_TIMEOUT_SECONDS", 60, maximum=600),
            dataset_cache_bytes=_integer(env, "PY_SANDBOX_DATASET_CACHE_BYTES", 1_073_741_824, minimum=0,
                                         maximum=17_179_869_184),
            max_runtime_seconds=_integer(env, "PY_SANDBOX_MAX_RUNTIME_SECONDS", 120, minimum=5, maximum=900),
            max_memory_mb=memory,
            max_virtual_memory_mb=_integer(env, "PY_SANDBOX_MAX_VIRTUAL_MEMORY_MB", max(4096, memory * 2),
                                           minimum=memory, maximum=65536),
            cpus_per_job=_integer(env, "PY_SANDBOX_CPUS_PER_JOB", 2, maximum=16),
            threads_per_job=_integer(env, "PY_SANDBOX_THREADS_PER_JOB", 2, maximum=16),
            max_threads=_integer(env, "PY_SANDBOX_MAX_THREADS", 128, minimum=16, maximum=1024),
            max_intermediate_bytes=_integer(env, "PY_SANDBOX_MAX_INTERMEDIATE_BYTES", 1_073_741_824,
                                            minimum=16_777_216, maximum=17_179_869_184),
            max_output_dir_bytes=_integer(env, "PY_SANDBOX_MAX_OUTPUT_DIR_BYTES", 268_435_456, minimum=1_048_576,
                                          maximum=4_294_967_296),
            duckdb_memory_mb=_integer(env, "PY_SANDBOX_DUCKDB_MEMORY_MB", max(128, memory // 2), minimum=64,
                                      maximum=memory),
            max_materialize_rows=_integer(env, "PY_SANDBOX_MAX_MATERIALIZE_ROWS", 2_000_000, minimum=1000,
                                          maximum=20_000_000),
            concurrency=_integer(env, "PY_SANDBOX_CONCURRENCY", 1, maximum=4),
            max_queued=_integer(env, "PY_SANDBOX_MAX_QUEUED", 8, maximum=100),
            slot_uid_base=_integer(env, "PY_SANDBOX_SLOT_UID_BASE", 20001, minimum=1000, maximum=60000),
            random_seed=_integer(env, "PY_SANDBOX_RANDOM_SEED", 0, minimum=0, maximum=2**32 - 1),
            require_isolation=_boolean(env, "PY_SANDBOX_REQUIRE_ISOLATION", True),
            validator_uid=_integer(env, "PY_SANDBOX_VALIDATOR_UID", 20100, minimum=1000, maximum=60000),
            validator_runtime_seconds=_integer(env, "PY_SANDBOX_VALIDATOR_RUNTIME_SECONDS", 120, minimum=10,
                                               maximum=900),
            validator_memory_mb=_integer(env, "PY_SANDBOX_VALIDATOR_MEMORY_MB", memory, minimum=256, maximum=16384),
            max_analyses_per_request=_integer(env, "PY_SANDBOX_MAX_ANALYSES_PER_REQUEST", 6, maximum=100),
            max_cpu_seconds_per_request=_integer(env, "PY_SANDBOX_MAX_CPU_SECONDS_PER_REQUEST", 1200, minimum=10,
                                                 maximum=86400),
            max_input_bytes_per_request=_integer(env, "PY_SANDBOX_MAX_INPUT_BYTES_PER_REQUEST", 1_073_741_824,
                                                 minimum=1024, maximum=68_719_476_736),
            max_specs_per_request=_integer(env, "PY_SANDBOX_MAX_SPECS_PER_REQUEST", 10, maximum=100),
            research_max_hypotheses=_integer(env, "PY_SANDBOX_RESEARCH_MAX_HYPOTHESES", 4, maximum=50),
            # default: every analysis of the request may be an experiment
            research_max_experiments=_integer(env, "PY_SANDBOX_RESEARCH_MAX_EXPERIMENTS",
                                              _integer(env, "PY_SANDBOX_MAX_ANALYSES_PER_REQUEST", 6, maximum=100),
                                              maximum=100),
            research_max_followups_per_hypothesis=_integer(env, "PY_SANDBOX_RESEARCH_MAX_FOLLOWUPS_PER_HYPOTHESIS", 5,
                                                           minimum=0, maximum=50),
            research_max_pairwise_candidates=_integer(env, "PY_SANDBOX_RESEARCH_MAX_PAIRWISE_CANDIDATES", 20_000,
                                                      maximum=10_000_000),
            research_max_candidates=_integer(env, "PY_SANDBOX_RESEARCH_MAX_CANDIDATES", 50, maximum=100_000),
            research_min_events=_integer(env, "PY_SANDBOX_RESEARCH_MIN_EVENTS", 30, maximum=100_000),
            research_min_baseline_observations=_integer(env, "PY_SANDBOX_RESEARCH_MIN_BASELINE_OBSERVATIONS", 100,
                                                        maximum=10_000_000),
            research_min_coverage_pct=_integer(env, "PY_SANDBOX_RESEARCH_MIN_COVERAGE_PCT", 95, maximum=100),
            research_min_holdout_pct=_integer(env, "PY_SANDBOX_RESEARCH_MIN_HOLDOUT_PCT", 20, maximum=90),
            leakage_check=_boolean(env, "PY_SANDBOX_LEAKAGE_CHECK", True),
            dataneed_enabled=_boolean(env, "PY_SANDBOX_DATANEED_ENABLED", False),
            bundle_dir=env.get("PY_SANDBOX_BUNDLE_DIR", "").strip() or str(
                Path(env.get("PY_SANDBOX_DATA_DIR", "/data").strip()) / "bundles"),
            bundle_retention_hours=_integer(env, "PY_SANDBOX_BUNDLE_RETENTION_HOURS", 24, maximum=168),
            bundle_max_rows=_integer(env, "PY_SANDBOX_BUNDLE_MAX_ROWS",
                                     _integer(env, "PY_SANDBOX_MAX_INPUT_ROWS", 2_000_000, maximum=20_000_000),
                                     maximum=50_000_000),
            bundle_max_bytes=_integer(env, "PY_SANDBOX_BUNDLE_MAX_BYTES",
                                      _integer(env, "PY_SANDBOX_MAX_INPUT_BYTES", 268_435_456, minimum=1024,
                                               maximum=4_294_967_296), minimum=1024, maximum=17_179_869_184),
            bundle_max_parts=_integer(env, "PY_SANDBOX_BUNDLE_MAX_PARTS", 128, maximum=1024),
            bundle_store_bytes=_integer(env, "PY_SANDBOX_BUNDLE_STORE_BYTES", 8_589_934_592, minimum=1 << 20,
                                        maximum=1 << 40),
            session_uid_base=_integer(env, "PY_SANDBOX_SESSION_UID_BASE", 20201, minimum=1000, maximum=60000),
            max_sessions=_integer(env, "PY_SANDBOX_MAX_SESSIONS", 2, maximum=4),
            session_execution_seconds=_integer(env, "PY_SANDBOX_SESSION_EXECUTION_SECONDS",
                                               _integer(env, "PY_SANDBOX_MAX_RUNTIME_SECONDS", 120, maximum=3600),
                                               minimum=5, maximum=900),
            session_cpu_seconds=_integer(env, "PY_SANDBOX_SESSION_CPU_SECONDS", 900, minimum=10, maximum=86400),
            session_idle_seconds=_integer(env, "PY_SANDBOX_SESSION_IDLE_SECONDS", 900, minimum=30, maximum=86400),
            session_max_seconds=_integer(env, "PY_SANDBOX_SESSION_MAX_SECONDS", 3600, minimum=60, maximum=86400),
            session_max_executions=_integer(env, "PY_SANDBOX_SESSION_MAX_EXECUTIONS", 40, maximum=500),
            session_max_failed=_integer(env, "PY_SANDBOX_SESSION_MAX_FAILED", 15, maximum=500),
            session_max_outputs=_integer(env, "PY_SANDBOX_SESSION_MAX_OUTPUTS", 40, maximum=500),
            max_tables=_integer(env, "PY_SANDBOX_MAX_TABLES", 8, maximum=32),
            max_table_output_rows=_integer(env, "PY_SANDBOX_MAX_TABLE_OUTPUT_ROWS", 100_000, maximum=5_000_000),
            max_table_preview_rows=_integer(env, "PY_SANDBOX_MAX_TABLE_PREVIEW_ROWS", 50, maximum=200),
            max_metrics=_integer(env, "PY_SANDBOX_MAX_METRICS", 8, maximum=32),
            max_metrics_bytes=_integer(env, "PY_SANDBOX_MAX_METRICS_BYTES", 8000, minimum=256, maximum=65536),
            max_output_bytes=_integer(env, "PY_SANDBOX_MAX_OUTPUT_BYTES", 24000, minimum=4096, maximum=262144),
            max_artifact_bytes=_integer(env, "PY_SANDBOX_MAX_ARTIFACT_BYTES", 67_108_864, minimum=65536,
                                        maximum=1_073_741_824),
            max_charts=_integer(env, "PY_SANDBOX_MAX_CHARTS", 8, minimum=0, maximum=32),
            max_artifacts=_integer(env, "PY_SANDBOX_MAX_ARTIFACTS", 8, minimum=0, maximum=32),
            diagnostics_chars=_integer(env, "PY_SANDBOX_DIAGNOSTICS_CHARS", 2000, minimum=0, maximum=20000),
            submit_wait_seconds=_integer(env, "PY_SANDBOX_SUBMIT_WAIT_SECONDS", 25, minimum=0, maximum=60),
            max_poll_wait_seconds=_integer(env, "PY_SANDBOX_MAX_POLL_WAIT_SECONDS", 20, minimum=0, maximum=60),
            retry_after_seconds=_integer(env, "PY_SANDBOX_RETRY_AFTER_SECONDS", 15, maximum=300),
            result_retention_hours=_integer(env, "PY_SANDBOX_RESULT_RETENTION_HOURS", 24, maximum=720),
            record_retention_days=_integer(env, "PY_SANDBOX_RECORD_RETENTION_DAYS", 30, maximum=3650),
            cleanup_interval_seconds=_integer(env, "PY_SANDBOX_CLEANUP_INTERVAL_SECONDS", 900, minimum=0,
                                              maximum=86400),
            retain_code=_boolean(env, "PY_SANDBOX_RETAIN_CODE", True),
            failed_workspace_ttl_hours=_integer(env, "PY_SANDBOX_FAILED_WORKSPACE_TTL_HOURS", 6, minimum=0,
                                                maximum=72),
            failed_workspace_max_bytes=_integer(env, "PY_SANDBOX_FAILED_WORKSPACE_MAX_BYTES", 67_108_864,
                                                minimum=0, maximum=1_073_741_824),
        )
        if settings.record_retention_days * 24 < settings.result_retention_hours:
            raise ConfigError("PY_SANDBOX_RECORD_RETENTION_DAYS must cover PY_SANDBOX_RESULT_RETENTION_HOURS")
        if settings.max_table_preview_rows > settings.max_table_output_rows:
            raise ConfigError("PY_SANDBOX_MAX_TABLE_PREVIEW_ROWS must not exceed PY_SANDBOX_MAX_TABLE_OUTPUT_ROWS")
        if settings.threads_per_job * 8 > settings.max_threads:
            raise ConfigError("PY_SANDBOX_MAX_THREADS must be at least 8x PY_SANDBOX_THREADS_PER_JOB")
        if settings.slot_uid_base <= settings.validator_uid < settings.slot_uid_base + settings.concurrency:
            raise ConfigError("PY_SANDBOX_VALIDATOR_UID must differ from every analysis slot user")
        sessions = range(settings.session_uid_base, settings.session_uid_base + settings.max_sessions)
        slots = range(settings.slot_uid_base, settings.slot_uid_base + settings.concurrency)
        if settings.validator_uid in sessions or set(sessions) & set(slots):
            raise ConfigError("PY_SANDBOX_SESSION_UID_BASE must give session users distinct from the analysis slot "
                              "users and the validator user")
        return settings

    def research_policy(self):
        from .research_policy import ResearchPolicy

        return ResearchPolicy(
            max_hypotheses=self.research_max_hypotheses, max_experiments=self.research_max_experiments,
            max_followups_per_hypothesis=self.research_max_followups_per_hypothesis,
            max_pairwise_candidates=self.research_max_pairwise_candidates,
            max_candidates=self.research_max_candidates, min_events=self.research_min_events,
            min_baseline_observations=self.research_min_baseline_observations,
            min_coverage_pct=self.research_min_coverage_pct, min_holdout_pct=self.research_min_holdout_pct)

    def governance_policy(self):
        """Budgets of the DataNeed Research Governor (the same run budgets as the Analysis Spec research governor)."""
        from .research_governance import GovernancePolicy

        return GovernancePolicy(
            max_experiments=self.research_max_experiments, max_hypotheses=self.research_max_hypotheses,
            max_followups_per_hypothesis=self.research_max_followups_per_hypothesis,
            max_candidates=self.research_max_candidates, max_pairwise_comparisons=self.research_max_pairwise_candidates,
            min_sample={"EVENTS": self.research_min_events, "OBSERVATIONS": self.research_min_baseline_observations,
                        "ENTITIES": 10},
            compute_seconds_per_experiment=max(60, self.max_cpu_seconds_per_request // max(1,
                                                                                           self.research_max_experiments)))

    @property
    def cpu_seconds(self) -> int:
        """RLIMIT_CPU: the wall-clock budget on every pinned CPU, plus a small margin."""
        return self.max_runtime_seconds * self.cpus_per_job + 5

    def child_limits(self, cpu_seconds: int | None = None) -> dict[str, int]:
        return {
            "virtual_memory_mb": self.max_virtual_memory_mb, "cpu_seconds": cpu_seconds or self.cpu_seconds,
            "max_file_bytes": max(self.max_artifact_bytes, self.max_intermediate_bytes),
            "max_artifact_bytes": self.max_artifact_bytes, "max_threads": self.max_threads,
            "max_materialize_rows": self.max_materialize_rows,
            "max_tables": self.max_tables, "max_table_output_rows": self.max_table_output_rows,
            "max_table_preview_rows": self.max_table_preview_rows, "max_metrics": self.max_metrics,
            "max_metrics_bytes": self.max_metrics_bytes, "max_charts": self.max_charts,
            "max_artifacts": self.max_artifacts,
        }

    def validator_limits(self) -> dict[str, int]:
        memory = self.validator_memory_mb
        return {"virtual_memory_mb": max(4096, memory * 2), "cpu_seconds": self.validator_runtime_seconds * 2 + 5,
                "max_file_bytes": 16_777_216, "max_threads": self.max_threads}
