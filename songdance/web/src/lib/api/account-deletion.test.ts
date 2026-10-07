import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AuthClientError } from "@/lib/auth/client";
import { getAccount } from "./jobs";
import { getAccountDeletion, requestAccountDeletion, type AccountDeletion } from "./account-deletion";

const mocks = vi.hoisted(() => ({ session: vi.fn() }));
vi.mock("@/lib/auth/client", async (original) => ({ ...await original<typeof import("@/lib/auth/client")>(), accessSession: mocks.session }));

const deletion: AccountDeletion = { id: "deletion-1", owner_id: "owner-1", status: "pending", phase: "billing", attempts: 0,
  requested_at: "2026-10-07T10:00:00Z", completed_at: null, error_code: null };
const account = { id: "owner-1", email: "owner@example.test" };
const snapshot = { enabled: true, deletion };
beforeEach(() => {
  vi.clearAllMocks();
  mocks.session.mockResolvedValue({ access_token: "owner-token", expires_at: 0, user: { id: "provider-identity" } });
});
afterEach(() => { vi.unstubAllGlobals(); sessionStorage.clear(); localStorage.clear(); });

describe("account deletion transport", () => {
  it("checks the current business owner and sends explicit confirmation with the same token", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(Response.json(account)).mockResolvedValueOnce(Response.json(snapshot, { status: 202 }));
    vi.stubGlobal("fetch", fetch);
    await expect(requestAccountDeletion("owner-1")).resolves.toEqual(snapshot);
    expect(fetch.mock.calls.map(([url]) => new URL(url).pathname)).toEqual(["/me", "/me"]);
    const write = fetch.mock.calls[1][1];
    expect(write.method).toBe("DELETE");
    expect(JSON.parse(write.body)).toEqual({ confirmation: "DELETE" });
    expect(write.credentials).toBe("omit");
    expect(write.redirect).toBe("error");
    expect(write.cache).toBe("no-store");
    for (const [, init] of fetch.mock.calls) expect(new Headers(init.headers).get("Authorization")).toBe("Bearer owner-token");
    expect(mocks.session).toHaveBeenCalledTimes(1);
  });

  it("does not use a browser timestamp or token expiry as proof of recent sign-in", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(Response.json(account))
      .mockResolvedValueOnce(Response.json({ detail: { code: "REAUTH_REQUIRED" } }, { status: 403 }));
    vi.stubGlobal("fetch", fetch);
    await expect(requestAccountDeletion("owner-1")).rejects.toMatchObject({ code: "REAUTH_REQUIRED", status: 403, uncertain: false });
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it("never sends DELETE after cookies have switched to another business owner", async () => {
    const fetch = vi.fn().mockResolvedValue(Response.json({ id: "owner-2", email: "another@example.test" }));
    vi.stubGlobal("fetch", fetch);
    await expect(requestAccountDeletion("owner-1")).rejects.toMatchObject({ code: "AUTH_CHANGED", status: 401, uncertain: false });
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch.mock.calls[0][1].method).toBeUndefined();
  });

  it("requires an authenticated session rather than falling back to a visitor", async () => {
    mocks.session.mockResolvedValue(null); const fetch = vi.fn(); vi.stubGlobal("fetch", fetch);
    await expect(requestAccountDeletion("owner-1")).rejects.toMatchObject({ code: "AUTH_REQUIRED", status: 401 });
    expect(fetch).not.toHaveBeenCalled();
    mocks.session.mockRejectedValue(new AuthClientError("AUTH_EXPIRED"));
    await expect(getAccountDeletion("owner-1")).rejects.toMatchObject({ code: "AUTH_EXPIRED", status: 401 });
  });

  it.each(["", "null", "{}", '{"enabled":true,"deletion":null}', '{"enabled":true,"deletion":'])
    ("treats an invalid successful DELETE body as unknown without repeating it: %s", async (body) => {
      const fetch = vi.fn().mockResolvedValueOnce(Response.json(account)).mockResolvedValueOnce(new Response(body, { status: 202 }));
      vi.stubGlobal("fetch", fetch);
      await expect(requestAccountDeletion("owner-1")).rejects.toMatchObject({ uncertain: true });
      expect(fetch).toHaveBeenCalledTimes(2);
    });

  it("preserves unknown mutation outcomes after network and server failures", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(Response.json(account)).mockRejectedValueOnce(new TypeError("lost response"))
      .mockResolvedValueOnce(Response.json(account)).mockResolvedValueOnce(Response.json({ detail: { code: "DELETION_UNAVAILABLE" } }, { status: 503 }));
    vi.stubGlobal("fetch", fetch);
    await expect(requestAccountDeletion("owner-1")).rejects.toMatchObject({ code: "NETWORK_ERROR", uncertain: true });
    await expect(requestAccountDeletion("owner-1")).rejects.toMatchObject({ status: 503, uncertain: true });
    expect(fetch.mock.calls.filter(([, init]) => init.method === "DELETE")).toHaveLength(2);
  });

  it("reads an existing request even when new deletion requests are disabled", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(Response.json(account)).mockResolvedValueOnce(Response.json({ ...snapshot, enabled: false }));
    vi.stubGlobal("fetch", fetch);
    await expect(getAccountDeletion("owner-1")).resolves.toEqual({ enabled: false, deletion });
    expect(new URL(fetch.mock.calls[1][0]).pathname).toBe("/me/deletion");
  });

  it.each([
    { ...deletion, status: "deleted" }, { ...deletion, phase: "finished" }, { ...deletion, attempts: -1 },
    { ...deletion, attempts: 1.5 }, { ...deletion, requested_at: "yesterday" }, { ...deletion, completed_at: false },
    { ...deletion, error_code: {} }, { ...deletion, owner_id: null },
  ])("rejects malformed deletion state instead of claiming completion: %j", async (value) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(Response.json(account)).mockResolvedValueOnce(Response.json({ enabled: true, deletion: value })));
    await expect(getAccountDeletion("owner-1")).rejects.toMatchObject({ code: "DELETION_UNAVAILABLE", status: 502, uncertain: false });
  });

  it("rejects another owner's deletion snapshot", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(Response.json(account))
      .mockResolvedValueOnce(Response.json({ enabled: true, deletion: { ...deletion, owner_id: "owner-2" } })));
    await expect(getAccountDeletion("owner-1")).rejects.toMatchObject({ code: "AUTH_CHANGED", status: 401 });
  });

  it("propagates cancellation to both owner checks and status reads", async () => {
    const controller = new AbortController();
    const fetch = vi.fn().mockResolvedValueOnce(Response.json(account)).mockResolvedValueOnce(Response.json({ enabled: true, deletion: null }));
    vi.stubGlobal("fetch", fetch);
    await getAccountDeletion("owner-1", controller.signal); controller.abort();
    for (const [, init] of fetch.mock.calls) expect(init.signal.aborted).toBe(true);
  });
});

describe("account summary compatibility", () => {
  it("accepts old flagless account responses and completed accounts without an email", async () => {
    const completed = { ...deletion, status: "completed", phase: "cleanup", completed_at: "2026-10-07T10:01:00Z" };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(Response.json(account))
      .mockResolvedValueOnce(Response.json({ ...account, email: null, account_deletion_enabled: false, deletion: completed })));
    await expect(getAccount()).resolves.toEqual(account);
    await expect(getAccount()).resolves.toMatchObject({ id: "owner-1", email: null, deletion: completed });
  });

  it("rejects malformed flags and owner-mismatched initial deletion state", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(Response.json({ ...account, account_deletion_enabled: "true" }))
      .mockResolvedValueOnce(Response.json({ ...account, deletion: { ...deletion, owner_id: "owner-2" } })));
    await expect(getAccount()).rejects.toMatchObject({ code: "ACCOUNT_UNAVAILABLE", status: 502 });
    await expect(getAccount()).rejects.toMatchObject({ code: "AUTH_CHANGED", status: 401 });
  });
});
