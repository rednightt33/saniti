import { defineRailway, postgres, preserve, project, service, volume } from "railway/iac";

export default defineRailway(() => {
  const Postgres = postgres("Postgres", { region: "sfo" });
  Postgres.networking = { privateNetworkEndpoint: "postgres", tcpProxies: { "5432": {} } };
  const postgresVolume = volume("postgres-volume", { alerts: { usage: { "100": {}, "80": {}, "95": {} } }, allowOnlineResize: true, region: "sfo", sizeMB: 50000 });
  const idxPriceCron = service("idx-price-cron", {
    build: { buildEnvironment: "V3", builder: "DOCKERFILE", dockerfilePath: "Dockerfile" },
    start: "python price_update.py --mode daily",
    replicas: { "sfo": 1 },
    deploy: { cronSchedule: "0 10 * * *", restartPolicyType: "NEVER" },
    env: { DATABASE_URL: preserve(), TELEGRAM_NOTIFY_ATTEMPTS: preserve(), TELEGRAM_NOTIFY_SECRET: preserve(), TELEGRAM_NOTIFY_TIMEOUT: preserve(), TELEGRAM_NOTIFY_URL: preserve() },
  });
  const telegramTrigger = service("telegram-trigger", {
    build: { buildEnvironment: "V3", builder: "DOCKERFILE", dockerfilePath: "Dockerfile" },
    start: "python telegram_trigger.py",
    healthcheck: "/health",
    healthcheckTimeout: 60,
    replicas: { "sfo": 1 },
    deploy: { restartPolicyType: "ALWAYS", sleepApplication: true },
    env: { COMMAND_COOLDOWN_SECONDS: preserve(), DATABASE_URL: preserve(), RAILWAY_DAILY_SERVICE_INSTANCE_ID: preserve(), RAILWAY_PROJECT_TOKEN: preserve(), RAILWAY_RECOVERY_SERVICE_INSTANCE_ID: preserve(), TELEGRAM_ALLOWED_CHAT_ID: preserve(), TELEGRAM_BOT_TOKEN: preserve(), TELEGRAM_WEBHOOK_SECRET: preserve() },
  });
  const telegramMonitor = service("telegram-monitor", {
    build: { buildEnvironment: "V3", builder: "DOCKERFILE", dockerfilePath: "Dockerfile" },
    start: "python telegram_monitor.py",
    healthcheck: "/health",
    healthcheckTimeout: 60,
    replicas: { "sfo": 1 },
    deploy: { restartPolicyType: "ALWAYS", sleepApplication: true },
    env: { DATABASE_URL: preserve(), TELEGRAM_BOT_TOKEN: preserve(), TELEGRAM_CHAT_ID: preserve(), TELEGRAM_NOTIFY_SECRET: preserve(), TELEGRAM_NOTIFY_SUCCESS: preserve() },
  });
  const idxPriceRecoveryCron = service("idx-price-recovery-cron", {
    build: { buildEnvironment: "V3", builder: "DOCKERFILE", dockerfilePath: "Dockerfile" },
    start: "python price_update.py --mode recovery",
    replicas: { "sfo": 1 },
    deploy: { cronSchedule: "0 23 * * *", restartPolicyType: "NEVER" },
    env: { DATABASE_URL: preserve(), TELEGRAM_NOTIFY_ATTEMPTS: preserve(), TELEGRAM_NOTIFY_SECRET: preserve(), TELEGRAM_NOTIFY_TIMEOUT: preserve(), TELEGRAM_NOTIFY_URL: preserve() },
  });

  return project("lucid-patience", {
    resources: [idxPriceCron, telegramTrigger, telegramMonitor, idxPriceRecoveryCron, Postgres, postgresVolume],
  });
});
