import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useUploadBilling } from "./use-upload-billing";
import { type BillingConfig, type BillingSummary } from "@/lib/api/billing";

const mocks = vi.hoisted(() => ({ access: vi.fn(), config: vi.fn(), summary: vi.fn(), guest: vi.fn() }));
vi.mock("@/lib/auth/client", () => ({ authEnabled: true, accessSession: mocks.access }));
vi.mock("@/lib/api/billing", () => ({ getBillingConfig: mocks.config, getBillingSummary: mocks.summary }));
vi.mock("@/lib/api/guest", () => ({ guestSession: mocks.guest }));
const config: BillingConfig = { usage_enabled: true, checkout_enabled: true, mode: "test", pro: { price_minor: 990, currency: "USD", seconds: 1800, max_clip_seconds: 90, min_charge_seconds: 15 }, free: { monthly_jobs: 1, max_clip_seconds: 90 }, guest: { max_clip_seconds: 30 }, retention_hours: 24, support_email: null };
beforeEach(() => { vi.clearAllMocks(); mocks.config.mockResolvedValue(config); mocks.access.mockResolvedValue(null); });

describe("upload billing admission preview", () => {
  it("uses the public guest cap only after the session is confirmed signed out", async () => {
    const { result } = renderHook(() => useUploadBilling());
    await waitFor(() => expect(result.current.pending).toBe(false));
    expect(result.current.maxSeconds).toBe(30);
    expect(mocks.summary).not.toHaveBeenCalled();
    expect(mocks.guest).not.toHaveBeenCalled();
  });
  it("loads a visitor ledger only when the guest feature is enabled", async () => {
    mocks.config.mockResolvedValue({ ...config, guest_usage_enabled: true });
    mocks.guest.mockResolvedValue({ visitor_token: "signed", remaining: 0, reserved: 0, used: 1, max_clip_seconds: 30 });
    const { result } = renderHook(() => useUploadBilling());
    await waitFor(() => expect(result.current.pending).toBe(false));
    expect(result.current.data?.guest?.remaining).toBe(0);
    expect(mocks.guest).toHaveBeenCalledTimes(1);
    expect(mocks.summary).not.toHaveBeenCalled();
  });
  it("blocks admission when the visitor ledger cannot be loaded", async () => {
    mocks.config.mockResolvedValue({ ...config, guest_usage_enabled: true });
    mocks.guest.mockRejectedValue(new Error("unavailable"));
    const { result } = renderHook(() => useUploadBilling());
    await waitFor(() => expect(result.current.failed).toBe(true));
    expect(result.current.data).toBeNull();
  });
  it("does not create a visitor identity for a signed-in user", async () => {
    mocks.config.mockResolvedValue({ ...config, guest_usage_enabled: true });
    mocks.access.mockResolvedValue({ access_token: "jwt" });
    mocks.summary.mockResolvedValue({ enabled: true, plan: "free", remaining: 1, max_clip_seconds: 90 });
    const { result } = renderHook(() => useUploadBilling());
    await waitFor(() => expect(result.current.data?.summary?.remaining).toBe(1));
    expect(mocks.guest).not.toHaveBeenCalled();
  });
  it("never degrades an unavailable authenticated account into a guest", async () => {
    mocks.access.mockResolvedValue({ access_token: "jwt" }); mocks.summary.mockRejectedValue(new Error("revoked"));
    const { result } = renderHook(() => useUploadBilling());
    await waitFor(() => expect(result.current.failed).toBe(true));
    expect(result.current.data).toBeNull();
  });
  it("refreshes remaining seconds after a refused task without altering the selected clip", async () => {
    const pro: BillingSummary = { enabled: true, plan: "pro", unit: "seconds", remaining: 20, max_clip_seconds: 90 };
    mocks.access.mockResolvedValue({ access_token: "jwt" }); mocks.summary.mockResolvedValueOnce(pro).mockResolvedValueOnce({ ...pro, remaining: 0 });
    const { result } = renderHook(() => useUploadBilling());
    await waitFor(() => expect(result.current.data?.summary?.remaining).toBe(20));
    act(() => result.current.refresh());
    await waitFor(() => expect(result.current.data?.summary?.remaining).toBe(0));
    expect(result.current.maxSeconds).toBe(90);
  });
  it("clears a previously loaded balance if authentication fails during refresh", async () => {
    mocks.access.mockResolvedValue({ access_token: "jwt" });
    mocks.summary.mockResolvedValueOnce({ enabled: true, plan: "pro", remaining: 20, max_clip_seconds: 90 }).mockRejectedValueOnce(new Error("revoked"));
    const { result } = renderHook(() => useUploadBilling());
    await waitFor(() => expect(result.current.data?.summary?.remaining).toBe(20));
    act(() => result.current.refresh());
    await waitFor(() => expect(result.current.failed).toBe(true));
    expect(result.current.data).toBeNull();
  });
});
