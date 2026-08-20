import { execFile } from "node:child_process";
import path from "node:path";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

export async function runE2eWorker(): Promise<void> {
  const apiRoot = path.resolve(process.cwd(), "../api");
  const timeout = Number(process.env.PLAYWRIGHT_INFRASTRUCTURE_TIMEOUT ?? 120_000);
  const environment = {
    ...process.env,
    SONGDANCE_ENVIRONMENT: "test",
    SONGDANCE_DATABASE_URL: requireEnvironment("SONGDANCE_DATABASE_URL"),
    SONGDANCE_LOCAL_STORAGE_PATH: requireEnvironment("SONGDANCE_LOCAL_STORAGE_PATH"),
    SONGDANCE_TEMP_PATH: requireEnvironment("SONGDANCE_TEMP_PATH"),
    SONGDANCE_AUTO_CREATE_SCHEMA: "true",
    SONGDANCE_QUEUE_NAME: requireEnvironment("SONGDANCE_QUEUE_NAME"),
    SONGDANCE_REDIS_URL: requireEnvironment("SONGDANCE_REDIS_URL"),
    SONGDANCE_QUOTA_BACKEND: "memory",
  };
  await execFileAsync(".venv/bin/alembic", ["upgrade", "head"], {
    cwd: apiRoot,
    env: environment,
    timeout,
  });
  await execFileAsync(
    ".venv/bin/python",
    [
      "-c",
      "import os; from redis import Redis; from rq import Queue, SimpleWorker; r=Redis.from_url(os.environ['SONGDANCE_REDIS_URL']); q=Queue(os.environ['SONGDANCE_QUEUE_NAME'], connection=r); SimpleWorker([q], connection=r).work(burst=True, with_scheduler=False)",
    ],
    {
      cwd: apiRoot,
      env: environment,
      timeout,
      maxBuffer: 1024 * 1024,
    },
  );
}

function requireEnvironment(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`${name} is not configured; run the worker through Playwright global setup`);
  return value;
}
