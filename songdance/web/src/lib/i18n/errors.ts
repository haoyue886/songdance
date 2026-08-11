type Translate = (key: string, values?: Record<string, string | number>) => string;

const ERROR_KEYS: Record<string, string> = {
  NETWORK_ERROR: "network",
  INVALID_DOWNLOAD_URL: "invalidDownload",
  NO_NOTES_DETECTED: "noNotes",
  DELETE_FAILED: "deleteFailed",
  QUEUE_UNAVAILABLE: "service",
  CAPACITY_UNAVAILABLE: "service",
  YOUTUBE_DISABLED: "youtubeDisabled",
  INVALID_YOUTUBE_URL: "invalidInput",
};

const QUOTA_ERROR_KEYS: Record<string, string> = {
  ACTIVE_JOB_LIMIT: "activeJobLimit",
  HOURLY_LIMIT: "hourlyLimit",
  GLOBAL_CAPACITY: "globalCapacity",
  DAILY_CAPACITY: "dailyCapacity",
};

export function localizeError(error: unknown, t: Translate): string {
  if (!error || typeof error !== "object") return t("unknown");
  const code = "code" in error && typeof error.code === "string" ? error.code : undefined;
  const status = "status" in error && typeof error.status === "number" ? error.status : 0;
  const retryAfter = "retryAfter" in error && typeof error.retryAfter === "number"
    ? Math.max(1, Math.ceil(error.retryAfter))
    : undefined;
  const quotaKey = code ? QUOTA_ERROR_KEYS[code] : undefined;
  if (quotaKey && retryAfter) return t(quotaKey, { seconds: retryAfter });
  const key = code ? ERROR_KEYS[code] : undefined;
  if (key) return t(key);
  if (status === 429) return t("rateLimit");
  if (status >= 400 && status < 500) return t("invalidInput");
  if (status === 0 && "name" in error && error.name !== "JobsApiError") return t("unknown");
  return t("service");
}

export function localizeJobError(code: string | null, t: Translate): string {
  const key = code ? ERROR_KEYS[code] : undefined;
  return t(key ?? "unknown");
}
