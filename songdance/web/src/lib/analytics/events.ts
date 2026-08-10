import { sendAnalyticsEvent } from "@/lib/api/jobs";

type AnalyticsEventMap = {
  result_viewed: { view: "score" | "roll" };
  view_changed: { view: "score" | "roll" };
  playback_started: { mode: "source" | "midi" };
  format_downloaded: { format: "raw_midi" | "midi" | "musicxml" | "pdf" };
};

export function trackEvent<Name extends keyof AnalyticsEventMap>(
  jobId: string,
  eventName: Name,
  properties: AnalyticsEventMap[Name],
): void {
  if (!isSafeJobId(jobId)) return;
  void sendAnalyticsEvent(jobId, eventName, properties).catch(() => undefined);
}

function isSafeJobId(jobId: string): boolean {
  return /^[A-Za-z0-9_-]{32,64}$/.test(jobId);
}
