// Offline browser contract checks. Auth, billing, and hosted Creem pages are protocol doubles.
// This does not verify real identity providers, payment settlement, or live subscriptions.
import assert from "node:assert/strict";
import { createHmac, randomUUID } from "node:crypto";
import { existsSync, mkdtempSync, mkdirSync, readFileSync, writeFileSync, rmSync } from "node:fs";
import { createServer } from "node:http";
import { tmpdir } from "node:os";
import path from "node:path";
import { spawn } from "node:child_process";
import { chromium, expect } from "@playwright/test";

const root = process.cwd();
const temp = mkdtempSync(path.join(tmpdir(), "songdance-billing-ui-"));
const id = path.basename(temp);
const dist = path.join(root, ".next", id);
const configDir = path.join(root, ".next", `${id}-config`);
const output = path.join(root, "test-results", id);
const nextEnvPath = path.join(root, "next-env.d.ts");
const nextEnvBefore = existsSync(nextEnvPath) ? readFileSync(nextEnvPath, "utf8") : null;
mkdirSync(configDir, { recursive: true });
mkdirSync(output, { recursive: true });
writeFileSync(path.join(configDir, "tsconfig.json"), JSON.stringify({ extends: "../../tsconfig.json" }));

const messageFiles = { en: "en", zh: "zh-CN", ja: "ja", ko: "ko", es: "es", "pt-br": "pt-BR", fr: "fr", de: "de" };
const messages = Object.fromEntries(Object.entries(messageFiles).map(([locale, file]) => [locale, JSON.parse(readFileSync(path.join(root, "messages", `${file}.json`), "utf8"))]));
function label(locale, key, values = {}) {
  return messages[locale].billing[key].replace(/\{([A-Za-z]+)\}/g, (_, name) => String(values[name]));
}
const standardConfig = {
  usage_enabled: true, checkout_enabled: true, mode: "test",
  pro: { price_minor: 990, currency: "USD", seconds: 1800, max_clip_seconds: 90, min_charge_seconds: 15 },
  free: { monthly_jobs: 1, max_clip_seconds: 90 }, guest: { max_clip_seconds: 30 },
  retention_hours: 24, support_email: null,
};
function freeSummary(extra = {}) {
  return { enabled: true, plan: "free", unit: "jobs", state: "active", limit: 1, remaining: 1, used: 0, reserved: 0,
    period_start: "2026-10-01T00:00:00Z", period_end: "2026-11-01T00:00:00Z", max_clip_seconds: 90,
    sync_state: "ready", checkout_status: null, subscription_status: null, portal_available: false, ...extra };
}
function proSummary(extra = {}) {
  return freeSummary({ plan: "pro", unit: "seconds", limit: 1800, remaining: 1640, used: 145, reserved: 15,
    subscription_status: "active", portal_available: true, ...extra });
}
function accessJWT(userId) {
  const now = Math.floor(Date.now() / 1000);
  const head = Buffer.from(JSON.stringify({ alg: "HS256", typ: "JWT" })).toString("base64url");
  const body = Buffer.from(JSON.stringify({ sub: userId, aud: "authenticated", role: "authenticated", iat: now, exp: now + 3600 })).toString("base64url");
  const signature = createHmac("sha256", "billing-browser-protocol-double-only").update(`${head}.${body}`).digest("base64url");
  return `${head}.${body}.${signature}`;
}

const tokens = new Map();
const requests = [];
const external = [];
const hosted = [];
const contexts = new Set();
const checks = [];
const failures = [];
let apiOrigin;
let site;
let publicFixture;
let browser;
let child;
let logs = "";
let currentCheck = "startup";

function fixture(extra = {}) {
  const userId = randomUUID();
  const value = { userId, accountId: `billing-owner-${userId}`, email: `${userId}@billing.example.test`,
    accessToken: accessJWT(userId), signedIn: true, config: structuredClone(standardConfig), summary: freeSummary(),
    configFailures: 0, summaryFailure: false, checkoutStatus: "pending", checkoutUrl: `https://www.creem.io/test/checkout/${randomUUID()}`,
    portalUrl: `https://www.creem.io/test/portal/${randomUUID()}`, intents: new Map(), authRequests: [], ...extra };
  tokens.set(value.accessToken, value);
  return value;
}
const count = (value, pathname) => requests.filter((request) => request.owner === value.accountId && request.pathname === pathname);
const listen = (server) => new Promise((resolve, reject) => { server.once("error", reject); server.listen(0, "127.0.0.1", resolve); });
const api = createServer(async (req, res) => {
  try {
    const url = new URL(req.url, apiOrigin ?? "http://localhost");
    res.setHeader("Access-Control-Allow-Origin", site ?? "http://localhost");
    res.setHeader("Access-Control-Allow-Headers", "authorization, content-type, idempotency-key");
    res.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
    if (req.method === "OPTIONS") { res.writeHead(204).end(); return; }
    const json = (data, status = 200) => res.writeHead(status, { "Content-Type": "application/json", "Cache-Control": "no-store" }).end(JSON.stringify(data));
    const owner = tokens.get(req.headers.authorization?.replace(/^Bearer /, ""));
    let body = "";
    for await (const chunk of req) { body += chunk; if (body.length > 16384) { json({}, 413); return; } }
    requests.push({ pathname: url.pathname, method: req.method, owner: owner?.accountId ?? null,
      authorization: req.headers.authorization ?? null, key: req.headers["idempotency-key"] ?? null, origin: req.headers.origin ?? null, body });
    if (url.pathname === "/health") { json({ ok: true }); return; }
    if (url.pathname === "/billing/config") {
      if (publicFixture.configFailures > 0) { publicFixture.configFailures--; json({ detail: { code: "BILLING_UNAVAILABLE" } }, 503); }
      else json(publicFixture.config);
      return;
    }
    if (!owner) { json({ detail: { code: "AUTH_REQUIRED" } }, 401); return; }
    if (url.pathname === "/me") { json({ id: owner.accountId, email: owner.email }); return; }
    if (url.pathname === "/billing/me") {
      json(owner.summaryFailure ? { detail: { code: "BILLING_UNAVAILABLE" } } : { ...owner.summary, owner_id: owner.accountId,
        checkout_key: owner.summary.checkout_key ?? owner.lastCheckoutKey ?? null }, owner.summaryFailure ? 503 : 200);
      return;
    }
    if (url.pathname === "/billing/checkout" && req.method === "POST") {
      const key = req.headers["idempotency-key"];
      if (!key || !/^[A-Za-z0-9_-]{8,128}$/.test(key)) { json({ detail: { code: "INVALID_IDEMPOTENCY_KEY" } }, 422); return; }
      assert.equal(req.headers.origin, site, "checkout origin must be the isolated site");
      assert.deepEqual(JSON.parse(body), {}, "checkout must not submit a browser price or product id");
      if (!owner.intents.has(key)) owner.intents.set(key, randomUUID());
      owner.lastCheckoutKey = key;
      json({ id: owner.intents.get(key), status: owner.checkoutStatus, checkout_url: owner.checkoutStatus === "pending" ? owner.checkoutUrl : null,
        sync_state: owner.checkoutStatus === "completed" ? "ready" : "payment_confirming" });
      return;
    }
    if (url.pathname === "/billing/portal" && req.method === "POST") {
      assert.equal(req.headers.origin, site, "portal origin must be the isolated site");
      assert.deepEqual(JSON.parse(body), {}, "portal identity must come from the backend");
      json({ url: owner.portalUrl }); return;
    }
    json({}, 404);
  } catch (error) { failures.push(`Local API double: ${error.message}`); if (!res.headersSent) res.writeHead(500); res.end(); }
});

async function open(value, viewport = { width: 1280, height: 900 }) {
  publicFixture = value;
  const context = await browser.newContext({ viewport, serviceWorkers: "block" });
  contexts.add(context);
  await context.route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.origin === site && url.pathname.startsWith("/api/auth/")) {
      const action = url.pathname.slice("/api/auth/".length);
      value.authRequests.push({ action, method: request.method(), body: request.postDataJSON() });
      assert.equal(request.method(), "POST");
      let body;
      let status = 200;
      if (action === "access-token") {
        status = value.signedIn ? 200 : 401;
        body = value.signedIn ? { access_token: value.accessToken, expires_at: Math.floor(Date.now() / 1000) + 3600, user: { id: value.userId, email: value.email } } : { signed_out: true };
      } else if (action === "email/start") body = { ok: true };
      else if (action === "email/verify") {
        const input = request.postDataJSON();
        assert.equal(input.email, value.email);
        assert.equal(input.token, "123456");
        value.signedIn = true; body = { ok: true };
      } else if (action === "logout") { value.signedIn = false; body = { ok: true }; }
      else { body = { code: "AUTH_UNAVAILABLE" }; status = 503; }
      await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    } else if (url.protocol === "https:" && [value.checkoutUrl, value.portalUrl].includes(url.href)) {
      hosted.push(url.href);
      await route.fulfill({ contentType: "text/html", body: "<!doctype html><title>Hosted payment protocol double</title><h1>Hosted payment protocol double</h1>" });
    } else if (url.protocol.startsWith("http") && ![site, apiOrigin].includes(url.origin)) {
      external.push(url.href); await route.abort();
    } else await route.continue();
  });
  const page = await context.newPage();
  page.setDefaultTimeout(15000);
  return { context, page };
}
async function close(context) { contexts.delete(context); await context.close(); }
async function geometry(page, name) {
  const errors = await page.evaluate(() => {
    const errors = [];
    if (document.documentElement.scrollWidth > innerWidth + 1) errors.push(`document overflow ${document.documentElement.scrollWidth}/${innerWidth}`);
    const selector = "header h1, header a, header select, main h1, main h2, main p, main dt, main dd, main label, main button, main a, main progress, footer p, footer a";
    const elements = [...document.querySelectorAll(selector)].map((element) => ({ element, box: element.getBoundingClientRect() }))
      .filter(({ element, box }) => box.width > 2 && box.height > 2 && getComputedStyle(element).visibility !== "hidden");
    const name = (element) => (element.textContent?.trim() || element.getAttribute("aria-label") || element.tagName).slice(0, 80);
    for (const { element, box } of elements) {
      if (box.left < -1 || box.right > innerWidth + 1) errors.push(`outside viewport: ${name(element)}`);
      if (element.clientWidth > 0 && element.scrollWidth > element.clientWidth + 2) errors.push(`text/control overflow: ${name(element)}`);
    }
    for (const element of document.querySelectorAll("main a[class~='text-white!'], main button[class~='text-white!']")) {
      if (getComputedStyle(element).color !== "rgb(255, 255, 255)") errors.push(`primary control is not white: ${name(element)}`);
    }
    for (let first = 0; first < elements.length; first++) {
      for (let second = first + 1; second < elements.length; second++) {
        const a = elements[first]; const b = elements[second];
        if (a.element.contains(b.element) || b.element.contains(a.element)) continue;
        const width = Math.min(a.box.right, b.box.right) - Math.max(a.box.left, b.box.left);
        const height = Math.min(a.box.bottom, b.box.bottom) - Math.max(a.box.top, b.box.top);
        if (width > 2 && height > 2) errors.push(`overlap: ${name(a.element)} / ${name(b.element)}`);
      }
    }
    return errors;
  });
  assert.deepEqual(errors, [], `${name} layout must fit without overlapping text or controls`);
}
async function capture(page, name) {
  await page.evaluate(() => document.fonts.ready);
  await page.evaluate(() => window.scrollTo({ top: 0, left: 0, behavior: "instant" }));
  await page.waitForTimeout(100);
  await geometry(page, name);
  await page.screenshot({ path: path.join(output, `${name}.png`), fullPage: true, animations: "disabled",
    style: "nextjs-portal { display: none !important; } html { scroll-behavior: auto !important; }" });
}
async function pair(page, name) {
  await page.setViewportSize({ width: 1280, height: 900 }); await capture(page, `${name}-desktop`);
  await page.setViewportSize({ width: 375, height: 812 }); await capture(page, `${name}-mobile`);
}
async function visit(page, pathname) {
  const response = await page.goto(`${site}${pathname}`);
  assert.equal(response?.status(), 200, `${pathname} must return HTTP 200, not a rendered error response`);
}
async function pricing(page, locale, config) {
  const prefix = locale === "en" ? "" : `/${locale}`;
  await visit(page, `${prefix}/pricing`);
  await expect(page.getByText(label(locale, "freeRules", { count: config.free.monthly_jobs, seconds: config.free.max_clip_seconds }), { exact: true })).toBeVisible();
  const main = page.locator("main");
  await expect(main).toContainText(new Intl.NumberFormat(locale, { style: "currency", currency: config.pro.currency, currencyDisplay: "code" }).format(config.pro.price_minor / 100));
  await expect(main).toContainText(label(locale, "paidRules", { minutes: config.pro.seconds / 60, seconds: config.pro.max_clip_seconds, min: config.pro.min_charge_seconds }));
  await expect(main).toContainText(label(locale, "retention", { hours: config.retention_hours }));
  await expect(main.locator("section[aria-labelledby='free-plan']").getByRole("link")).toHaveCSS("color", "rgb(255, 255, 255)");
  if (config.usage_enabled) await expect(main).toContainText(label(locale, "guestRules", { seconds: config.guest.max_clip_seconds }));
}
async function run(name, work) {
  currentCheck = name;
  try { await work(); checks.push(name); console.log(`PASS ${name}`); }
  catch (error) {
    failures.push(`${name}: ${error.stack ?? error}`);
    for (const context of contexts) for (const page of context.pages()) await page.screenshot({ path: path.join(output, `failure-${checks.length}-${randomUUID()}.png`), fullPage: true }).catch(() => {});
    console.error(`FAIL ${name}: ${error.message}`);
  } finally { for (const context of contexts) await close(context); }
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
      SONGDANCE_SUPABASE_URL: apiOrigin, SONGDANCE_SUPABASE_PUBLISHABLE_KEY: "sb_publishable_billing_protocol_double",
      SONGDANCE_AUTH_BRIDGE_SECRET: "local-billing-browser-protocol-double-only",
      SONGDANCE_NEXT_DIST_DIR: path.relative(root, dist), SONGDANCE_TSCONFIG_PATH: path.relative(root, path.join(configDir, "tsconfig.json")),
    },
  });
  for (const stream of [child.stdout, child.stderr]) stream.on("data", (data) => { logs = (logs + data).slice(-20000); });
  let ready = false;
  for (let attempt = 0; attempt < 90; attempt++) {
    if (child.exitCode !== null) throw new Error("Next.js exited before readiness");
    try { if ((await fetch(`${site}/pricing`, { signal: AbortSignal.timeout(3000) })).ok) { ready = true; break; } } catch { /* startup */ }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  assert.ok(ready, "Next.js readiness timeout");
  browser = await chromium.launch({ headless: true, executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH ?? (process.platform === "darwin" ? "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" : undefined) });

  await run("eight locales use backend price, allowances and disclosures", async () => {
    const value = fixture({ signedIn: false }); const { page } = await open(value);
    for (const locale of Object.keys(messages)) {
      await pricing(page, locale, value.config);
      await pair(page, `pricing-${locale}`);
      if (locale !== "en" && locale !== "zh") await expect(page.getByText(label(locale, "localeFallback"), { exact: true })).toBeVisible();
    }
    assert.ok(requests.filter((request) => request.pathname === "/billing/config").length >= 8, "pricing must fetch backend config");
  });
  await run("backend config changes do not leave hard-coded numeric promises", async () => {
    const config = { ...structuredClone(standardConfig), pro: { price_minor: 1250, currency: "USD", seconds: 2340, max_clip_seconds: 75, min_charge_seconds: 20 },
      free: { monthly_jobs: 2, max_clip_seconds: 80 }, guest: { max_clip_seconds: 25 }, retention_hours: 12 };
    const { page } = await open(fixture({ signedIn: false, config }));
    await pricing(page, "en", config); await pair(page, "pricing-config-override");
  });
  await run("signed-out localized checkout returns through email login to pricing", async () => {
    const value = fixture({ signedIn: false }); const { page } = await open(value, { width: 375, height: 812 });
    await pricing(page, "zh", value.config);
    await page.getByRole("button", { name: label("zh", "testCheckout"), exact: true }).click();
    await page.waitForURL((url) => url.pathname === "/zh/login");
    assert.equal(new URL(page.url()).searchParams.get("return_to"), "/zh/pricing");
    assert.equal(count(value, "/billing/checkout").length, 0, "signed-out users must not create a checkout");
    await capture(page, "checkout-login-zh-mobile");
    await page.getByLabel(messages.zh.auth.email).fill(value.email);
    await page.getByRole("button", { name: messages.zh.auth.sendCode, exact: true }).click();
    await page.getByLabel(messages.zh.auth.code).fill("123456");
    await page.getByRole("button", { name: messages.zh.auth.verify, exact: true }).click();
    await page.waitForURL((url) => url.pathname === "/zh/pricing");
    await page.getByRole("button", { name: label("zh", "testCheckout"), exact: true }).click();
    await page.waitForURL(value.checkoutUrl);
    await expect(page.getByRole("heading", { name: "Hosted payment protocol double" })).toBeVisible();
    assert.equal(count(value, "/billing/checkout").length, 1);
    assert.ok(value.authRequests.some((request) => request.action === "email/verify"));
  });
  await run("return stays pending until authenticated backend entitlement becomes Pro", async () => {
    const value = fixture({ summary: freeSummary({ sync_state: "payment_confirming", checkout_status: "pending" }) });
    const { page } = await open(value); await page.clock.install();
    await visit(page, "/billing/return?status=paid&checkout_id=forged-browser-id");
    await expect(page.getByRole("status").filter({ hasText: label("en", "paymentPending") })).toBeVisible();
    await expect(page.getByText(label("en", "paymentConfirmed"), { exact: true })).toHaveCount(0);
    await pair(page, "billing-return-pending");
    value.summary = proSummary({ checkout_status: "completed" });
    await page.clock.fastForward(3000);
    await expect(page.getByRole("status").filter({ hasText: label("en", "paymentConfirmed") })).toBeVisible();
    await expect(page.locator("header")).toContainText(label("en", "proName"));
    await expect(page.locator("header")).not.toContainText(/Free\s*·/);
    await pair(page, "billing-return-confirmed");
    assert.ok(count(value, "/billing/me").length >= 2, "return must fetch and poll backend billing state");
    assert.equal(count(value, "/billing/checkout").length, 0);
  });
  await run("forged paid query never confirms Free access", async () => {
    const value = fixture(); const { page } = await open(value);
    await visit(page, "/billing/return?status=paid&subscription_id=forged&signature=forged");
    await expect(page.getByRole("status").filter({ hasText: label("en", "paymentMissing") })).toBeVisible();
    await expect(page.getByText(label("en", "paymentConfirmed"), { exact: true })).toHaveCount(0);
    assert.ok(count(value, "/billing/me").length > 0);
    assert.equal(count(value, "/billing/checkout").length, 0);
  });
  await run("uncertain checkout reuses one intent until authoritative completion, with bounded polling", async () => {
    const value = fixture({ checkoutStatus: "uncertain", summary: freeSummary({ sync_state: "payment_confirming", checkout_status: "uncertain" }) });
    const { page } = await open(value); await page.clock.install();
    await pricing(page, "en", value.config);
    await page.getByRole("button", { name: label("en", "testCheckout"), exact: true }).evaluate((button) => { button.click(); button.click(); });
    await page.waitForURL((url) => url.pathname === "/billing/return");
    await expect(page.getByRole("status").filter({ hasText: label("en", "paymentPending") })).toBeVisible();
    assert.equal(count(value, "/billing/checkout").length, 1, "concurrent clicks must create only one request");
    await page.clock.fastForward(61000);
    await expect(page.getByRole("status").filter({ hasText: label("en", "paymentTimeout") })).toBeVisible();
    await pair(page, "billing-return-timeout");
    await expect(page.getByRole("button", { name: label("en", "testCheckout"), exact: true })).toHaveCount(0);
    await page.getByRole("button", { name: label("en", "refresh"), exact: true }).click();
    await expect(page.getByRole("status").filter({ hasText: label("en", "paymentPending") })).toBeVisible();
    assert.equal(count(value, "/billing/checkout").length, 1, "status refresh must not POST another checkout");
    await pricing(page, "en", value.config);
    await page.getByRole("button", { name: label("en", "testCheckout"), exact: true }).click();
    await page.waitForURL((url) => url.pathname === "/billing/return");
    await expect(page.getByRole("status").filter({ hasText: label("en", "paymentPending") })).toBeVisible();
    assert.equal(count(value, "/billing/checkout").length, 2);
    assert.equal(new Set(count(value, "/billing/checkout").map((request) => request.key)).size, 1, "an explicit retry must reuse the owner's idempotency key");
    assert.equal(value.intents.size, 1, "the local backend contract double must retain one intent");
    value.summary = proSummary({ checkout_status: "completed" });
    await page.clock.fastForward(3000);
    await expect(page.getByRole("status").filter({ hasText: label("en", "paymentConfirmed") })).toBeVisible();
    assert.equal(await page.evaluate((owner) => sessionStorage.getItem(`songdance-checkout-key:${owner}`), value.accountId), null,
      "an authoritative terminal summary must clear only its owner's previous checkout key");
    value.summary = freeSummary(); value.checkoutStatus = "pending";
    await pricing(page, "en", value.config);
    await page.getByRole("button", { name: label("en", "testCheckout"), exact: true }).click();
    await page.waitForURL(value.checkoutUrl);
    const checkout = count(value, "/billing/checkout");
    assert.equal(checkout.length, 3);
    assert.notEqual(checkout[2].key, checkout[0].key, "a later purchase may use a new key only after authoritative completion");
    assert.equal(value.intents.size, 2);
    value.summary = proSummary({ checkout_status: "completed", checkout_key: checkout[0].key });
    await visit(page, "/billing/return");
    await expect(page.getByRole("status").filter({ hasText: label("en", "paymentConfirmed") })).toBeVisible();
    assert.equal(await page.evaluate((owner) => sessionStorage.getItem(`songdance-checkout-key:${owner}`), value.accountId), checkout[2].key,
      "a late completed response for the previous intent must not clear a newer pending key");
  });
  await run("exhausted Pro stays Pro, portal URL is backend-only and another context stays private", async () => {
    const pro = fixture({ summary: proSummary({ remaining: 0, used: 1800, reserved: 0 }) });
    const first = await open(pro); await visit(first.page, "/account");
    await expect(first.page.getByText(pro.email, { exact: true })).toBeVisible();
    const main = first.page.locator("main");
    await expect(main.getByText(label("en", "remainingSeconds", { seconds: 0 }), { exact: true })).toBeVisible();
    await expect(main.getByText(label("en", "balanceEmpty"), { exact: true })).toBeVisible();
    await expect(main.getByText(label("en", "proName"), { exact: true })).toBeVisible();
    await expect(main.getByText(label("en", "freeName"), { exact: true })).toHaveCount(0);
    await expect(main.getByRole("button", { name: label("en", "testCheckout"), exact: true })).toHaveCount(0);
    await pair(first.page, "account-pro-exhausted");
    const free = fixture(); const second = await open(free); await visit(second.page, "/account");
    await expect(second.page.getByText(free.email, { exact: true })).toBeVisible();
    await expect(second.page.locator("main").getByText(label("en", "remainingJobs", { count: 1 }), { exact: true })).toBeVisible();
    await expect(second.page.getByText(pro.email, { exact: true })).toHaveCount(0);
    await expect(second.page.locator("main").getByText(label("en", "proName"), { exact: true })).toHaveCount(0);
    await expect(second.page.getByRole("button", { name: label("en", "manageBilling"), exact: true })).toHaveCount(0);
    await pair(second.page, "account-free-other-owner");
    assert.ok(count(free, "/me").length > 0 && count(free, "/billing/me").length > 0);
    assert.ok(count(free, "/billing/me").every((request) => request.authorization === `Bearer ${free.accessToken}`));
    await close(second.context); publicFixture = pro;
    await first.page.getByRole("button", { name: label("en", "manageBilling"), exact: true }).click();
    await first.page.waitForURL(pro.portalUrl);
    assert.equal(count(pro, "/billing/portal").length, 1);
    assert.ok(hosted.includes(pro.portalUrl));
  });
  await run("pricing and account API failures recover using refresh", async () => {
    const value = fixture({ configFailures: 1 }); const { page } = await open(value);
    await visit(page, "/pricing");
    await expect(page.locator("main").getByRole("alert")).toContainText(label("en", "loadError"));
    await page.getByRole("button", { name: label("en", "refresh"), exact: true }).click();
    await expect(page.getByRole("button", { name: label("en", "testCheckout"), exact: true })).toBeVisible();
    value.summaryFailure = true;
    await visit(page, "/account");
    await expect(page.locator("main").getByRole("alert")).toContainText(label("en", "loadError"));
    await pair(page, "account-api-error");
    value.summaryFailure = false;
    await page.getByRole("button", { name: label("en", "refresh"), exact: true }).click();
    await expect(page.getByText(label("en", "remainingJobs", { count: 1 }), { exact: true })).toBeVisible();
    assert.equal(count(value, "/billing/checkout").length, 0);
  });
  await run("return API error retries backend state and signed-out return keeps localized target", async () => {
    const value = fixture({ summaryFailure: true }); const { page } = await open(value);
    await visit(page, "/billing/return");
    await expect(page.locator("main").getByRole("alert")).toContainText(label("en", "paymentUnknown"));
    value.summaryFailure = false; value.summary = proSummary();
    await page.getByRole("button", { name: label("en", "refresh"), exact: true }).click();
    await expect(page.getByRole("status")).toContainText(label("en", "paymentConfirmed"));
    value.signedIn = false;
    await visit(page, "/zh/billing/return?status=paid");
    await expect(page.getByRole("status")).toContainText(label("zh", "authExpired"));
    const href = await page.locator("main").getByRole("link", { name: label("zh", "signIn"), exact: true }).getAttribute("href");
    assert.equal(new URL(href, site).pathname, "/zh/login");
    assert.equal(new URL(href, site).searchParams.get("return_to"), "/zh/billing/return");
  });
  await run("disabled config disables purchase and does not display active proposed allowances", async () => {
    const config = { ...structuredClone(standardConfig), usage_enabled: false, checkout_enabled: false, mode: "unavailable", guest: { max_clip_seconds: 90 } };
    const value = fixture({ config, summary: { enabled: false, plan: null } }); const { page } = await open(value);
    await pricing(page, "en", config);
    await expect(page.getByRole("button", { name: label("en", "notAvailable"), exact: true })).toBeDisabled();
    await expect(page.getByText(label("en", "meterOff"), { exact: true })).toBeVisible();
    await pair(page, "pricing-disabled");
    await visit(page, "/account");
    await expect(page.getByText(label("en", "meterOff"), { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: label("en", "manageBilling"), exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: label("en", "testCheckout"), exact: true })).toHaveCount(0);
    assert.equal(count(value, "/billing/checkout").length, 0);
  });
  await run("support address comes from config and refund page does not invent approved terms", async () => {
    const value = fixture({ signedIn: false }); const { page } = await open(value);
    await visit(page, "/contact");
    await expect(page.getByRole("status")).toContainText(label("en", "supportUnavailable"));
    await expect(page.locator("a[href^='mailto:']")).toHaveCount(0);
    value.config.support_email = "support@billing.example.test";
    await page.reload();
    const email = page.getByRole("link", { name: label("en", "contactEmail"), exact: true });
    await expect(email).toBeVisible();
    assert.equal(new URL(await email.getAttribute("href")).pathname, "support@billing.example.test");
    await pair(page, "contact-configured");
    await visit(page, "/refund");
    await expect(page.getByText(label("en", "refundPolicyBody"), { exact: true })).toBeVisible();
    await expect(page.getByText(label("en", "refundReviewBody"), { exact: true })).toBeVisible();
    await expect(page.getByText(label("en", "refundFilesBody"), { exact: true })).toBeVisible();
    await expect(page.locator("main")).toContainText(label("en", "retention", { hours: 24 }));
    await pair(page, "refund");
  });
  assert.deepEqual(external, [], "all external network traffic must be blocked and reported");
  if (failures.length) throw new Error(failures.join("\n\n"));
  console.log(JSON.stringify({ status: "passed", scope: "browser_against_offline_auth_billing_and_hosted_payment_protocol_doubles",
    real_provider_verified: false, real_payments_verified: false, checks, apiRequests: requests.length,
    checkoutRequests: requests.filter((request) => request.pathname === "/billing/checkout").length,
    portalRequests: requests.filter((request) => request.pathname === "/billing/portal").length, externalRequests: external.length, screenshots: output }));
} catch (error) {
  console.error(`Billing UI smoke failed during ${currentCheck}: ${error.stack ?? String(error)}`);
  console.error(logs); console.error(JSON.stringify({ status: "failed", passedChecks: checks, screenshots: output }));
  process.exitCode = 1;
} finally {
  for (const context of contexts) await close(context);
  await browser?.close();
  if (child && child.exitCode === null) {
    try { process.kill(-child.pid, "SIGTERM"); } catch { /* already stopped */ }
    await Promise.race([new Promise((resolve) => child.once("exit", resolve)), new Promise((resolve) => setTimeout(resolve, 5000))]);
    if (child.exitCode === null) { try { process.kill(-child.pid, "SIGKILL"); } catch { /* already stopped */ } }
  }
  await new Promise((resolve) => api.close(resolve));
  // Next writes this ignored file even with an isolated tsconfig; don't undo another server's update.
  if (existsSync(nextEnvPath) && readFileSync(nextEnvPath, "utf8").includes(`.next/${id}/`)) {
    if (nextEnvBefore === null) rmSync(nextEnvPath);
    else writeFileSync(nextEnvPath, nextEnvBefore);
  }
  rmSync(configDir, { recursive: true, force: true });
  rmSync(dist, { recursive: true, force: true });
  rmSync(temp, { recursive: true, force: true });
}
