// Real browser audio decoding/clipping and HTTP requests against offline protocol doubles.
// This does not exercise the Python queue, billing ledger, suppliers, or transcription models.
import assert from "node:assert/strict";
import { createHash, randomUUID } from "node:crypto";
import { existsSync, mkdtempSync, mkdirSync, readFileSync, writeFileSync, rmSync } from "node:fs";
import { createServer } from "node:http";
import { tmpdir } from "node:os";
import path from "node:path";
import { spawn } from "node:child_process";
import { chromium, expect } from "@playwright/test";

const root = process.cwd();
const temp = mkdtempSync(path.join(tmpdir(), "songdance-submission-ui-"));
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
  usage_enabled: true, checkout_enabled: false, mode: "test",
  pro: { price_minor: 990, currency: "USD", seconds: 1800, max_clip_seconds: 90, min_charge_seconds: 15 },
  free: { monthly_jobs: 1, max_clip_seconds: 90 }, guest: { max_clip_seconds: 30 },
  retention_hours: 24, support_email: null,
};
const requests = [];
const external = [];
const failures = [];
const checks = [];
const contexts = new Set();
const owners = new Map();
let site;
let apiOrigin;
let child;
let browser;
let logs = "";
let currentCheck = "startup";
const listen = (server) => new Promise((resolve, reject) => { server.once("error", reject); server.listen(0, "127.0.0.1", resolve); });

function wav(frequency = 440) {
  const rate = 44100;
  const frames = rate * 4;
  const bytes = Buffer.alloc(44 + frames * 2);
  bytes.write("RIFF", 0); bytes.writeUInt32LE(bytes.length - 8, 4); bytes.write("WAVEfmt ", 8);
  bytes.writeUInt32LE(16, 16); bytes.writeUInt16LE(1, 20); bytes.writeUInt16LE(1, 22);
  bytes.writeUInt32LE(rate, 24); bytes.writeUInt32LE(rate * 2, 28);
  bytes.writeUInt16LE(2, 32); bytes.writeUInt16LE(16, 34); bytes.write("data", 36);
  bytes.writeUInt32LE(frames * 2, 40);
  for (let index = 0; index < frames; index++) bytes.writeInt16LE(Math.round(9000 * Math.sin(2 * Math.PI * frequency * index / rate)), 44 + index * 2);
  return bytes;
}
function fixture(failure = "503") {
  const owner = { token: randomUUID(), id: randomUUID(), jobId: randomUUID().replaceAll("-", ""), failure,
    remaining: 1, reserved: 0, creates: [], retries: [], queued: false, retryScenario: false };
  owners.set(owner.token, owner);
  return owner;
}
function job(owner, status = "queued") {
  const now = new Date().toISOString();
  return { id: owner.jobId, access_type: "owned", status, stage: status === "failed" ? "transcribing" : "queued",
    source_type: "upload", start_sec: 0, end_sec: 4, attempt_count: owner.queued ? 2 : 1,
    error_code: status === "failed" ? "TRANSCRIPTION_FAILED" : null, error_message: null,
    created_at: now, updated_at: now, expires_at: new Date(Date.now() + 86400000).toISOString(),
    result: null, quality_report: null, artifacts: [] };
}
const api = createServer(async (req, res) => {
  try {
    const pathname = new URL(req.url, apiOrigin ?? "http://localhost").pathname;
    res.setHeader("Access-Control-Allow-Origin", site ?? "http://localhost");
    res.setHeader("Access-Control-Allow-Headers", "authorization, content-type, idempotency-key, x-job-access");
    res.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
    if (req.method === "OPTIONS") { res.writeHead(204).end(); return; }
    const json = (data, status = 200) => res.writeHead(status, { "Content-Type": "application/json", "Cache-Control": "no-store" }).end(JSON.stringify(data));
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    const body = Buffer.concat(chunks);
    const owner = owners.get(req.headers.authorization?.replace(/^Bearer /, ""));
    requests.push({ pathname, method: req.method, owner: owner?.id ?? null });
    if (pathname === "/billing/config") { json(config); return; }
    if (pathname === "/youtube/config") { json({ enabled: false }); return; }
    if (!owner) { json({ detail: { code: "AUTH_REQUIRED" } }, 401); return; }
    if (pathname === "/me") { json({ id: owner.id, email: "submission@example.test" }); return; }
    if (pathname === "/billing/me") {
      json({ owner_id: owner.id, enabled: true, plan: "free", unit: "jobs", state: "active", sync_state: "ready",
        limit: 1, remaining: owner.remaining, used: 0, reserved: owner.reserved, max_clip_seconds: 90,
        period_start: "2026-10-01T00:00:00Z", period_end: "2026-11-01T00:00:00Z" }); return;
    }
    if (pathname.startsWith("/events")) { res.writeHead(202).end(); return; }
    if (pathname === "/jobs" && req.method === "POST") {
      const key = req.headers["idempotency-key"];
      assert.match(key ?? "", /^[A-Za-z0-9_-]{8,128}$/);
      const form = await new Response(body, { headers: { "Content-Type": req.headers["content-type"] } }).formData();
      const file = form.get("audio_file");
      assert.ok(file && typeof file.arrayBuffer === "function", "multipart must contain actual clipped file");
      const bytes = Buffer.from(await file.arrayBuffer());
      const upload = { key, filename: file.name, sha256: createHash("sha256").update(bytes).digest("hex"),
        bytes: bytes.length, start: form.get("start_sec"), end: form.get("end_sec"), rights: form.get("rights_confirmed") };
      assert.equal(bytes.toString("ascii", 0, 4), "RIFF");
      assert.equal(upload.start, "0"); assert.equal(upload.end, "4"); assert.equal(upload.rights, "true");
      owner.creates.push(upload);
      if (owner.creates.length === 1) {
        owner.remaining = 0; owner.reserved = 1;
        if (owner.failure === "network") { json(job(owner), 201); return; }
        json({ detail: { code: "SUBMISSION_UNAVAILABLE", message: "Local response loss protocol double" } }, 503); return;
      }
      assert.deepEqual(upload, owner.creates[0], "replay must preserve key, filename, clipped bytes, and clip contract");
      json(job(owner), 201); return;
    }
    if (pathname === `/jobs/${owner.jobId}/retry` && req.method === "POST") {
      const key = req.headers["idempotency-key"];
      assert.match(key ?? "", /^[A-Za-z0-9_-]{8,128}$/);
      owner.retries.push(key);
      if (owner.retries.length === 1) { res.writeHead(200).end(); return; }
      assert.equal(key, owner.retries[0], "empty success response must keep the retry identity");
      owner.queued = true; json(job(owner)); return;
    }
    if (pathname === `/jobs/${owner.jobId}`) { json(job(owner, owner.retryScenario && !owner.queued ? "failed" : "queued")); return; }
    json({}, 404);
  } catch (error) { failures.push(`API double: ${error.stack ?? error}`); if (!res.headersSent) res.writeHead(500); res.end(); }
});

async function open(owner) {
  const context = await browser.newContext({ viewport: { width: 1280, height: 1000 }, serviceWorkers: "block" });
  contexts.add(context);
  let dropFirstAcceptedResponse = owner.failure === "network";
  await context.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.origin === site && url.pathname === "/api/auth/access-token") {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify({ access_token: owner.token,
        expires_at: Math.floor(Date.now() / 1000) + 3600, user: { id: owner.id, email: "submission@example.test" } }) });
    } else if (url.origin === apiOrigin && url.pathname === "/jobs" && route.request().method() === "POST" && dropFirstAcceptedResponse) {
      dropFirstAcceptedResponse = false;
      // Let the server accept the task, then deterministically lose the response.
      // Closing a TCP socket alone lets Chromium transparently resend the request.
      await route.fetch();
      await route.abort("failed");
    } else if (url.protocol.startsWith("http") && ![site, apiOrigin].includes(url.origin)) {
      external.push(url.href); await route.abort();
    } else await route.continue();
  });
  const page = await context.newPage();
  page.setDefaultTimeout(15000);
  page.on("pageerror", (error) => failures.push(`Browser: ${error.message}`));
  return page;
}
async function capture(page, name) {
  await page.evaluate(() => document.fonts.ready);
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `${name}: no horizontal overflow`);
  await page.screenshot({ path: path.join(output, `${name}.png`), fullPage: true, animations: "disabled",
    style: "nextjs-portal { display: none !important; }" });
}
async function uploadAndFail(owner) {
  const page = await open(owner);
  const response = await page.goto(`${site}/transcribe`);
  assert.equal(response.status(), 200);
  await page.getByLabel(messages.audio.chooseLabel).setInputFiles({ name: "piano.wav", mimeType: "audio/wav", buffer: wav() });
  await expect(page.getByRole("button", { name: messages.audio.playSelection, exact: true })).toBeEnabled();
  await page.getByRole("checkbox").check();
  const create = page.getByRole("button", { name: messages.transcribe.create, exact: true });
  await expect(create).toBeEnabled();
  await create.click();
  await expect(page.getByText(messages.transcribe.createFailed, { exact: true })).toBeVisible();
  await expect(page.getByText(messages.billing.remainingJobs.replace("{count}", "0"), { exact: true })).toBeVisible();
  await expect(create).toBeEnabled();
  assert.equal(owner.creates.length, 1);
  assert.equal(owner.reserved, 1);
  await capture(page, `${owner.failure}-same-draft-retry-enabled`);
  return page;
}
async function run(name, work) {
  currentCheck = name;
  try { await work(); checks.push(name); console.log(`PASS ${name}`); }
  catch (error) {
    failures.push(`${name}: ${error.stack ?? error}`);
    for (const context of contexts) for (const page of context.pages()) await capture(page, `failure-${checks.length}-${randomUUID()}`).catch(() => {});
    console.error(`FAIL ${name}: ${error.message}`);
  } finally { for (const context of contexts) { await context.close(); contexts.delete(context); } }
}

try {
  await listen(api);
  apiOrigin = `http://127.0.0.1:${api.address().port}`;
  const probe = createServer(); await listen(probe);
  const port = probe.address().port; await new Promise((resolve) => probe.close(resolve));
  site = `http://127.0.0.1:${port}`;
  child = spawn(process.execPath, ["node_modules/next/dist/bin/next", "dev", "--webpack", "--hostname", "127.0.0.1", "-p", String(port)], {
    cwd: root, detached: true, stdio: ["ignore", "pipe", "pipe"], env: { ...process.env,
      NODE_ENV: "development", NEXT_PUBLIC_AUTH_ENABLED: "true", SONGDANCE_AUTH_ENABLED: "true",
      NEXT_PUBLIC_SITE_URL: site, NEXT_PUBLIC_API_URL: apiOrigin, SONGDANCE_AUTH_API_URL: apiOrigin,
      SONGDANCE_SUPABASE_URL: apiOrigin, SONGDANCE_SUPABASE_PUBLISHABLE_KEY: "sb_publishable_submission_protocol_double",
      SONGDANCE_AUTH_BRIDGE_SECRET: "local-submission-browser-protocol-double-only",
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

  for (const failure of ["503", "network"]) await run(`${failure}: replay preserves identity and bytes after quota reservation`, async () => {
    const owner = fixture(failure);
    const page = await uploadAndFail(owner);
    await page.getByRole("button", { name: messages.transcribe.create, exact: true }).click();
    await page.waitForURL(`**/jobs/${owner.jobId}`);
    await expect(page.getByRole("heading", { name: messages.job.stageQueued, exact: true })).toBeVisible();
    assert.equal(owner.creates.length, 2);
    assert.deepEqual(owner.creates[1], owner.creates[0]);
    await capture(page, `${failure}-same-job-recovered`);
  });
  for (const change of ["clip", "file"]) await run(`changed ${change} cannot reuse quota exception`, async () => {
    const owner = fixture();
    const page = await uploadAndFail(owner);
    if (change === "clip") await page.getByRole("spinbutton", { name: new RegExp(`^${messages.audio.endTime}`) }).fill("3");
    else {
      await page.getByLabel(messages.audio.chooseLabel).setInputFiles({ name: "other.wav", mimeType: "audio/wav", buffer: wav(660) });
      await expect(page.getByRole("button", { name: messages.audio.playSelection, exact: true })).toBeEnabled();
      await page.getByRole("checkbox").check();
    }
    await expect(page.getByRole("button", { name: messages.transcribe.create, exact: true })).toBeDisabled();
    await expect(page.getByText(messages.billing.balanceEmpty, { exact: true })).toBeVisible();
    assert.equal(owner.creates.length, 1, "changed draft must not issue another create request");
    await capture(page, `changed-${change}-quota-blocked-desktop`);
    await page.setViewportSize({ width: 375, height: 812 });
    await capture(page, `changed-${change}-quota-blocked-mobile`);
  });
  await run("empty retry 200 retains identity through reload and subsequent retry", async () => {
    const owner = fixture(); owner.retryScenario = true;
    const page = await open(owner);
    await page.goto(`${site}/jobs/${owner.jobId}`);
    await page.getByRole("button", { name: messages.job.retry, exact: true }).click();
    await expect(page.getByRole("heading", { name: messages.job.readFailedTitle, exact: true })).toBeVisible();
    await capture(page, "retry-empty-success-recoverable");
    assert.equal(await page.evaluate((jobId) => sessionStorage.getItem(`songdance-retry-key:${jobId}`), owner.jobId), owner.retries[0]);
    await page.reload();
    await page.getByRole("button", { name: messages.job.retry, exact: true }).click();
    await expect(page.getByRole("heading", { name: messages.job.stageQueued, exact: true })).toBeVisible();
    assert.equal(owner.retries.length, 2); assert.equal(owner.retries[0], owner.retries[1]);
    assert.equal(await page.evaluate((jobId) => sessionStorage.getItem(`songdance-retry-key:${jobId}`), owner.jobId), null);
    await capture(page, "retry-empty-success-recovered");
  });
  assert.deepEqual(external, [], "no external providers should be contacted");
  if (failures.length) throw new Error(failures.join("\n\n"));
  const report = { status: "passed", scope: "real_browser_audio_and_frontend_transport_against_local_protocol_doubles",
    real_backend_verified: false, real_models_verified: false, checks, externalRequests: external.length,
    submissions: [...owners.values()].map(({ id: owner, creates, retries }) => ({ owner, creates, retries })), screenshots: output };
  writeFileSync(path.join(output, "report.json"), JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report));
} catch (error) {
  console.error(`Submission UI smoke failed during ${currentCheck}: ${error.stack ?? error}`);
  console.error(logs); process.exitCode = 1;
  writeFileSync(path.join(output, "failure.json"), JSON.stringify({ status: "failed", checks, failures, logs }, null, 2));
} finally {
  for (const context of contexts) await context.close();
  await browser?.close();
  if (child && child.exitCode === null) {
    try { process.kill(-child.pid, "SIGTERM"); } catch { /* already stopped */ }
    await Promise.race([new Promise((resolve) => child.once("exit", resolve)), new Promise((resolve) => setTimeout(resolve, 5000))]);
    if (child.exitCode === null) { try { process.kill(-child.pid, "SIGKILL"); } catch { /* already stopped */ } }
  }
  await new Promise((resolve) => api.close(resolve));
  // Restore only this run's generated reference; preserve changes made by another server.
  if (existsSync(nextEnvPath) && readFileSync(nextEnvPath, "utf8").includes(`.next/${id}/`)) {
    if (nextEnvBefore === null) rmSync(nextEnvPath); else writeFileSync(nextEnvPath, nextEnvBefore);
  }
  rmSync(configDir, { recursive: true, force: true });
  rmSync(dist, { recursive: true, force: true });
  rmSync(temp, { recursive: true, force: true });
}
