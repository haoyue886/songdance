import { beforeEach, afterEach, expect, it, vi } from "vitest";

beforeEach(() => { vi.resetModules(); vi.stubEnv("NEXT_PUBLIC_AUTH_ENABLED", "true"); });
afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals(); vi.resetModules(); sessionStorage.clear(); });

it("only treats an explicit signed-out response as a guest", async () => {
  const fetchMock = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ signed_out: true }), { status: 401 }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ code: "AUTH_EXPIRED" }), { status: 401 }));
  vi.stubGlobal("fetch", fetchMock);
  const { accessSession } = await import("./client");
  expect(await accessSession()).toBeNull();
  await expect(accessSession()).rejects.toThrow("AUTH_EXPIRED");
});

it("coalesces concurrent refresh requests without persisting credentials", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ access_token: "access", expires_at: 12345, user: { id: "u" } }))));
  const { accessSession } = await import("./client");
  const results = await Promise.all([accessSession(), accessSession(), accessSession()]);
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(results[0]?.access_token).toBe("access");
  expect(localStorage.length).toBe(0);
  expect(sessionStorage.length).toBe(0);
});

it("keeps a guest task usable when session storage is unavailable", async () => {
  const { rememberGuest, guestToken, forgetGuest } = await import("./client");
  const spy = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("QuotaExceeded"); });
  rememberGuest("job", "guest-secret");
  expect(guestToken("job")).toBe("guest-secret");
  forgetGuest("job");
  expect(guestToken("job")).toBeNull();
  spy.mockRestore();
});
