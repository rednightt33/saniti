import { bucket, defineRailway, github, image, postgres, preserve, project, service, volume } from "railway/iac";

export default defineRailway(() => {
  const saniti = github("rednightt33/saniti", { checkSuites: false, rootDirectory: "/apps/idx-price-cron" });

  const Postgres = postgres("Postgres", { region: "sfo" });
  Postgres.networking = { privateNetworkEndpoint: "postgres", tcpProxies: { "5432": {} } };
  const postgresVolumeThQL = volume("postgres-volume-thQL", { alerts: { usage: { "100": {}, "80": {}, "95": {} } }, allowOnlineResize: true, region: "sfo", sizeMB: 50000 });
  const postgresVolume = volume("postgres-volume", { alerts: { usage: { "100": {}, "80": {}, "95": {} } }, allowOnlineResize: true, region: "sfo", sizeMB: 50000 });
  const marketPythonSandboxData = volume("market-python-sandbox-data", { alerts: { usage: { "100": {}, "80": {}, "95": {} } }, allowOnlineResize: true, region: "sfo", sizeMB: 50000 });
  const marketSqlDatasets = bucket("market-sql-datasets", { region: "sjc" });
  const marketAnalyticsInput = bucket("market-analytics-input", { region: "sin" });
  const marketSqlGovernor = service("market-sql-governor", {
    build: { buildEnvironment: "V3", builder: "DOCKERFILE", dockerfilePath: "Dockerfile" },
    start: "uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8080",
    healthcheck: "/ready",
    healthcheckTimeout: 120,
    replicas: { "sfo": 1 },
    deploy: { restartPolicyType: "ALWAYS" },
    env: { GOVERNOR_DATABASE_URL: preserve(), MARKET_SQL_GOVERNOR_DB_PASSWORD: preserve(), PORT: preserve(), SQL_DATASET_BUCKET_ACCESS_KEY_ID: preserve(), SQL_DATASET_BUCKET_ENDPOINT: preserve(), SQL_DATASET_BUCKET_NAME: preserve(), SQL_DATASET_BUCKET_REGION: preserve(), SQL_DATASET_BUCKET_SECRET_ACCESS_KEY: preserve(), SQL_GOVERNOR_API_KEY: preserve(), SQL_GOVERNOR_DATASET_ACCESS_KEY: preserve() },
  });
  const marketPythonSandbox = service("market-python-sandbox", {
    build: { buildEnvironment: "V3", builder: "DOCKERFILE", dockerfilePath: "Dockerfile" },
    start: "uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8080",
    healthcheck: "/ready",
    healthcheckTimeout: 300,
    replicas: { "sfo": 1 },
    deploy: { restartPolicyType: "ALWAYS" },
    volumeMounts: { "/data": marketPythonSandboxData },
    env: { PORT: preserve(), PY_SANDBOX_API_KEY: preserve(), SQL_GOVERNOR_DATASET_ACCESS_KEY: preserve(), SQL_GOVERNOR_URL: preserve() },
  });
  const marketAiBackend = service("market-ai-backend", {
    source: github("rednightt33/saniti", { checkSuites: false, rootDirectory: "/apps/market-ai-backend" }),
    build: { buildEnvironment: "V3", builder: "DOCKERFILE", dockerfilePath: "Dockerfile", watchPatterns: ["/apps/market-ai-backend/**"] },
    start: "uvicorn app.main:app --host 0.0.0.0 --port 8080",
    healthcheck: "/health",
    healthcheckTimeout: 120,
    replicas: { "sfo": 1 },
    deploy: { restartPolicyType: "ALWAYS" },
    env: { AI_ANALYSIS_MODE: preserve(), AI_CONTEXT_COMPACTION_MODE: preserve(), AI_CONTEXT_COMPACTION_THRESHOLD_TOKENS: preserve(), AI_CONTEXT_RESERVE_TOKENS: preserve(), AI_CUMULATIVE_COMPACTION_THRESHOLD_PERCENT: preserve(), AI_FINALIZATION_OUTPUT_RESERVE_TOKENS: preserve(), AI_FINALIZATION_TOOL_RESULT_RESERVE_TOKENS: preserve(), AI_FINAL_RESPONSE_MAX_RETRIES: preserve(), AI_MAX_ANALYSIS_SECONDS: preserve(), AI_MAX_CONTEXT_TOKENS: preserve(), AI_MAX_CUMULATIVE_INPUT_TOKENS: preserve(), AI_MAX_CUMULATIVE_OUTPUT_TOKENS: preserve(), AI_MAX_DISCOVERY_CALLS: preserve(), AI_MAX_FEATURE_METADATA_TOKENS: preserve(), AI_MAX_HISTORY_TOKENS: preserve(), AI_MAX_OUTPUT_TOKENS: preserve(), AI_MAX_TOOL_CALLS: preserve(), AI_MAX_TOOL_ITERATIONS: preserve(), AI_MAX_TOOL_RESULT_TOKENS_PER_CALL: preserve(), AI_MAX_TOOL_RESULT_TOKENS_TOTAL: preserve(), AI_MIN_INSIGHT_DATA_CALLS: preserve(), AI_MODEL: preserve(), AI_PROVIDER: preserve(), AI_REASONING_CLEANUP_INTERVAL_SECONDS: preserve(), AI_REASONING_EFFORT: preserve(), AI_REASONING_MAX_BYTES_PER_CALL: preserve(), AI_REASONING_RETENTION_DAYS: preserve(), AI_REQUEST_TIMEOUT_SECONDS: preserve(), AI_STORE_REASONING_DETAILS: preserve(), AI_TARGET_CONTEXT_TOKENS: preserve(), ANALYTICS_BUCKET_ACCESS_KEY_ID: preserve(), ANALYTICS_BUCKET_ENDPOINT: preserve(), ANALYTICS_BUCKET_NAME: preserve(), ANALYTICS_BUCKET_REGION: preserve(), ANALYTICS_BUCKET_SECRET_ACCESS_KEY: preserve(), ANALYTICS_ENABLED: preserve(), ANALYTICS_JOB_POLL_MILLISECONDS: preserve(), ANALYTICS_JOB_WAIT_SECONDS: preserve(), ANALYTICS_MAX_COLUMNS: preserve(), ANALYTICS_MAX_DATASETS: preserve(), ANALYTICS_MAX_DATE_RANGE_DAYS: preserve(), ANALYTICS_MAX_ESTIMATED_ROWS: preserve(), ANALYTICS_MAX_INPUT_BYTES: preserve(), ANALYTICS_MAX_MEMORY_MB: preserve(), ANALYTICS_MAX_RESULT_BYTES: preserve(), ANALYTICS_MAX_RESULT_ROWS: preserve(), ANALYTICS_MAX_ROWS: preserve(), ANALYTICS_MAX_RUNTIME_SECONDS: preserve(), ANALYTICS_RESULT_RETENTION_DAYS: preserve(), ANALYTICS_SNAPSHOT_RETENTION_HOURS: preserve(), ANALYTICS_TERMINAL_SNAPSHOT_GRACE_SECONDS: preserve(), ANALYTICS_WORKER_API_KEY: preserve(), CONDITION_RUNS_MAX_DATE_RANGE_DAYS: preserve(), CONDITION_RUNS_MAX_EPISODES: preserve(), DATABASE_URL: preserve(), LLM_TOOL_RESULT_MAX_BYTES: preserve(), LLM_TOOL_RESULT_MAX_ROWS: preserve(), MARKET_AI_INTERNAL_API_KEY: preserve(), OPENAI_API_KEY: preserve(), OPENAI_MODEL: preserve(), OPENAI_REASONING_EFFORT: preserve(), OPENROUTER_DEEPSEEK: preserve(), QUERY_DEFAULT_ROWS: preserve(), QUERY_MAX_COLUMNS: preserve(), QUERY_MAX_DATE_RANGE_DAYS: preserve(), QUERY_MAX_ESTIMATED_ROWS: preserve(), QUERY_MAX_GROUPS: preserve(), QUERY_MAX_OUTPUT_BYTES: preserve(), QUERY_MAX_PERIODS: preserve(), QUERY_MAX_ROWS: preserve(), QUERY_MAX_TICKERS: preserve(), QUERY_MAX_UNFILTERED_DATE_RANGE_DAYS: preserve(), QUERY_SANDBOX_API_KEY: preserve(), QUERY_SANDBOX_MAX_COLUMNS: preserve(), QUERY_SANDBOX_MAX_DATASETS: preserve(), QUERY_SANDBOX_MAX_DATE_RANGE_DAYS: preserve(), QUERY_SANDBOX_MAX_ESTIMATED_ROWS: preserve(), QUERY_SANDBOX_MAX_INPUT_BYTES: preserve(), QUERY_SANDBOX_MAX_MEMORY_MB: preserve(), QUERY_SANDBOX_MAX_RESULT_BYTES: preserve(), QUERY_SANDBOX_MAX_RESULT_ROWS: preserve(), QUERY_SANDBOX_MAX_ROWS: preserve(), QUERY_SANDBOX_MAX_RUNTIME_SECONDS: preserve(), QUERY_SANDBOX_MAX_TICKERS: preserve(), QUERY_TIMEOUT_SECONDS: preserve(), STATISTICAL_MAX_COLUMNS: preserve(), STATISTICAL_MAX_DATASETS: preserve(), STATISTICAL_MAX_DATE_RANGE_DAYS: preserve(), STATISTICAL_MAX_ESTIMATED_ROWS: preserve(), STATISTICAL_MAX_INPUT_BYTES: preserve(), STATISTICAL_MAX_MEMORY_MB: preserve(), STATISTICAL_MAX_RESULT_BYTES: preserve(), STATISTICAL_MAX_RESULT_ROWS: preserve(), STATISTICAL_MAX_ROWS: preserve(), STATISTICAL_MAX_RUNTIME_SECONDS: preserve(), STATISTICAL_MAX_TICKERS: preserve(), STATISTICAL_WORKER_API_KEY: preserve(), WORKER_LEASE_SECONDS: preserve(), WORKER_POLL_SECONDS: preserve() },
  });
  const marketAiOrc = service("market-ai-orc", {
    build: { buildEnvironment: "V3", builder: "DOCKERFILE", dockerfilePath: "Dockerfile" },
    start: "uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8080",
    healthcheck: "/ready",
    healthcheckTimeout: 120,
    replicas: { "sfo": 1 },
    deploy: { restartPolicyType: "ALWAYS" },
    env: { AI_MAX_TOOL_CALLS: preserve(), AI_MAX_TOOL_ITERATIONS: preserve(), AI_MODEL: preserve(), AI_REASONING_EFFORT: preserve(), CATALOG_DATABASE_URL: preserve(), MARKET_AI_ORC_API_KEY: preserve(), MARKET_AI_ORC_DB_PASSWORD: preserve(), OPENROUTER_API_KEY: preserve(), PORT: preserve(), PY_SANDBOX_API_KEY: preserve(), PY_SANDBOX_URL: preserve(), SQL_GOVERNOR_API_KEY: preserve(), SQL_GOVERNOR_URL: preserve() },
  });
  const idxPriceCron = service("idx-price-cron", {
    source: saniti,
    build: { buildEnvironment: "V3", builder: "DOCKERFILE", dockerfilePath: "Dockerfile", watchPatterns: ["/apps/idx-price-cron/**"] },
    start: "python price_update.py --mode daily",
    replicas: { "sfo": 1 },
    deploy: { cronSchedule: "0 10 * * *", restartPolicyType: "NEVER" },
    env: { DATABASE_URL: preserve(), TELEGRAM_NOTIFY_ATTEMPTS: preserve(), TELEGRAM_NOTIFY_SECRET: preserve(), TELEGRAM_NOTIFY_TIMEOUT: preserve(), TELEGRAM_NOTIFY_URL: preserve() },
  });
  const pgweb = service("pgweb", {
    source: image("sosedoff/pgweb:0.17.0"),
    replicas: { "sfo": 1 },
    env: { PGWEB_AUTH_PASS: preserve(), PGWEB_AUTH_USER: preserve(), PGWEB_DATABASE_URL: preserve() },
  });
  const telegramTrigger = service("telegram-trigger", {
    source: github("rednightt33/saniti", { checkSuites: false, rootDirectory: "/apps/telegram-trigger" }),
    build: { buildEnvironment: "V3", builder: "DOCKERFILE", dockerfilePath: "Dockerfile", watchPatterns: ["/apps/telegram-trigger/**"] },
    start: "python telegram_trigger.py",
    healthcheck: "/health",
    healthcheckTimeout: 60,
    replicas: { "sfo": 1 },
    deploy: { restartPolicyType: "ALWAYS", sleepApplication: true },
    env: { COMMAND_COOLDOWN_SECONDS: preserve(), DATABASE_URL: preserve(), RAILWAY_DAILY_SERVICE_INSTANCE_ID: preserve(), RAILWAY_PROJECT_TOKEN: preserve(), RAILWAY_RECOVERY_SERVICE_INSTANCE_ID: preserve(), TELEGRAM_ALLOWED_CHAT_ID: preserve(), TELEGRAM_BOT_TOKEN: preserve(), TELEGRAM_WEBHOOK_SECRET: preserve() },
  });
  const marketAnalyticsWorker = service("market-analytics-worker", {
    source: github("rednightt33/saniti", { checkSuites: false, rootDirectory: "/apps/market-analytics-worker" }),
    build: { buildEnvironment: "V3", builder: "DOCKERFILE", dockerfilePath: "Dockerfile", watchPatterns: ["/apps/market-analytics-worker/**"] },
    start: "python worker.py",
    healthcheck: "/health",
    healthcheckTimeout: 120,
    replicas: { "sfo": 1 },
    deploy: { restartPolicyType: "ALWAYS" },
    env: { ANALYTICS_WORKER_API_KEY: preserve(), ANALYTICS_WORKER_POLL_SECONDS: preserve(), MARKET_AI_BACKEND_URL: preserve(), STATISTICAL_WORKER_API_KEY: preserve() },
  });
  const telegramMonitor = service("telegram-monitor", {
    source: github("rednightt33/saniti", { checkSuites: false, rootDirectory: "/apps/telegram-monitor" }),
    build: { buildEnvironment: "V3", builder: "DOCKERFILE", dockerfilePath: "Dockerfile", watchPatterns: ["/apps/telegram-monitor/**"] },
    start: "python telegram_monitor.py",
    healthcheck: "/health",
    healthcheckTimeout: 60,
    replicas: { "sfo": 1 },
    deploy: { restartPolicyType: "ALWAYS", sleepApplication: true },
    env: { DATABASE_URL: preserve(), TELEGRAM_BOT_TOKEN: preserve(), TELEGRAM_CHAT_ID: preserve(), TELEGRAM_NOTIFY_SECRET: preserve(), TELEGRAM_NOTIFY_SUCCESS: preserve() },
  });
  const idxPriceRecoveryCron = service("idx-price-recovery-cron", {
    source: saniti,
    build: { buildEnvironment: "V3", builder: "DOCKERFILE", dockerfilePath: "Dockerfile", watchPatterns: ["/apps/idx-price-cron/**"] },
    start: "python price_update.py --mode recovery",
    replicas: { "sfo": 1 },
    deploy: { cronSchedule: "0 23 * * *", restartPolicyType: "NEVER" },
    env: { DATABASE_URL: preserve(), TELEGRAM_NOTIFY_ATTEMPTS: preserve(), TELEGRAM_NOTIFY_SECRET: preserve(), TELEGRAM_NOTIFY_TIMEOUT: preserve(), TELEGRAM_NOTIFY_URL: preserve() },
  });
  const marketQuerySandbox = service("market-query-sandbox", {
    source: github("rednightt33/saniti", { checkSuites: false, rootDirectory: "/apps/market-query-sandbox" }),
    build: { buildEnvironment: "V3", builder: "DOCKERFILE", dockerfilePath: "Dockerfile", watchPatterns: ["/apps/market-query-sandbox/**"] },
    start: "python worker.py",
    healthcheck: "/health",
    healthcheckTimeout: 120,
    replicas: { "sfo": 1 },
    deploy: { restartPolicyType: "ALWAYS" },
    env: { MARKET_AI_BACKEND_URL: preserve(), PORT: preserve(), QUERY_SANDBOX_API_KEY: preserve(), QUERY_SANDBOX_POLL_SECONDS: preserve() },
  });
  const aiDataCoverage = service("ai-data-coverage", {
    source: github("rednightt33/saniti", { checkSuites: false, rootDirectory: "/apps/ai-data-coverage" }),
    build: { buildEnvironment: "V3", builder: "DOCKERFILE", dockerfilePath: "Dockerfile", watchPatterns: ["/apps/ai-data-coverage/**"] },
    start: "python coverage_job.py --mode nightly",
    replicas: { "sfo": 1 },
    deploy: { cronSchedule: "30 0 * * *", restartPolicyType: "NEVER" },
    env: { DATABASE_URL: preserve() },
  });
  const feature01Worker = service("feature-01-worker", {
    source: github("rednightt33/saniti", { checkSuites: false, rootDirectory: "/apps/feature-01-worker" }),
    build: { buildEnvironment: "V3", builder: "DOCKERFILE", dockerfilePath: "Dockerfile", watchPatterns: ["/apps/feature-01-worker/**"] },
    start: "python worker.py",
    replicas: { "sfo": 1 },
    deploy: { restartPolicyType: "ALWAYS" },
    env: { DATABASE_URL: preserve() },
  });
  const dbOpsRunner = service("db-ops-runner", {
    source: image("ghcr.io/railwayapp/function-bun:1.4.0"),
    start: "./run.sh aW1wb3J0IHsgU1FMIH0gZnJvbSAiYnVuIjsKCmNvbnN0IGRiID0gbmV3IFNRTChCdW4uZW52LkRBVEFCQVNFX1VSTCEpOwoKaW50ZXJmYWNlIFRhYmxlIHsKICBzY2hlbWFfbmFtZTogc3RyaW5nOwogIHRhYmxlX25hbWU6IHN0cmluZzsKICB0YWJsZV9jb21tZW50OiBzdHJpbmcgfCBudWxsOwogIHJlbGtpbmQ6IHN0cmluZzsKICBlc3RpbWF0ZWRfcm93czogbnVtYmVyOwp9CgppbnRlcmZhY2UgQ29sdW1uIHsKICBzY2hlbWFfbmFtZTogc3RyaW5nOwogIHRhYmxlX25hbWU6IHN0cmluZzsKICBvcmRpbmFsX3Bvc2l0aW9uOiBudW1iZXI7CiAgY29sdW1uX25hbWU6IHN0cmluZzsKICBkYXRhX3R5cGU6IHN0cmluZzsKICBudWxsYWJsZTogYm9vbGVhbjsKICBjb2x1bW5fZGVmYXVsdDogc3RyaW5nIHwgbnVsbDsKICBpZGVudGl0eTogYm9vbGVhbjsKICBnZW5lcmF0ZWQ6IGJvb2xlYW47CiAgY29sdW1uX2NvbW1lbnQ6IHN0cmluZyB8IG51bGw7Cn0KCmludGVyZmFjZSBDb25zdHJhaW50IHsKICBzY2hlbWFfbmFtZTogc3RyaW5nOwogIHRhYmxlX25hbWU6IHN0cmluZzsKICBjb25zdHJhaW50X25hbWU6IHN0cmluZzsKICBjb25zdHJhaW50X3R5cGU6IHN0cmluZzsKICBsb2NhbF9jb2x1bW5zOiBzdHJpbmdbXTsKICByZWZlcmVuY2VkX3NjaGVtYTogc3RyaW5nIHwgbnVsbDsKICByZWZlcmVuY2VkX3RhYmxlOiBzdHJpbmcgfCBudWxsOwogIHJlZmVyZW5jZWRfY29sdW1uczogc3RyaW5nW10gfCBudWxsOwogIGRlZmluaXRpb246IHN0cmluZzsKfQoKaW50ZXJmYWNlIEluZGV4IHsKICBzY2hlbWFfbmFtZTogc3RyaW5nOwogIHRhYmxlX25hbWU6IHN0cmluZzsKICBpbmRleF9uYW1lOiBzdHJpbmc7CiAgaW5kZXhfZGVmaW5pdGlvbjogc3RyaW5nOwp9Cgphc3luYyBmdW5jdGlvbiBtYWluKCkgewogIHRyeSB7CiAgICAvLyBGZXRjaCB0YWJsZXMKICAgIGNvbnN0IHRhYmxlcyA9IGF3YWl0IGRiYAogICAgICBTRUxFQ1QKICAgICAgICBuLm5zcG5hbWUgYXMgc2NoZW1hX25hbWUsCiAgICAgICAgYy5yZWxuYW1lIGFzIHRhYmxlX25hbWUsCiAgICAgICAgb2JqX2Rlc2NyaXB0aW9uKGMub2lkLCAncGdfY2xhc3MnKSBhcyB0YWJsZV9jb21tZW50LAogICAgICAgIGMucmVsa2luZCwKICAgICAgICBjLnJlbHR1cGxlczo6YmlnaW50IGFzIGVzdGltYXRlZF9yb3dzCiAgICAgIEZST00gcGdfY2xhc3MgYwogICAgICBKT0lOIHBnX25hbWVzcGFjZSBuIE9OIGMucmVsbmFtZXNwYWNlID0gbi5vaWQKICAgICAgV0hFUkUgYy5yZWxraW5kIElOICgncicsICdwJykKICAgICAgICBBTkQgbi5uc3BuYW1lIE5PVCBJTiAoJ3BnX2NhdGFsb2cnLCAnaW5mb3JtYXRpb25fc2NoZW1hJywgJ3BnX3RvYXN0JywgJ2NhdGFsb2cnKQogICAgICAgIEFORCBjLnJlbG5hbWUgTk9UIExJS0UgJ3BnX3RvYXN0JScKICAgICAgICBBTkQgYy5yZWxuYW1lIE5PVCBMSUtFICdwZ190ZW1wJScKICAgICAgT1JERVIgQlkgbi5uc3BuYW1lLCBjLnJlbG5hbWUKICAgIGA7CgogICAgLy8gRmV0Y2ggY29sdW1ucwogICAgY29uc3QgY29sdW1ucyA9IGF3YWl0IGRiYAogICAgICBTRUxFQ1QKICAgICAgICBuLm5zcG5hbWUgYXMgc2NoZW1hX25hbWUsCiAgICAgICAgYy5yZWxuYW1lIGFzIHRhYmxlX25hbWUsCiAgICAgICAgYS5hdHRudW0gYXMgb3JkaW5hbF9wb3NpdGlvbiwKICAgICAgICBhLmF0dG5hbWUgYXMgY29sdW1uX25hbWUsCiAgICAgICAgZm9ybWF0X3R5cGUoYS5hdHR0eXBpZCwgYS5hdHR0eXBtb2QpIGFzIGRhdGFfdHlwZSwKICAgICAgICBOT1QgYS5hdHRub3RudWxsIGFzIG51bGxhYmxlLAogICAgICAgIHBnX2dldF9leHByKGQuYWRiaW4sIGQuYWRyZWxpZCkgYXMgY29sdW1uX2RlZmF1bHQsCiAgICAgICAgYS5hdHRpZGVudGl0eSAhPSAnJyBhcyBpZGVudGl0eSwKICAgICAgICBhLmF0dGdlbmVyYXRlZCAhPSAnJyBhcyBnZW5lcmF0ZWQsCiAgICAgICAgY29sX2Rlc2NyaXB0aW9uKGMub2lkLCBhLmF0dG51bSkgYXMgY29sdW1uX2NvbW1lbnQKICAgICAgRlJPTSBwZ19hdHRyaWJ1dGUgYQogICAgICBKT0lOIHBnX2NsYXNzIGMgT04gYS5hdHRyZWxpZCA9IGMub2lkCiAgICAgIEpPSU4gcGdfbmFtZXNwYWNlIG4gT04gYy5yZWxuYW1lc3BhY2UgPSBuLm9pZAogICAgICBMRUZUIEpPSU4gcGdfYXR0cmRlZiBkIE9OIGQuYWRyZWxpZCA9IGMub2lkIEFORCBkLmFkbnVtID0gYS5hdHRudW0KICAgICAgV0hFUkUgYy5yZWxraW5kIElOICgncicsICdwJykKICAgICAgICBBTkQgbi5uc3BuYW1lIE5PVCBJTiAoJ3BnX2NhdGFsb2cnLCAnaW5mb3JtYXRpb25fc2NoZW1hJywgJ3BnX3RvYXN0JywgJ2NhdGFsb2cnKQogICAgICAgIEFORCBjLnJlbG5hbWUgTk9UIExJS0UgJ3BnX3RvYXN0JScKICAgICAgICBBTkQgYy5yZWxuYW1lIE5PVCBMSUtFICdwZ190ZW1wJScKICAgICAgICBBTkQgYS5hdHRudW0gPiAwCiAgICAgICAgQU5EIE5PVCBhLmF0dGlzZHJvcHBlZAogICAgICBPUkRFUiBCWSBuLm5zcG5hbWUsIGMucmVsbmFtZSwgYS5hdHRudW0KICAgIGA7CgogICAgLy8gRmV0Y2ggY29uc3RyYWludHMgd2l0aCBjb3JyZWxhdGVkIHN1YnF1ZXJpZXMgZm9yIGNvbHVtbiByZXNvbHV0aW9uCiAgICBjb25zdCBjb25zdHJhaW50cyA9IGF3YWl0IGRiYAogICAgICBTRUxFQ1QKICAgICAgICBuLm5zcG5hbWUgYXMgc2NoZW1hX25hbWUsCiAgICAgICAgYy5yZWxuYW1lIGFzIHRhYmxlX25hbWUsCiAgICAgICAgY29uLmNvbm5hbWUgYXMgY29uc3RyYWludF9uYW1lLAogICAgICAgIGNvbi5jb250eXBlIGFzIGNvbnN0cmFpbnRfdHlwZSwKICAgICAgICBBUlJBWSgKICAgICAgICAgIFNFTEVDVCBhLmF0dG5hbWUKICAgICAgICAgIEZST00gdW5uZXN0KGNvbi5jb25rZXkpIFdJVEggT1JESU5BTElUWSBBUyBrKGF0dG51bSwgb3JkKQogICAgICAgICAgSk9JTiBwZ19hdHRyaWJ1dGUgYSBPTiBhLmF0dHJlbGlkPWNvbi5jb25yZWxpZCBBTkQgYS5hdHRudW09ay5hdHRudW0KICAgICAgICAgIE9SREVSIEJZIGsub3JkCiAgICAgICAgKSBBUyBsb2NhbF9jb2x1bW5zLAogICAgICAgIHJuLm5zcG5hbWUgYXMgcmVmZXJlbmNlZF9zY2hlbWEsCiAgICAgICAgcmMucmVsbmFtZSBhcyByZWZlcmVuY2VkX3RhYmxlLAogICAgICAgIENBU0UgV0hFTiBjb24uY29udHlwZT0nZicgVEhFTgogICAgICAgICAgQVJSQVkoCiAgICAgICAgICAgIFNFTEVDVCBhLmF0dG5hbWUKICAgICAgICAgICAgRlJPTSB1bm5lc3QoY29uLmNvbmZrZXkpIFdJVEggT1JESU5BTElUWSBBUyBrKGF0dG51bSwgb3JkKQogICAgICAgICAgICBKT0lOIHBnX2F0dHJpYnV0ZSBhIE9OIGEuYXR0cmVsaWQ9Y29uLmNvbmZyZWxpZCBBTkQgYS5hdHRudW09ay5hdHRudW0KICAgICAgICAgICAgT1JERVIgQlkgay5vcmQKICAgICAgICAgICkKICAgICAgICBFTFNFIE5VTEwgRU5EIEFTIHJlZmVyZW5jZWRfY29sdW1ucywKICAgICAgICBwZ19nZXRfY29uc3RyYWludGRlZihjb24ub2lkKSBhcyBkZWZpbml0aW9uCiAgICAgIEZST00gcGdfY29uc3RyYWludCBjb24KICAgICAgSk9JTiBwZ19jbGFzcyBjIE9OIGNvbi5jb25yZWxpZCA9IGMub2lkCiAgICAgIEpPSU4gcGdfbmFtZXNwYWNlIG4gT04gYy5yZWxuYW1lc3BhY2UgPSBuLm9pZAogICAgICBMRUZUIEpPSU4gcGdfY2xhc3MgcmMgT04gcmMub2lkID0gY29uLmNvbmZyZWxpZAogICAgICBMRUZUIEpPSU4gcGdfbmFtZXNwYWNlIHJuIE9OIHJuLm9pZCA9IHJjLnJlbG5hbWVzcGFjZQogICAgICBXSEVSRSBjb24uY29udHlwZSBJTiAoJ3AnLCAndScsICdmJykKICAgICAgICBBTkQgbi5uc3BuYW1lIE5PVCBJTiAoJ3BnX2NhdGFsb2cnLCAnaW5mb3JtYXRpb25fc2NoZW1hJywgJ3BnX3RvYXN0JywgJ2NhdGFsb2cnKQogICAgICAgIEFORCBjLnJlbG5hbWUgTk9UIExJS0UgJ3BnX3RvYXN0JScKICAgICAgICBBTkQgYy5yZWxuYW1lIE5PVCBMSUtFICdwZ190ZW1wJScKICAgICAgT1JERVIgQlkgbi5uc3BuYW1lLCBjLnJlbG5hbWUsIGNvbi5jb25uYW1lCiAgICBgOwoKICAgIC8vIEZldGNoIGluZGV4ZXMKICAgIGNvbnN0IGluZGV4ZXMgPSBhd2FpdCBkYmAKICAgICAgU0VMRUNUCiAgICAgICAgc2NoZW1hbmFtZSBhcyBzY2hlbWFfbmFtZSwKICAgICAgICB0YWJsZW5hbWUgYXMgdGFibGVfbmFtZSwKICAgICAgICBpbmRleG5hbWUgYXMgaW5kZXhfbmFtZSwKICAgICAgICBpbmRleGRlZiBhcyBpbmRleF9kZWZpbml0aW9uCiAgICAgIEZST00gcGdfaW5kZXhlcwogICAgICBXSEVSRSBzY2hlbWFuYW1lIE5PVCBJTiAoJ3BnX2NhdGFsb2cnLCAnaW5mb3JtYXRpb25fc2NoZW1hJywgJ3BnX3RvYXN0JywgJ2NhdGFsb2cnKQogICAgICAgIEFORCB0YWJsZW5hbWUgTk9UIExJS0UgJ3BnX3RvYXN0JScKICAgICAgICBBTkQgdGFibGVuYW1lIE5PVCBMSUtFICdwZ190ZW1wJScKICAgICAgT1JERVIgQlkgc2NoZW1hbmFtZSwgdGFibGVuYW1lLCBpbmRleG5hbWUKICAgIGA7CgogICAgLy8gQnVpbGQgZmluYWwgY2F0YWxvZyBvYmplY3QKICAgIGNvbnN0IGNhdGFsb2cgPSB7CiAgICAgIHRhYmxlczogdGFibGVzLm1hcCgodDogYW55KSA9PiAoewogICAgICAgIHNjaGVtYV9uYW1lOiB0LnNjaGVtYV9uYW1lLAogICAgICAgIHRhYmxlX25hbWU6IHQudGFibGVfbmFtZSwKICAgICAgICB0YWJsZV9jb21tZW50OiB0LnRhYmxlX2NvbW1lbnQsCiAgICAgICAgcmVsa2luZDogdC5yZWxraW5kLAogICAgICAgIGVzdGltYXRlZF9yb3dzOiBOdW1iZXIodC5lc3RpbWF0ZWRfcm93cyksCiAgICAgIH0pKSwKICAgICAgY29sdW1uczogY29sdW1ucy5tYXAoKGM6IGFueSkgPT4gKHsKICAgICAgICBzY2hlbWFfbmFtZTogYy5zY2hlbWFfbmFtZSwKICAgICAgICB0YWJsZV9uYW1lOiBjLnRhYmxlX25hbWUsCiAgICAgICAgb3JkaW5hbF9wb3NpdGlvbjogYy5vcmRpbmFsX3Bvc2l0aW9uLAogICAgICAgIGNvbHVtbl9uYW1lOiBjLmNvbHVtbl9uYW1lLAogICAgICAgIGRhdGFfdHlwZTogYy5kYXRhX3R5cGUsCiAgICAgICAgbnVsbGFibGU6IGMubnVsbGFibGUsCiAgICAgICAgY29sdW1uX2RlZmF1bHQ6IGMuY29sdW1uX2RlZmF1bHQsCiAgICAgICAgaWRlbnRpdHk6IGMuaWRlbnRpdHksCiAgICAgICAgZ2VuZXJhdGVkOiBjLmdlbmVyYXRlZCwKICAgICAgICBjb2x1bW5fY29tbWVudDogYy5jb2x1bW5fY29tbWVudCwKICAgICAgfSkpLAogICAgICBjb25zdHJhaW50czogY29uc3RyYWludHMubWFwKChjb246IGFueSkgPT4gKHsKICAgICAgICBzY2hlbWFfbmFtZTogY29uLnNjaGVtYV9uYW1lLAogICAgICAgIHRhYmxlX25hbWU6IGNvbi50YWJsZV9uYW1lLAogICAgICAgIGNvbnN0cmFpbnRfbmFtZTogY29uLmNvbnN0cmFpbnRfbmFtZSwKICAgICAgICBjb25zdHJhaW50X3R5cGU6IGNvbi5jb25zdHJhaW50X3R5cGUsCiAgICAgICAgbG9jYWxfY29sdW1uczogY29uLmxvY2FsX2NvbHVtbnMgfHwgW10sCiAgICAgICAgcmVmZXJlbmNlZF9zY2hlbWE6IGNvbi5yZWZlcmVuY2VkX3NjaGVtYSwKICAgICAgICByZWZlcmVuY2VkX3RhYmxlOiBjb24ucmVmZXJlbmNlZF90YWJsZSwKICAgICAgICByZWZlcmVuY2VkX2NvbHVtbnM6IGNvbi5yZWZlcmVuY2VkX2NvbHVtbnMsCiAgICAgICAgZGVmaW5pdGlvbjogY29uLmRlZmluaXRpb24sCiAgICAgIH0pKSwKICAgICAgaW5kZXhlczogaW5kZXhlcy5tYXAoKGk6IGFueSkgPT4gKHsKICAgICAgICBzY2hlbWFfbmFtZTogaS5zY2hlbWFfbmFtZSwKICAgICAgICB0YWJsZV9uYW1lOiBpLnRhYmxlX25hbWUsCiAgICAgICAgaW5kZXhfbmFtZTogaS5pbmRleF9uYW1lLAogICAgICAgIGluZGV4X2RlZmluaXRpb246IGkuaW5kZXhfZGVmaW5pdGlvbiwKICAgICAgfSkpLAogICAgfTsKCiAgICAvLyBTZXJpYWxpemUgd2l0aCBCaWdJbnQgaGFuZGxpbmcKICAgIGNvbnN0IGpzb25TdHIgPSBKU09OLnN0cmluZ2lmeShjYXRhbG9nLCAoa2V5LCB2YWx1ZSkgPT4gewogICAgICBpZiAodHlwZW9mIHZhbHVlID09PSAnYmlnaW50JykgewogICAgICAgIHJldHVybiB2YWx1ZS50b1N0cmluZygpOwogICAgICB9CiAgICAgIHJldHVybiB2YWx1ZTsKICAgIH0pOwoKICAgIC8vIEJhc2U2NCBlbmNvZGUgYW5kIGNodW5rIChtYXggNzAwMCBjaGFycyBwZXIgY2h1bmspCiAgICBjb25zdCBiYXNlNjQgPSBCdWZmZXIuZnJvbShqc29uU3RyKS50b1N0cmluZygnYmFzZTY0Jyk7CiAgICBjb25zdCBjaHVua1NpemUgPSA3MDAwOwogICAgY29uc3QgY2h1bmtzID0gW107CiAgICBmb3IgKGxldCBpID0gMDsgaSA8IGJhc2U2NC5sZW5ndGg7IGkgKz0gY2h1bmtTaXplKSB7CiAgICAgIGNodW5rcy5wdXNoKGJhc2U2NC5zbGljZShpLCBpICsgY2h1bmtTaXplKSk7CiAgICB9CgogICAgLy8gTG9nIGNodW5rcwogICAgY29uc3QgdG90YWxDaHVua3MgPSBjaHVua3MubGVuZ3RoOwogICAgZm9yIChsZXQgaSA9IDA7IGkgPCBjaHVua3MubGVuZ3RoOyBpKyspIHsKICAgICAgY29uc29sZS5sb2coYENBVEFMT0dfTUVUQTo6JHtpfTo6JHt0b3RhbENodW5rc306OiR7Y2h1bmtzW2ldfWApOwogICAgfQoKICAgIC8vIExvZyBzdW1tYXJ5CiAgICBjb25zb2xlLmxvZygKICAgICAgYENBVEFMT0dfTUVUQV9TVU1NQVJZOjoke2NhdGFsb2cudGFibGVzLmxlbmd0aH06OiR7Y2F0YWxvZy5jb2x1bW5zLmxlbmd0aH06OiR7Y2F0YWxvZy5jb25zdHJhaW50cy5sZW5ndGh9Ojoke2NhdGFsb2cuaW5kZXhlcy5sZW5ndGh9YAogICAgKTsKICB9IGNhdGNoIChlcnJvcikgewogICAgY29uc29sZS5lcnJvcignTWV0YWRhdGEgaW5zcGVjdGlvbiBmYWlsZWQ6JywgZXJyb3IpOwogICAgcHJvY2Vzcy5leGl0KDEpOwogIH0KfQoKYXdhaXQgbWFpbigpOwo=",
    replicas: { "sfo": 1 },
    deploy: { restartPolicyType: "NEVER" },
    env: { DATABASE_URL: preserve() },
  });

  return project("lucid-patience", {
    resources: [marketSqlGovernor, marketPythonSandbox, marketAiBackend, marketAiOrc, idxPriceCron, pgweb, telegramTrigger, marketAnalyticsWorker, telegramMonitor, idxPriceRecoveryCron, Postgres, marketQuerySandbox, aiDataCoverage, feature01Worker, dbOpsRunner, postgresVolumeThQL, postgresVolume, marketPythonSandboxData, marketSqlDatasets, marketAnalyticsInput],
  });
});
