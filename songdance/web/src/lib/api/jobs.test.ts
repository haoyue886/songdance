import { afterEach, describe, expect, it, vi } from "vitest";
import { createJob, createYoutubeJob, getYoutubeConfig, retryJob, sendAnalyticsEvent, sendUploadStartedEvent } from "./jobs";
import { rememberGuest, forgetGuest } from "@/lib/auth/client";

describe("jobs API empty success responses", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("resolves empty 202 analytics responses without parsing JSON", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(null, { status: 202 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(sendUploadStartedEvent()).resolves.toBeUndefined();
    await expect(
      sendAnalyticsEvent("a".repeat(32), "result_viewed", { view: "score" }),
    ).resolves.toBeUndefined();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("attaches a guest capability to the actual /events call", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 202 }));
    vi.stubGlobal("fetch", fetchMock);
    rememberGuest("guest-event-job", "guest-capability");
    try {
      await sendAnalyticsEvent("guest-event-job", "result_viewed", { view: "score" });
      const [url, init] = fetchMock.mock.calls[0];
      expect(url).toContain("/events");
      expect(new Headers(init.headers).get("X-Job-Access")).toBe("guest-capability");
      expect(JSON.parse(init.body).job_id).toBe("guest-event-job");
    } finally { forgetGuest("guest-event-job"); }
  });
});

describe("YouTube jobs API contract", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("reads the feature flag and sends only the selected clip contract", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ enabled: true }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: "youtube-job" }), { status: 201 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(getYoutubeConfig()).resolves.toEqual({ enabled: true });
    await expect(createYoutubeJob({
      url: "https://youtu.be/dQw4w9WgXcQ",
      startSec: 12.5,
      endSec: 42.5,
      rightsConfirmed: true,
    })).resolves.toEqual({ id: "youtube-job" });

    expect(fetchMock.mock.calls[1][0]).toContain("/youtube/jobs");
    expect(JSON.parse(fetchMock.mock.calls[1][1].body as string)).toEqual({
      url: "https://youtu.be/dQw4w9WgXcQ",
      start_sec: 12.5,
      end_sec: 42.5,
      rights_confirmed: true,
    });
  });
});

describe("job submission identities", () => {
  afterEach(() => { vi.unstubAllGlobals(); sessionStorage.clear(); });

  it("sends the supplied create identity without changing multipart fields and allows legacy callers", async () => {
    const fetchMock = vi.fn().mockImplementation(async () => Response.json({ id: "job" }, { status: 201 }));
    vi.stubGlobal("fetch", fetchMock);
    const input = { file: new File(["audio"], "clip.wav"), startSec: 0, endSec: 30, rightsConfirmed: true };
    await createJob({ ...input, submissionKey: "draft-identity" });
    await createJob(input);
    const init = fetchMock.mock.calls[0][1];
    expect(new Headers(init.headers).get("Idempotency-Key")).toBe("draft-identity");
    expect(init.body.get("audio_file")).toBe(input.file);
    expect(init.body.get("start_sec")).toBe("0");
    expect(init.body.get("end_sec")).toBe("30");
    expect(new Headers(fetchMock.mock.calls[1][1].headers).has("Idempotency-Key")).toBe(false);
  });

  it("retains retry identity after network, server, and incomplete response failures, rotating after success", async () => {
    const incomplete = new Response('{"id":', { status: 200 });
    const fetchMock = vi.fn()
      .mockRejectedValueOnce(new TypeError("Offline"))
      .mockResolvedValueOnce(Response.json({ detail: { code: "SUBMISSION_UNAVAILABLE" } }, { status: 503 }))
      .mockResolvedValueOnce(incomplete)
      .mockImplementation(async () => Response.json({ id: "retry-uncertain" }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(retryJob("retry-uncertain")).rejects.toMatchObject({ status: 0 });
    const stored = sessionStorage.getItem("songdance-retry-key:retry-uncertain");
    expect(stored).toMatch(/^[a-f0-9-]{36}$/);
    await expect(retryJob("retry-uncertain")).rejects.toMatchObject({ status: 503 });
    await expect(retryJob("retry-uncertain")).rejects.toMatchObject({ status: 0 });
    await retryJob("retry-uncertain");
    expect(sessionStorage.getItem("songdance-retry-key:retry-uncertain")).toBeNull();
    await retryJob("retry-uncertain");
    const keys = fetchMock.mock.calls.map(([, init]) => new Headers(init.headers).get("Idempotency-Key"));
    expect(keys.slice(0, 4)).toEqual([stored, stored, stored, stored]);
    expect(keys[4]).not.toBe(stored);
  });

  it("treats a lost create response body as an uncertain result", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 201 })));
    await expect(createJob({ file: new File(["audio"], "clip.wav"), startSec: 0, endSec: 30, rightsConfirmed: true, submissionKey: "lost-response-key" }))
      .rejects.toMatchObject({ status: 0, code: "NETWORK_ERROR" });
  });

  it("rotates retry identity after a deterministic conflict", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(Response.json({ detail: { code: "RETRY_NOT_ALLOWED" } }, { status: 409 }))
      .mockResolvedValueOnce(Response.json({ id: "retry-conflict" }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(retryJob("retry-conflict")).rejects.toMatchObject({ status: 409 });
    await retryJob("retry-conflict");
    expect(new Headers(fetchMock.mock.calls[0][1].headers).get("Idempotency-Key"))
      .not.toBe(new Headers(fetchMock.mock.calls[1][1].headers).get("Idempotency-Key"));
  });

  it("coalesces concurrent retries and keeps identities separate between jobs", async () => {
    const fetchMock = vi.fn().mockImplementation(async (url: string) => Response.json({ id: decodeURIComponent(url.split("/").at(-2)!) }));
    vi.stubGlobal("fetch", fetchMock);
    const first = retryJob("retry-concurrent");
    const second = retryJob("retry-concurrent");
    expect(second).toBe(first);
    await Promise.all([first, second, retryJob("retry-other")]);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    const keys = fetchMock.mock.calls.map(([, init]) => new Headers(init.headers).get("Idempotency-Key"));
    expect(new Set(keys).size).toBe(2);
  });

  it("reuses a tab's saved retry key after module initialization", async () => {
    sessionStorage.setItem("songdance-retry-key:retry-saved", "saved-tab-identity");
    const fetchMock = vi.fn().mockResolvedValue(Response.json({ id: "retry-saved" }));
    vi.stubGlobal("fetch", fetchMock);
    await retryJob("retry-saved");
    expect(new Headers(fetchMock.mock.calls[0][1].headers).get("Idempotency-Key")).toBe("saved-tab-identity");
  });
  it.each(["", "null", "{}"])("retains the retry key for an empty or incomplete success body %s", async (body) => {
    const id = `invalid-body-${body.length}-${body.charCodeAt(0) || 0}`;
    const fetchMock = vi.fn().mockResolvedValueOnce(new Response(body, { status: 200 }))
      .mockResolvedValueOnce(Response.json({ id }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(retryJob(id)).rejects.toMatchObject({ status: 0, code: "NETWORK_ERROR" });
    const key = sessionStorage.getItem(`songdance-retry-key:${id}`);
    expect(key).toBeTruthy();
    await retryJob(id);
    expect(new Headers(fetchMock.mock.calls[1][1].headers).get("Idempotency-Key")).toBe(key);
  });
});
