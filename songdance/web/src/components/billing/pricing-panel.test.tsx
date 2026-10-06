import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as intl from "next-intl";
import { getBillingConfig, type BillingConfig } from "@/lib/api/billing";
import { accessSession } from "@/lib/auth/client";
import { PricingPanel } from "./pricing-panel";
import en from "../../../messages/en.json";
import zh from "../../../messages/zh-CN.json";
import de from "../../../messages/de.json";
import es from "../../../messages/es.json";
import fr from "../../../messages/fr.json";
import ja from "../../../messages/ja.json";
import ko from "../../../messages/ko.json";
import ptBR from "../../../messages/pt-BR.json";

vi.mock("@/lib/api/billing", () => ({ getBillingConfig: vi.fn() }));
vi.mock("@/lib/auth/client", () => ({ authEnabled: true, accessSession: vi.fn() }));
vi.mock("./checkout-button", () => ({
  CheckoutButton: ({ config }: { config: BillingConfig }) => <button disabled={!config.checkout_enabled}>{config.checkout_enabled ? "Test checkout" : "暂不开放付款"}</button>,
}));

const CONFIG: BillingConfig = {
  usage_enabled: false, checkout_enabled: false, mode: "unavailable",
  pro: { price_minor: 990, currency: "USD", seconds: 1800, max_clip_seconds: 90, min_charge_seconds: 15 },
  free: { monthly_jobs: 1, max_clip_seconds: 90 }, guest: { max_clip_seconds: 30 },
  retention_hours: 24, support_email: null,
};

beforeEach(() => { vi.clearAllMocks(); vi.spyOn(intl, "useLocale").mockReturnValue("zh"); vi.mocked(accessSession).mockResolvedValue(null); });

describe("public pricing", () => {
  it("does not present disabled metering or proposed pricing as active", async () => {
    vi.mocked(getBillingConfig).mockResolvedValue(CONFIG);
    render(<PricingPanel />);
    expect(await screen.findByText(/Pro 价格与额度仍为提案/)).toBeInTheDocument();
    expect(screen.getByText(/当前环境尚未启用每月用量/)).toBeInTheDocument();
    expect(screen.getByText(/USD\s*9\.90／月/)).toBeInTheDocument();
    expect(screen.getByText(/任务文件|音频和导出文件自任务创建起临时保留 24 小时/)).toBeInTheDocument();
    expect(screen.getByText(/MIDI 是主要交付/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "暂不开放付款" })).toBeDisabled();
    expect(screen.getByRole("link", { name: "转录音频" })).toHaveAttribute("href", "/transcribe");
    expect(screen.queryByText(/7 日|180 秒|无限量|10 分钟/)).not.toBeInTheDocument();
  });

  it("uses the same server config for all plan amounts and limits", async () => {
    vi.mocked(getBillingConfig).mockResolvedValue({
      ...CONFIG, usage_enabled: true, checkout_enabled: true, mode: "test",
      pro: { price_minor: 1500, currency: "USD", seconds: 1920, max_clip_seconds: 89, min_charge_seconds: 17 },
      free: { monthly_jobs: 2, max_clip_seconds: 90 }, guest: { max_clip_seconds: 29 }, retention_hours: 48,
    });
    render(<PricingPanel />);
    expect(await screen.findByText(/当前环境只提供 Test checkout/)).toBeInTheDocument();
    expect(screen.getByText(/USD\s*15\.00／月/)).toBeInTheDocument();
    expect(screen.getByText("每个已付费周期 32 分钟")).toBeInTheDocument();
    expect(screen.getByText(/每次最低扣 17 秒/)).toBeInTheDocument();
    expect(screen.getByText(/每个 UTC 自然月 2 次成功转录，每次最长 90 秒/)).toBeInTheDocument();
    expect(screen.getByText("单次片段最长 89 秒")).toBeInTheDocument();
    expect(screen.getByText(/游客钢琴片段最长 29 秒/)).toBeInTheDocument();
    expect(screen.getByText(/临时保留 48 小时/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "登录" })).toHaveAttribute("href", "/login?return_to=%2Fzh%2Ftranscribe");
    expect(screen.getByRole("button", { name: "Test checkout" })).toBeEnabled();
  });

  it("sends a signed-in user directly to transcription", async () => {
    vi.mocked(getBillingConfig).mockResolvedValue({ ...CONFIG, usage_enabled: true });
    vi.mocked(accessSession).mockResolvedValue({ access_token: "local-test-token", expires_at: 9999999999, user: { id: "local-test-user" } });
    render(<PricingPanel />);
    expect(await screen.findByRole("link", { name: "转录音频" })).toHaveAttribute("href", "/transcribe");
    expect(screen.queryByRole("link", { name: "登录" })).not.toBeInTheDocument();
  });

  it("shows a retryable error without inventing plan data", async () => {
    vi.mocked(getBillingConfig).mockRejectedValueOnce(new Error("unavailable")).mockResolvedValueOnce(CONFIG);
    render(<PricingPanel />);
    expect(await screen.findByRole("alert")).toHaveTextContent("套餐与用量信息暂不可用，请刷新重试。");
    expect(screen.queryByRole("button", { name: "暂不开放付款" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "刷新" }));
    expect(await screen.findByRole("button", { name: "暂不开放付款" })).toBeDisabled();
    expect(getBillingConfig).toHaveBeenCalledTimes(2);
  });

  it("aborts its config read when the page is left", () => {
    vi.mocked(getBillingConfig).mockImplementation(() => new Promise(() => undefined));
    const view = render(<PricingPanel />);
    const signal = vi.mocked(getBillingConfig).mock.calls[0][0];
    expect(signal?.aborted).toBe(false);
    view.unmount();
    expect(signal?.aborted).toBe(true);
  });

  it("marks untranslated commercial text as an explicit English fallback", async () => {
    vi.spyOn(intl, "useLocale").mockReturnValue("ja");
    vi.mocked(getBillingConfig).mockResolvedValue(CONFIG);
    render(<PricingPanel />);
    expect(screen.getByText(/商业条款目前以英文显示/)).toHaveAttribute("lang", "en");
    await screen.findByRole("button", { name: "暂不开放付款" });
    for (const messages of [de, es, fr, ja, ko, ptBR]) expect(messages.billing).toEqual(en.billing);
  });

  it("keeps legal disclosures aligned with account access and separate metadata retention", () => {
    expect(en.billing.freeAllowance).toBe("Successful transcriptions per UTC calendar month: {count}");
    expect(en.billing.freeRules).not.toContain("{count} successful transcriptions");
    expect(en.privacy.metaDescription).not.toContain("anonymous");
    expect(en.privacy.section1P1).toContain("issued task access credential");
    expect(en.privacy.section1P1).toContain("owning account");
    expect(zh.privacy.section1P1).toContain("任务访问凭证");
    expect(zh.privacy.section1P1).toContain("所属账户");
    expect(en.privacy.section4P2).toContain("separate from the 24-hour audio cleanup");
    expect(zh.privacy.section4P2).toContain("与音频的 24 小时清理相互独立");
    expect(en.terms.section3P2).toContain("Pro uses a separately configured IP security limit");
    expect(zh.terms.section3P2).toContain("Pro 使用独立配置的 IP 安全限流");
    for (const messages of [de, es, fr, ja, ko, ptBR]) {
      expect(messages.privacy.metaDescription).toBe(en.privacy.metaDescription);
      expect(messages.privacy.section1P1).toBe(en.privacy.section1P1);
      expect(messages.privacy.section4P2).toBe(en.privacy.section4P2);
      expect(messages.terms.section3P2).toBe(en.terms.section3P2);
    }
  });
});
