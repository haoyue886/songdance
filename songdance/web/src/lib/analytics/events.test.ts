import { beforeEach, describe, expect, it, vi } from "vitest";
import { trackEvent } from "./events";

const mocks = vi.hoisted(() => ({ sendAnalyticsEvent: vi.fn() }));

vi.mock("@/lib/api/jobs", () => ({ sendAnalyticsEvent: mocks.sendAnalyticsEvent }));

describe("privacy-safe analytics", () => {
  beforeEach(() => mocks.sendAnalyticsEvent.mockReset().mockResolvedValue(undefined));

  it("sends only the typed event name, task token and view", () => {
    const jobId = "a".repeat(32);
    trackEvent(jobId, "result_viewed", { view: "score" });
    expect(mocks.sendAnalyticsEvent).toHaveBeenCalledWith(jobId, "result_viewed", {
      view: "score",
    });
  });

  it("drops malformed task identifiers", () => {
    trackEvent("https://example.com/private", "result_viewed", { view: "roll" });
    expect(mocks.sendAnalyticsEvent).not.toHaveBeenCalled();
  });

  it("sends playback and each export format without URLs or filenames", () => {
    const jobId = "b".repeat(32);

    trackEvent(jobId, "playback_started", { mode: "source" });
    trackEvent(jobId, "format_downloaded", { format: "midi" });
    trackEvent(jobId, "format_downloaded", { format: "musicxml" });
    trackEvent(jobId, "format_downloaded", { format: "pdf" });

    expect(mocks.sendAnalyticsEvent.mock.calls).toEqual([
      [jobId, "playback_started", { mode: "source" }],
      [jobId, "format_downloaded", { format: "midi" }],
      [jobId, "format_downloaded", { format: "musicxml" }],
      [jobId, "format_downloaded", { format: "pdf" }],
    ]);
  });
});
