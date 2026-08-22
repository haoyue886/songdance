import { rm } from "node:fs/promises";
import path from "node:path";

export default async function globalTeardown(): Promise<void> {
  const root = process.env.SONGDANCE_E2E_ROOT;
  if (root) {
    const runId = path.basename(root);
    await rm(root, { recursive: true, force: true });
    await rm(path.resolve(".next", `e2e-${runId}`), { recursive: true, force: true });
  }
  await rm(path.resolve(".next", "e2e-config"), { recursive: true, force: true });
  const webDistDir = process.env.SONGDANCE_E2E_WEB_DIST_DIR;
  if (webDistDir) await rm(webDistDir, { recursive: true, force: true });
  const tsconfigRoot = process.env.SONGDANCE_E2E_TSCONFIG_ROOT;
  if (tsconfigRoot) await rm(tsconfigRoot, { recursive: true, force: true });
}
