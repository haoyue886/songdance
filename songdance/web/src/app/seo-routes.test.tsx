import { describe, expect, it } from "vitest";
import { generateMetadata as generateJobMetadata } from "./[locale]/jobs/[jobId]/page";
import robots from "./robots";
import sitemap from "./sitemap";
import { routing } from "@/i18n/routing";

describe("SEO routes", () => {
  it("publishes every stable locale without exposing ephemeral or legacy URLs", () => {
    const paths = sitemap().map((entry) => new URL(entry.url).pathname);
    for (const locale of routing.locales) {
      const prefix = locale === "en" ? "" : `/${locale}`;
      expect(paths).toContain(`${prefix || "/"}`);
      expect(paths).toContain(`${prefix}/examples`);
    }
    expect(paths).toContain("/examples");
    expect(paths).not.toContain("/audio-to-midi");
    expect(paths.some((path) => path.includes("/jobs/"))).toBe(false);
    expect(new URL(String(robots().sitemap)).pathname).toBe("/sitemap.xml");

    const homeEntry = sitemap().find((entry) => new URL(entry.url).pathname === "/");
    expect(Object.keys(homeEntry?.alternates?.languages ?? {}).sort()).toEqual([
      "de", "en", "es", "fr", "ja", "ko", "pt-BR", "x-default", "zh-CN",
    ]);
  });

  it("keeps localized job pages out of search indexes", async () => {
    const metadata = await generateJobMetadata({
      params: Promise.resolve({ locale: "zh", jobId: "job-1" }),
    });
    expect(metadata.robots).toMatchObject({ index: false, follow: false, nocache: true });
    expect(metadata.openGraph).toBeNull();
    expect(metadata.twitter).toBeNull();
  });
});
