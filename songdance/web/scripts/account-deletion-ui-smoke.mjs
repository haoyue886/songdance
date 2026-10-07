// Real-browser account deletion against isolated local protocol doubles.
// No real Supabase session, provider cancellation, payment or data cleanup is verified.
import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { existsSync, mkdtempSync, mkdirSync, readFileSync, writeFileSync, rmSync } from "node:fs";
import { createServer } from "node:http";
import { tmpdir } from "node:os";
import path from "node:path";
import { spawn } from "node:child_process";
import { chromium, expect } from "@playwright/test";

const root = process.cwd();
const temp = mkdtempSync(path.join(tmpdir(), "songdance-account-deletion-ui-"));
const id = path.basename(temp);
const dist = path.join(root, ".next", id);
const configDir = path.join(root, ".next", `${id}-config`);
const output = path.join(root, "test-results", id);
const nextEnvPath = path.join(root, "next-env.d.ts");
const nextEnvBefore = existsSync(nextEnvPath) ? readFileSync(nextEnvPath, "utf8") : null;
mkdirSync(configDir, { recursive: true }); mkdirSync(output, { recursive: true });
writeFileSync(path.join(configDir, "tsconfig.json"), JSON.stringify({ extends: "../../tsconfig.json" }));
const en = JSON.parse(readFileSync(path.join(root, "messages/en.json"), "utf8"));
const zh = JSON.parse(readFileSync(path.join(root, "messages/zh-CN.json"), "utf8"));
const config = {
  usage_enabled: true, checkout_enabled: true, mode: "test",
  pro: { price_minor: 990, currency: "USD", seconds: 1800, max_clip_seconds: 90, min_charge_seconds: 15 },
  free: { monthly_jobs: 1, max_clip_seconds: 90 }, guest: { max_clip_seconds: 30 }, retention_hours: 24, support_email: null,
};
const external = [], failures = [], checks = [], requests = [];
const contexts = new Set();
let fixture, site, apiOrigin, child, browser;
let logs = "";
const listen = (server) => new Promise((resolve, reject) => { server.once("error", reject); server.listen(0, "127.0.0.1", resolve); });
function reset(overrides = {}) {
  fixture = { owner: randomUUID(), email: "account-deletion@example.test", signedIn: true, enabled: true, legacy: false,
    deletion: null, behavior: "pending", statusUnavailable: false, deletes: [], authActions: [], ...overrides };
  return fixture;
}
function deletion(overrides = {}) {
  return { id: randomUUID(), owner_id: fixture.owner, status: "pending", phase: "billing", attempts: 1,
    requested_at: "2026-10-07T10:00:00Z", completed_at: null, error_code: null, ...overrides };
}
function complete() {
  fixture.deletion = { ...fixture.deletion, status: "completed", phase: "cleanup", completed_at: "2026-10-07T10:01:00Z", error_code: null };
}
function account() {
  return { id: fixture.owner, email: fixture.deletion?.status === "completed" ? null : fixture.email,
    ...(!fixture.legacy ? { account_deletion_enabled: fixture.enabled, deletion: fixture.deletion } : {}) };
}
const api = createServer(async (req, res) => {
  try {
    const pathname = new URL(req.url, apiOrigin ?? "http://localhost").pathname;
    res.setHeader("Access-Control-Allow-Origin", site ?? "http://localhost");
    res.setHeader("Access-Control-Allow-Headers", "authorization, content-type, idempotency-key, x-job-access, x-visitor-token");
    res.setHeader("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS");
    if (req.method === "OPTIONS") { res.writeHead(204).end(); return; }
    const json = (value, status = 200) => res.writeHead(status, { "Content-Type": "application/json", "Cache-Control": "no-store" }).end(JSON.stringify(value));
    const chunks = []; for await (const chunk of req) chunks.push(chunk);
    const text = Buffer.concat(chunks).toString("utf8");
    requests.push({ pathname, method: req.method });
    if (pathname === "/billing/config") { json(config); return; }
    if (pathname === "/youtube/config") { json({ enabled: false }); return; }
    if (pathname.startsWith("/events")) { json({}); return; }
    if (!fixture?.signedIn) { json({ detail: { code: "AUTH_REQUIRED" } }, 401); return; }
    assert.equal(req.headers.authorization, `Bearer local-owner-token:${fixture.owner}`, "requests must use the current owner's token");
    if (pathname === "/me" && req.method === "GET") { json(account()); return; }
    if (pathname === "/me/deletion" && req.method === "GET") {
      if (fixture.statusUnavailable) { json({ detail: { code: "DELETION_UNAVAILABLE" } }, 503); return; }
      json({ enabled: fixture.enabled, deletion: fixture.deletion }); return;
    }
    if (pathname === "/me" && req.method === "DELETE") {
      assert.deepEqual(JSON.parse(text), { confirmation: "DELETE" }); fixture.deletes.push({ owner: fixture.owner, confirmation: JSON.parse(text) });
      if (fixture.behavior === "reauth") { json({ detail: { code: "REAUTH_REQUIRED" } }, 403); return; }
      if (!fixture.enabled && !fixture.deletion) { json({ detail: { code: "DELETION_DISABLED" } }, 404); return; }
      fixture.deletion ??= deletion(fixture.behavior === "retry" ? { status: "retry", error_code: "CANCEL_UNAVAILABLE" } : {});
      if (fixture.behavior === "unknown") {
        fixture.statusUnavailable = true;
        res.writeHead(202, { "Content-Type": "application/json", "Cache-Control": "no-store" }).end('{"enabled":true,"deletion":'); return;
      }
      const value = fixture.behavior === "completed-create" ? { ...fixture.deletion, status: "completed", phase: "cleanup", completed_at: "2026-10-07T10:01:00Z" } : fixture.deletion;
      json({ enabled: fixture.enabled, deletion: value }, 202); return;
    }
    if (pathname === "/billing/me") {
      json({ owner_id: fixture.owner, enabled: true, plan: "free", unit: "jobs", state: "active", sync_state: "ready", limit: 1,
        remaining: 1, used: 0, reserved: 0, max_clip_seconds: 90, period_start: "2026-10-01T00:00:00Z", period_end: "2026-11-01T00:00:00Z" }); return;
    }
    json({}, 404);
  } catch (error) { failures.push(`API double: ${error.stack ?? error}`); if (!res.headersSent) res.writeHead(500); res.end(); }
});
async function open() {
  const context = await browser.newContext({ viewport: { width: 1280, height: 1000 }, serviceWorkers: "block" }); contexts.add(context);
  await context.addInitScript(() => sessionStorage.setItem("songdance-guest:legacy-guest-task", "local-guest-capability"));
  await context.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.origin === site && url.pathname === "/api/auth/access-token") {
      await route.fulfill({ status: fixture.signedIn ? 200 : 401, contentType: "application/json", body: JSON.stringify(fixture.signedIn
        ? { access_token: `local-owner-token:${fixture.owner}`, expires_at: Math.floor(Date.now() / 1000) + 3600, user: { id: `provider-${fixture.owner}`, email: fixture.email } }
        : { signed_out: true }) });
    } else if (url.origin === site && url.pathname === "/api/auth/logout") {
      fixture.authActions.push("logout"); fixture.signedIn = false;
      await route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
    } else if (url.protocol.startsWith("http") && ![site, apiOrigin].includes(url.origin)) { external.push(url.href); await route.abort(); }
    else await route.continue();
  });
  const page = await context.newPage(); page.setDefaultTimeout(15000);
  page.on("pageerror", (error) => failures.push(`Browser: ${error.message}`)); return page;
}
async function capture(page, name) {
  await page.evaluate(() => document.fonts.ready);
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `${name}: no horizontal overflow`);
  await page.screenshot({ path: path.join(output, `${name}.png`), fullPage: true, animations: "disabled", style: "nextjs-portal { display: none !important; }" });
}
async function captureBoth(page, name) {
  await page.setViewportSize({ width: 1280, height: 1000 }); await capture(page, `${name}-desktop`);
  await page.setViewportSize({ width: 375, height: 812 }); await capture(page, `${name}-mobile`);
}
async function confirm(page, messages = en) {
  await page.getByRole("button", { name: messages.auth.deletionAction, exact: true }).click();
  await expect(page.getByText(messages.auth.deletionImpact, { exact: true })).toBeVisible();
  const submit = page.getByRole("button", { name: messages.auth.deletionSubmit, exact: true });
  await expect(submit).toBeDisabled(); await page.getByRole("checkbox").check(); return submit;
}
async function assertBlocked(page) {
  for (const name of [en.auth.upload, en.auth.claim]) await expect(page.getByRole(name === en.auth.upload ? "link" : "button", { name, exact: true })).toHaveCount(0);
  await expect(page.getByRole("link", { name: en.auth.back, exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: en.billing.testCheckout, exact: true })).toHaveCount(0);
}
async function run(name, work) {
  try { await work(); checks.push(name); console.log(`PASS ${name}`); }
  catch (error) {
    failures.push(`${name}: ${error.stack ?? error}`);
    for (const context of contexts) for (const page of context.pages()) await capture(page, `failure-${checks.length}-${randomUUID()}`).catch(() => {});
    console.error(`FAIL ${name}: ${error.message}`);
  } finally { for (const context of contexts) { await context.close(); contexts.delete(context); } }
}
try {
  await listen(api); apiOrigin = `http://127.0.0.1:${api.address().port}`;
  const probe = createServer(); await listen(probe); const port = probe.address().port; await new Promise((resolve) => probe.close(resolve)); site = `http://127.0.0.1:${port}`;
  child = spawn(process.execPath, ["node_modules/next/dist/bin/next", "dev", "--webpack", "--hostname", "127.0.0.1", "-p", String(port)], {
    cwd: root, detached: true, stdio: ["ignore", "pipe", "pipe"], env: { ...process.env,
      NODE_ENV: "development", NEXT_TELEMETRY_DISABLED: "1", NEXT_PUBLIC_AUTH_ENABLED: "true", SONGDANCE_AUTH_ENABLED: "true",
      NEXT_PUBLIC_SITE_URL: site, NEXT_PUBLIC_API_URL: apiOrigin, SONGDANCE_AUTH_API_URL: apiOrigin,
      SONGDANCE_SUPABASE_URL: apiOrigin, SONGDANCE_SUPABASE_PUBLISHABLE_KEY: "sb_publishable_account_deletion_protocol_double",
      SONGDANCE_AUTH_BRIDGE_SECRET: "local-account-deletion-browser-double-only",
      SONGDANCE_NEXT_DIST_DIR: path.relative(root, dist), SONGDANCE_TSCONFIG_PATH: path.relative(root, path.join(configDir, "tsconfig.json")),
    },
  });
  for (const stream of [child.stdout, child.stderr]) stream.on("data", (data) => { logs = (logs + data).slice(-20000); });
  let ready = false;
  for (let attempt = 0; attempt < 90; attempt++) {
    if (child.exitCode !== null) throw new Error("Next.js exited before readiness");
    try { if ((await fetch(`${site}/account`, { signal: AbortSignal.timeout(3000) })).ok) { ready = true; break; } } catch { /* startup */ }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  assert.ok(ready, "Next.js readiness timeout");
  browser = await chromium.launch({ headless: true, executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH ?? (process.platform === "darwin" ? "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" : undefined) });
  await run("default-off and old flagless account responses retain existing account actions", async () => {
    for (const legacy of [false, true]) {
      reset({ enabled: false, legacy }); const page = await open(); await page.goto(`${site}/account`);
      await expect(page.getByText(fixture.email, { exact: true })).toBeVisible();
      await expect(page.getByRole("button", { name: en.auth.deletionAction, exact: true })).toHaveCount(0);
      await expect(page.getByRole("link", { name: en.auth.upload, exact: true })).toBeVisible();
      await expect(page.getByRole("button", { name: en.billing.testCheckout, exact: true })).toBeVisible();
      assert.equal(fixture.deletes.length, 0); if (!legacy) await captureBoth(page, "default-off");
    }
  });
  await run("confirmation, cancellation retry, cleanup and verified completion preserve one deletion request", async () => {
    reset({ behavior: "retry" }); const page = await open(); await page.goto(`${site}/account?return_to=${encodeURIComponent("/jobs/legacy-guest-task")}`);
    await expect(page.getByRole("button", { name: en.auth.claim, exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: en.auth.back, exact: true })).toBeVisible();
    const submit = await confirm(page); await captureBoth(page, "confirmation"); await submit.click();
    await expect(page.getByText(en.auth.deletionRetryBilling, { exact: true })).toBeVisible();
    await expect(page.getByText(en.auth.deletionErrorCode.replace("{code}", "CANCEL_UNAVAILABLE"), { exact: true })).toBeVisible();
    await expect(page.getByText(fixture.email, { exact: true })).toBeVisible(); await assertBlocked(page); await captureBoth(page, "billing-retry");
    fixture.deletion = { ...fixture.deletion, status: "pending", phase: "cleanup", error_code: null }; fixture.enabled = false;
    await page.getByRole("button", { name: en.auth.deletionRefresh }).click();
    await expect(page.getByText(en.auth.deletionCleanup, { exact: true })).toBeVisible(); await captureBoth(page, "cleanup");
    complete(); await page.getByRole("button", { name: en.auth.deletionRefresh }).click();
    await expect(page.getByText(en.auth.deletionCompleted, { exact: true })).toBeVisible();
    await expect(page.getByText(en.auth.deletionCompletedAccount, { exact: true })).toBeVisible(); await assertBlocked(page);
    await expect(page.getByText(fixture.email, { exact: true })).toHaveCount(0); await captureBoth(page, "completed");
    assert.equal(fixture.deletes.length, 1); await page.reload();
    await expect(page.getByText(en.auth.deletionCompleted, { exact: true })).toBeVisible();
    await page.getByRole("button", { name: en.auth.signOut, exact: true }).click(); await page.waitForURL("**/login");
    assert.deepEqual(fixture.authActions, ["logout"]);
  });
  await run("malformed DELETE responses recover only through GET status without another mutation", async () => {
    reset({ behavior: "unknown" }); const page = await open(); await page.goto(`${site}/account?return_to=${encodeURIComponent("/jobs/legacy-guest-task")}`); await (await confirm(page)).click();
    await expect(page.getByText(en.auth.deletionUnknown, { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: en.auth.deletionRefresh })).toBeEnabled(); await assertBlocked(page); await captureBoth(page, "unknown-response");
    fixture.statusUnavailable = false; fixture.deletion = { ...fixture.deletion, status: "retry", phase: "cleanup", error_code: "CLEANUP_UNAVAILABLE" };
    await page.getByRole("button", { name: en.auth.deletionRefresh }).click(); await expect(page.getByText(en.auth.deletionRetryCleanup, { exact: true })).toBeVisible();
    complete(); await page.getByRole("button", { name: en.auth.deletionRefresh }).click(); await expect(page.getByText(en.auth.deletionCompleted, { exact: true })).toBeVisible();
    assert.equal(fixture.deletes.length, 1);
  });
  await run("completed creation responses cannot bypass the separate status query", async () => {
    reset({ behavior: "completed-create" }); const page = await open(); await page.goto(`${site}/account`); await (await confirm(page)).click();
    await expect(page.getByText(en.auth.deletionBilling, { exact: true })).toBeVisible();
    await expect(page.getByText(en.auth.deletionCompleted, { exact: true })).toHaveCount(0); assert.equal(fixture.deletes.length, 1);
  });
  await run("reauthentication logs out and returns to the localized account for fresh confirmation", async () => {
    reset({ behavior: "reauth" }); const page = await open(); await page.goto(`${site}/zh/account`); await (await confirm(page, zh)).click();
    await expect(page.getByText(zh.auth.deletionReauth, { exact: true })).toBeVisible(); await expect(page.getByRole("checkbox")).not.toBeChecked();
    await captureBoth(page, "reauth-required"); await page.getByRole("button", { name: zh.auth.deletionReauthAction, exact: true }).click();
    await page.waitForURL("**/zh/login?return_to=%2Fzh%2Faccount"); assert.deepEqual(fixture.authActions, ["logout"]);
    assert.equal(new URL(page.url()).searchParams.get("return_to"), "/zh/account");
    fixture.signedIn = true; fixture.behavior = "pending"; await page.goto(`${site}/zh/account`);
    await page.getByRole("button", { name: zh.auth.deletionAction, exact: true }).click();
    await expect(page.getByRole("checkbox")).not.toBeChecked(); await expect(page.getByRole("button", { name: zh.auth.deletionSubmit })).toBeDisabled();
    await page.getByRole("checkbox").check(); await page.getByRole("button", { name: zh.auth.deletionSubmit }).click();
    await expect(page.getByText(zh.auth.deletionBilling, { exact: true })).toBeVisible(); assert.equal(fixture.deletes.length, 2);
  });
  await run("changed cookie identity discards old confirmation before any deletion request", async () => {
    reset(); const page = await open(); await page.goto(`${site}/account`); const submit = await confirm(page);
    fixture.owner = randomUUID(); fixture.email = "new-account@example.test"; await submit.click();
    await expect(page.getByText(fixture.email, { exact: true })).toBeVisible(); await expect(page.getByRole("checkbox")).toHaveCount(0);
    assert.equal(fixture.deletes.length, 0); await page.getByRole("button", { name: en.auth.deletionAction, exact: true }).click();
    await expect(page.getByRole("checkbox")).not.toBeChecked();
  });
  assert.deepEqual(external, [], "no external auth or billing providers may be contacted");
  if (failures.length) throw new Error(failures.join("\n\n"));
  const report = { status: "passed", scope: "real_browser_frontend_against_local_protocol_doubles", real_provider_verified: false,
    real_cancellation_verified: false, real_data_cleanup_verified: false, checks, externalRequests: external.length, requestCount: requests.length, screenshots: output };
  writeFileSync(path.join(output, "report.json"), JSON.stringify(report, null, 2)); console.log(JSON.stringify(report));
} catch (error) {
  console.error(error.stack ?? error); console.error(logs); process.exitCode = 1;
  writeFileSync(path.join(output, "failure.json"), JSON.stringify({ status: "failed", checks, failures, logs }, null, 2));
} finally {
  for (const context of contexts) await context.close(); await browser?.close();
  if (child && child.exitCode === null) {
    try { process.kill(-child.pid, "SIGTERM"); } catch { /* already stopped */ }
    await Promise.race([new Promise((resolve) => child.once("exit", resolve)), new Promise((resolve) => setTimeout(resolve, 5000))]);
    if (child.exitCode === null) { try { process.kill(-child.pid, "SIGKILL"); } catch { /* already stopped */ } }
  }
  await new Promise((resolve) => api.close(resolve));
  if (existsSync(nextEnvPath) && readFileSync(nextEnvPath, "utf8").includes(`.next/${id}/`)) {
    if (nextEnvBefore === null) rmSync(nextEnvPath); else writeFileSync(nextEnvPath, nextEnvBefore);
  }
  rmSync(configDir, { recursive: true, force: true }); rmSync(dist, { recursive: true, force: true }); rmSync(temp, { recursive: true, force: true });
}
