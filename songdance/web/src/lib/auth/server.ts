import { createServerClient, type CookieOptions } from "@supabase/ssr";
import { randomBytes, timingSafeEqual } from "node:crypto";
import { isIP } from "node:net";
import { NextRequest, NextResponse } from "next/server";
import { isEmailOtp } from "./otp";
import { safeReturnPath } from "./return-path";

const MARKER = "songdance-auth-present";
const OTP = "songdance-otp-challenge";
const FLOW = "songdance-oauth-flow";
const NO_STORE = { "Cache-Control": "private, no-store", "Vary": "Cookie, Origin" };
class AuthFailure extends Error {
  constructor(readonly status: number, readonly code: string) { super(code); }
}

function config() {
  if (process.env.NEXT_PUBLIC_AUTH_ENABLED !== "true" || process.env.SONGDANCE_AUTH_ENABLED !== "true") {
    throw new AuthFailure(503, "AUTH_DISABLED");
  }
  const site = process.env.NEXT_PUBLIC_SITE_URL;
  const provider = process.env.SONGDANCE_SUPABASE_URL;
  const api = process.env.SONGDANCE_AUTH_API_URL;
  const key = process.env.SONGDANCE_SUPABASE_PUBLISHABLE_KEY;
  const bridge = process.env.SONGDANCE_AUTH_BRIDGE_SECRET;
  if (!site || !provider || !api || !key?.startsWith("sb_publishable_") || !bridge || !/^[A-Za-z0-9_-]{32,128}$/.test(bridge)) {
    throw new AuthFailure(503, "AUTH_UNAVAILABLE");
  }
  for (const value of [site, provider, api]) {
    const u = new URL(value);
    const local = ["localhost", "127.0.0.1", "[::1]"].includes(u.hostname);
    if ((u.protocol !== "https:" && !(process.env.NODE_ENV !== "production" && local && u.protocol === "http:")) || u.username || u.password || !["", "/"].includes(u.pathname) || u.search || u.hash) {
      throw new AuthFailure(503, "AUTH_UNAVAILABLE");
    }
  }
  return { site: new URL(site).origin, provider: provider.replace(/\/$/, ""), api: api.replace(/\/$/, ""), key, bridge, secure: new URL(site).protocol === "https:" };
}

async function readBody(request: NextRequest): Promise<Record<string, unknown>> {
  const reader = request.body?.getReader();
  if (!reader) throw new AuthFailure(400, "AUTH_INVALID");
  const chunks: Uint8Array[] = [];
  let size = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.length;
    if (size > 8192) { await reader.cancel(); throw new AuthFailure(413, "AUTH_INVALID"); }
    chunks.push(value);
  }
  try {
    const data: unknown = JSON.parse(Buffer.concat(chunks).toString("utf8"));
    if (!data || typeof data !== "object" || Array.isArray(data)) throw new Error();
    return data as Record<string, unknown>;
  } catch { throw new AuthFailure(400, "AUTH_INVALID"); }
}

function normalizeEmail(value: unknown): string {
  if (typeof value !== "string" || value.length > 254 || !/^[^@\s]{1,64}@[^@\s]+\.[^@\s]+$/.test(value)) throw new AuthFailure(400, "AUTH_INVALID");
  return value.toLowerCase();
}

export async function handleAuth(request: NextRequest, action: string): Promise<NextResponse> {
  const pending: { name: string; value: string; options: CookieOptions }[] = [];
  let callbackSite: string | undefined;
  try {
    const cfg = config();
    callbackSite = cfg.site;
    if (!["email/start", "email/verify", "google/start", "callback", "access-token", "logout"].includes(action)) throw new AuthFailure(404, "AUTH_INVALID");
    const cookieOptions: CookieOptions = { httpOnly: true, secure: cfg.secure, sameSite: "lax", path: "/" };
    const put = (name: string, value: string, options: CookieOptions = {}) => pending.push({ name, value, options: { ...options, ...cookieOptions } });
    const finish = (payload: unknown, status = 200) => {
      const response = NextResponse.json(payload, { status, headers: NO_STORE });
      for (const cookie of pending) response.cookies.set(cookie.name, cookie.value, cookie.options);
      return response;
    };
    if (action !== "callback") {
      if (request.method !== "POST") throw new AuthFailure(405, "AUTH_INVALID");
      if (request.headers.get("origin") !== cfg.site || !request.headers.get("content-type")?.startsWith("application/json")) {
        throw new AuthFailure(403, "AUTH_ORIGIN_REJECTED");
      }
    } else if (request.method !== "GET") throw new AuthFailure(405, "AUTH_INVALID");

    const callBridge = async (operation: string, body: unknown) => fetch(`${cfg.api}/auth/bridge/${operation}`, {
      method: "POST", headers: { "Content-Type": "application/json", "X-Auth-Bridge": cfg.bridge },
      body: JSON.stringify(body), cache: "no-store", redirect: "error", signal: AbortSignal.timeout(20_000),
    });
    const bridgeData = async (operation: string, body: unknown) => {
      const result = await callBridge(operation, body);
      if (!result.ok) throw new AuthFailure(result.status === 429 ? 429 : result.status === 401 ? 401 : 503, result.status === 429 ? "AUTH_RATE_LIMITED" : "AUTH_UNAVAILABLE");
      return result.json();
    };
    const supabase = createServerClient(cfg.provider, cfg.key, {
      cookieOptions,
      cookies: {
        getAll: () => request.cookies.getAll(),
        setAll: (cookies) => { for (const { name, value, options } of cookies) { request.cookies.set(name, value); put(name, value, options); } },
      },
      global: { fetch: async (input, init) => {
        const url = new URL(input instanceof Request ? input.url : String(input));
        if (url.origin !== new URL(cfg.provider).origin) throw new AuthFailure(503, "AUTH_UNAVAILABLE");
        if (url.pathname.endsWith("/auth/v1/token") && url.searchParams.get("grant_type") === "refresh_token") {
          if (typeof init?.body !== "string") throw new AuthFailure(503, "AUTH_UNAVAILABLE");
          return callBridge("refresh", JSON.parse(init.body));
        }
        return fetch(input, { ...init, cache: "no-store", redirect: "error", signal: AbortSignal.timeout(10_000) });
      } },
    });

    if (action === "email/start") {
      const body = await readBody(request);
      const email = normalizeEmail(body.email);
      // Only use the platform-controlled address on Vercel; do not trust generic XFF.
      const forwarded = process.env.VERCEL === "1" ? request.headers.get("x-vercel-forwarded-for") : null;
      const clientIp = forwarded && isIP(forwarded) ? forwarded : "127.0.0.1";
      const reservation = await bridgeData("otp-start", { email, client_ip: clientIp });
      const { error } = await supabase.auth.signInWithOtp({ email });
      if (error?.status === 429) throw new AuthFailure(429, "AUTH_RATE_LIMITED");
      if (error && (!error.status || error.status >= 500)) throw new AuthFailure(503, "AUTH_UNAVAILABLE");
      // Keep account-dependent provider rejections indistinguishable from accepted requests.
      // Neither this response nor its message promises that an email was delivered.
      if (error) console.warn("auth_email_request_rejected", { status: error.status });
      put(OTP, reservation.challenge, { maxAge: 600 });
      return finish({ ok: true, retry_after: 60 });
    }
    if (action === "email/verify") {
      const body = await readBody(request);
      const email = normalizeEmail(body.email);
      if (!isEmailOtp(body.token)) throw new AuthFailure(400, "AUTH_INVALID");
      const challenge = request.cookies.get(OTP)?.value;
      if (!challenge) throw new AuthFailure(401, "AUTH_INVALID");
      await bridgeData("otp-attempt", { challenge, email });
      const { data, error } = await supabase.auth.verifyOtp({ email, token: body.token, type: "email" });
      if (error || !data.user || !data.session) throw new AuthFailure(401, "AUTH_INVALID");
      await bridgeData("otp-consume", { challenge, email });
      put(OTP, "", { maxAge: 0 });
      put(MARKER, "1", { maxAge: 31_536_000 });
      return finish({ ok: true, return_to: safeReturnPath(body.return_to) });
    }
    if (action === "google/start") {
      const body = await readBody(request);
      const flow = randomBytes(32).toString("hex");
      const callback = new URL("/api/auth/callback", cfg.site);
      callback.searchParams.set("flow", flow);
      callback.searchParams.set("return_to", safeReturnPath(body.return_to));
      const { data, error } = await supabase.auth.signInWithOAuth({ provider: "google", options: { redirectTo: callback.toString(), skipBrowserRedirect: true } });
      if (error || !data.url || new URL(data.url).origin !== new URL(cfg.provider).origin) throw new AuthFailure(503, "AUTH_UNAVAILABLE");
      put(FLOW, flow, { maxAge: 600 });
      return finish({ url: data.url });
    }
    if (action === "callback") {
      const flow = request.nextUrl.searchParams.get("flow") ?? "";
      const expected = request.cookies.get(FLOW)?.value ?? "";
      const code = request.nextUrl.searchParams.get("code");
      if (!/^[a-f0-9]{64}$/.test(flow) || flow.length !== expected.length || !timingSafeEqual(Buffer.from(flow), Buffer.from(expected)) || !code || code.length > 4096) throw new AuthFailure(401, "AUTH_INVALID");
      const { data, error } = await supabase.auth.exchangeCodeForSession(code);
      if (error || !data.session) throw new AuthFailure(401, "AUTH_INVALID");
      put(FLOW, "", { maxAge: 0 }); put(MARKER, "1", { maxAge: 31_536_000 });
      const response = NextResponse.redirect(new URL(safeReturnPath(request.nextUrl.searchParams.get("return_to")), cfg.site), 303);
      Object.entries(NO_STORE).forEach(([name, value]) => response.headers.set(name, value));
      for (const cookie of pending) response.cookies.set(cookie.name, cookie.value, cookie.options);
      return response;
    }
    if (action === "access-token") {
      const hasSession = request.cookies.get(MARKER) || request.cookies.getAll().some(({ name }) => /^sb-.+-auth-token(?:\.\d+)?$/.test(name));
      if (!hasSession) return finish({ signed_out: true }, 401);
      const { data: verified, error } = await supabase.auth.getUser();
      if (error || !verified.user) throw new AuthFailure(error && "status" in error && Number(error.status) >= 500 ? 503 : 401, "AUTH_EXPIRED");
      const { data } = await supabase.auth.getSession();
      if (!data.session || data.session.user.id !== verified.user.id) throw new AuthFailure(401, "AUTH_INVALID");
      put(MARKER, "1", { maxAge: 31_536_000 });
      return finish({ access_token: data.session.access_token, expires_at: data.session.expires_at, user: { id: verified.user.id, email: verified.user.email } });
    }
    if (action === "logout") {
      const { error } = await supabase.auth.signOut({ scope: "local" });
      if (error) throw new AuthFailure(503, "AUTH_UNAVAILABLE");
      put(MARKER, "", { maxAge: 0 }); put(OTP, "", { maxAge: 0 }); put(FLOW, "", { maxAge: 0 });
      return finish({ ok: true });
    }
    throw new AuthFailure(404, "AUTH_INVALID");
  } catch (error) {
    const failure = error instanceof AuthFailure ? error : new AuthFailure(503, "AUTH_UNAVAILABLE");
    if (action === "callback" && callbackSite) {
      const target = safeReturnPath(request.nextUrl.searchParams.get("return_to"));
      const locale = target.match(/^\/(zh|ja|ko|es|pt-br|fr|de)(?:\/|$)/)?.[1];
      const destination = new URL(`${locale ? `/${locale}` : ""}/login`, callbackSite);
      destination.searchParams.set("auth_error", "1");
      destination.searchParams.set("return_to", target);
      const response = NextResponse.redirect(destination, 303);
      Object.entries(NO_STORE).forEach(([name, value]) => response.headers.set(name, value));
      response.cookies.set(FLOW, "", { maxAge: 0, httpOnly: true, secure: callbackSite.startsWith("https:"), sameSite: "lax", path: "/" });
      return response;
    }
    return NextResponse.json({ code: failure.code }, { status: failure.status, headers: NO_STORE });
  }
}
