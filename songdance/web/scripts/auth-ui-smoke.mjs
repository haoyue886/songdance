// Isolated browser/BFF contract test. Provider and API are local protocol doubles.
// Never contacts Supabase, Google, SMTP, or the production API.
import assert from "node:assert/strict";
import { createHash, createHmac, randomUUID } from "node:crypto";
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from "node:fs";
import { createServer } from "node:http";
import { tmpdir } from "node:os";
import path from "node:path";
import { spawn } from "node:child_process";
import { chromium } from "@playwright/test";

const root = process.cwd();
const temp = mkdtempSync(path.join(tmpdir(), "songdance-auth-ui-"));
const id = path.basename(temp);
const dist = path.join(root, ".next", id);
const configDir = path.join(root, ".next", `${id}-config`);
const output = path.join(root, "test-results", id);
mkdirSync(configDir, { recursive: true });
mkdirSync(output, { recursive: true });
writeFileSync(path.join(configDir, "tsconfig.json"), JSON.stringify({ extends: "../../tsconfig.json" }));
const bridgeSecret = "local-auth-ui-test-bridge-not-a-real-secret";
const user = { id: "12345678-1234-4234-8234-123456789012", aud: "authenticated", role: "authenticated", email: "browser-test@example.test", email_confirmed_at: "2026-09-30T00:00:00Z", created_at: "2026-09-30T00:00:00Z", app_metadata: { provider: "email", providers: ["email", "google"] }, user_metadata: {}, identities: [] };
const tokens = new Map();
const refreshes = new Map();
const challenges = new Map();
const codes = new Map();
let providerOrigin;
let site;
let refreshCount = 0;
let nextShort = false;
function session(short = false) {
  const now = Math.floor(Date.now() / 1000);
  const payload = { iss: `${providerOrigin}/auth/v1`, aud: "authenticated", sub: user.id, session_id: randomUUID(), role: "authenticated", email: user.email, iat: now - 10, exp: short ? now - 1 : now + 3600 };
  const head = Buffer.from(JSON.stringify({ alg: "HS256", typ: "JWT" })).toString("base64url");
  const body = Buffer.from(JSON.stringify(payload)).toString("base64url");
  const signature = createHmac("sha256", "local-test-only-key-never-production").update(`${head}.${body}`).digest("base64url");
  const result = { access_token: `${head}.${body}.${signature}`, refresh_token: `test-refresh-${randomUUID()}`, expires_in: short ? 1 : 3600, expires_at: payload.exp, token_type: "bearer", user };
  tokens.set(result.access_token, payload.exp);
  refreshes.set(result.refresh_token, result);
  return result;
}
const api = createServer(async (req, res) => {
  try {
    const url = new URL(req.url, providerOrigin ?? "http://localhost");
    res.setHeader("Access-Control-Allow-Origin", site ?? "http://localhost");
    res.setHeader("Access-Control-Allow-Headers", "authorization, content-type, x-job-access");
    res.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
    if (req.method === "OPTIONS") { res.writeHead(204).end(); return; }
    const json = (value, status = 200) => { res.writeHead(status, { "Content-Type": "application/json", "Cache-Control": "no-store" }).end(JSON.stringify(value)); };
    let text = "";
    for await (const chunk of req) { text += chunk; if (text.length > 16384) { json({}, 413); return; } }
    const body = text ? JSON.parse(text) : {};
    const bearer = req.headers.authorization?.replace(/^Bearer /, "");
    const active = bearer && (tokens.get(bearer) ?? 0) > Date.now() / 1000;
    if (url.pathname === "/health") { json({ ok: true }); return; }
    if (url.pathname.startsWith("/auth/bridge/") || url.pathname === "/test/short-session") {
      if (req.headers["x-auth-bridge"] !== bridgeSecret) { json({}, 403); return; }
      if (url.pathname === "/test/short-session") { nextShort = true; json({ ok: true }); return; }
      if (url.pathname.endsWith("otp-start")) {
        const challenge = randomUUID(); challenges.set(challenge, body.email); json({ challenge }); return;
      }
      if (url.pathname.endsWith("otp-attempt") || url.pathname.endsWith("otp-consume")) {
        if (challenges.get(body.challenge) !== body.email) { json({}, 401); return; }
        if (url.pathname.endsWith("otp-consume")) challenges.delete(body.challenge);
        json({ ok: true }); return;
      }
      if (url.pathname.endsWith("refresh")) {
        if (!refreshes.has(body.refresh_token)) { json({}, 401); return; }
        refreshCount++; json(session()); return;
      }
    }
    if (url.pathname === "/auth/v1/otp") { json({}); return; }
    if (url.pathname === "/auth/v1/verify") {
      if (!["123456", "12345678"].includes(body.token)) { json({ msg: "Invalid token" }, 400); return; }
      const value = session(nextShort); nextShort = false; json(value); return;
    }
    if (url.pathname === "/auth/v1/authorize") {
      const destination = new URL(url.searchParams.get("redirect_to"));
      const code = randomUUID(); codes.set(code, url.searchParams.get("code_challenge"));
      destination.searchParams.set("code", code);
      res.writeHead(302, { Location: destination.toString() }).end(); return;
    }
    if (url.pathname === "/auth/v1/token") {
      // Refresh MUST take the BFF's bridge path, not this direct provider endpoint.
      const challenge = codes.get(body.auth_code);
      if (url.searchParams.get("grant_type") !== "pkce" || !challenge || createHash("sha256").update(body.code_verifier ?? "").digest("base64url") !== challenge) { json({ msg: "Invalid PKCE" }, 400); return; }
      codes.delete(body.auth_code); json(session()); return;
    }
    if (url.pathname === "/auth/v1/user") { json(active ? user : { msg: "Expired" }, active ? 200 : 401); return; }
    if (url.pathname === "/auth/v1/logout") { tokens.delete(bearer); res.writeHead(204).end(); return; }
    if (url.pathname === "/me") { json(active ? { id: "local-business-user", email: user.email } : { detail: { code: "AUTH_REQUIRED" } }, active ? 200 : 401); return; }
    json({}, 404);
  } catch { res.writeHead(500).end(); }
});

let child;
let browser;
let logs = "";
const listen = (server) => new Promise((resolve, reject) => { server.once("error", reject); server.listen(0, "127.0.0.1", resolve); });
try {
  await listen(api);
  providerOrigin = `http://127.0.0.1:${api.address().port}`;
  const portProbe = createServer(); await listen(portProbe);
  const port = portProbe.address().port;
  await new Promise(resolve => portProbe.close(resolve));
  site = `http://127.0.0.1:${port}`;
  child = spawn(process.execPath, ["node_modules/next/dist/bin/next", "dev", "--webpack", "--hostname", "127.0.0.1", "-p", String(port)], {
    cwd: root, detached: true, stdio: ["ignore", "pipe", "pipe"], env: {
      ...process.env, NODE_ENV: "development", NEXT_PUBLIC_AUTH_ENABLED: "true", SONGDANCE_AUTH_ENABLED: "true",
      NEXT_PUBLIC_SITE_URL: site, NEXT_PUBLIC_API_URL: providerOrigin, SONGDANCE_AUTH_API_URL: providerOrigin,
      SONGDANCE_SUPABASE_URL: providerOrigin, SONGDANCE_SUPABASE_PUBLISHABLE_KEY: "sb_publishable_local_test",
      SONGDANCE_AUTH_BRIDGE_SECRET: bridgeSecret, SONGDANCE_NEXT_DIST_DIR: path.relative(root, dist),
      SONGDANCE_TSCONFIG_PATH: path.relative(root, path.join(configDir, "tsconfig.json")),
    },
  });
  for (const stream of [child.stdout, child.stderr]) stream.on("data", data => { logs = (logs + data).slice(-12000); });
  let ready = false;
  for (let attempt = 0; attempt < 90; attempt++) {
    if (child.exitCode !== null) throw new Error("Next.js exited before readiness");
    try { if ((await fetch(`${site}/login`, { signal: AbortSignal.timeout(3000) })).ok) { ready = true; break; } } catch { /* startup */ }
    await new Promise(resolve => setTimeout(resolve, 1000));
  }
  assert.ok(ready, "Next.js readiness timeout");
  browser = await chromium.launch({ headless: true, executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH ?? (process.platform === "darwin" ? "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" : undefined) });
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  const external = [];
  await context.route("**/*", async route => {
    const url = new URL(route.request().url());
    if (url.protocol.startsWith("http") && ![site, providerOrigin].includes(url.origin)) { external.push(url.origin); await route.abort(); } else await route.continue();
  });
  const hydrated = page.waitForResponse(response => response.url().endsWith("/api/auth/access-token"));
  await page.goto(`${site}/login?return_to=/account`);
  await hydrated;
  await page.getByRole("button", { name: "Continue with Google" }).waitFor();
  await page.screenshot({ path: path.join(output, "login-desktop.png"), fullPage: true });
  await page.setViewportSize({ width: 375, height: 812 });
  await page.screenshot({ path: path.join(output, "login-mobile.png"), fullPage: true });
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), "375px page must not overflow");
  await page.getByLabel("Email address").fill(user.email);
  await page.getByRole("button", { name: "Send code", exact: true }).click();
  const otpInput = page.getByLabel("Verification code");
  await otpInput.waitFor();
  assert.equal(await otpInput.getAttribute("maxlength"), "8");
  await otpInput.fill("1234567");
  assert.equal(await otpInput.evaluate(input => input.checkValidity()), false, "seven-digit OTP must fail HTML validation");
  assert.ok(await page.getByRole("button", { name: /Send another code/ }).isDisabled());
  await otpInput.fill("00000000");
  assert.equal(await otpInput.evaluate(input => input.checkValidity()), true, "eight-digit OTP must pass HTML validation");
  await page.getByRole("button", { name: "Verify and sign in" }).click();
  await page.getByRole("alert").waitFor();
  await otpInput.fill("12345678");
  await page.screenshot({ path: path.join(output, "otp-mobile.png"), fullPage: true });
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.screenshot({ path: path.join(output, "otp-desktop.png"), fullPage: true });
  await page.setViewportSize({ width: 375, height: 812 });
  await page.getByRole("button", { name: "Verify and sign in" }).click();
  await page.waitForURL("**/account");
  await page.getByText(user.email, { exact: true }).waitFor();
  const cookies = await context.cookies();
  assert.ok(cookies.filter(cookie => cookie.name.includes("auth-token")).length > 0);
  assert.ok(cookies.filter(cookie => cookie.name.includes("auth-token")).every(cookie => cookie.httpOnly));
  const access = await context.request.post(`${site}/api/auth/access-token`, { headers: { Origin: site }, data: {} });
  const accessBody = await access.json(); assert.ok(accessBody.access_token); assert.equal("refresh_token" in accessBody, false);
  assert.equal(await page.evaluate(() => Object.keys(localStorage).some(key => key.includes("auth-token"))), false);
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await page.waitForURL("**/login");
  const loggedOut = await context.request.post(`${site}/api/auth/access-token`, { headers: { Origin: site }, data: {} });
  assert.equal((await loggedOut.json()).signed_out, true);
  await page.goto(`${site}/zh/login`);
  await page.getByRole("button", { name: "使用 Google 登录" }).click();
  await page.waitForURL("**/zh/account");
  await page.getByText(user.email, { exact: true }).waitFor();
  await page.screenshot({ path: path.join(output, "account-mobile.png"), fullPage: true });
  await page.getByRole("button", { name: "退出登录", exact: true }).click();
  await page.waitForURL("**/zh/login");
  await fetch(`${providerOrigin}/test/short-session`, { method: "POST", headers: { "X-Auth-Bridge": bridgeSecret } });
  await page.goto(`${site}/login?return_to=/account`);
  await page.getByLabel("Email address").fill(user.email);
  await page.getByRole("button", { name: "Send code", exact: true }).click();
  await page.getByLabel("Verification code").fill("123456");
  await page.getByRole("button", { name: "Verify and sign in" }).click();
  await page.waitForURL("**/account");
  await page.getByText(user.email, { exact: true }).waitFor();
  assert.ok(refreshCount >= 1, "expired session must refresh through bridge");
  assert.deepEqual(external, []);
  console.log(JSON.stringify({ status: "passed", scope: "browser_and_real_sdk_against_local_protocol_doubles", real_provider_verified: false, checks: ["desktop/mobile", "8-digit OTP failure/success", "6-digit OTP compatibility", "7-digit OTP rejected", "HttpOnly/no refresh JSON", "logout", "Google PKCE callback + locale", "refresh bridge"], refreshCount, screenshots: output }));
} catch (error) {
  console.error(error.stack ?? String(error)); console.error(logs); process.exitCode = 1;
} finally {
  await browser?.close();
  if (child && child.exitCode === null) {
    try { process.kill(-child.pid, "SIGTERM"); } catch { /* already stopped */ }
    await Promise.race([new Promise(resolve => child.once("exit", resolve)), new Promise(resolve => setTimeout(resolve, 5000))]);
  }
  await new Promise(resolve => api.close(resolve));
  rmSync(configDir, { recursive: true, force: true });
  rmSync(dist, { recursive: true, force: true });
  rmSync(temp, { recursive: true, force: true });
}
