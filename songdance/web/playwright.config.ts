import { defineConfig } from "@playwright/test";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";

const chromePath =
  process.env.PLAYWRIGHT_EXECUTABLE_PATH ??
  (process.platform === "darwin"
    ? "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    : undefined);
const infrastructureTimeout = Number(process.env.PLAYWRIGHT_INFRASTRUCTURE_TIMEOUT ?? 30_000);
const apiPort = process.env.PLAYWRIGHT_API_PORT ?? "8002";
const webPort = process.env.PLAYWRIGHT_WEB_PORT ?? "3001";
const webOrigin = `http://localhost:${webPort}`;
const apiOrigin = `http://127.0.0.1:${apiPort}`;
const e2eRoot = mkdtempSync(path.join(os.tmpdir(), "songdance-e2e-"));
const e2eWebDistDir = path.join(".next", `e2e-${path.basename(e2eRoot)}`);
const e2eTsconfigRoot = path.join(".next", "e2e-config");
const e2eTsconfigPath = path.join(e2eTsconfigRoot, "tsconfig.json");
const e2eDatabaseUrl = `sqlite:///${path.join(e2eRoot, "e2e.sqlite3")}`;
const e2eQueueName = `songdance-e2e-${path.basename(e2eRoot)}`;
const e2eEnvironment = {
  SONGDANCE_DATABASE_URL: e2eDatabaseUrl,
  SONGDANCE_LOCAL_STORAGE_PATH: path.join(e2eRoot, "storage"),
  SONGDANCE_TEMP_PATH: path.join(e2eRoot, "tmp"),
  SONGDANCE_REDIS_URL: "redis://127.0.0.1:6379/0",
  SONGDANCE_QUEUE_NAME: e2eQueueName,
};
const e2eEnvironmentFile = path.join(e2eRoot, "environment.json");
writeFileSync(e2eEnvironmentFile, JSON.stringify(e2eEnvironment), { encoding: "utf8", mode: 0o600 });
mkdirSync(e2eTsconfigRoot, { recursive: true });
writeFileSync(
  e2eTsconfigPath,
  JSON.stringify({ extends: path.relative(e2eTsconfigRoot, path.resolve("tsconfig.json")) }),
  { encoding: "utf8", mode: 0o600 },
);
process.env.SONGDANCE_E2E_ENV_FILE = e2eEnvironmentFile;
process.env.SONGDANCE_E2E_ROOT = e2eRoot;
process.env.SONGDANCE_E2E_WEB_DIST_DIR = path.resolve(e2eWebDistDir);
process.env.SONGDANCE_E2E_TSCONFIG_ROOT = path.resolve(e2eTsconfigRoot);

export default defineConfig({
  testDir: "./e2e",
  globalSetup: "./e2e/global-setup.ts",
  globalTeardown: "./e2e/global-teardown.ts",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: "list",
  use: {
    baseURL: webOrigin,
    headless: true,
    launchOptions: chromePath ? { executablePath: chromePath } : undefined,
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: `.venv/bin/alembic upgrade head && .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port ${apiPort}`,
      cwd: "../api",
      env: {
        SONGDANCE_ENVIRONMENT: "test",
        SONGDANCE_CORS_ORIGINS: webOrigin,
        SONGDANCE_DATABASE_URL: e2eDatabaseUrl,
        SONGDANCE_LOCAL_STORAGE_PATH: path.join(e2eRoot, "storage"),
        SONGDANCE_TEMP_PATH: path.join(e2eRoot, "tmp"),
        SONGDANCE_REDIS_URL: e2eEnvironment.SONGDANCE_REDIS_URL,
        SONGDANCE_AUTO_CREATE_SCHEMA: "true",
        SONGDANCE_QUEUE_NAME: e2eQueueName,
        SONGDANCE_QUOTA_BACKEND: "memory",
        SONGDANCE_HOURLY_JOB_LIMIT: "100",
        SONGDANCE_DAILY_JOB_LIMIT: "100",
      },
      url: `${apiOrigin}/health`,
      reuseExistingServer: false,
      timeout: infrastructureTimeout,
    },
    {
      command: `pnpm exec next dev -p ${webPort}`,
      env: {
        NEXT_PUBLIC_API_URL: apiOrigin,
        NEXT_PUBLIC_SITE_URL: webOrigin,
        SONGDANCE_NEXT_DIST_DIR: e2eWebDistDir,
        SONGDANCE_TSCONFIG_PATH: e2eTsconfigPath,
      },
      url: webOrigin,
      reuseExistingServer: false,
      timeout: infrastructureTimeout,
    },
  ],
});
