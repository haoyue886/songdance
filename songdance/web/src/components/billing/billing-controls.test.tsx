import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AccountUsage } from "./account-usage";
import { CheckoutButton } from "./checkout-button";
import { PaymentReturn } from "./payment-return";
import { BillingApiError, type BillingConfig, type BillingSummary } from "@/lib/api/billing";

const mocks = vi.hoisted(() => ({ summary: vi.fn(), config: vi.fn(), checkout: vi.fn(), portal: vi.fn(), account: vi.fn(), push: vi.fn(), session: vi.fn() }));
vi.mock("@/lib/api/billing", async (original) => ({ ...await original<typeof import("@/lib/api/billing")>(), getBillingSummary: mocks.summary, getBillingConfig: mocks.config, createCheckout: mocks.checkout, createPortal: mocks.portal }));
vi.mock("@/lib/api/jobs", () => ({ getAccount: mocks.account }));
vi.mock("@/lib/auth/client", () => ({ authEnabled: true, accessSession: mocks.session }));
vi.mock("@/i18n/navigation", () => ({ Link: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => <a href={href} {...rest}>{children}</a>, useRouter: () => ({ push: mocks.push }) }));
const config: BillingConfig = { usage_enabled: true, checkout_enabled: true, mode: "test", pro: { price_minor: 990, currency: "USD", seconds: 1800, max_clip_seconds: 90, min_charge_seconds: 15 }, free: { monthly_jobs: 1, max_clip_seconds: 90 }, guest: { max_clip_seconds: 30 }, retention_hours: 24, support_email: null };
const pending: BillingSummary = { enabled: true, plan: "free", unit: "jobs", state: "active", limit: 1, remaining: 1, reserved: 0, used: 0, period_end: "2026-11-01T00:00:00Z", sync_state: "payment_confirming", checkout_status: "uncertain" };
const pro: BillingSummary = { ...pending, plan: "pro", unit: "seconds", limit: 1800, remaining: 0, used: 1800, sync_state: "ready", checkout_status: "completed", portal_available: true };
beforeEach(() => {
  vi.clearAllMocks(); mocks.config.mockResolvedValue(config); mocks.summary.mockResolvedValue(pending); mocks.account.mockResolvedValue({ id: "owner" });
});
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

describe("task summary response validation", () => {
  it.each([null, [], { succeeded: -1, failed: 0, in_progress: 0 },
    { succeeded: 1.5, failed: 0, in_progress: 0 }, { succeeded: 0, failed: 0 },
    { succeeded: 0, failed: 0, in_progress: "1" }])("rejects malformed task counts: %j", async (task_summary) => {
    const api = await vi.importActual<typeof import("@/lib/api/billing")>("@/lib/api/billing");
    mocks.session.mockResolvedValue({ access_token: "test-token" });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ ...pending, task_summary }))));
    await expect(api.getBillingSummary()).rejects.toMatchObject({ code: "BILLING_UNAVAILABLE", status: 502 });
  });
  it("accepts zero counts without requiring task summaries from older servers", async () => {
    const api = await vi.importActual<typeof import("@/lib/api/billing")>("@/lib/api/billing");
    mocks.session.mockResolvedValue({ access_token: "test-token" });
    const task_summary = { succeeded: 0, failed: 0, in_progress: 0 };
    vi.stubGlobal("fetch", vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...pending, task_summary })))
      .mockResolvedValueOnce(new Response(JSON.stringify(pending))));
    expect((await api.getBillingSummary()).task_summary).toEqual(task_summary);
    expect((await api.getBillingSummary()).task_summary).toBeUndefined();
  });
});

describe("checkout controls", () => {
  it("keeps purchase disabled when the server hasn't opened checkout", () => {
    render(<CheckoutButton config={{ ...config, checkout_enabled: false }} />);
    expect(screen.getByRole("button")).toBeDisabled();
    expect(mocks.checkout).not.toHaveBeenCalled();
  });
  it("returns signed-out buyers to pricing after sign-in", async () => {
    mocks.account.mockRejectedValue({ status: 401 });
    render(<CheckoutButton config={config} />); fireEvent.click(screen.getByRole("button"));
    await waitFor(() => expect(mocks.push).toHaveBeenCalledWith("/login?return_to=%2Fzh%2Fpricing"));
    expect(mocks.checkout).not.toHaveBeenCalled();
  });
  it("unknown checkout results move to confirmation without sending another request", async () => {
    mocks.checkout.mockResolvedValue({ id: "intent", status: "uncertain", checkout_url: null });
    render(<CheckoutButton config={config} ownerId="owner" />);
    fireEvent.click(screen.getByRole("button")); fireEvent.click(screen.getByRole("button"));
    await waitFor(() => expect(mocks.push).toHaveBeenCalledWith("/billing/return"));
    expect(mocks.checkout).toHaveBeenCalledTimes(1);
  });
  it("provider or network errors remain retryable without claiming purchase success", async () => {
    mocks.checkout.mockRejectedValue(new BillingApiError("NETWORK_ERROR"));
    render(<CheckoutButton config={config} ownerId="owner" />); fireEvent.click(screen.getByRole("button"));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(mocks.push).not.toHaveBeenCalled();
    expect(screen.getByRole("button")).toBeEnabled();
  });
});

describe("payment confirmation", () => {
  it("does not trust forged return URL parameters", async () => {
    window.history.replaceState(null, "", "/billing/return?status=paid&plan=pro&balance=1800");
    mocks.summary.mockResolvedValue({ enabled: true, plan: "free", sync_state: "ready" });
    render(<PaymentReturn />);
    expect(await screen.findByText("目前没有等待确认的 checkout。")).toBeInTheDocument();
    expect(screen.queryByText("你的 Pro 权益已生效。")).not.toBeInTheDocument();
  });
  it("stops polling when the backend confirms an active Pro entitlement", async () => {
    vi.useFakeTimers(); mocks.summary.mockResolvedValueOnce(pending).mockResolvedValue(pro);
    render(<PaymentReturn />);
    await act(async () => { await Promise.resolve(); });
    await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
    expect(screen.getByText("你的 Pro 权益已生效。")).toBeInTheDocument();
    await act(async () => { await vi.advanceTimersByTimeAsync(90_000); });
    expect(mocks.summary).toHaveBeenCalledTimes(2);
  });
  it("stops automatically after sixty seconds and offers a manual refresh", async () => {
    vi.useFakeTimers(); mocks.summary.mockResolvedValue(pending);
    render(<PaymentReturn />);
    await act(async () => { await vi.advanceTimersByTimeAsync(60_001); });
    expect(screen.getByRole("button", { name: "刷新" })).toBeEnabled();
    const count = mocks.summary.mock.calls.length;
    await act(async () => { await vi.advanceTimersByTimeAsync(60_000); });
    expect(mocks.summary).toHaveBeenCalledTimes(count);
    expect(mocks.checkout).not.toHaveBeenCalled();
  });
  it("clears pending polling when leaving the page", async () => {
    vi.useFakeTimers(); const view = render(<PaymentReturn />);
    await act(async () => { await Promise.resolve(); }); view.unmount();
    const count = mocks.summary.mock.calls.length;
    await act(async () => { await vi.advanceTimersByTimeAsync(90_000); });
    expect(mocks.summary).toHaveBeenCalledTimes(count);
  });
});

describe("account usage", () => {
  it("shows server task counts separately from paid seconds", async () => {
    mocks.summary.mockResolvedValue({ ...pro, task_summary: { succeeded: 2, failed: 3, in_progress: 1 } });
    render(<AccountUsage ownerId="owner" />);
    const summary = within(await screen.findByRole("region", { name: "本用量周期任务" }));
    expect(summary.getByText("已成功").nextElementSibling).toHaveTextContent("2");
    expect(summary.getByText("未成功／已取消").nextElementSibling).toHaveTextContent("3");
    expect(summary.getByText("进行中").nextElementSibling).toHaveTextContent("1");
    expect(screen.getByText("1800 秒")).toBeInTheDocument();
  });
  it("shows an empty current period and clears its counts after an expired session", async () => {
    mocks.summary.mockResolvedValueOnce({ ...pending, task_summary: { succeeded: 0, failed: 0, in_progress: 0 } })
      .mockRejectedValueOnce(new BillingApiError("AUTH_EXPIRED", 401));
    render(<AccountUsage ownerId="owner" />);
    const summary = within(await screen.findByRole("region", { name: "本用量周期任务" }));
    expect(summary.getAllByText("0")).toHaveLength(3);
    fireEvent.click(screen.getByRole("button", { name: "刷新" }));
    await screen.findByRole("alert");
    expect(screen.queryByRole("region", { name: "本用量周期任务" })).not.toBeInTheDocument();
  });
  it("shows consumed and reserved paid seconds without Free fallback", async () => {
    mocks.summary.mockResolvedValue(pro);
    render(<AccountUsage ownerId="owner" />);
    expect(await screen.findByText("Pro 月付")).toBeInTheDocument();
    expect(screen.getByText("剩余 0 秒")).toBeInTheDocument();
    expect(screen.getByText("1800 秒")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "管理账单" })).toBeInTheDocument();
    expect(screen.queryByText("Free（登录）")).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "本用量周期任务" })).not.toBeInTheDocument();
  });
  it("shows a failed read instead of inventing allowance and supports retry", async () => {
    mocks.summary.mockRejectedValueOnce(new BillingApiError("NETWORK_ERROR")).mockResolvedValue(pro);
    render(<AccountUsage ownerId="owner" />);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.queryByText("剩余 0 秒")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "刷新" }));
    expect(await screen.findByText("剩余 0 秒")).toBeInTheDocument();
  });
  it("drops old balances and paid controls when a session expires on refresh", async () => {
    mocks.summary.mockResolvedValueOnce(pro).mockRejectedValueOnce(new BillingApiError("AUTH_EXPIRED", 401));
    render(<AccountUsage ownerId="owner" />);
    await screen.findByRole("button", { name: "管理账单" });
    fireEvent.click(screen.getByRole("button", { name: "刷新" }));
    await screen.findByRole("alert");
    expect(screen.queryByText("剩余 0 秒")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "管理账单" })).not.toBeInTheDocument();
  });
  it("rejects another account's balance when shared cookies change identity", async () => {
    mocks.summary.mockResolvedValue({ ...pro, owner_id: "different-owner" });
    render(<AccountUsage ownerId="owner" />);
    await screen.findByRole("alert");
    expect(screen.queryByText("剩余 0 秒")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "管理账单" })).not.toBeInTheDocument();
  });
});
