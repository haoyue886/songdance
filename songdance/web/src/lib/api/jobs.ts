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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, { cache: "no-store", ...init });
  } catch {
    throw new JobsApiError("Network error", 0, "NETWORK_ERROR");
  }

  if (!response.ok) {
    throw await responseError(response);
  }

  const responseBody = await response.text();
  if (!responseBody) return undefined as T;
  return JSON.parse(responseBody) as T;
}

export function createJob(input: CreateJobInput): Promise<TranscriptionJob> {
  const body = new FormData();
  body.set("audio_file", input.file);
  body.set("start_sec", String(input.startSec));
  body.set("end_sec", String(input.endSec));
  body.set("rights_confirmed", String(input.rightsConfirmed));
  return request<TranscriptionJob>("/jobs", { method: "POST", body });
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

export function retryJob(jobId: string): Promise<TranscriptionJob> {
  return request<TranscriptionJob>(`${jobPath(jobId)}/retry`, {
    method: "POST",
  });
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
  });
}
