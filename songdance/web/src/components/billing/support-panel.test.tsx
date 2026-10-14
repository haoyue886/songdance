import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { getBillingConfig, type BillingConfig } from "@/lib/api/billing";
import { SupportPanel, supportMailto } from "./support-panel";

vi.mock("@/lib/api/billing", () => ({ getBillingConfig: vi.fn() }));

const CONFIG: BillingConfig = {
  usage_enabled: false, checkout_enabled: false, mode: "unavailable",
  pro: { price_minor: 990, currency: "USD", seconds: 1800, max_clip_seconds: 90, min_charge_seconds: 15 },
  free: { monthly_jobs: 1, max_clip_seconds: 90 }, guest: { max_clip_seconds: 30 },
  retention_hours: 24, support_email: null,
};

beforeEach(() => { vi.clearAllMocks(); });

describe("support contact", () => {
  it("does not show an invented address or form when support is unconfigured", async () => {
    vi.mocked(getBillingConfig).mockResolvedValue(CONFIG);
    const { container } = render(<SupportPanel mode="contact" />);
    expect(await screen.findByText(/当前环境尚未配置支持邮箱/)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "邮件联系支持" })).not.toBeInTheDocument();
    expect(container.querySelector("form")).toBeNull();
  });

  it("uses only the configured support address with an encoded subject", async () => {
    vi.mocked(getBillingConfig).mockResolvedValue({ ...CONFIG, support_email: "support+test@example.com" });
    render(<SupportPanel mode="contact" />);
    const link = await screen.findByRole("link", { name: "邮件联系支持" });
    expect(link).toHaveAttribute("href", `mailto:support%2Btest@example.com?subject=${encodeURIComponent("Notavue 支持咨询")}`);
    expect(screen.getByText("support+test@example.com")).toBeInTheDocument();
  });

  it("rejects injected recipients and email headers", () => {
    for (const address of [null, "", "javascript:alert(1)", "support@example.com?bcc=other@example.com", "support@example.com\r\nBcc: other@example.com", "a@example.com,b@example.com"]) {
      expect(supportMailto(address)).toBeNull();
    }
    expect(supportMailto("support@example.com")).toBe("mailto:support@example.com");
    expect(supportMailto("support@example.com", "Refund & account?")).toBe("mailto:support@example.com?subject=Refund%20%26%20account%3F");
  });
});

describe("refund disclosures", () => {
  it("leaves the unapproved voluntary policy inactive and independently reviews failures", async () => {
    vi.mocked(getBillingConfig).mockResolvedValue(CONFIG);
    render(<SupportPanel mode="refund" />);
    expect(screen.getByText(/没有已生效的自愿退款期限或用量门槛/)).toBeInTheDocument();
    expect(screen.getByText(/不限制适用于你的强制消费者权利/)).toBeInTheDocument();
    expect(screen.getByText(/无法交付的服务故障、重复扣款和明显质量问题/)).toBeInTheDocument();
    expect(screen.getByText(/退款与停止未来扣款须分别确认/)).toBeInTheDocument();
    expect(screen.getByText(/不会秘密延长音频保留/)).toBeInTheDocument();
    expect(await screen.findByText(/临时保留 24 小时/)).toBeInTheDocument();
    expect(screen.queryByText(/7 日|180 秒|无条件退款/)).not.toBeInTheDocument();
  });
});
