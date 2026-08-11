import { expect, test } from "@playwright/test";
import { JSDOM } from "jsdom";

test("serves crawlable SEO assets and keeps job pages out of the index", async ({ page, request }, testInfo) => {
  const corePageResponse = await request.get("/audio-to-midi");
  expect(corePageResponse.status()).toBe(200);
  const serverDocument = new JSDOM(await corePageResponse.text()).window.document;
  expect(serverDocument.querySelectorAll("h1")).toHaveLength(1);
  expect(serverDocument.querySelector("h1")?.textContent).toContain("Audio to MIDI Converter for Piano Recordings");
  expect(serverDocument.body.textContent).toContain("Convert piano audio");
  expect(serverDocument.body.textContent).toContain("Is the generated MIDI always accurate?");
  const serverJsonLd = JSON.parse(
    serverDocument.querySelector('script[type="application/ld+json"]')?.textContent ?? "{}",
  ) as { "@graph"?: Array<{ "@type"?: string; offers?: unknown }> };
  expect(serverJsonLd["@graph"]?.map((entry) => entry["@type"]))
    .toEqual(["WebApplication", "FAQPage"]);
  expect(serverJsonLd["@graph"]?.[0]).not.toHaveProperty("offers");

  await page.goto("/audio-to-midi");

  await expect(page).toHaveTitle("Audio to MIDI Converter for Piano Recordings | SongDance");
  await expect(page.getByRole("heading", {
    level: 1,
    name: "Audio to MIDI Converter for Piano Recordings",
  })).toHaveCount(1);
  await expect(page.locator('link[rel="canonical"]'))
    .toHaveAttribute("href", "http://localhost:3001/audio-to-midi");
  await expect(page.getByRole("link", { name: "Convert piano audio" }))
    .toHaveAttribute("href", "/transcribe");

  const jsonLd = await page.locator('script[type="application/ld+json"]').textContent();
  const structuredData = JSON.parse(jsonLd ?? "{}") as {
    "@graph"?: Array<{ "@type"?: string }>;
  };
  expect(structuredData["@graph"]?.map((entry) => entry["@type"]))
    .toEqual(["WebApplication", "FAQPage"]);
  await page.screenshot({ path: testInfo.outputPath("audio-to-midi-desktop.png"), fullPage: true });

  const robotsResponse = await request.get("/robots.txt");
  expect(robotsResponse.status()).toBe(200);
  expect(await robotsResponse.text()).toContain("Sitemap: http://localhost:3001/sitemap.xml");

  const sitemapResponse = await request.get("/sitemap.xml");
  expect(sitemapResponse.status()).toBe(200);
  const sitemap = await sitemapResponse.text();
  expect(sitemap).toContain("http://localhost:3001/audio-to-midi");
  expect(sitemap).not.toContain("/jobs/");

  await page.goto("/jobs/seo-index-test");
  await expect(page.locator('meta[name="robots"]'))
    .toHaveAttribute("content", /noindex/);
  await expect(page.locator('meta[property="og:url"]')).toHaveCount(0);
  await expect(page.locator('meta[property^="og:"]')).toHaveCount(0);
  await expect(page.locator('meta[name^="twitter:"]')).toHaveCount(0);

  const notFoundResponse = await page.goto("/seo-route-that-does-not-exist");
  expect(notFoundResponse?.status()).toBe(404);
  await expect(page).toHaveTitle("Page not found | SongDance");
  await expect(page.locator("title")).toHaveCount(1);
  await expect(page.locator('meta[name="robots"]')).toHaveCount(1);
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content", "noindex");
  await expect(page.locator('meta[property^="og:"]')).toHaveCount(0);
  await expect(page.locator('meta[name^="twitter:"]')).toHaveCount(0);

  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/audio-to-midi");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth))
    .toBe(true);
  await page.screenshot({ path: testInfo.outputPath("audio-to-midi-mobile.png"), fullPage: true });
});
