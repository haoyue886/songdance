// Real browser/BFF/API/ledger/RQ/model journey against disposable local services.
// Only external provider protocols are local doubles; no business API body is mocked.
import assert from "node:assert/strict";
import { randomBytes, createHash } from "node:crypto";
import { existsSync, mkdtempSync, mkdirSync, readFileSync, writeFileSync, rmSync } from "node:fs";
import { createServer } from "node:http";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawn } from "node:child_process";
import { chromium, expect } from "@playwright/test";
import midiPackage from "@tonejs/midi";

const { Midi } = midiPackage;
const webRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const apiRoot = path.resolve(webRoot, "../api");
const python = process.env.SONGDANCE_COMMERCIAL_PYTHON ?? path.join(apiRoot, ".venv/bin/python");
const temp = mkdtempSync(path.join(tmpdir(), "songdance-commercial-e2e-"));
const id = path.basename(temp);
const dist = path.join(webRoot, ".next", id);
const configDir = path.join(webRoot, ".next", `${id}-config`);
const output = path.join(webRoot, "test-results", id);
const nextEnvPath = path.join(webRoot, "next-env.d.ts");
const nextEnvBefore = existsSync(nextEnvPath) ? readFileSync(nextEnvPath, "utf8") : null;
const controlSecret = randomBytes(32).toString("hex");
const bridgeSecret = randomBytes(32).toString("hex");
const en = JSON.parse(readFileSync(path.join(webRoot, "messages/en.json"), "utf8"));
const checks = [];
const evidence = [];
const requests = [];
const external = [];
const contexts = new Set();
const sensitive = new Set([controlSecret, bridgeSecret]);
const errors = [];
const interruption = new AbortController();
let apiOrigin, providerOrigin, controlPath, site, apiChild, webChild, browser;
let apiLogs = "", webLogs = "", currentStep = "startup";
let signalCleanup = Promise.resolve();
let lastState;

for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => {
  if (interruption.signal.aborted) return;
  interruption.abort(new Error(`Commercial journey interrupted by ${signal}`));
  process.exitCode = 1;
  signalCleanup = closeResources().catch((error) => errors.push(`signal cleanup: ${safe(error.message)}`));
});

mkdirSync(configDir, { recursive: true });
mkdirSync(output, { recursive: true });
writeFileSync(path.join(configDir, "tsconfig.json"), JSON.stringify({ extends: "../../tsconfig.json" }));

function safe(value) {
  let text = String(value);
  for (const secret of sensitive) text = text.replaceAll(secret, "[redacted]");
  return text.replace(/eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+/g, "[redacted-jwt]")
    .replace(/(Bearer\s+)[^\s"']+/gi, "$1[redacted]")
    .replace(/([?&](?:code|flow|token|refresh_token|signature)=)[^&\s"']+/g, "$1[redacted]");
}
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
async function bounded(promise, ms, label) {
  let timer;
  try {
    return await Promise.race([promise, new Promise((_, reject) => { timer = setTimeout(() => reject(new Error(`${label}: timed out after ${ms}ms`)), ms); })]);
  } finally { clearTimeout(timer); }
}
async function json(response, label) { return bounded(response.json(), 15000, label); }
async function port() {
  const probe = createServer();
  await new Promise((resolve, reject) => { probe.once("error", reject); probe.listen(0, "127.0.0.1", resolve); });
  const value = probe.address().port;
  await new Promise((resolve, reject) => probe.close((error) => error ? reject(error) : resolve()));
  assert.ok(![3000, 3001, 8000].includes(value), "existing development service ports are excluded");
  return value;
}
function trackChild(child, kind) {
  for (const stream of [child.stdout, child.stderr]) stream.on("data", (chunk) => {
    if (kind === "api") apiLogs = (apiLogs + safe(chunk)).slice(-24000);
    else webLogs = (webLogs + safe(chunk)).slice(-24000);
  });
  child.on("error", (error) => errors.push(`${kind} process: ${safe(error.message)}`));
}
async function stop(child) {
  if (!child || child.exitCode !== null || child.signalCode !== null) return;
  const exited = new Promise((resolve) => child.once("exit", resolve));
  try { process.kill(-child.pid, "SIGTERM"); } catch { /* This task's process already stopped. */ }
  await Promise.race([exited, sleep(10000)]);
  if (child.exitCode === null && child.signalCode === null) {
    try { process.kill(-child.pid, "SIGKILL"); } catch { /* Already stopped. */ }
    await Promise.race([exited, sleep(2000)]);
  }
  assert.ok(child.exitCode !== null || child.signalCode !== null, "owned child process must stop before removing its files");
}
async function closeResources() {
  if (browser) await bounded(browser.close().catch(() => {}), 15000, "browser shutdown").catch((error) => errors.push(safe(error.message)));
  for (const context of contexts) await bounded(context.close().catch(() => {}), 5000, "context shutdown").catch((error) => errors.push(safe(error.message)));
  await stop(webChild); await stop(apiChild);
}
async function verifyPrivateServicesStopped() {
  const manifestPath = path.join(temp, "resources.json");
  if (!existsSync(manifestPath)) {
    assert.ok(!existsSync(path.join(temp, "cluster/postmaster.pid")), "PostgreSQL must not be deleted without a cleanup manifest");
    return { stopped: true, manifest_present: false };
  }
  const child = spawn(python, ["-m", "tests.support.commercial_stack", "--cleanup-root", temp], {
    cwd: apiRoot, detached: true, stdio: ["ignore", "pipe", "pipe"], env: { ...process.env, PYTHONUNBUFFERED: "1" },
  });
  let logs = "";
  for (const stream of [child.stdout, child.stderr]) stream.on("data", (chunk) => { logs = (logs + safe(chunk)).slice(-8000); });
  let code;
  try {
    code = await bounded(new Promise((resolve, reject) => { child.once("error", reject); child.once("exit", resolve); }), 30000, "private-service cleanup verifier");
  } finally { await stop(child); }
  assert.equal(code, 0, `private-service cleanup failed: ${logs}`);
  assert.equal(JSON.parse(readFileSync(manifestPath, "utf8")).stopped, true);
  assert.equal(existsSync(path.join(temp, "cluster/postmaster.pid")), false);
  return { stopped: true, manifest_present: true };
}
function localOrigin(value) {
  const url = new URL(value);
  assert.equal(url.protocol, "http:");
  assert.equal(url.hostname, "127.0.0.1");
  assert.equal(url.origin, value);
  return value;
}
async function control(action, data = {}) {
  interruption.signal.throwIfAborted();
  const response = await fetch(`${apiOrigin}${controlPath}`, {
    method: "POST", headers: { Authorization: `Bearer ${controlSecret}`, "Content-Type": "application/json" },
    body: JSON.stringify({ action, ...data }), signal: AbortSignal.any([interruption.signal, AbortSignal.timeout(action === "transcription_worker" ? 300000 : 60000)]),
  });
  const body = await json(response, `local control ${action} body`);
  assert.ok(response.ok, `local control ${action} failed with HTTP ${response.status}: ${safe(JSON.stringify(body))}`);
  return body;
}
async function state() { lastState = await control("state"); return lastState; }
async function step(name, work) {
  interruption.signal.throwIfAborted();
  currentStep = name;
  const started = Date.now();
  console.log(`RUN ${name}`);
  try {
    const result = await bounded(work(), 360000, name);
    checks.push({ name, duration_ms: Date.now() - started });
    console.log(`PASS ${name}`);
    return result;
  } catch (error) {
    for (const context of contexts) for (const page of context.pages()) await capture(page, `failure-${checks.length}-${contexts.size}-${context.pages().indexOf(page)}`).catch(() => {});
    throw error;
  }
}
async function visit(page, pathname) {
  const [response] = await Promise.all([
    page.goto(`${site}${pathname}`),
    page.waitForResponse((reply) => reply.url() === `${site}/api/auth/access-token` && reply.request().method() === "POST"),
  ]);
  assert.equal(response?.status(), 200, `${pathname} must return HTTP 200`);
}
async function capture(page, name) {
  await bounded(page.evaluate(() => document.fonts.ready), 10000, `${name}: fonts`);
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `${name}: no horizontal overflow`);
  const filename = path.join(output, `${name}.png`);
  await page.screenshot({ path: filename, fullPage: true, animations: "disabled", style: "nextjs-portal { display: none !important; }" });
  evidence.push({ type: "screenshot", name, path: filename });
}
function hostedUrl(value, kind) {
  const url = new URL(value);
  assert.equal(url.protocol, "https:");
  assert.ok(["creem.io", "www.creem.io"].includes(url.hostname));
  assert.equal(url.port, "");
  assert.equal(url.search, "");
  assert.equal(url.hash, "");
  assert.match(url.pathname, kind === "checkout" ? /^\/test\/checkout\/ch_[A-Za-z0-9_-]+$/ : /^\/test\/portal\/[A-Za-z0-9_-]+$/);
  return url.href;
}
function hostedHtml(kind, actionUrl) {
  const command = kind === "checkout" ? "Confirm test payment" : "Cancel future renewal";
  return `<!doctype html><html lang="en"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Local Creem protocol page</title><body><main><h1>${kind === "checkout" ? "Test checkout" : "Test billing portal"}</h1><form method="post" action="${actionUrl}"><button type="submit">${command}</button></form></main></body></html>`;
}
async function open(name, viewport) {
  const context = await browser.newContext({ viewport, serviceWorkers: "block", acceptDownloads: true });
  contexts.add(context);
  const session = { name, context, email: `${name}@commercial.example.test`, hosted: new Map(), fault: null, token: null, ownerId: null };
  await context.route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (!session.hosted.has(url.href) && url.protocol === "https:" && ["creem.io", "www.creem.io"].includes(url.hostname)
      && request.method() === "GET" && /^\/test\/(checkout\/ch_|portal\/)[A-Za-z0-9_-]+$/.test(url.pathname)) {
      // Navigation may finish before Playwright can read an unloaded response body.
      // Resolve only this exact hosted target against the authenticated owner's DB rows.
      const snapshot = await bounded(state(), 5000, "hosted target ownership lookup");
      const providerId = url.pathname.split("/").at(-1);
      const kind = url.pathname.startsWith("/test/checkout/") ? "checkout" : "portal";
      const owned = kind === "checkout"
        ? rows(snapshot, "checkouts", session).some((row) => row.provider_id === providerId)
        : rows(snapshot, "subscriptions", session).some((row) => row.customer_id === providerId);
      if (owned) session.hosted.set(hostedUrl(url.href, kind), { kind, providerId });
    }
    if (session.hosted.has(url.href)) {
      const entry = session.hosted.get(url.href);
      if (request.method() === "GET") {
        await route.fulfill({ contentType: "text/html", body: hostedHtml(entry.kind, `${url.href}/submit`) });
        return;
      }
    }
    const entry = session.hosted.get(url.href.replace(/\/submit$/, ""));
    if (entry && url.href.endsWith("/submit") && request.method() === "POST") {
      let result;
      if (entry.kind === "checkout") {
        result = await control("complete_payment", { checkout_id: entry.providerId, deliver: false });
        session.subscriptionId = result.subscription_id;
      } else {
        result = await control("cancel_subscription", { subscription_id: session.subscriptionId, scheduled: true, deliver: true });
      }
      const target = entry.kind === "checkout" ? result.success_url : `${site}/account`;
      const destination = new URL(target);
      assert.equal(destination.origin, site, "hosted provider can return only to this local site");
      assert.equal(destination.pathname, entry.kind === "checkout" ? "/billing/return" : "/account");
      await route.fulfill({ status: 303, headers: { Location: destination.href }, body: "" });
      return;
    }
    if (url.protocol.startsWith("http") && ![site, apiOrigin, providerOrigin].includes(url.origin)) {
      external.push({ origin: url.origin, pathname: url.pathname });
      await route.abort("blockedbyclient");
      return;
    }
    if (url.origin === apiOrigin) {
      requests.push({ session: name, method: request.method(), path: url.pathname,
        key: request.headers()["idempotency-key"] ?? null });
      if (session.fault && request.method() === "POST" && url.pathname === session.fault) {
        session.fault = null;
        // Commit the real request first, then lose its response without fabricating a body.
        const committed = await route.fetch();
        assert.ok(committed.ok(), `response-loss setup must commit real ${url.pathname}`);
        if (url.pathname === "/billing/checkout") {
          const checkout = await json(committed, "committed checkout body");
          session.checkout = checkout;
          session.hosted.set(hostedUrl(checkout.checkout_url, "checkout"), { kind: "checkout", providerId: new URL(checkout.checkout_url).pathname.split("/").at(-1) });
        }
        await route.abort("connectionclosed");
        return;
      }
    }
    await route.continue();
  });
  session.page = await context.newPage();
  session.page.setDefaultTimeout(30000);
  session.page.on("pageerror", (error) => errors.push(`${name}: ${safe(error.message)}`));
  return session;
}
async function access(session) {
  const response = await session.context.request.post(`${site}/api/auth/access-token`, { headers: { Origin: site }, data: {} });
  assert.equal(response.status(), 200, "real BFF must expose only a verified access session");
  const value = await response.json();
  assert.equal("refresh_token" in value, false);
  assert.ok(value.access_token);
  sensitive.add(value.access_token);
  session.token = value.access_token;
  const cookies = await session.context.cookies();
  const authCookies = cookies.filter((cookie) => /auth-token/.test(cookie.name));
  assert.ok(authCookies.length > 0 && authCookies.every((cookie) => cookie.httpOnly));
  assert.equal(await session.page.evaluate(() => Object.keys(localStorage).some((key) => key.includes("auth-token"))), false);
  return value;
}
async function api(session, pathname, { method = "GET", data, status = 200, headers = {} } = {}) {
  const response = await session.context.request.fetch(`${apiOrigin}${pathname}`, {
    method, headers: { Authorization: `Bearer ${session.token}`, Origin: site, ...headers }, ...(data === undefined ? {} : { data }),
  });
  assert.equal(response.status(), status, `real API ${method} ${pathname}`);
  return response.headers()["content-type"]?.includes("json") ? response.json() : response.body();
}
async function login(session, google = false) {
  const { page } = session;
  if (google) await control("select_google_user", { email: session.email });
  await visit(page, "/login?return_to=/account");
  if (google) await page.getByRole("button", { name: en.auth.google, exact: true }).click();
  else {
    await page.getByLabel(en.auth.email).fill(session.email);
    await page.getByRole("button", { name: en.auth.sendCode, exact: true }).click();
    await page.getByLabel(en.auth.code).fill("123456");
    await page.getByRole("button", { name: en.auth.verify, exact: true }).click();
  }
  await page.waitForURL(`${site}/account`);
  await expect(page.getByText(session.email, { exact: true })).toBeVisible();
  await access(session);
  const account = await api(session, "/me");
  session.ownerId = account.id;
  assert.equal(account.email, session.email);
  const snapshot = await state();
  assert.ok(snapshot.users.some((user) => user.id === account.id && user.email === session.email));
}
const rows = (snapshot, table, session) => snapshot[table].filter((row) => (row.owner_id ?? row.user_id ?? row.owner_user_id) === session.ownerId);
const jobLedger = (snapshot, jobId) => snapshot.ledger.filter((row) => row.job_id === jobId);
function assertLedger(snapshot, jobId, terminal, units) {
  const ledger = jobLedger(snapshot, jobId);
  assert.equal(ledger.filter((row) => row.event_type === "reservation").length, 1, "one durable reservation per unchanged job");
  assert.equal(ledger.filter((row) => row.event_type === terminal).length, 1, `one durable ${terminal} event`);
  assert.equal(ledger.filter((row) => ["consume", "release"].includes(row.event_type)).length, 1, "exactly one terminal usage event");
  assert.ok(ledger.every((row) => row.units === units));
  const reservations = snapshot.reservations.filter((row) => row.job_id === jobId);
  assert.equal(reservations.length, 1);
  assert.equal(reservations[0].status, terminal);
  assert.equal(reservations[0].units, units);
}
function wav(silence = false) {
  const rate = 44100, frames = rate * 5;
  const bytes = Buffer.alloc(44 + frames * 2);
  bytes.write("RIFF", 0); bytes.writeUInt32LE(bytes.length - 8, 4); bytes.write("WAVEfmt ", 8);
  bytes.writeUInt32LE(16, 16); bytes.writeUInt16LE(1, 20); bytes.writeUInt16LE(1, 22);
  bytes.writeUInt32LE(rate, 24); bytes.writeUInt32LE(rate * 2, 28);
  bytes.writeUInt16LE(2, 32); bytes.writeUInt16LE(16, 34); bytes.write("data", 36); bytes.writeUInt32LE(frames * 2, 40);
  if (!silence) for (let index = 0; index < frames; index++) {
    const seconds = index / rate;
    const attack = Math.min(1, seconds / 0.025), release = Math.min(1, (5 - seconds) / 0.04);
    bytes.writeInt16LE(Math.round(9000 * attack * release * Math.sin(2 * Math.PI * 440 * seconds)), 44 + index * 2);
  }
  return bytes;
}
async function prepareUpload(session, silence = false) {
  await visit(session.page, "/transcribe");
  await expect(session.page.locator("header").getByRole("link", { name: en.auth.account, exact: true })).toBeVisible();
  await session.page.getByLabel(en.audio.chooseLabel).setInputFiles({ name: silence ? "silence.wav" : "a4-five-seconds.wav", mimeType: "audio/wav", buffer: wav(silence) });
  await session.page.getByLabel(en.audio.rightsText).check();
  await expect(session.page.getByRole("button", { name: en.transcribe.create, exact: true })).toBeEnabled();
}
async function submit(session, { silence = false, lostResponse = false } = {}) {
  await prepareUpload(session, silence);
  if (lostResponse) {
    session.fault = "/jobs";
    await session.page.getByRole("button", { name: en.transcribe.create, exact: true }).click();
    await expect(session.page.getByRole("alert").filter({ hasText: en.transcribe.createFailed })).toBeVisible();
    await capture(session.page, `${session.name}-submission-response-lost`);
    const snapshot = await state();
    assert.equal(rows(snapshot, "jobs", session).length, 1);
    const ledger = jobLedger(snapshot, rows(snapshot, "jobs", session)[0].id);
    assert.equal(ledger.filter((row) => row.event_type === "reservation").length, 1);
  }
  await session.page.getByRole("button", { name: en.transcribe.create, exact: true }).click();
  await session.page.waitForURL((url) => /^\/jobs\/[A-Za-z0-9_-]+$/.test(url.pathname));
  const jobId = new URL(session.page.url()).pathname.split("/").at(-1);
  const queued = await api(session, `/jobs/${jobId}`);
  assert.equal(queued.status, "queued");
  assert.equal(queued.start_sec, 0);
  assert.equal(queued.end_sec, 5);
  await capture(session.page, `${session.name}-${silence ? "silence-" : ""}queued`);
  return jobId;
}
async function transcribe(session, jobId, expected = "succeeded") {
  await control("transcription_worker");
  const job = await api(session, `/jobs/${jobId}`);
  assert.equal(job.status, expected, `real model job ${jobId}: ${job.error_code ?? ""}`);
  if (expected === "failed") {
    assert.equal(job.error_code, "NO_NOTES_DETECTED");
    await expect(session.page.getByRole("heading", { name: en.job.noNotes, exact: true })).toBeVisible();
  } else {
    assert.ok(job.artifacts.some((artifact) => artifact.type === "midi" && artifact.status === "succeeded"));
    assert.ok(job.artifacts.some((artifact) => artifact.type === "musicxml" && artifact.status === "succeeded"));
    await expect(session.page.getByRole("heading", { name: en.result.title, exact: true })).toBeVisible({ timeout: 60000 });
  }
  return job;
}
async function download(session, kind, label) {
  const button = session.page.getByRole("button", { name: new RegExp(`^${label}`) });
  await expect(button).toBeEnabled({ timeout: 60000 });
  const waiting = session.page.waitForEvent("download");
  await button.click();
  const received = await waiting;
  assert.equal(await received.failure(), null);
  const filename = path.join(output, `${session.name}-${kind}.${kind === "midi" ? "mid" : kind}`);
  await received.saveAs(filename);
  const bytes = readFileSync(filename);
  const item = { type: "download", kind, path: filename, size_bytes: bytes.length, sha256: createHash("sha256").update(bytes).digest("hex") };
  if (kind === "midi") {
    assert.equal(bytes.toString("ascii", 0, 4), "MThd");
    const midi = new Midi(bytes);
    const notes = midi.tracks.flatMap((track) => track.notes);
    assert.ok(notes.length > 0, "actual MIDI must contain notes");
    assert.ok(notes.some((note) => note.midi === 69), "known A4 input must produce an A4 note");
    item.notes = notes.length;
  } else if (kind === "musicxml") {
    const xml = bytes.toString("utf8");
    const parsed = await session.page.evaluate((value) => {
      const doc = new DOMParser().parseFromString(value, "application/xml");
      return { error: Boolean(doc.querySelector("parsererror")), root: doc.documentElement.nodeName, pitches: doc.querySelectorAll("note pitch").length };
    }, xml);
    assert.equal(parsed.error, false); assert.equal(parsed.root, "score-partwise"); assert.ok(parsed.pitches > 0);
    item.pitched_notes = parsed.pitches;
  } else {
    assert.equal(bytes.toString("ascii", 0, 5), "%PDF-");
    assert.ok(bytes.length > 1000);
    assert.match(bytes.toString("latin1"), /%%EOF\s*$/);
  }
  evidence.push(item);
}
async function result(session, jobId) {
  const { page } = session;
  const snapshotBefore = await state();
  const ledgerBefore = jobLedger(snapshotBefore, jobId);
  await expect(page.getByRole("button", { name: /^PDF/ })).toBeEnabled({ timeout: 60000 });
  const svg = page.locator("svg[id^='osmdSvgPage']");
  await expect(svg.first()).toBeVisible();
  assert.ok(await svg.first().locator("path").count() > 10, "score engraving must contain actual music paths");
  await capture(page, `${session.name}-score`);
  await download(session, "midi", en.result.cleanedMidi);
  await download(session, "musicxml", "MusicXML");
  await download(session, "pdf", "PDF");
  await page.getByRole("tab", { name: en.result.pianoRoll, exact: true }).click();
  const canvas = page.getByRole("img", { name: en.result.rollLabel, exact: true });
  await expect(canvas).toBeVisible();
  const pixels = await canvas.evaluate((element) => {
    const data = element.getContext("2d").getImageData(0, 0, element.width, element.height).data;
    const colors = new Set();
    for (let offset = 0; offset < data.length; offset += 64) colors.add(`${data[offset]},${data[offset + 1]},${data[offset + 2]},${data[offset + 3]}`);
    return { width: element.width, height: element.height, colors: colors.size };
  });
  assert.ok(pixels.width > 0 && pixels.height > 0 && pixels.colors > 8, "piano-roll canvas must be nonblank");
  await capture(page, `${session.name}-piano-roll`);
  await page.getByRole("button", { name: en.result.midiMode, exact: true }).click();
  await page.getByRole("button", { name: en.result.play, exact: true }).click();
  await expect(page.getByRole("button", { name: en.result.pause, exact: true })).toBeVisible();
  await expect.poll(async () => Number(await page.getByLabel(en.result.position, { exact: true }).inputValue())).toBeGreaterThan(0.1);
  await page.getByRole("button", { name: en.result.pause, exact: true }).click();
  await page.getByRole("button", { name: en.result.sourceMode, exact: true }).click();
  await page.getByRole("button", { name: en.result.play, exact: true }).click();
  await expect.poll(() => page.locator("audio").evaluate((audio) => audio.currentTime)).toBeGreaterThan(0.1);
  await page.getByRole("button", { name: en.result.pause, exact: true }).click();
  const snapshotAfter = await state();
  assert.deepEqual(jobLedger(snapshotAfter, jobId), ledgerBefore, "playback and downloads must not mutate usage ledger");
  assert.equal(snapshotAfter.counts.model_calls, snapshotBefore.counts.model_calls, "playback and downloads must not rerun inference");
  assert.equal(snapshotAfter.counts.rq_executions, snapshotBefore.counts.rq_executions, "playback and downloads must not enqueue another transcription");
}
async function crossAccount(session, jobId) {
  const other = await open(`${session.name}-other`, { width: 375, height: 812 });
  try {
    await login(other);
    await api(other, `/jobs/${jobId}`, { status: 404 });
    await api(other, `/jobs/${jobId}/download-url/midi`, { status: 404 });
    await api(other, `/jobs/${jobId}`, { method: "DELETE", status: 404 });
    await visit(other.page, `/jobs/${jobId}`);
    await expect(other.page.getByRole("heading", { name: en.job.unavailableTitle, exact: true })).toBeVisible();
    await capture(other.page, `${session.name}-cross-account-denied`);
  } finally { contexts.delete(other.context); await other.context.close(); }
}
async function paidJourney(name, viewport, recover = false) {
  const session = await open(name, viewport);
  try {
    await step(`${name}: OTP / real Supabase SDK / HttpOnly cookies`, () => login(session));
    if (name === "desktop") await step("desktop: Google PKCE callback returns to the same account", async () => {
      const owner = session.ownerId;
      await session.page.getByRole("button", { name: en.auth.signOut, exact: true }).click();
      await session.page.waitForURL(`${site}/login`);
      await login(session, true);
      assert.equal(session.ownerId, owner, "provider identity must resolve to the same existing account");
    });
    await capture(session.page, `${name}-free-account`);
    await step(`${name}: checkout${recover ? " response-loss recovery" : ""} stays pending on return`, async () => {
      if (recover) {
        session.fault = "/billing/checkout";
        await session.page.getByRole("button", { name: en.billing.testCheckout, exact: true }).click();
        await expect(session.page.getByText(en.billing.checkoutError, { exact: true })).toBeVisible();
        await capture(session.page, `${name}-checkout-response-lost`);
        assert.equal(rows(await state(), "checkouts", session).length, 1);
      }
      const response = session.page.waitForResponse((reply) => reply.url() === `${apiOrigin}/billing/checkout` && reply.request().method() === "POST" && reply.ok());
      await session.page.getByRole("button", { name: en.billing.testCheckout, exact: true }).click();
      const reply = await response;
      assert.equal(reply.status(), 200);
      await session.page.waitForURL((value) => value.protocol === "https:" && ["creem.io", "www.creem.io"].includes(value.hostname) && value.pathname.startsWith("/test/checkout/ch_"));
      const url = hostedUrl(session.page.url(), "checkout");
      if (session.checkout) assert.equal(url, session.checkout.checkout_url, "response-loss recovery must reopen the same hosted checkout");
      session.checkout = { ...session.checkout, checkout_url: url };
      session.hosted.set(url, { kind: "checkout", providerId: new URL(url).pathname.split("/").at(-1) });
      await session.page.waitForURL(url);
      await session.page.getByRole("button", { name: "Confirm test payment", exact: true }).click();
      await session.page.waitForURL((value) => value.origin === site && value.pathname === "/billing/return");
      await expect(session.page.getByText(en.billing.paymentPending, { exact: true })).toBeVisible();
      await expect(session.page.getByText(en.billing.paymentConfirmed, { exact: true })).toHaveCount(0);
      const summary = await api(session, "/billing/me");
      assert.equal(summary.plan, "free"); assert.equal(summary.sync_state, "payment_confirming");
      const snapshot = await state();
      assert.equal(rows(snapshot, "checkouts", session).length, 1);
      assert.equal(rows(snapshot, "paid_periods", session).length, 0);
      await capture(session.page, `${name}-payment-pending`);
    });
    await step(`${name}: signed duplicate webhooks and billing worker grant one paid period`, async () => {
      const providerId = new URL(session.checkout.checkout_url).pathname.split("/").at(-1);
      await control("deliver", { checkout_id: providerId, event_types: ["checkout.completed", "subscription.paid"], duplicates: 2 });
      await control("billing_worker");
      await expect(session.page.getByText(en.billing.paymentConfirmed, { exact: true })).toBeVisible({ timeout: 60000 });
      const summary = await api(session, "/billing/me");
      assert.equal(summary.plan, "pro"); assert.equal(summary.state, "active"); assert.equal(summary.sync_state, "ready");
      assert.equal(summary.remaining, 1800); assert.equal(summary.reserved, 0); assert.equal(summary.used, 0);
      assert.equal(rows(await state(), "paid_periods", session).length, 1, "duplicate events cannot grant a second period");
      const checkoutRequests = requests.filter((request) => request.session === name && request.method === "POST" && request.path === "/billing/checkout");
      assert.equal(new Set(checkoutRequests.map((request) => request.key)).size, 1, "checkout recovery must preserve one idempotency key");
      await capture(session.page, `${name}-payment-confirmed`);
    });
    const jobId = await step(`${name}: actual browser audio clipping / upload${recover ? " / response-loss replay" : ""}`, () => submit(session, { lostResponse: recover }));
    await step(`${name}: real RQ worker and BasicPitch consume once`, async () => {
      const before = await state();
      await transcribe(session, jobId);
      const summary = await api(session, "/billing/me");
      assert.equal(summary.used, 15); assert.equal(summary.reserved, 0); assert.equal(summary.remaining, 1785);
      const snapshot = await state();
      assertLedger(snapshot, jobId, "consume", 15);
      assert.equal(rows(snapshot, "jobs", session).length, 1);
      const createRequests = requests.filter((request) => request.session === name && request.method === "POST" && request.path === "/jobs");
      assert.equal(new Set(createRequests.map((request) => request.key)).size, 1, "upload recovery must preserve one idempotency key");
      assert.equal(snapshot.counts.model_calls, before.counts.model_calls + 1, "success must run real BasicPitch exactly once");
      assert.equal(snapshot.counts.rq_executions, before.counts.rq_executions + 1, "success must execute exactly one real RQ job");
    });
    await step(`${name}: score / canvas / source + MIDI playback / parsed downloads`, () => result(session, jobId));
    if (name === "desktop") await step("desktop: another verified account cannot read, download or delete the result", () => crossAccount(session, jobId));
    await step(`${name}: portal scheduled cancellation preserves paid quota`, async () => {
      const before = await api(session, "/billing/me");
      await visit(session.page, "/account");
      const response = session.page.waitForResponse((reply) => reply.url() === `${apiOrigin}/billing/portal` && reply.request().method() === "POST" && reply.ok());
      await session.page.getByRole("button", { name: en.billing.manageBilling, exact: true }).click();
      const reply = await response;
      assert.equal(reply.status(), 200);
      await session.page.waitForURL((value) => value.protocol === "https:" && ["creem.io", "www.creem.io"].includes(value.hostname) && value.pathname.startsWith("/test/portal/"));
      const url = hostedUrl(session.page.url(), "portal"); session.hosted.set(url, { kind: "portal" });
      await session.page.waitForURL(url);
      await session.page.getByRole("button", { name: "Cancel future renewal", exact: true }).click();
      await session.page.waitForURL(`${site}/account`);
      await control("billing_worker");
      await session.page.getByRole("button", { name: en.billing.refresh, exact: true }).click();
      const after = await api(session, "/billing/me");
      assert.equal(after.plan, "pro"); assert.equal(after.state, "active");
      assert.equal(after.subscription_status, "scheduled_cancel");
      assert.equal(after.remaining, before.remaining); assert.equal(after.used, before.used);
      await expect(session.page.getByText(en.billing.proName, { exact: true })).toBeVisible();
      await capture(session.page, `${name}-cancelled-renewal`);
    });
    if (name === "desktop") await step("desktop: reactivated existing renewal preserves the same paid period", async () => {
      await control("reactivate_subscription", { subscription_id: session.subscriptionId, deliver: true });
      await control("billing_worker");
      const summary = await api(session, "/billing/me");
      assert.equal(summary.plan, "pro"); assert.equal(summary.state, "active");
      assert.equal(summary.subscription_status, "active");
      assert.equal(summary.used, 15); assert.equal(summary.reserved, 0); assert.equal(summary.remaining, 1785);
      const snapshot = await state();
      assert.equal(rows(snapshot, "paid_periods", session).length, 1, "reactivation cannot grant a new paid period");
      assertLedger(snapshot, jobId, "consume", 15);
      await session.page.getByRole("button", { name: en.billing.refresh, exact: true }).click();
      await expect(session.page.getByText(en.billing.remainingSeconds.replace("{seconds}", "1785"), { exact: true })).toBeVisible();
      await capture(session.page, "desktop-renewal-reactivated");
    });
    await step(`${name}: deletion waits for billing, then cleans actual files and completes`, async () => {
      const ticket = await api(session, `/jobs/${jobId}/download-url/midi`);
      assert.ok(ticket.path.startsWith(`/jobs/${jobId}/files/midi?`) && !ticket.path.includes("://"));
      const ticketBefore = await session.context.request.get(`${apiOrigin}${ticket.path}`);
      assert.equal(ticketBefore.status(), 200);
      assert.equal((await ticketBefore.body()).toString("ascii", 0, 4), "MThd");
      const hasSourceAndExports = (snapshot) => {
        assert.ok(Array.isArray(snapshot.storage_files));
        const files = snapshot.storage_files.filter((filename) => filename.startsWith(`jobs/${jobId}/`));
        const job = rows(snapshot, "jobs", session).find((item) => item.id === jobId);
        assert.ok(job);
        const artifactPrefix = `jobs/${jobId}/artifacts/attempt-${job.attempt_count}/`;
        assert.ok(files.includes(`jobs/${jobId}/source.wav`), "billing checkpoint must preserve source audio");
        assert.ok(files.includes(`${artifactPrefix}score.mid`), "billing checkpoint must preserve MIDI");
        assert.ok(files.includes(`${artifactPrefix}score.musicxml`), "billing checkpoint must preserve MusicXML");
      };
      await session.page.getByRole("button", { name: en.auth.deletionAction, exact: true }).click();
      await expect(session.page.getByRole("button", { name: en.auth.deletionSubmit, exact: true })).toBeDisabled();
      await session.page.getByRole("checkbox", { name: en.auth.deletionConfirm, exact: true }).check();
      await capture(session.page, `${name}-deletion-confirmation`);
      await session.page.getByRole("button", { name: en.auth.deletionSubmit, exact: true }).click();
      await expect(session.page.getByText(en.auth.deletionBilling, { exact: true })).toBeVisible();
      const billingCheckpoint = await state();
      assert.equal(rows(billingCheckpoint, "jobs", session).length, 1, "billing checkpoint cannot remove jobs yet");
      hasSourceAndExports(billingCheckpoint);
      await capture(session.page, `${name}-deletion-billing`);
      await control("delete_worker");
      await session.page.getByRole("button", { name: en.auth.deletionRefresh, exact: true }).click();
      await expect(session.page.getByText(en.auth.deletionCleanup, { exact: true })).toBeVisible();
      const cleanupCheckpoint = await state();
      assert.equal(rows(cleanupCheckpoint, "jobs", session).length, 1, "cleanup checkpoint precedes data deletion");
      hasSourceAndExports(cleanupCheckpoint);
      const cancelCalls = cleanupCheckpoint.counts.cancel_posts - billingCheckpoint.counts.cancel_posts;
      assert.equal(cancelCalls, name === "desktop" ? 1 : 0, name === "desktop"
        ? "deletion must cancel the reactivated subscription once through real Creem HTTP"
        : "already scheduled cancellation must not be submitted twice");
      evidence.push({ type: "billing_cancellation", owner_id: session.ownerId, subscription_id: session.subscriptionId,
        real_http_cancel_calls: cancelCalls, checkpoint: "billing_to_cleanup" });
      await capture(session.page, `${name}-deletion-cleanup`);
      await control("delete_worker");
      await session.page.getByRole("button", { name: en.auth.deletionRefresh, exact: true }).click();
      await expect(session.page.getByText(en.auth.deletionCompleted, { exact: true })).toBeVisible();
      await expect(session.page.getByText(session.email, { exact: true })).toHaveCount(0);
      const snapshot = await state();
      assert.equal(rows(snapshot, "jobs", session).length, 0);
      assert.equal(snapshot.storage_files.filter((filename) => filename.startsWith(`jobs/${jobId}/`)).length, 0, "completed deletion removes actual source and artifact objects");
      assert.deepEqual(snapshot.temp_files, [], "completed deletion leaves no pipeline/download temporary files");
      assert.equal(rows(snapshot, "deletions", session).length, 1);
      assert.equal(rows(snapshot, "deletions", session)[0].status, "completed");
      assert.ok(snapshot.users.some((user) => user.id === session.ownerId && user.email === null && user.active === false));
      assertLedger(snapshot, jobId, "consume", 15);
      assert.equal(rows(snapshot, "paid_periods", session).length, 1, "transaction records remain after account cleanup");
      assert.equal(snapshot.counts.cancel_posts, cleanupCheckpoint.counts.cancel_posts, "data cleanup cannot repeat provider cancellation");
      assert.ok(ticket.expires_at * 1000 > Date.now(), "the old ticket must still be unexpired so 404 proves deletion");
      const ticketAfter = await session.context.request.get(`${apiOrigin}${ticket.path}`);
      assert.equal(ticketAfter.status(), 404, "previously valid signed artifact ticket must fail after physical cleanup");
      const newTicket = await session.context.request.get(`${apiOrigin}/jobs/${jobId}/download-url/midi`, { headers: { Authorization: `Bearer ${session.token}` } });
      assert.ok([401, 403].includes(newTicket.status()), "inactive account cannot create a fresh signed download ticket");
      await capture(session.page, `${name}-deletion-completed`);
      await session.page.reload();
      await expect(session.page.getByText(en.auth.deletionCompleted, { exact: true })).toBeVisible();
    });
  } finally { contexts.delete(session.context); await session.context.close(); }
}
async function freeJourney() {
  const session = await open("free-failure", { width: 375, height: 812 });
  try {
    await step("Free: verified email account", () => login(session));
    const failed = await step("Free: actual silence upload enters RQ", () => submit(session, { silence: true }));
    await step("Free: real model no-notes failure releases allowance", async () => {
      await transcribe(session, failed, "failed");
      const summary = await api(session, "/billing/me");
      assert.equal(summary.remaining, 1); assert.equal(summary.used, 0); assert.equal(summary.reserved, 0);
      assertLedger(await state(), failed, "release", 1);
      await capture(session.page, "free-no-notes-released");
    });
    const succeeded = await step("Free: subsequent real audio task succeeds", () => submit(session));
    await step("Free: monthly allowance exhausted only after success", async () => {
      await transcribe(session, succeeded);
      assertLedger(await state(), succeeded, "consume", 1);
      const summary = await api(session, "/billing/me");
      assert.equal(summary.remaining, 0); assert.equal(summary.used, 1); assert.equal(summary.reserved, 0);
      await visit(session.page, "/transcribe");
      await session.page.getByLabel(en.audio.chooseLabel).setInputFiles({ name: "no-more-free.wav", mimeType: "audio/wav", buffer: wav() });
      await session.page.getByLabel(en.audio.rightsText).check();
      await expect(session.page.getByText(en.billing.balanceEmpty, { exact: true })).toBeVisible();
      await expect(session.page.getByRole("button", { name: en.transcribe.create, exact: true })).toBeDisabled();
      const form = new FormData();
      form.set("audio_file", new Blob([wav()], { type: "audio/wav" }), "direct-exhausted.wav");
      form.set("start_sec", "0"); form.set("end_sec", "5"); form.set("rights_confirmed", "true");
      const denied = await fetch(`${apiOrigin}/jobs`, { method: "POST", headers: { Authorization: `Bearer ${session.token}`, "Idempotency-Key": randomBytes(16).toString("hex") }, body: form });
      assert.equal(denied.status, 429, "server must enforce exhausted Free allowance as well as the UI");
      assert.equal(rows(await state(), "jobs", session).length, 2, "rejection cannot insert another job");
      await capture(session.page, "free-exhausted");
    });
  } finally { contexts.delete(session.context); await session.context.close(); }
}

let report;
try {
  interruption.signal.throwIfAborted();
  const webPort = await port();
  let apiPort = await port();
  while (apiPort === webPort) apiPort = await port();
  site = `http://127.0.0.1:${webPort}`;
  assert.ok(existsSync(python), "Python 3.11+ API virtualenv is required (SONGDANCE_COMMERCIAL_PYTHON may override it)");
  const startupFile = path.join(apiRoot, "tests/support/commercial_stack.py");
  assert.ok(existsSync(startupFile), "tests/support/commercial_stack.py must exist");
  interruption.signal.throwIfAborted();
  apiChild = spawn(python, ["-m", "tests.support.commercial_stack", "--root", temp, "--site-url", site, "--port", String(apiPort)], {
    cwd: apiRoot, detached: true, stdio: ["ignore", "pipe", "pipe"], env: {
      ...process.env, PYTHONUNBUFFERED: "1", SONGDANCE_COMMERCIAL_CONTROL_SECRET: controlSecret, SONGDANCE_COMMERCIAL_BRIDGE_SECRET: bridgeSecret,
    },
  });
  trackChild(apiChild, "api");
  const startup = await new Promise((resolve, reject) => {
    let buffer = "";
    const timeout = setTimeout(() => reject(new Error("Disposable API stack readiness timeout")), 120000);
    interruption.signal.addEventListener("abort", () => { clearTimeout(timeout); reject(interruption.signal.reason); }, { once: true });
    apiChild.once("exit", (code) => { clearTimeout(timeout); reject(new Error(`Disposable API stack exited (${code})`)); });
    apiChild.stdout.on("data", (chunk) => {
      buffer += chunk.toString();
      let newline;
      while ((newline = buffer.indexOf("\n")) >= 0) {
        const line = buffer.slice(0, newline); buffer = buffer.slice(newline + 1);
        try {
          const value = JSON.parse(line);
          if (value.ready === true && value.api_origin && value.provider_origin) { clearTimeout(timeout); resolve(value); }
        } catch { /* Non-JSON setup diagnostics are collected separately. */ }
      }
    });
  });
  apiOrigin = localOrigin(startup.api_origin); providerOrigin = localOrigin(startup.provider_origin);
  interruption.signal.throwIfAborted();
  assert.equal(apiOrigin, `http://127.0.0.1:${apiPort}`);
  assert.equal(startup.control_path, "/__commercial__/control"); controlPath = startup.control_path;
  webChild = spawn(process.execPath, ["node_modules/next/dist/bin/next", "dev", "--webpack", "--hostname", "127.0.0.1", "-p", String(webPort)], {
    cwd: webRoot, detached: true, stdio: ["ignore", "pipe", "pipe"], env: {
      ...process.env, NODE_ENV: "development", NEXT_TELEMETRY_DISABLED: "1", NEXT_PUBLIC_AUTH_ENABLED: "true", SONGDANCE_AUTH_ENABLED: "true",
      NEXT_PUBLIC_SITE_URL: site, NEXT_PUBLIC_API_URL: apiOrigin, SONGDANCE_AUTH_API_URL: apiOrigin,
      SONGDANCE_SUPABASE_URL: providerOrigin, SONGDANCE_SUPABASE_PUBLISHABLE_KEY: "sb_publishable_commercial_local", SONGDANCE_AUTH_BRIDGE_SECRET: bridgeSecret,
      SONGDANCE_NEXT_DIST_DIR: path.relative(webRoot, dist), SONGDANCE_TSCONFIG_PATH: path.relative(webRoot, path.join(configDir, "tsconfig.json")),
    },
  });
  trackChild(webChild, "web");
  let ready = false;
  for (let attempt = 0; attempt < 90; attempt++) {
    interruption.signal.throwIfAborted();
    if (webChild.exitCode !== null || webChild.signalCode !== null) throw new Error("Next.js exited before readiness");
    try { if ((await fetch(`${site}/login`, { signal: AbortSignal.any([interruption.signal, AbortSignal.timeout(3000)]) })).ok) { ready = true; break; } } catch { /* Startup. */ }
    await sleep(1000);
  }
  assert.ok(ready, "Next.js readiness timeout");
  browser = await chromium.launch({ headless: true, executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH ?? (process.platform === "darwin" ? "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" : undefined) });
  interruption.signal.throwIfAborted();
  await paidJourney("desktop", { width: 1280, height: 1000 }, true);
  await paidJourney("mobile", { width: 375, height: 812 });
  await freeJourney();
  assert.deepEqual(external, [], "no production API, identity or billing provider may be contacted");
  assert.deepEqual(errors, [], "no uncaught browser/process errors");
  const snapshot = await state();
  report = { status: "passed", scope: "real_browser_bff_fastapi_migrated_postgresql_redis_rq_basic_pitch", real_provider_verified: false,
    live_payments_verified: false, provider_protocols: ["local Supabase with RSA JWT/JWKS", "local Creem HTTP plus signed webhook"],
    transcription_quality_gate_verified: false,
    limitations: ["Synthetic A4/silence audio verifies orchestration, not professional transcription acceptance", "Live Supabase, Google, email delivery and Creem settlement are not exercised"],
    checks, evidence, requests, external_requests: external, final_state: snapshot, screenshots: output };
} catch (error) {
  console.error(safe(error.stack ?? error));
  for (const context of contexts) for (const page of context.pages()) await capture(page, `failure-${context.pages().indexOf(page)}`).catch(() => {});
  report = { status: "failed", current_step: currentStep, error: safe(error.stack ?? error), checks, evidence, requests, external_requests: external,
    browser_errors: errors, last_state: lastState, logs: { api: apiLogs, web: webLogs }, screenshots: output };
  console.error(JSON.stringify({ status: "failed", current_step: currentStep, report: path.join(output, "report.json") }));
  process.exitCode = 1;
} finally {
  let removeTemp = false;
  try {
    await signalCleanup;
    await closeResources();
    const cleanup = await verifyPrivateServicesStopped();
    if (report) report.cleanup = cleanup;
    removeTemp = true;
  } catch (error) {
    process.exitCode = 1;
    report = { ...report, status: "failed", cleanup: { stopped: false, error: safe(error.stack ?? error), preserved_temp_root: temp } };
    console.error(`Cleanup incomplete; preserved ${temp}: ${safe(error.message)}`);
  }
  if (existsSync(nextEnvPath) && readFileSync(nextEnvPath, "utf8").includes(`.next/${id}/`)) {
    if (nextEnvBefore === null) rmSync(nextEnvPath); else writeFileSync(nextEnvPath, nextEnvBefore);
  }
  for (const directory of [configDir, dist, ...(removeTemp ? [temp] : [])]) rmSync(directory, { recursive: true, force: true });
  if (report) {
    writeFileSync(path.join(output, "report.json"), safe(JSON.stringify(report, null, 2)));
    console.log(JSON.stringify({ status: report.status, scope: report.scope, checks: checks.length,
      cleanup_verified: report.cleanup?.stopped === true, report: path.join(output, "report.json"), screenshots: output }));
  }
}
