import { afterEach, describe, expect, it, vi } from "vitest";
import { createYoutubeJob, getYoutubeConfig, sendAnalyticsEvent, sendUploadStartedEvent } from "./jobs";
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
