const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
const KEY = "songdance-visitor-v1";
let memory: string | null = null;
let pending: Promise<GuestSession> | null = null;

export type GuestSession = { visitor_token: string; remaining: number; reserved: number; used: number; max_clip_seconds: number };
export function savedVisitor(): string | null {
  try { return memory ?? localStorage.getItem(KEY); } catch { return memory; }
}

export function guestSession(): Promise<GuestSession> {
  if (pending) return pending;
  pending = (async () => {
    const token = savedVisitor();
    const response = await fetch(`${API_URL}/guest/session`, {
      method: "POST", headers: token ? { "X-Visitor-Token": token } : {},
      credentials: "omit", cache: "no-store", redirect: "error", signal: AbortSignal.timeout(15_000),
    });
    const value = await response.json() as GuestSession;
    if (!response.ok || !/^v1\.[a-f0-9]{64}\.[a-f0-9]{64}$/.test(value.visitor_token)
      || ![value.remaining, value.reserved, value.used].every((n) => n === 0 || n === 1)) throw new Error("Visitor trial unavailable");
    memory = value.visitor_token;
    try { localStorage.setItem(KEY, value.visitor_token); } catch { /* Current tab still works. */ }
    return value;
  })().finally(() => { pending = null; });
  return pending;
}
