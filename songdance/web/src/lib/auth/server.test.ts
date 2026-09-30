// @vitest-environment node
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { handleAuth } from "./server";
import { safeReturnPath } from "./return-path";

const sdk = vi.hoisted(() => ({ getUser: vi.fn(), getSession: vi.fn(), signInWithOtp: vi.fn(), verifyOtp: vi.fn(), signInWithOAuth: vi.fn(), exchangeCodeForSession: vi.fn(), signOut: vi.fn() }));
const factory = vi.hoisted(() => vi.fn());
vi.mock("@supabase/ssr", () => ({ createServerClient: (...args: unknown[]) => factory(...args) }));

function request(action: string, body: unknown = {}, cookie = "", origin = "https://site.example") {
  return new NextRequest(`https://site.example/api/auth/${action}`, { method: "POST", headers: { "Content-Type": "application/json", Origin: origin, Cookie: cookie }, body: JSON.stringify(body) });
}

beforeEach(() => {
  vi.resetAllMocks();
  for (const [key, value] of Object.entries({ NEXT_PUBLIC_AUTH_ENABLED: "true", SONGDANCE_AUTH_ENABLED: "true", NEXT_PUBLIC_SITE_URL: "https://site.example", SONGDANCE_SUPABASE_URL: "https://auth.example", SONGDANCE_AUTH_API_URL: "https://api.example", SONGDANCE_SUPABASE_PUBLISHABLE_KEY: "sb_publishable_test", SONGDANCE_AUTH_BRIDGE_SECRET: "x".repeat(40) })) vi.stubEnv(key, value);
  factory.mockReturnValue({ auth: sdk });
  sdk.getUser.mockResolvedValue({ data: { user: { id: "user-a", email: "a@example.test" } }, error: null });
  sdk.getSession.mockResolvedValue({ data: { session: { access_token: "short-access", refresh_token: "NEVER_RETURN_REFRESH", expires_at: 9999999999, user: { id: "user-a" } } } });
  sdk.signOut.mockResolvedValue({ error: null });
  vi.stubGlobal("fetch", vi.fn().mockImplementation(async () => Response.json({ ok: true, challenge: "a".repeat(43) })));
});
afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals(); });

describe("auth BFF", () => {
  it("rejects cross-site requests before touching the SDK", async () => {
    const response = await handleAuth(request("logout", {}, "", "https://evil.example"), "logout");
    expect(response.status).toBe(403);
    expect(factory).not.toHaveBeenCalled();
  });
  it("does not expose refresh tokens or cache session responses", async () => {
    const response = await handleAuth(request("access-token", {}, "songdance-auth-present=1"), "access-token");
    expect(response.status).toBe(200);
    expect(await response.text()).not.toContain("NEVER_RETURN_REFRESH");
    expect(response.headers.get("cache-control")).toContain("no-store");
    expect(response.headers.get("set-cookie")).toContain("HttpOnly");
    expect(response.headers.get("set-cookie")).toContain("Secure");
    expect(sdk.getUser).toHaveBeenCalledBefore(sdk.getSession);
  });
  it("sets Secure based on the parsed HTTPS origin", async () => {
    vi.stubEnv("NEXT_PUBLIC_SITE_URL", "HTTPS://site.example");
    const response = await handleAuth(request("access-token", {}, "songdance-auth-present=1"), "access-token");
    expect(response.status).toBe(200);
    expect(response.headers.get("set-cookie")).toContain("Secure");
  });
  it("distinguishes a visitor from an expired logged-in session", async () => {
    const guest = await handleAuth(request("access-token"), "access-token");
    expect(await guest.json()).toEqual({ signed_out: true });
    expect(sdk.getUser).not.toHaveBeenCalled();
    sdk.getUser.mockResolvedValue({ data: { user: null }, error: { status: 401 } });
    const expired = await handleAuth(request("access-token", {}, "songdance-auth-present=1"), "access-token");
    expect(expired.status).toBe(401);
    expect(await expired.json()).toEqual({ code: "AUTH_EXPIRED" });
    expect(sdk.getSession).not.toHaveBeenCalled();
  });
  it("rejects inconsistent provider user/session identities", async () => {
    sdk.getSession.mockResolvedValue({ data: { session: { user: { id: "different" } } } });
    expect((await handleAuth(request("access-token", {}, "songdance-auth-present=1"), "access-token")).status).toBe(401);
  });
  it("requires the stored challenge before checking an OTP", async () => {
    const result = await handleAuth(request("email/verify", { email: "a@example.test", token: "123456" }), "email/verify");
    expect(result.status).toBe(401);
    expect(sdk.verifyOtp).not.toHaveBeenCalled();
  });
  it("does not expose account-dependent email rejections", async () => {
    const warning = vi.spyOn(console, "warn").mockImplementation(() => {});
    sdk.signInWithOtp.mockResolvedValueOnce({ error: null }).mockResolvedValueOnce({ error: { status: 400, message: "ACCOUNT_PRIVATE" } });
    const accepted = await handleAuth(request("email/start", { email: "a@example.test" }), "email/start");
    const rejected = await handleAuth(request("email/start", { email: "b@example.test" }), "email/start");
    expect(rejected.status).toBe(accepted.status);
    expect(await rejected.json()).toEqual(await accepted.json());
    expect(JSON.stringify(warning.mock.calls)).not.toContain("ACCOUNT_PRIVATE");
    warning.mockRestore();
  });
  it("reserves an attempt and consumes the challenge only after provider success", async () => {
    sdk.verifyOtp.mockResolvedValue({ data: { user: { id: "a" }, session: {} }, error: null });
    const response = await handleAuth(request("email/verify", { email: "a@example.test", token: "123456", return_to: "https://evil.example" }, `songdance-otp-challenge=${"a".repeat(43)}`), "email/verify");
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ ok: true, return_to: "/account" });
    const calls = vi.mocked(fetch).mock.calls.map(([url]) => String(url));
    expect(calls).toEqual(["https://api.example/auth/bridge/otp-attempt", "https://api.example/auth/bridge/otp-consume"]);
  });
  it("does not consume a failed OTP or echo its upstream error", async () => {
    sdk.verifyOtp.mockResolvedValue({ data: {}, error: { message: "PRIVATE_UPSTREAM_DETAILS" } });
    const response = await handleAuth(request("email/verify", { email: "a@example.test", token: "123456" }, `songdance-otp-challenge=${"a".repeat(43)}`), "email/verify");
    expect(response.status).toBe(401);
    expect(await response.text()).not.toContain("PRIVATE_UPSTREAM_DETAILS");
    expect(fetch).toHaveBeenCalledTimes(1);
  });
  it("does not claim logout succeeded when provider revocation failed", async () => {
    sdk.signOut.mockResolvedValue({ error: { message: "provider error" } });
    const response = await handleAuth(request("logout", {}, "songdance-auth-present=1"), "logout");
    expect(response.status).toBe(503);
    expect(response.headers.get("set-cookie")).toBeNull();
  });
  it("rejects mismatched OAuth state without exchanging the code", async () => {
    const response = await handleAuth(new NextRequest(`https://site.example/api/auth/callback?flow=${"a".repeat(64)}&code=code`, { headers: { Cookie: `songdance-oauth-flow=${"b".repeat(64)}` } }), "callback");
    expect(response.status).toBe(303);
    expect(response.headers.get("location")).toContain("https://site.example/login?auth_error=1");
    expect(sdk.exchangeCodeForSession).not.toHaveBeenCalled();
  });
  it("rejects oversized bodies before sending email", async () => {
    const response = await handleAuth(request("email/start", { email: "x".repeat(9000) }), "email/start");
    expect(response.status).toBe(413);
    expect(sdk.signInWithOtp).not.toHaveBeenCalled();
  });
});

describe("return destinations", () => {
  it.each(["https://evil.example", "//evil.example", "/\\evil.example", "/%2f%2fevil.example", "/api/auth/logout", "/account%0d%0aevil", "javascript:alert(1)"])("rejects %s", (input) => expect(safeReturnPath(input)).toBe("/account"));
  it("preserves valid task destinations and locale", () => expect(safeReturnPath("/zh/jobs/abc-123?view=score#play")).toBe("/zh/jobs/abc-123?view=score#play"));
});
