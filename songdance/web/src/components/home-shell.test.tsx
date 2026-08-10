import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { HeroTranscriber } from "./hero-transcriber";
import { HowItWorks } from "./how-it-works";
import { SiteHeader } from "./site-header";

describe("public product shell", () => {
  it("states the product job and honest MVP limits", () => {
    render(<HeroTranscriber />);

    expect(
      screen.getByRole("heading", { name: /让钢琴录音重新变得可编辑/ }),
    ).toBeInTheDocument();
    expect(screen.getByText("仅支持钢琴")).toBeInTheDocument();
    expect(screen.getByText("最长 90 秒")).toBeInTheDocument();
    expect(screen.getByText("支持立即删除")).toBeInTheDocument();
    expect(screen.getByText(/拥有处理该音频所需的版权或授权/)).toBeInTheDocument();
  });

  it("uses working in-page navigation instead of dead product actions", () => {
    render(
      <>
        <SiteHeader />
        <HowItWorks />
      </>,
    );

    const flowLinks = screen.getAllByRole("link", { name: "查看流程" });
    expect(flowLinks[0]).toHaveAttribute("href", "/#how-it-works");
    expect(flowLinks[0]).toBeVisible();
    expect(screen.getByRole("heading", { name: /从声音，到能继续工作的音符/ })).toBeInTheDocument();
  });
});
