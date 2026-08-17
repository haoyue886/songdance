import { defineConfig } from "@playwright/test";

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

export default defineConfig({
  testDir: "./e2e",
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
      command: `.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port ${apiPort}`,
      cwd: "../api",
      env: {
        SONGDANCE_ENVIRONMENT: "test",
        SONGDANCE_CORS_ORIGINS: webOrigin,
        SONGDANCE_DATABASE_URL: "sqlite:///./.data/e2e.sqlite3",
        SONGDANCE_LOCAL_STORAGE_PATH: ".data/e2e-storage",
        SONGDANCE_TEMP_PATH: ".data/e2e-tmp",
        SONGDANCE_AUTO_CREATE_SCHEMA: "true",
        SONGDANCE_QUEUE_NAME: "songdance-e2e",
        SONGDANCE_QUOTA_BACKEND: "memory",
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
      },
      url: webOrigin,
      reuseExistingServer: false,
      timeout: infrastructureTimeout,
    },
  ],
});
