import { accessSession, AuthClientError } from "@/lib/auth/client";

const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export type AccountDeletion = {
  id: string;
  owner_id: string;
  status: "pending" | "retry" | "review" | "completed";
  phase: "billing" | "cleanup";
  attempts: number;
  requested_at: string;
  completed_at: string | null;
  error_code: string | null;
};

export type AccountDeletionSnapshot = { enabled: boolean; deletion: AccountDeletion | null };

export class AccountDeletionApiError extends Error {
  constructor(readonly code: string, readonly status = 0, readonly uncertain = false) { super(code); }
}

export function validateAccountDeletion(value: unknown, ownerId: string): AccountDeletion {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new AccountDeletionApiError("DELETION_UNAVAILABLE", 502);
  const deletion = value as AccountDeletion;
  if (typeof deletion.owner_id === "string" && deletion.owner_id !== ownerId) throw new AccountDeletionApiError("AUTH_CHANGED", 401);
  if (typeof deletion.id !== "string" || !deletion.id || deletion.owner_id !== ownerId
    || !["pending", "retry", "review", "completed"].includes(deletion.status)
    || !["billing", "cleanup"].includes(deletion.phase)
    || !Number.isSafeInteger(deletion.attempts) || deletion.attempts < 0
    || typeof deletion.requested_at !== "string" || !Number.isFinite(Date.parse(deletion.requested_at))
    || deletion.completed_at !== null && (typeof deletion.completed_at !== "string" || !Number.isFinite(Date.parse(deletion.completed_at)))
    || deletion.error_code !== null && (typeof deletion.error_code !== "string" || deletion.error_code.length > 128)) {
    throw new AccountDeletionApiError("DELETION_UNAVAILABLE", 502);
  }
  return deletion;
}

function validateSnapshot(value: unknown, ownerId: string): AccountDeletionSnapshot {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new AccountDeletionApiError("DELETION_UNAVAILABLE", 502);
  const snapshot = value as AccountDeletionSnapshot;
  if (typeof snapshot.enabled !== "boolean" || snapshot.deletion === undefined) throw new AccountDeletionApiError("DELETION_UNAVAILABLE", 502);
  return { enabled: snapshot.enabled, deletion: snapshot.deletion === null ? null : validateAccountDeletion(snapshot.deletion, ownerId) };
}

async function request(path: string, token: string, init: RequestInit = {}): Promise<unknown> {
  const deleting = init.method === "DELETE";
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${token}`);
  let response: Response;
  try {
    const timeout = AbortSignal.timeout(deleting ? 45_000 : 15_000);
    const signal = init.signal ? AbortSignal.any([init.signal, timeout]) : timeout;
    response = await fetch(`${API_URL}${path}`, { ...init, headers, signal, credentials: "omit", cache: "no-store", redirect: "error" });
  } catch {
    throw new AccountDeletionApiError("NETWORK_ERROR", 0, deleting);
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new AccountDeletionApiError(typeof body?.detail?.code === "string" ? body.detail.code : "DELETION_UNAVAILABLE", response.status, deleting && (response.status >= 500 || response.status === 408));
  if (!body || typeof body !== "object" || Array.isArray(body)) throw new AccountDeletionApiError("DELETION_UNAVAILABLE", 502, deleting);
  return body;
}

async function currentToken(ownerId: string, signal?: AbortSignal): Promise<string> {
  let session;
  try { session = await accessSession(); }
  catch (error) {
    const code = error instanceof AuthClientError ? error.code : "AUTH_UNAVAILABLE";
    throw new AccountDeletionApiError(code, ["AUTH_EXPIRED", "AUTH_INVALID", "AUTH_REVOKED"].includes(code) ? 401 : 503);
  }
  if (!session) throw new AccountDeletionApiError("AUTH_REQUIRED", 401);
  const account = await request("/me", session.access_token, { signal }) as { id?: unknown };
  if (account.id !== ownerId) throw new AccountDeletionApiError("AUTH_CHANGED", 401);
  return session.access_token;
}

export async function getAccountDeletion(ownerId: string, signal?: AbortSignal): Promise<AccountDeletionSnapshot> {
  const token = await currentToken(ownerId, signal);
  return validateSnapshot(await request("/me/deletion", token, { signal }), ownerId);
}

export async function requestAccountDeletion(ownerId: string): Promise<AccountDeletionSnapshot> {
  const token = await currentToken(ownerId);
  const result = await request("/me", token, { method: "DELETE", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ confirmation: "DELETE" }) });
  try {
    const snapshot = validateSnapshot(result, ownerId);
    if (!snapshot.deletion) throw new AccountDeletionApiError("DELETION_UNAVAILABLE", 502);
    return snapshot;
  } catch (error) {
    // A malformed success body must not trigger another destructive request.
    throw new AccountDeletionApiError(error instanceof AccountDeletionApiError ? error.code : "DELETION_UNAVAILABLE", error instanceof AccountDeletionApiError ? error.status : 502, true);
  }
}
