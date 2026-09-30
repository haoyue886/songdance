export const authEnabled = process.env.NEXT_PUBLIC_AUTH_ENABLED === "true";
export type AccessSession = { access_token: string; expires_at: number; user: { id: string; email?: string } };
let pending: Promise<AccessSession | null> | null = null;

export class AuthClientError extends Error {
  constructor(readonly code: string) { super(code); }
}

export async function authPost(action: string, body: Record<string, unknown> = {}) {
  const response = await fetch(`/api/auth/${action}`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    credentials: "same-origin", cache: "no-store",
  });
  const data = await response.json();
  if (!response.ok) throw new AuthClientError(typeof data.code === "string" ? data.code : "AUTH_UNAVAILABLE");
  return data;
}

export function accessSession(): Promise<AccessSession | null> {
  if (!authEnabled) return Promise.resolve(null);
  if (pending) return pending;
  pending = (async () => {
    const response = await fetch("/api/auth/access-token", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: "{}", credentials: "same-origin", cache: "no-store",
    });
    const data = await response.json();
    if (response.status === 401 && data.signed_out === true) return null;
    if (!response.ok || typeof data.access_token !== "string") throw new AuthClientError(data.code ?? "AUTH_UNAVAILABLE");
    return data as AccessSession;
  })().catch((error) => { throw error instanceof AuthClientError ? error : new AuthClientError("AUTH_UNAVAILABLE"); }).finally(() => { pending = null; });
  return pending;
}

const guestMemory = new Map<string, string>();
export function subscribeGuest(listener: () => void): () => void {
  window.addEventListener("songdance-guest-change", listener);
  window.addEventListener("storage", listener);
  return () => { window.removeEventListener("songdance-guest-change", listener); window.removeEventListener("storage", listener); };
}
function guestChanged(): void { if (typeof window !== "undefined") window.dispatchEvent(new Event("songdance-guest-change")); }
export function rememberGuest(jobId: string, token: string): void {
  guestMemory.set(jobId, token);
  try { sessionStorage.setItem(`songdance-guest:${jobId}`, token); } catch { /* Current tab remains usable. */ }
  guestChanged();
}
export function guestToken(jobId: string): string | null {
  try { return guestMemory.get(jobId) ?? sessionStorage.getItem(`songdance-guest:${jobId}`); } catch { return guestMemory.get(jobId) ?? null; }
}
export function forgetGuest(jobId: string): void {
  guestMemory.delete(jobId);
  try { sessionStorage.removeItem(`songdance-guest:${jobId}`); } catch { /* Ownership is enforced server-side. */ }
  guestChanged();
}
