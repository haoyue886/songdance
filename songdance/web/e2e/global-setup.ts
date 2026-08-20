import { readFile } from "node:fs/promises";

export default async function globalSetup(): Promise<void> {
  const environmentPath = process.env.SONGDANCE_E2E_ENV_FILE;
  if (!environmentPath) throw new Error("SONGDANCE_E2E_ENV_FILE is not configured");
  const environment = JSON.parse(await readFile(environmentPath, "utf8")) as Record<string, string>;
  Object.assign(process.env, environment);
}
