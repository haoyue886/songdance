import { expect, test, type Page } from "@playwright/test";

test("switches locale while preserving the logical page, query and hash", async ({ page, context }) => {
  await page.goto("/zh/examples?source=phase28#sample-score");
  await page.getByLabel("语言").selectOption("en");
  await expect(page).toHaveURL(/\/examples\?source=phase28#sample-score$/);
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(page.getByRole("heading", { level: 1, name: "Hear the source. Inspect the transcription." }))
    .toBeVisible();

  const cookie = (await context.cookies()).find((entry) => entry.name === "NEXT_LOCALE");
  expect(cookie?.value).toBe("en");
});

test("keeps an anonymous job id when switching to Chinese", async ({ page }) => {
  await page.goto("/jobs/phase28-locale-job?source=header#result");
  await page.getByLabel("Language").selectOption("zh-CN");
  await expect(page).toHaveURL(/\/zh\/jobs\/phase28-locale-job\?source=header#result$/);
  await expect(page.locator("html")).toHaveAttribute("lang", "zh-CN");
});

test("keeps shared public pages within the 375px viewport", async ({ page }, testInfo) => {
  const paths = ["/", "/zh", "/transcribe", "/zh/transcribe", "/examples", "/zh/examples"];
  await page.setViewportSize({ width: 375, height: 812 });
  for (const path of paths) {
    await page.goto(path);
    await expectPageReady(page, path);
    await expectNoHorizontalOverflow(page);
    await page.screenshot({
      path: testInfo.outputPath(`mobile${path.replaceAll("/", "-") || "-en-home"}.png`),
      fullPage: true,
    });
  }

  await page.setViewportSize({ width: 1440, height: 900 });
  for (const path of paths) {
    await page.goto(path);
    await expectPageReady(page, path);
    await expectNoHorizontalOverflow(page);
    await page.screenshot({
      path: testInfo.outputPath(`desktop${path.replaceAll("/", "-") || "-en-home"}.png`),
      fullPage: true,
    });
  }
});

async function expectPageReady(page: Page, path: string): Promise<void> {
  await expect(page.locator("main h1").first()).toBeVisible();
  await expect(page.getByLabel(path.startsWith("/zh") ? "语言" : "Language")).toBeVisible();
  await expect(page.getByText("Loading SongDance...")).toHaveCount(0);
}

async function expectNoHorizontalOverflow(page: Page): Promise<void> {
  const widths = await page.evaluate(() => ({
    client: document.documentElement.clientWidth,
    scroll: document.documentElement.scrollWidth,
  }));
  expect(widths.scroll).toBe(widths.client);
}
