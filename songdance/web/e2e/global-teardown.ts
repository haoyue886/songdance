import { rm } from "node:fs/promises";

export default async function globalTeardown(): Promise<void> {
  const root = process.env.SONGDANCE_E2E_ROOT;
  if (root) await rm(root, { recursive: true, force: true });
}
