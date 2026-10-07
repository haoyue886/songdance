import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import messages from "../../../messages/zh-CN.json";
import { AccountDeletion } from "./account-deletion";
import { AuthPanel } from "./auth-panel";
import { AccountDeletionApiError, type AccountDeletionSnapshot } from "@/lib/api/account-deletion";

const mocks = vi.hoisted(() => ({ get: vi.fn(), request: vi.fn(), logout: vi.fn(), replace: vi.fn(), refresh: vi.fn(), account: vi.fn(), guest: vi.fn() }));
vi.mock("@/lib/api/account-deletion", async (original) => ({ ...await original<typeof import("@/lib/api/account-deletion")>(), getAccountDeletion: mocks.get, requestAccountDeletion: mocks.request }));
vi.mock("@/lib/api/jobs", () => ({ getAccount: mocks.account, claimJob: vi.fn() }));
vi.mock("@/lib/auth/client", async (original) => ({ ...await original<typeof import("@/lib/auth/client")>(), authEnabled: true, authPost: mocks.logout, guestToken: mocks.guest }));
vi.mock("@/i18n/navigation", () => ({ Link: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => <a href={href} {...rest}>{children}</a>, useRouter: () => ({ replace: mocks.replace, refresh: mocks.refresh }) }));
vi.mock("@/components/billing/account-usage", () => ({ AccountUsage: () => <div data-testid="account-usage"><button>Purchase</button></div> }));

const t = messages.auth;
const initial: AccountDeletionSnapshot = { enabled: true, deletion: null };
const pending: AccountDeletionSnapshot = { enabled: true, deletion: { id: "deletion-1", owner_id: "owner-1", status: "pending", phase: "billing", attempts: 0,
  requested_at: "2026-10-07T10:00:00Z", completed_at: null, error_code: null } };
const completed: AccountDeletionSnapshot = { enabled: true, deletion: { ...pending.deletion!, status: "completed", phase: "cleanup", completed_at: "2026-10-07T10:01:00Z" } };
function props(value = initial, ownerId = "owner-1") {
  return { ownerId, initial: value, onSnapshot: vi.fn(), onBlocked: vi.fn(), onIdentityChanged: vi.fn() };
}
function confirm() {
  fireEvent.click(screen.getByRole("button", { name: t.deletionAction }));
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(screen.getByRole("button", { name: t.deletionSubmit }));
}
beforeEach(() => {
  vi.clearAllMocks(); mocks.get.mockResolvedValue(pending); mocks.request.mockResolvedValue(pending); mocks.logout.mockResolvedValue({});
  mocks.guest.mockReturnValue(null); mocks.account.mockResolvedValue({ id: "owner-1", email: "owner@example.test", account_deletion_enabled: true, deletion: null });
});
afterEach(() => vi.useRealTimers());

describe("account deletion confirmation", () => {
  it("hides the default-off section without making a status request", () => {
    const view = render(<AccountDeletion {...props({ enabled: false, deletion: null })} />);
    expect(view.container).toBeEmptyDOMElement(); expect(mocks.get).not.toHaveBeenCalled();
  });

  it("requires a checked statement covering the deletion impact", async () => {
    render(<AccountDeletion {...props()} />);
    fireEvent.click(screen.getByRole("button", { name: t.deletionAction }));
    expect(screen.getByText(t.deletionImpact)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: t.deletionSubmit })).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: t.deletionSubmit }));
    fireEvent.click(screen.getByRole("button", { name: t.deletionSubmit }));
    expect(await screen.findByText(t.deletionBilling)).toBeInTheDocument();
    expect(mocks.request).toHaveBeenCalledTimes(1);
    expect(mocks.request).toHaveBeenCalledWith("owner-1");
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });

  it("does not display completion from the DELETE response until GET confirms it", async () => {
    let finish!: (value: AccountDeletionSnapshot) => void;
    mocks.request.mockResolvedValue(completed); mocks.get.mockReturnValue(new Promise((resolve) => { finish = resolve; }));
    const options = props(); render(<AccountDeletion {...options} />); confirm();
    await waitFor(() => expect(mocks.get).toHaveBeenCalledTimes(1));
    expect(screen.queryByText(t.deletionCompleted)).not.toBeInTheDocument();
    expect(options.onBlocked).toHaveBeenCalledWith(true);
    await act(async () => finish(completed));
    expect(screen.getByText(t.deletionCompleted)).toBeInTheDocument();
  });

  it("recovers a lost DELETE response only through status queries", async () => {
    mocks.request.mockRejectedValue(new AccountDeletionApiError("NETWORK_ERROR", 0, true));
    mocks.get.mockRejectedValueOnce(new AccountDeletionApiError("NETWORK_ERROR")).mockResolvedValue(completed);
    const options = props(); render(<AccountDeletion {...options} />); confirm();
    expect(await screen.findByText(t.deletionUnknown)).toBeInTheDocument();
    expect(options.onBlocked).toHaveBeenCalledWith(true);
    expect(screen.queryByRole("button", { name: t.deletionAction })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: t.deletionRefresh }));
    expect(await screen.findByText(t.deletionCompleted)).toBeInTheDocument();
    expect(mocks.request).toHaveBeenCalledTimes(1); expect(mocks.get).toHaveBeenCalledTimes(2);
  });

  it("logs out before returning to localized sign-in for reauthentication", async () => {
    mocks.request.mockRejectedValue(new AccountDeletionApiError("REAUTH_REQUIRED", 403));
    render(<AccountDeletion {...props()} />); confirm();
    expect(await screen.findByText(t.deletionReauth)).toBeInTheDocument();
    expect(screen.getByRole("checkbox")).not.toBeChecked();
    expect(screen.getByRole("button", { name: t.deletionSubmit })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: t.deletionReauthAction }));
    await waitFor(() => expect(mocks.replace).toHaveBeenCalledWith("/login?return_to=%2Fzh%2Faccount"));
    expect(mocks.logout).toHaveBeenCalledWith("logout");
    expect(mocks.logout.mock.invocationCallOrder[0]).toBeLessThan(mocks.replace.mock.invocationCallOrder[0]);
    expect(mocks.request).toHaveBeenCalledTimes(1); expect(mocks.get).not.toHaveBeenCalled();
  });

  it("does not navigate if logout fails", async () => {
    mocks.request.mockRejectedValue(new AccountDeletionApiError("REAUTH_REQUIRED", 403)); mocks.logout.mockRejectedValue(new Error("unavailable"));
    render(<AccountDeletion {...props()} />); confirm();
    fireEvent.click(await screen.findByRole("button", { name: t.deletionReauthAction }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(t.error));
    expect(mocks.replace).not.toHaveBeenCalled();
  });

  it("clears previous errors and confirmation when the owner changes", async () => {
    mocks.request.mockRejectedValue(new AccountDeletionApiError("REAUTH_REQUIRED", 403));
    const view = render(<AccountDeletion {...props()} />); confirm();
    await screen.findByText(t.deletionReauth);
    view.rerender(<AccountDeletion {...props(initial, "owner-2")} />);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument(); expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: t.deletionAction }));
    expect(screen.getByRole("checkbox")).not.toBeChecked();
  });

  it("ignores an old owner's response after the component changes identity", async () => {
    let finish!: (value: AccountDeletionSnapshot) => void;
    mocks.get.mockReturnValue(new Promise((resolve) => { finish = resolve; }));
    const options = props(pending); const view = render(<AccountDeletion {...options} />);
    fireEvent.click(screen.getByRole("button", { name: t.deletionRefresh }));
    view.rerender(<AccountDeletion {...props(initial, "owner-2")} />);
    await act(async () => finish(completed));
    expect(screen.queryByText(t.deletionCompleted)).not.toBeInTheDocument(); expect(options.onSnapshot).not.toHaveBeenCalled();
  });
});

describe("account deletion progress", () => {
  it.each([
    [pending, t.deletionBilling],
    [{ enabled: false, deletion: { ...pending.deletion!, status: "retry", error_code: "CANCEL_UNAVAILABLE" } }, t.deletionRetryBilling],
    [{ enabled: false, deletion: { ...pending.deletion!, phase: "cleanup" } }, t.deletionCleanup],
    [{ enabled: false, deletion: { ...pending.deletion!, status: "retry", phase: "cleanup" } }, t.deletionRetryCleanup],
    [{ enabled: false, deletion: { ...pending.deletion!, status: "review" } }, t.deletionReview],
    [completed, t.deletionCompleted],
  ] as const)("shows backend progress without offering another deletion request", (value, label) => {
    render(<AccountDeletion {...props(value as AccountDeletionSnapshot)} />);
    expect(screen.getByText(label)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: t.deletionSupport })).toHaveAttribute("href", "/contact");
    expect(screen.getByRole("button", { name: t.deletionRefresh })).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument(); expect(mocks.request).not.toHaveBeenCalled();
  });

  it("polls every fifteen seconds for at most two minutes and remains manually refreshable", async () => {
    vi.useFakeTimers(); render(<AccountDeletion {...props(pending)} />);
    await act(async () => { await vi.advanceTimersByTimeAsync(120_000); });
    expect(mocks.get).toHaveBeenCalledTimes(8);
    await act(async () => { await vi.advanceTimersByTimeAsync(120_000); });
    expect(mocks.get).toHaveBeenCalledTimes(8);
    fireEvent.click(screen.getByRole("button", { name: t.deletionRefresh }));
    await act(async () => { await Promise.resolve(); }); expect(mocks.get).toHaveBeenCalledTimes(9);
  });

  it("stops polling after confirmed completion and on unmount", async () => {
    vi.useFakeTimers(); mocks.get.mockResolvedValue(completed);
    const view = render(<AccountDeletion {...props(pending)} />);
    await act(async () => { await vi.advanceTimersByTimeAsync(15_000); });
    expect(screen.getByText(t.deletionCompleted)).toBeInTheDocument();
    await act(async () => { await vi.advanceTimersByTimeAsync(120_000); });
    expect(mocks.get).toHaveBeenCalledTimes(1); view.unmount();
    await act(async () => { await vi.advanceTimersByTimeAsync(120_000); }); expect(mocks.get).toHaveBeenCalledTimes(1);
  });

  it("requests a fresh owner snapshot when progress queries detect identity change", async () => {
    mocks.get.mockRejectedValue(new AccountDeletionApiError("AUTH_CHANGED", 401));
    const options = props(pending); render(<AccountDeletion {...options} />);
    fireEvent.click(screen.getByRole("button", { name: t.deletionRefresh }));
    await waitFor(() => expect(options.onIdentityChanged).toHaveBeenCalledTimes(1));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

describe("account page deletion integration", () => {
  it("keeps old default-off responses usable", async () => {
    mocks.account.mockResolvedValue({ id: "owner-1", email: "owner@example.test" });
    render(<AuthPanel mode="account" returnTo="/jobs/guest-job" />);
    expect(await screen.findByTestId("account-usage")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: t.upload })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: t.back })).toHaveAttribute("href", "/jobs/guest-job");
    expect(screen.queryByRole("button", { name: t.deletionAction })).not.toBeInTheDocument();
  });

  it("hides purchases, upload, claim and task navigation while deletion is pending", async () => {
    mocks.account.mockResolvedValue({ id: "owner-1", email: "owner@example.test", account_deletion_enabled: false, deletion: pending.deletion });
    mocks.guest.mockReturnValue("guest-capability"); render(<AuthPanel mode="account" returnTo="/jobs/guest-job" />);
    expect(await screen.findByText(t.deletionBilling)).toBeInTheDocument();
    expect(screen.queryByTestId("account-usage")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: t.upload })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: t.claim })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: t.back })).not.toBeInTheDocument();
  });

  it("hides account actions after an uncertain deletion and restores them only after a verified empty status", async () => {
    mocks.request.mockRejectedValue(new AccountDeletionApiError("NETWORK_ERROR", 0, true));
    mocks.get.mockRejectedValueOnce(new AccountDeletionApiError("NETWORK_ERROR")).mockResolvedValueOnce(initial);
    render(<AuthPanel mode="account" returnTo="/jobs/guest-job" />); await screen.findByTestId("account-usage"); confirm();
    await screen.findByText(t.deletionUnknown); expect(screen.queryByTestId("account-usage")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: t.back })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: t.deletionRefresh }));
    expect(await screen.findByTestId("account-usage")).toBeInTheDocument(); expect(mocks.request).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("link", { name: t.back })).toBeInTheDocument();
  });

  it("keeps completed account status and logout available when email is removed", async () => {
    mocks.account.mockResolvedValue({ id: "owner-1", email: null, account_deletion_enabled: false, deletion: completed.deletion });
    render(<AuthPanel mode="account" returnTo="/jobs/guest-job" />);
    expect(await screen.findByText(t.deletionCompleted)).toBeInTheDocument();
    expect(screen.getByText(t.deletionCompletedAccount)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: t.signOut })).toBeEnabled(); expect(screen.queryByTestId("account-usage")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: t.back })).not.toBeInTheDocument();
  });
});
