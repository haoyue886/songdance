import { accessSession, guestToken, rememberGuest, forgetGuest } from "@/lib/auth/client";
import { savedVisitor } from "@/lib/api/guest";
import { validateAccountDeletion, type AccountDeletion } from "@/lib/api/account-deletion";

export type Account = {
  id: string;
  email: string | null;
  account_deletion_enabled?: boolean;
  deletion?: AccountDeletion | null;
};

export type JobStatus = "queued" | "running" | "succeeded" | "failed";

export type JobStage =
  | "upload"
  | "queued"
  | "preprocessing"
  | "transcribing"
  | "score"
  | "completed";

export type ArtifactType = "raw_midi" | "raw_timeline" | "midi" | "musicxml" | "timeline";
export type DownloadFileType = ArtifactType | "source";

export type JobArtifact = {
  type: ArtifactType;
  status: "succeeded" | "failed";
  size_bytes: number;
  mime_type: string | null;
  error_code: string | null;
};

export type TranscriptionResult = {
  tempo: number | null;
  time_signature: string | null;
  note_count: number | null;
  quality_flags: string | null;
  model_version: string | null;
};

export type QualityReportEnvelope = {
  report_version: string;
  summary: string;
};

export type TranscriptionJob = {
  access_type?: "legacy" | "guest" | "owned";
  guest_access_token?: string | null;
  id: string;
  status: JobStatus;
  stage: JobStage;
  source_type: string;
  start_sec: number;
  end_sec: number;
  attempt_count: number;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  expires_at: string;
  result: TranscriptionResult | null;
  quality_report: QualityReportEnvelope | null;
  artifacts: JobArtifact[];
};

export type CreateJobInput = {
  file: File;
  submissionKey?: string;
  startSec: number;
  endSec: number;
  rightsConfirmed: boolean;
};

export type CreateYoutubeJobInput = {
  url: string;
  startSec: number;
  endSec: number;
  rightsConfirmed: boolean;
};

export class JobsApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code?: string,
    readonly retryAfter?: number,
  ) {
    super(message);
    this.name = "JobsApiError";
  }
}

const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

function jobPath(jobId: string): string {
  return `/jobs/${encodeURIComponent(jobId)}`;
}

async function responseError(response: Response): Promise<JobsApiError> {
  const payload = (await response.json().catch(() => null)) as
    | { detail?: string | { code?: string; message?: string; retry_after?: number } }
    | null;
  const detail = payload?.detail;
  const baseMessage = typeof detail === "string" ? detail : detail?.message ?? "Service unavailable";
  const retryAfter = typeof detail === "object" ? detail?.retry_after : undefined;
  const message = retryAfter
    ? `${baseMessage} Retry after ${formatRetryAfter(retryAfter)}.`
    : baseMessage;
  return new JobsApiError(
    message,
    response.status,
    typeof detail === "object" ? detail?.code : undefined,
    retryAfter,
  );
}

function formatRetryAfter(seconds: number): string {
  if (seconds < 60) return `${Math.ceil(seconds)} seconds`;
  if (seconds < 3600) return `${Math.ceil(seconds / 60)} minutes`;
  return `${Math.ceil(seconds / 3600)} hours`;
}

async function request<T>(path: string, init?: RequestInit, contextJobId?: string): Promise<T> {
  const access = await accessSession();
  const headers = new Headers(init?.headers);
  if (access) headers.set("Authorization", `Bearer ${access.access_token}`);
  const visitor = savedVisitor();
  if (!access && visitor) headers.set("X-Visitor-Token", visitor);
  const jobId = contextJobId ?? path.match(/^\/jobs\/([^/]+)/)?.[1];
  const capability = jobId ? guestToken(decodeURIComponent(jobId)) : null;
  if (capability) headers.set("X-Job-Access", capability);
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, { cache: "no-store", ...init, headers });
  } catch {
    throw new JobsApiError("Network error", 0, "NETWORK_ERROR");
  }

  if (!response.ok) {
    throw await responseError(response);
  }

  let result;
  try {
    const responseBody = await response.text();
    if (!responseBody) return undefined as T;
    result = JSON.parse(responseBody);
  } catch {
    // The server may already have committed even if its response body was lost.
    throw new JobsApiError("Network error", 0, "NETWORK_ERROR");
  }
  if (result && typeof result.id === "string" && typeof result.guest_access_token === "string") rememberGuest(result.id, result.guest_access_token);
  return result as T;
}

export async function claimJob(jobId: string): Promise<TranscriptionJob> {
  const result = await request<TranscriptionJob>(`${jobPath(jobId)}/claim`, { method: "POST" });
  forgetGuest(jobId);
  return result;
}

export async function getAccount(): Promise<Account> {
  const account = await request<Account>("/me");
  if (!account || typeof account.id !== "string" || !account.id || account.email !== null && typeof account.email !== "string"
    || account.account_deletion_enabled !== undefined && typeof account.account_deletion_enabled !== "boolean") {
    throw new JobsApiError("Invalid account response", 502, "ACCOUNT_UNAVAILABLE");
  }
  if (account.deletion !== undefined && account.deletion !== null) validateAccountDeletion(account.deletion, account.id);
  return account;
}

export function createJob(input: CreateJobInput): Promise<TranscriptionJob> {
  const body = new FormData();
  body.set("audio_file", input.file);
  body.set("start_sec", String(input.startSec));
  body.set("end_sec", String(input.endSec));
  body.set("rights_confirmed", String(input.rightsConfirmed));
  return request<TranscriptionJob>("/jobs", {
    method: "POST",
    body,
    headers: input.submissionKey ? { "Idempotency-Key": input.submissionKey } : undefined,
  }).then((job) => {
    if (!job || typeof job.id !== "string" || !job.id) throw new JobsApiError("Network error", 0, "NETWORK_ERROR");
    return job;
  });
}

export function sendUploadStartedEvent(): Promise<void> {
  return request<void>("/events/upload-started", { method: "POST", keepalive: true });
}

export function getYoutubeConfig(): Promise<{ enabled: boolean }> {
  return request<{ enabled: boolean }>("/youtube/config");
}

export function createYoutubeJob(input: CreateYoutubeJobInput): Promise<TranscriptionJob> {
  return request<TranscriptionJob>("/youtube/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      url: input.url,
      start_sec: input.startSec,
      end_sec: input.endSec,
      rights_confirmed: input.rightsConfirmed,
    }),
  });
}

export function getJob(jobId: string, signal?: AbortSignal): Promise<TranscriptionJob> {
  return request<TranscriptionJob>(jobPath(jobId), { signal });
}

const retryKeys = new Map<string, string>();
const pendingRetries = new Map<string, Promise<TranscriptionJob>>();

export function retryJob(jobId: string): Promise<TranscriptionJob> {
  const pending = pendingRetries.get(jobId);
  if (pending) return pending;
  const storageKey = `songdance-retry-key:${jobId}`;
  let key = retryKeys.get(jobId);
  try { key ??= sessionStorage.getItem(storageKey) ?? undefined; } catch { /* Keep the key in memory when storage is unavailable. */ }
  if (!key || !/^[A-Za-z0-9_-]{8,128}$/.test(key)) key = crypto.randomUUID();
  retryKeys.set(jobId, key);
  try { sessionStorage.setItem(storageKey, key); } catch { /* Memory preserves retries in this document. */ }
  const clearKey = () => {
    retryKeys.delete(jobId);
    try { sessionStorage.removeItem(storageKey); } catch { /* A retained key safely replays the previous attempt. */ }
  };
  const result = request<TranscriptionJob>(`${jobPath(jobId)}/retry`, {
    method: "POST",
    headers: { "Idempotency-Key": key },
  }).then((job) => {
    if (!job || job.id !== jobId) throw new JobsApiError("Network error", 0, "NETWORK_ERROR");
    clearKey();
    return job;
  }).catch((error: unknown) => {
    // A missing response (including a truncated success body) may have committed.
    if (error instanceof JobsApiError && error.status >= 400 && error.status < 500 && error.status !== 408) clearKey();
    throw error;
  }).finally(() => {
    pendingRetries.delete(jobId);
  });
  pendingRetries.set(jobId, result);
  return result;
}

export function deleteJob(jobId: string): Promise<void> {
  return request<void>(jobPath(jobId), { method: "DELETE" });
}

export async function getDownloadUrl(
  jobId: string,
  type: DownloadFileType,
  signal?: AbortSignal,
): Promise<string> {
  const ticket = await request<{ path: string; expires_at: number }>(
    `${jobPath(jobId)}/download-url/${type}`,
    { signal },
  );
  const expectedPrefix = `${jobPath(jobId)}/files/${type}?`;
  if (!ticket.path.startsWith(expectedPrefix) || ticket.path.includes("://")) {
    throw new JobsApiError("Invalid download URL", 502, "INVALID_DOWNLOAD_URL");
  }
  return `${API_URL}${ticket.path}`;
}

export async function fetchArtifact(
  jobId: string,
  type: ArtifactType,
  signal?: AbortSignal,
): Promise<Response> {
  let response: Response;
  try {
    const url = await getDownloadUrl(jobId, type, signal);
    response = await fetch(url, { cache: "no-store", signal });
  } catch {
    throw new JobsApiError("Network error", 0, "NETWORK_ERROR");
  }
  if (!response.ok) throw await responseError(response);
  return response;
}

export function sendAnalyticsEvent(
  jobId: string,
  eventName: string,
  properties: Record<string, string>,
): Promise<void> {
  return request<void>("/events", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ event_name: eventName, job_id: jobId, properties }),
    keepalive: true,
  }, jobId);
}
