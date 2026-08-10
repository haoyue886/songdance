import { execFile } from "node:child_process";
import path from "node:path";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

export async function runE2eWorker(): Promise<void> {
  const apiRoot = path.resolve(process.cwd(), "../api");
  const timeout = Number(process.env.PLAYWRIGHT_INFRASTRUCTURE_TIMEOUT ?? 120_000);
  await execFileAsync(
    ".venv/bin/python",
    [
      "-c",
      "from redis import Redis; from rq import Queue, SimpleWorker; r=Redis.from_url('redis://127.0.0.1:6379/0'); q=Queue('songdance-e2e', connection=r); SimpleWorker([q], connection=r).work(burst=True, with_scheduler=False)",
    ],
    {
      cwd: apiRoot,
      env: {
        ...process.env,
        SONGDANCE_ENVIRONMENT: "test",
        SONGDANCE_DATABASE_URL: "sqlite:///./.data/e2e.sqlite3",
        SONGDANCE_LOCAL_STORAGE_PATH: ".data/e2e-storage",
        SONGDANCE_TEMP_PATH: ".data/e2e-tmp",
        SONGDANCE_AUTO_CREATE_SCHEMA: "true",
        SONGDANCE_QUEUE_NAME: "songdance-e2e",
        SONGDANCE_QUOTA_BACKEND: "memory",
      },
      timeout,
      maxBuffer: 1024 * 1024,
    },
  );
}
