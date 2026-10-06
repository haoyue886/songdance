import { accessSession, AuthClientError } from "@/lib/auth/client";

const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export type BillingConfig = {
  usage_enabled: boolean;
  checkout_enabled: boolean;
  mode: "test" | "unavailable";
  pro: { price_minor: number; currency: string; seconds: number; max_clip_seconds: number; min_charge_seconds: number };
  free: { monthly_jobs: number; max_clip_seconds: number };
  guest: { max_clip_seconds: number };
  retention_hours: number;
  support_email: string | null;
};
export type BillingSummary = {
  owner_id?: string;
  enabled: boolean;
  plan: "free" | "pro" | null;
  unit?: "jobs" | "seconds";
  state?: "active" | "frozen" | "revoked";
  limit?: number;
  remaining?: number;
  used?: number;
  reserved?: number;
  period_start?: string;
  period_end?: string;
  max_clip_seconds?: number;
  sync_state?: "ready" | "payment_confirming" | "review_required";
  checkout_status?: "creating" | "pending" | "uncertain" | "completed" | "failed" | "expired" | null;
  checkout_key?: string | null;
  subscription_status?: string | null;
  portal_available?: boolean;
};
export type CheckoutReply = { id: string; status: NonNullable<BillingSummary["checkout_status"]>; checkout_url: string | null; sync_state: string };

export class BillingApiError extends Error {
  constructor(readonly code: string, readonly status = 0) { super(code); }
}

async function verifiedSession() {
  try {
    const session = await accessSession();
    if (!session) throw new BillingApiError("AUTH_REQUIRED", 401);
    return session;
  } catch (error) {
    if (error instanceof BillingApiError) throw error;
    throw new BillingApiError(error instanceof AuthClientError ? error.code : "AUTH_UNAVAILABLE", error instanceof AuthClientError && ["AUTH_EXPIRED", "AUTH_INVALID", "AUTH_REVOKED"].includes(error.code) ? 401 : 503);
  }
}

async function request(path: string, init: RequestInit = {}, authenticated = true, token?: string): Promise<unknown> {
  const headers = new Headers(init.headers);
  if (authenticated && !token) {
    const session = await verifiedSession();
    headers.set("Authorization", `Bearer ${session.access_token}`);
  }
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let response: Response;
  try {
    const timeout = AbortSignal.timeout(init.method === "POST" ? 45_000 : 15_000);
    const signal = init.signal ? AbortSignal.any([init.signal, timeout]) : timeout;
    response = await fetch(`${API_URL}${path}`, { ...init, signal, headers, credentials: "omit", cache: "no-store", redirect: "error" });
  } catch {
    throw new BillingApiError("NETWORK_ERROR");
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new BillingApiError(typeof body?.detail?.code === "string" ? body.detail.code : "BILLING_UNAVAILABLE", response.status);
  if (!body || typeof body !== "object" || Array.isArray(body)) throw new BillingApiError("BILLING_UNAVAILABLE", 502);
  return body;
}

export async function getBillingConfig(signal?: AbortSignal): Promise<BillingConfig> {
  const value = await request("/billing/config", { signal }, false) as BillingConfig;
  const counts = [value.pro?.price_minor, value.pro?.seconds, value.pro?.max_clip_seconds,
    value.pro?.min_charge_seconds, value.free?.monthly_jobs, value.free?.max_clip_seconds,
    value.guest?.max_clip_seconds, value.retention_hours];
  if (typeof value.usage_enabled !== "boolean" || typeof value.checkout_enabled !== "boolean"
    || !["test", "unavailable"].includes(value.mode) || value.pro?.currency !== "USD"
    || counts.some((number) => !Number.isSafeInteger(number) || number <= 0)
    || value.checkout_enabled && value.mode !== "test") throw new BillingApiError("BILLING_UNAVAILABLE", 502);
  return value;
}

export async function getBillingSummary(signal?: AbortSignal): Promise<BillingSummary> {
  const value = await request("/billing/me", { signal }) as BillingSummary;
  if (typeof value.enabled !== "boolean" || !["free", "pro", null].includes(value.plan)) throw new BillingApiError("BILLING_UNAVAILABLE", 502);
  if (value.enabled && (![value.limit, value.remaining, value.reserved, value.used].every((number) => typeof number === "number" && Number.isSafeInteger(number) && number >= 0)
    || !["jobs", "seconds"].includes(value.unit ?? "") || !value.period_end || !Number.isFinite(Date.parse(value.period_end)))) throw new BillingApiError("BILLING_UNAVAILABLE", 502);
  if (value.owner_id && value.checkout_key && ["completed", "failed", "expired"].includes(value.checkout_status ?? "")) clearCheckoutKey(value.owner_id, value.checkout_key);
  return value;
}

export function validatePaymentUrl(value: unknown): string {
  if (typeof value !== "string" || value.length > 8192) throw new BillingApiError("INVALID_PAYMENT_URL", 502);
  let url: URL;
  try { url = new URL(value); } catch { throw new BillingApiError("INVALID_PAYMENT_URL", 502); }
  let decoded: string;
  try { decoded = decodeURIComponent(value); } catch { throw new BillingApiError("INVALID_PAYMENT_URL", 502); }
  if (url.protocol !== "https:" || !["creem.io", "www.creem.io"].includes(url.hostname)
    || url.username || url.password || url.port && url.port !== "443" || /[\u0000-\u0020\u007f\\]/.test(decoded)) throw new BillingApiError("INVALID_PAYMENT_URL", 502);
  return value;
}

const keys = new Map<string, string>();
function checkoutKey(ownerId: string): string {
  const storageKey = `songdance-checkout-key:${ownerId}`;
  let key = keys.get(ownerId);
  try { key ??= sessionStorage.getItem(storageKey) ?? undefined; } catch { /* Memory survives transient failures. */ }
  if (!key || !/^[A-Za-z0-9_-]{8,128}$/.test(key)) key = crypto.randomUUID();
  keys.set(ownerId, key);
  try { sessionStorage.setItem(storageKey, key); } catch { /* Server also reuses open intents. */ }
  return key;
}
function clearCheckoutKey(ownerId: string, expectedKey: string): void {
  let current = keys.get(ownerId);
  try { current ??= sessionStorage.getItem(`songdance-checkout-key:${ownerId}`) ?? undefined; } catch { /* Memory is sufficient in this document. */ }
  if (current !== expectedKey) return;
  keys.delete(ownerId);
  try { sessionStorage.removeItem(`songdance-checkout-key:${ownerId}`); } catch { /* A stale key safely returns the same intent. */ }
}

export async function createCheckout(ownerId: string): Promise<CheckoutReply> {
  const session = await verifiedSession();
  const account = await request("/me", {}, true, session.access_token) as { id?: unknown };
  if (account.id !== ownerId) throw new BillingApiError("AUTH_CHANGED", 401);
  const key = checkoutKey(ownerId);
  const result = await request("/billing/checkout", { method: "POST", body: "{}",
    headers: { "Content-Type": "application/json", "Idempotency-Key": key } }, true, session.access_token) as CheckoutReply;
  if (typeof result.id !== "string" || !["creating", "pending", "uncertain", "completed", "failed", "expired"].includes(result.status)) throw new BillingApiError("BILLING_UNAVAILABLE", 502);
  if (result.checkout_url !== null) result.checkout_url = validatePaymentUrl(result.checkout_url);
  if (["completed", "failed", "expired"].includes(result.status)) clearCheckoutKey(ownerId, key);
  return result;
}

export async function createPortal(ownerId: string): Promise<string> {
  const session = await verifiedSession();
  const account = await request("/me", {}, true, session.access_token) as { id?: unknown };
  if (account.id !== ownerId) throw new BillingApiError("AUTH_CHANGED", 401);
  const result = await request("/billing/portal", { method: "POST", body: "{}", headers: { "Content-Type": "application/json" } }, true, session.access_token) as { url?: unknown };
  return validatePaymentUrl(result.url);
}

export function estimatedSeconds(duration: number, config: BillingConfig): number {
  return Math.max(config.pro.min_charge_seconds, Math.ceil(duration));
}

export function notifyBillingChanged(): void {
  window.dispatchEvent(new Event("songdance-billing-change"));
}
