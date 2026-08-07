import { defineConfig } from "@playwright/test";

const chromePath =
  process.env.PLAYWRIGHT_EXECUTABLE_PATH ??
  (process.platform === "darwin"
    ? "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    : undefined);
const infrastructureTimeout = Number(process.env.PLAYWRIGHT_INFRASTRUCTURE_TIMEOUT ?? 30_000);

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: "list",
  use: {
    baseURL: "http://localhost:3001",
    headless: true,
    launchOptions: chromePath ? { executablePath: chromePath } : undefined,
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: ".venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8002",
      cwd: "../api",
      env: {
        SONGDANCE_ENVIRONMENT: "test",
        SONGDANCE_CORS_ORIGINS: "http://localhost:3001",
        SONGDANCE_DATABASE_URL: "sqlite:///./.data/e2e.sqlite3",
        SONGDANCE_LOCAL_STORAGE_PATH: ".data/e2e-storage",
        SONGDANCE_TEMP_PATH: ".data/e2e-tmp",
        SONGDANCE_AUTO_CREATE_SCHEMA: "true",
        SONGDANCE_QUEUE_NAME: "songdance-e2e",
        SONGDANCE_QUOTA_BACKEND: "memory",
      },
      url: "http://127.0.0.1:8002/health",
      reuseExistingServer: false,
      timeout: infrastructureTimeout,
    },
    {
      command: "pnpm exec next dev -p 3001",
      env: { NEXT_PUBLIC_API_URL: "http://127.0.0.1:8002" },
      url: "http://localhost:3001",
      reuseExistingServer: false,
      timeout: infrastructureTimeout,
    },
  ],
});
