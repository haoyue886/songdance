import { describe, expect, it } from "vitest";
import { generateMetadata as generateJobMetadata } from "./[locale]/jobs/[jobId]/page";
import robots from "./robots";
import sitemap from "./sitemap";

describe("SEO routes", () => {
  it("publishes both stable locales without exposing ephemeral or legacy URLs", () => {
    const paths = sitemap().map((entry) => new URL(entry.url).pathname);
    expect(paths).toContain("/");
    expect(paths).toContain("/zh");
    expect(paths).toContain("/examples");
    expect(paths).toContain("/zh/examples");
    expect(paths).not.toContain("/audio-to-midi");
    expect(paths.some((path) => path.includes("/jobs/"))).toBe(false);
    expect(new URL(String(robots().sitemap)).pathname).toBe("/sitemap.xml");
  });

  it("keeps localized job pages out of search indexes", async () => {
    const metadata = await generateJobMetadata({
      params: Promise.resolve({ locale: "zh-CN", jobId: "job-1" }),
    });
    expect(metadata.robots).toMatchObject({ index: false, follow: false, nocache: true });
    expect(metadata.openGraph).toBeNull();
    expect(metadata.twitter).toBeNull();
  });
});
