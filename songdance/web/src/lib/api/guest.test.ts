import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const KEY = "songdance-visitor-v1";
const token = `v1.${"a".repeat(64)}.${"b".repeat(64)}`;
const session = { visitor_token: token, remaining: 1, reserved: 0, used: 0, max_clip_seconds: 30 };
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status });

beforeEach(() => { vi.resetModules(); localStorage.clear(); });
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe("signed visitor session", () => {
  it("saves the server signature and reuses it after a module reload", async () => {
    const fetcher = vi.fn().mockImplementation(() => Promise.resolve(json(session)));
    vi.stubGlobal("fetch", fetcher);
    const first = await import("./guest");
    expect(await first.guestSession()).toEqual(session);
    expect(localStorage.getItem(KEY)).toBe(token);
    expect(new Headers(fetcher.mock.calls[0][1].headers).has("X-Visitor-Token")).toBe(false);
    expect(fetcher.mock.calls[0][1]).toMatchObject({ method: "POST", credentials: "omit", redirect: "error", cache: "no-store" });
    vi.resetModules();
    const reloaded = await import("./guest");
    expect(reloaded.savedVisitor()).toBe(token);
    await reloaded.guestSession();
    expect(new Headers(fetcher.mock.calls[1][1].headers).get("X-Visitor-Token")).toBe(token);
  });

  it("shares one in-flight request across simultaneous callers and refreshes afterwards", async () => {
    let resolve!: (response: Response) => void;
    const fetcher = vi.fn().mockImplementationOnce(() => new Promise<Response>((done) => { resolve = done; }))
      .mockImplementationOnce(() => Promise.resolve(json({ ...session, remaining: 0, used: 1 })));
    vi.stubGlobal("fetch", fetcher);
    const { guestSession } = await import("./guest");
    const first = guestSession();
    const concurrent = guestSession();
    expect(first).toBe(concurrent);
    expect(fetcher).toHaveBeenCalledTimes(1);
    resolve(json(session));
    await expect(first).resolves.toEqual(session);
    expect((await guestSession()).remaining).toBe(0);
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it.each(["network", "server", "invalid-signature", "invalid-count"])("keeps the stored identity after %s failure and never retries anonymously", async (failure) => {
    localStorage.setItem(KEY, token);
    const fetcher = vi.fn();
    if (failure === "network") fetcher.mockRejectedValueOnce(new Error("offline"));
    else fetcher.mockResolvedValueOnce(json(failure === "server" ? session : {
      ...session, ...(failure === "invalid-signature" ? { visitor_token: "unsigned" } : { remaining: -1 }),
    }, failure === "server" ? 503 : 200));
    fetcher.mockImplementationOnce(() => Promise.resolve(json(session)));
    vi.stubGlobal("fetch", fetcher);
    const { guestSession, savedVisitor } = await import("./guest");
    await expect(guestSession()).rejects.toThrow();
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(savedVisitor()).toBe(token);
    expect(localStorage.getItem(KEY)).toBe(token);
    await guestSession();
    for (const [, init] of fetcher.mock.calls) expect(new Headers(init.headers).get("X-Visitor-Token")).toBe(token);
  });

  it("retains the signature in memory when browser storage is unavailable", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("blocked"); });
    const fetcher = vi.fn().mockImplementation(() => Promise.resolve(json(session)));
    vi.stubGlobal("fetch", fetcher);
    const { guestSession, savedVisitor } = await import("./guest");
    await guestSession();
    expect(savedVisitor()).toBe(token);
    await guestSession();
    expect(new Headers(fetcher.mock.calls[1][1].headers).get("X-Visitor-Token")).toBe(token);
  });
});
