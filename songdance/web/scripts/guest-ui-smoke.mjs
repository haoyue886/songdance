// Real browser audio + HTTP transport against offline protocol doubles.
// Python ledger, IP enforcement, external auth, and transcription models are not exercised.
import assert from "node:assert/strict";
import { randomBytes, randomUUID } from "node:crypto";
import { existsSync, mkdtempSync, mkdirSync, readFileSync, writeFileSync, rmSync } from "node:fs";
import { createServer } from "node:http";
import { tmpdir } from "node:os";
import path from "node:path";
import { spawn } from "node:child_process";
import { chromium, expect } from "@playwright/test";

const root = process.cwd();
const temp = mkdtempSync(path.join(tmpdir(), "songdance-guest-ui-"));
const id = path.basename(temp);
const dist = path.join(root, ".next", id);
const configDir = path.join(root, ".next", `${id}-config`);
const output = path.join(root, "test-results", id);
const nextEnvPath = path.join(root, "next-env.d.ts");
const nextEnvBefore = existsSync(nextEnvPath) ? readFileSync(nextEnvPath, "utf8") : null;
mkdirSync(configDir, { recursive: true });
mkdirSync(output, { recursive: true });
writeFileSync(path.join(configDir, "tsconfig.json"), JSON.stringify({ extends: "../../tsconfig.json" }));
const messages = JSON.parse(readFileSync(path.join(root, "messages/en.json"), "utf8"));
const config = {
  usage_enabled: true, guest_usage_enabled: true, checkout_enabled: false, mode: "test",
  pro: { price_minor: 990, currency: "USD", seconds: 1800, max_clip_seconds: 90, min_charge_seconds: 15 },
  free: { monthly_jobs: 1, max_clip_seconds: 90 }, guest: { max_clip_seconds: 30 }, retention_hours: 24, support_email: null,
};
const external = [], failures = [], checks = [], requests = [];
const contexts = new Set();
let fixture, site, apiOrigin, child, browser;
let logs = "";
const listen = (server) => new Promise((resolve, reject) => { server.once("error", reject); server.listen(0, "127.0.0.1", resolve); });
function reset(overrides = {}) {
  fixture = { token: `v1.${randomBytes(32).toString("hex")}.${randomBytes(32).toString("hex")}`, remaining: 1,
    reserved: 0, used: 0, sessions: [], creates: [], behavior: "daily", signedIn: false,
    owner: randomUUID(), jobId: randomUUID().replaceAll("-", ""), ...overrides };
  return fixture;
}
function wav() {
  const rate = 44100, frames = rate * 4;
  const bytes = Buffer.alloc(44 + frames * 2);
  bytes.write("RIFF", 0); bytes.writeUInt32LE(bytes.length - 8, 4); bytes.write("WAVEfmt ", 8);
  bytes.writeUInt32LE(16, 16); bytes.writeUInt16LE(1, 20); bytes.writeUInt16LE(1, 22);
  bytes.writeUInt32LE(rate, 24); bytes.writeUInt32LE(rate * 2, 28);
  bytes.writeUInt16LE(2, 32); bytes.writeUInt16LE(16, 34); bytes.write("data", 36); bytes.writeUInt32LE(frames * 2, 40);
  for (let index = 0; index < frames; index++) bytes.writeInt16LE(Math.round(9000 * Math.sin(2 * Math.PI * 440 * index / rate)), 44 + index * 2);
  return bytes;
}
function job() {
  return { id: fixture.jobId, access_type: "guest", guest_access_token: "local-job-capability", status: "queued", stage: "queued",
    source_type: "upload", start_sec: 0, end_sec: 4, attempt_count: 1, error_code: null, error_message: null,
    created_at: new Date().toISOString(), updated_at: new Date().toISOString(), expires_at: new Date(Date.now() + 86400000).toISOString(),
    result: null, quality_report: null, artifacts: [] };
}
const api = createServer(async (req, res) => {
  try {
    const pathname = new URL(req.url, apiOrigin ?? "http://localhost").pathname;
    res.setHeader("Access-Control-Allow-Origin", site ?? "http://localhost");
    res.setHeader("Access-Control-Allow-Headers", "authorization, content-type, idempotency-key, x-job-access, x-visitor-token");
    res.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
    if (req.method === "OPTIONS") { res.writeHead(204).end(); return; }
    const json = (value, status = 200) => res.writeHead(status, { "Content-Type": "application/json", "Cache-Control": "no-store" }).end(JSON.stringify(value));
    const chunks = []; for await (const chunk of req) chunks.push(chunk);
    const body = Buffer.concat(chunks);
    requests.push({ pathname, method: req.method });
    if (pathname === "/billing/config") { json(config); return; }
    if (pathname === "/youtube/config") { json({ enabled: false }); return; }
    if (pathname.startsWith("/events")) { json({}); return; }
    if (pathname === "/guest/session") {
      fixture.sessions.push(req.headers["x-visitor-token"] ?? null);
      const token = req.headers["x-visitor-token"];
      if (token) assert.equal(token, fixture.token, "refresh must reuse the signed visitor identity");
      json({ visitor_token: fixture.token, remaining: fixture.remaining, reserved: fixture.reserved, used: fixture.used, max_clip_seconds: 30 }); return;
    }
    if (pathname === "/jobs" && req.method === "POST") {
      assert.equal(req.headers["x-visitor-token"], fixture.token, "anonymous create must carry the signature");
      assert.equal(req.headers.authorization, undefined);
      const form = await new Response(body, { headers: { "Content-Type": req.headers["content-type"] } }).formData();
      const audio = form.get("audio_file");
      assert.ok(audio && typeof audio.arrayBuffer === "function");
      const key = req.headers["idempotency-key"];
      assert.match(key ?? "", /^[A-Za-z0-9_-]{8,128}$/);
      fixture.creates.push({ key, token: req.headers["x-visitor-token"], bytes: Buffer.from(await audio.arrayBuffer()).toString("base64") });
      if (fixture.behavior === "daily") { json({ detail: { code: "GUEST_DAILY_LIMIT" } }, 429); return; }
      if (fixture.creates.length === 1) {
        fixture.remaining = 0; fixture.reserved = 1;
        json({ detail: { code: "SUBMISSION_UNAVAILABLE" } }, 503); return;
      }
      assert.deepEqual(fixture.creates[1], fixture.creates[0], "replay must preserve identity, key, and bytes");
      json(job(), 201); return;
    }
    if (pathname === `/jobs/${fixture?.jobId}`) { json(job()); return; }
    if (pathname === "/me" && fixture?.signedIn) { json({ id: fixture.owner, email: "guest-summary@example.test" }); return; }
    if (pathname === "/billing/me" && fixture?.signedIn) {
      assert.equal(req.headers.authorization, "Bearer local-owner-token");
      json({ owner_id: fixture.owner, enabled: true, plan: "free", unit: "jobs", state: "active", sync_state: "ready",
        limit: 1, remaining: 0, used: 1, reserved: 0, max_clip_seconds: 90,
        period_start: "2026-10-01T00:00:00Z", period_end: "2026-11-01T00:00:00Z",
        task_summary: { succeeded: 1, failed: 2, in_progress: 0 } }); return;
    }
    json({ detail: { code: "AUTH_REQUIRED" } }, 401);
  } catch (error) { failures.push(`API double: ${error.stack ?? error}`); if (!res.headersSent) res.writeHead(500); res.end(); }
});
async function open() {
  const context = await browser.newContext({ viewport: { width: 1280, height: 1000 }, serviceWorkers: "block" });
  contexts.add(context);
  await context.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.origin === site && url.pathname === "/api/auth/access-token") {
      await route.fulfill({ status: fixture.signedIn ? 200 : 401, contentType: "application/json", body: JSON.stringify(fixture.signedIn
        ? { access_token: "local-owner-token", expires_at: Math.floor(Date.now() / 1000) + 3600, user: { id: fixture.owner, email: "guest-summary@example.test" } }
        : { signed_out: true }) });
    } else if (url.protocol.startsWith("http") && ![site, apiOrigin].includes(url.origin)) { external.push(url.href); await route.abort(); }
    else await route.continue();
  });
  const page = await context.newPage(); page.setDefaultTimeout(15000);
  page.on("pageerror", (error) => failures.push(`Browser: ${error.message}`));
  return page;
}
async function capture(page, name) {
  await page.evaluate(() => document.fonts.ready);
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `${name}: no horizontal overflow`);
  await page.screenshot({ path: path.join(output, `${name}.png`), fullPage: true, animations: "disabled", style: "nextjs-portal { display: none !important; }" });
}
async function captureBoth(page, name) {
  await capture(page, `${name}-desktop`);
  await page.setViewportSize({ width: 375, height: 812 }); await capture(page, `${name}-mobile`);
}
async function selectAudio(page) {
  await page.getByLabel(messages.audio.chooseLabel).setInputFiles({ name: "piano.wav", mimeType: "audio/wav", buffer: wav() });
  await expect(page.getByRole("button", { name: messages.audio.playSelection, exact: true })).toBeEnabled();
  await page.getByRole("checkbox").check();
}
const createButton = (page) => page.getByRole("button", { name: messages.transcribe.create, exact: true });
const trialNotice = (count) => messages.billing.guestTrial.replace("{count}", String(count));
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
  const probe = createServer(); await listen(probe); const port = probe.address().port; await new Promise((resolve) => probe.close(resolve));
  site = `http://127.0.0.1:${port}`;
  child = spawn(process.execPath, ["node_modules/next/dist/bin/next", "dev", "--webpack", "--hostname", "127.0.0.1", "-p", String(port)], {
    cwd: root, detached: true, stdio: ["ignore", "pipe", "pipe"], env: { ...process.env,
      NODE_ENV: "development", NEXT_TELEMETRY_DISABLED: "1", NEXT_PUBLIC_AUTH_ENABLED: "true", SONGDANCE_AUTH_ENABLED: "true",
      NEXT_PUBLIC_SITE_URL: site, NEXT_PUBLIC_API_URL: apiOrigin, SONGDANCE_AUTH_API_URL: apiOrigin,
      SONGDANCE_SUPABASE_URL: apiOrigin, SONGDANCE_SUPABASE_PUBLISHABLE_KEY: "sb_publishable_guest_protocol_double",
      SONGDANCE_AUTH_BRIDGE_SECRET: "local-guest-browser-protocol-double-only",
      SONGDANCE_NEXT_DIST_DIR: path.relative(root, dist), SONGDANCE_TSCONFIG_PATH: path.relative(root, path.join(configDir, "tsconfig.json")),
    },
  });
  for (const stream of [child.stdout, child.stderr]) stream.on("data", (data) => { logs = (logs + data).slice(-20000); });
  let ready = false;
  for (let attempt = 0; attempt < 90; attempt++) {
    if (child.exitCode !== null) throw new Error("Next.js exited before readiness");
    try { if ((await fetch(`${site}/transcribe`, { signal: AbortSignal.timeout(3000) })).ok) { ready = true; break; } } catch { /* startup */ }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  assert.ok(ready, "Next.js readiness timeout");
  browser = await chromium.launch({ headless: true, executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH ?? (process.platform === "darwin" ? "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" : undefined) });
  await run("available guest signature survives reload and reaches job admission; daily rejection is localized", async () => {
    reset(); const page = await open(); await page.goto(`${site}/transcribe`); await selectAudio(page);
    await expect(page.getByText(trialNotice(1), { exact: true })).toBeVisible();
    await expect(page.getByText(messages.audio.trimHelp.replace("{seconds}", "30"), { exact: true })).toBeVisible();
    await expect(createButton(page)).toBeEnabled(); await captureBoth(page, "guest-available");
    assert.equal(await page.evaluate(() => localStorage.getItem("songdance-visitor-v1")), fixture.token);
    await page.reload(); await selectAudio(page); await expect(createButton(page)).toBeEnabled();
    assert.ok(fixture.sessions.includes(fixture.token), "reload reuses the saved signed identity");
    await createButton(page).click();
    await expect(page.getByText(messages.errors.guestDaily, { exact: true })).toBeVisible();
    assert.equal(fixture.creates.length, 1);
    await page.setViewportSize({ width: 1280, height: 1000 }); await captureBoth(page, "guest-daily-refusal");
  });
  await run("used visitor allowance disables new task without issuing a POST", async () => {
    reset({ remaining: 0, used: 1 }); const page = await open(); await page.goto(`${site}/transcribe`); await selectAudio(page);
    await expect(page.getByText(trialNotice(0), { exact: true })).toBeVisible();
    await expect(createButton(page)).toBeDisabled(); assert.equal(fixture.creates.length, 0);
    await captureBoth(page, "guest-exhausted");
  });
  await run("unknown submission can replay unchanged despite visitor reservation", async () => {
    reset({ behavior: "unknown" }); const page = await open(); await page.goto(`${site}/transcribe`); await selectAudio(page);
    await expect(createButton(page)).toBeEnabled(); await createButton(page).click();
    await expect(page.getByText(messages.transcribe.createFailed, { exact: true })).toBeVisible();
    await expect(page.getByText(trialNotice(0), { exact: true })).toBeVisible(); await expect(createButton(page)).toBeEnabled();
    await captureBoth(page, "guest-unknown-replay");
    await createButton(page).click(); await page.waitForURL(`**/jobs/${fixture.jobId}`);
    await expect(page.getByRole("heading", { name: messages.job.stageQueued, exact: true })).toBeVisible();
    assert.equal(fixture.creates.length, 2);
  });
  await run("changed clip cannot reuse the unknown-submission quota exception", async () => {
    reset({ behavior: "unknown" }); const page = await open(); await page.goto(`${site}/transcribe`); await selectAudio(page);
    await expect(createButton(page)).toBeEnabled(); await createButton(page).click();
    await expect(page.getByText(trialNotice(0), { exact: true })).toBeVisible();
    await page.getByRole("spinbutton", { name: new RegExp(`^${messages.audio.endTime}`) }).fill("3");
    await expect(createButton(page)).toBeDisabled(); assert.equal(fixture.creates.length, 1);
  });
  await run("Free account shows one monthly allowance and persisted task summary", async () => {
    reset({ signedIn: true }); const page = await open(); await page.goto(`${site}/account`);
    const summary = page.getByRole("region", { name: messages.billing.taskSummary });
    await expect(summary).toBeVisible();
    for (const [label, value] of [[messages.billing.tasksSucceeded, "1"], [messages.billing.tasksFailed, "2"], [messages.billing.tasksInProgress, "0"]]) {
      await expect(summary.locator("div").filter({ has: page.getByText(label, { exact: true }) }).locator("dd")).toHaveText(value);
    }
    await expect(page.getByText(messages.billing.freeRules.replace("{count}", "1").replace("{seconds}", "90"), { exact: true })).toBeVisible();
    assert.equal(fixture.sessions.length, 0, "account must not mint a guest identity");
    await captureBoth(page, "account-task-summary");
  });
  assert.deepEqual(external, [], "no external providers should be contacted");
  if (failures.length) throw new Error(failures.join("\n\n"));
  const report = { status: "passed", scope: "real_browser_frontend_against_local_protocol_doubles", real_backend_verified: false,
    real_ip_enforcement_verified: false, checks, externalRequests: external.length, requestCount: requests.length, screenshots: output };
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
