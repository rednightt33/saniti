import { defineRailway, postgres, preserve, project, service, volume } from "railway/iac";

export default defineRailway(() => {
  const Postgres = postgres("Postgres", { region: "sfo" });
  Postgres.networking = { privateNetworkEndpoint: "postgres", tcpProxies: { "5432": {} } };
  const postgresVolume = volume("postgres-volume", { alerts: { usage: { "100": {}, "80": {}, "95": {} } }, allowOnlineResize: true, region: "sfo", sizeMB: 50000 });
  const valiantConnectionVolume = volume("valiant-connection-volume", { alerts: { usage: { "100": {}, "80": {}, "95": {} } }, allowOnlineResize: true, region: "sfo", sizeMB: 50000 });
  const idxPriceCron = service("idx-price-cron", {
    build: { buildEnvironment: "V3", builder: "DOCKERFILE", dockerfilePath: "Dockerfile" },
    start: "python price_update.py --mode auto",
    replicas: { "sfo": 1 },
    deploy: { cronSchedule: "0 10,23 * * *", restartPolicyType: "NEVER" },
    env: { DATABASE_URL: preserve() },
  });
  const valiantConnection = service("valiant-connection", {
    replicas: { "sfo": 1 },
    volumeMounts: { "/data": valiantConnectionVolume },
    env: { DATABASE_URL: preserve(), RAILPACK_PYTHON_VERSION: preserve() },
  });

  return project("lucid-patience", {
    resources: [idxPriceCron, valiantConnection, Postgres, postgresVolume, valiantConnectionVolume],
  });
});
