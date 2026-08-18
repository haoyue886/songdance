import { expect, test } from "@playwright/test";
import { JSDOM } from "jsdom";

const SITE_URL = "http://localhost:3001";

test("serves localized, crawlable HTML and structured data", async ({ request }) => {
  for (const locale of [
    { path: "/", lang: "en", heading: "Audio to MIDI Converter for Piano Recordings" },
    { path: "/zh", lang: "zh-CN", heading: "钢琴音频转 MIDI 转换器" },
  ]) {
    const response = await request.get(locale.path);
    expect(response.status()).toBe(200);
    const document = new JSDOM(await response.text()).window.document;

    expect(document.documentElement.lang).toBe(locale.lang);
    expect(document.querySelectorAll("h1")).toHaveLength(1);
    expect(document.querySelector("h1")?.textContent).toContain(locale.heading);
    const canonicalPath = locale.path === "/" ? "" : locale.path;
    expect(document.querySelector('link[rel="canonical"]')?.getAttribute("href"))
      .toBe(`${SITE_URL}${canonicalPath}`);
    expect(alternateHref(document, "en")).toBe(SITE_URL);
    expect(alternateHref(document, "zh-CN")).toBe(`${SITE_URL}/zh`);
    expect(alternateHref(document, "x-default")).toBe(SITE_URL);

    const jsonLd = JSON.parse(
      document.querySelector('script[type="application/ld+json"]')?.textContent ?? "{}",
    ) as { "@graph"?: Array<{ "@type"?: string; offers?: unknown }> };
    expect(jsonLd["@graph"]?.map((entry) => entry["@type"]))
      .toEqual(["WebApplication", "FAQPage"]);
    expect(jsonLd["@graph"]?.[0]).not.toHaveProperty("offers");
  }
});

test("redirects the retired landing page and publishes only stable locale URLs", async ({ request }) => {
  const legacyResponse = await request.get("/audio-to-midi", { maxRedirects: 0 });
  expect(legacyResponse.status()).toBe(308);
  expect(legacyResponse.headers().location).toBe("/");

  const robotsResponse = await request.get("/robots.txt");
  expect(robotsResponse.status()).toBe(200);
  expect(await robotsResponse.text()).toContain(`Sitemap: ${SITE_URL}/sitemap.xml`);

  const sitemapResponse = await request.get("/sitemap.xml");
  expect(sitemapResponse.status()).toBe(200);
  const sitemap = await sitemapResponse.text();
  for (const path of ["/", "/zh", "/transcribe", "/zh/transcribe", "/examples", "/zh/examples"])
    expect(sitemap).toContain(`<loc>${SITE_URL}${path}</loc>`);
  expect(sitemap).not.toContain("/audio-to-midi");
  expect(sitemap).not.toContain("/jobs/");
});

test("keeps both job locales out of search indexes", async ({ page }) => {
  for (const path of ["/jobs/seo-index-test", "/zh/jobs/seo-index-test"]) {
    await page.goto(path);
    await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content", /noindex/);
    await expect(page.locator('link[rel="canonical"]')).toHaveCount(0);
    await expect(page.locator('meta[property="og:url"]')).toHaveCount(0);
  }
});

test("returns localized 404 pages with noindex metadata", async ({ page }) => {
  for (const locale of [
    { path: "/route-that-does-not-exist", title: "Page not found", lang: "en" },
    { path: "/zh/route-that-does-not-exist", title: "页面不存在", lang: "zh-CN" },
    { path: "/ja/route-that-does-not-exist", title: "Page not found", lang: "ja" },
    { path: "/ko/route-that-does-not-exist", title: "Page not found", lang: "ko" },
    { path: "/es/route-that-does-not-exist", title: "Page not found", lang: "es" },
    { path: "/pt-br/route-that-does-not-exist", title: "Page not found", lang: "pt-BR" },
    { path: "/fr/route-that-does-not-exist", title: "Page not found", lang: "fr" },
    { path: "/de/route-that-does-not-exist", title: "Page not found", lang: "de" },
  ]) {
    const response = await page.goto(locale.path);
    expect(response?.status()).toBe(404);
    await expect(page.locator("html")).toHaveAttribute("lang", locale.lang);
    await expect(page.getByRole("heading", { level: 1, name: locale.title })).toBeVisible();
    await expect(page.locator("title")).toHaveCount(1);
    const robots = await page.locator('meta[name="robots"]').evaluateAll((elements) =>
      elements.map((element) => element.getAttribute("content")));
    expect(robots.length).toBeGreaterThan(0);
    expect(robots.every((content) => content?.includes("noindex"))).toBe(true);
  }
});

function alternateHref(document: Document, language: string): string | null | undefined {
  return document.querySelector(`link[rel="alternate"][hreflang="${language}"]`)?.getAttribute("href");
}
