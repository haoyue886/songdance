import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { BillingApiError, createCheckout, createPortal, estimatedSeconds, getBillingConfig, getBillingSummary, validatePaymentUrl, type BillingConfig } from "./billing";
import { AuthClientError } from "@/lib/auth/client";

const auth = vi.hoisted(() => ({ accessSession: vi.fn() }));
vi.mock("@/lib/auth/client", () => ({ accessSession: auth.accessSession, AuthClientError: class extends Error { constructor(readonly code: string) { super(code); } } }));

const config: BillingConfig = {
  usage_enabled: true, checkout_enabled: true, mode: "test",
  pro: { price_minor: 990, currency: "USD", seconds: 1800, max_clip_seconds: 90, min_charge_seconds: 15 },
  free: { monthly_jobs: 1, max_clip_seconds: 90 }, guest: { max_clip_seconds: 30 }, retention_hours: 24, support_email: null,
};
beforeEach(() => { auth.accessSession.mockReset().mockResolvedValue({ access_token: "private-jwt" }); });
afterEach(() => vi.unstubAllGlobals());
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status });
function stubIdentity(owner: () => string, fetcher: (url: string, init: RequestInit) => Promise<Response>) {
  vi.stubGlobal("fetch", (url: string, init: RequestInit) => url.endsWith("/me") && !url.endsWith("/billing/me") ? Promise.resolve(json({ id: owner() })) : fetcher(url, init));
}

describe("billing API contract", () => {
  it("reads public config without authentication or credentials", async () => {
    const fetcher = vi.fn().mockResolvedValue(json(config)); vi.stubGlobal("fetch", fetcher);
    expect(await getBillingConfig()).toEqual(config);
    expect(auth.accessSession).not.toHaveBeenCalled();
    expect(fetcher.mock.calls[0][1].credentials).toBe("omit");
  });
  it("requires verified access and passes no browser plan or balance", async () => {
    const fetcher = vi.fn().mockResolvedValue(json({ enabled: false, plan: null })); vi.stubGlobal("fetch", fetcher);
    await getBillingSummary();
    expect(new Headers(fetcher.mock.calls[0][1].headers).get("Authorization")).toBe("Bearer private-jwt");
    auth.accessSession.mockResolvedValue(null);
    await expect(getBillingSummary()).rejects.toMatchObject({ code: "AUTH_REQUIRED" });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
  it("retains an owner-bound idempotency key after an unknown outcome", async () => {
    const fetcher = vi.fn().mockRejectedValueOnce(new Error("network lost")).mockImplementation(() => Promise.resolve(json({ id: "checkout", status: "uncertain", checkout_url: null, sync_state: "payment_confirming" })));
    let owner = "owner-a";
    stubIdentity(() => owner, fetcher);
    await expect(createCheckout("owner-a")).rejects.toBeInstanceOf(BillingApiError);
    await createCheckout("owner-a"); owner = "owner-b"; await createCheckout("owner-b");
    const inits = fetcher.mock.calls.map(([, init]) => init);
    const keys = inits.map((init) => new Headers(init.headers).get("Idempotency-Key"));
    expect(keys[0]).toBe(keys[1]); expect(keys[2]).not.toBe(keys[0]);
    expect(inits.every((init) => init.body === "{}")).toBe(true);
  });
  it("rotates a key only after the backend reports a definitely failed intent", async () => {
    const fetcher = vi.fn().mockImplementation(() => Promise.resolve(json({ id: "checkout", status: "failed", checkout_url: null, sync_state: "payment_confirming" }))); stubIdentity(() => "retry-owner", fetcher);
    await createCheckout("retry-owner"); await createCheckout("retry-owner");
    expect(new Headers(fetcher.mock.calls[0][1].headers).get("Idempotency-Key")).not.toBe(new Headers(fetcher.mock.calls[1][1].headers).get("Idempotency-Key"));
  });
  it("ends a completed intent when the authenticated backend confirms it", async () => {
    const fetcher = vi.fn()
      .mockImplementationOnce(() => Promise.resolve(json({ id: "checkout", status: "pending", checkout_url: "https://creem.io/checkout" })))
      .mockImplementationOnce(() => Promise.resolve(json({ enabled: false, plan: null, owner_id: "renew-owner", checkout_key: sessionStorage.getItem("songdance-checkout-key:renew-owner"), checkout_status: "completed" })))
      .mockImplementationOnce(() => Promise.resolve(json({ id: "renewal-checkout", status: "pending", checkout_url: "https://creem.io/checkout" })));
    stubIdentity(() => "renew-owner", fetcher);
    await createCheckout("renew-owner"); await getBillingSummary(); await createCheckout("renew-owner");
    expect(new Headers(fetcher.mock.calls[0][1].headers).get("Idempotency-Key")).not.toBe(new Headers(fetcher.mock.calls[2][1].headers).get("Idempotency-Key"));
  });
  it("never clears a new checkout key based on an older completed response", async () => {
    const fetcher = vi.fn().mockImplementation(() => Promise.resolve(json({ id: "new", status: "uncertain", checkout_url: null })));
    stubIdentity(() => "racing-owner", fetcher);
    await createCheckout("racing-owner");
    const current = sessionStorage.getItem("songdance-checkout-key:racing-owner");
    fetcher.mockImplementationOnce(() => Promise.resolve(json({ enabled: false, plan: null, owner_id: "racing-owner", checkout_key: "old-completed-key", checkout_status: "completed" })));
    await getBillingSummary();
    expect(sessionStorage.getItem("songdance-checkout-key:racing-owner")).toBe(current);
  });
  it.each(["https://evil.example/", "https://creem.io.evil.example/", "javascript:alert(1)", "https://user@creem.io/", "https://creem.io/%0a", "https://creem.io:8000/", "https://creem.io\\@evil.example/"])("rejects an unsafe checkout or portal URL %s", (url) => {
    expect(() => validatePaymentUrl(url)).toThrow(BillingApiError);
  });
  it("validates portal redirects and never sends a customer ID", async () => {
    const fetcher = vi.fn().mockResolvedValue(json({ url: "https://www.creem.io/portal/safe" })); stubIdentity(() => "owner", fetcher);
    expect(await createPortal("owner")).toBe("https://www.creem.io/portal/safe");
    expect(fetcher.mock.calls[0][1].body).toBe("{}");
  });
  it("does not purchase or open a portal when another tab has changed the account", async () => {
    const fetcher = vi.fn(); stubIdentity(() => "new-owner", fetcher);
    await expect(createCheckout("old-owner")).rejects.toMatchObject({ code: "AUTH_CHANGED", status: 401 });
    await expect(createPortal("old-owner")).rejects.toMatchObject({ code: "AUTH_CHANGED", status: 401 });
    expect(fetcher).not.toHaveBeenCalled();
  });
  it("maps expired BFF sessions consistently during identity preflight", async () => {
    const fetcher = vi.fn(); vi.stubGlobal("fetch", fetcher);
    auth.accessSession.mockRejectedValue(new AuthClientError("AUTH_EXPIRED"));
    await expect(createCheckout("owner")).rejects.toMatchObject({ code: "AUTH_EXPIRED", status: 401 });
    await expect(createPortal("owner")).rejects.toMatchObject({ code: "AUTH_EXPIRED", status: 401 });
    expect(fetcher).not.toHaveBeenCalled();
  });
  it.each([[1,15],[14.9,15],[15,15],[30.1,31],[90,90]])("previews %s decoded seconds as %s metered seconds", (duration, units) => {
    expect(estimatedSeconds(duration, config)).toBe(units);
  });
});
