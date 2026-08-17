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

test("serves the additional locale pages with localized core metadata", async ({ page }) => {
  const locales = [
    { path: "/ja", lang: "ja", heading: "ピアノ録音向けオーディオMIDI変換ツール", transcribeHeading: "きれいなピアノ録音を準備" },
    { path: "/ko", lang: "ko", heading: "피아노 녹음을 위한 오디오 MIDI 변환기", transcribeHeading: "깨끗한 피아노 녹음 준비" },
    { path: "/es", lang: "es", heading: "Convertidor de audio a MIDI para grabaciones de piano", transcribeHeading: "Prepara una grabación de piano limpia" },
    { path: "/pt-br", lang: "pt-BR", heading: "Conversor de áudio para MIDI para gravações de piano", transcribeHeading: "Prepare uma gravação de piano limpa" },
    { path: "/fr", lang: "fr", heading: "Convertisseur audio vers MIDI pour les enregistrements de piano", transcribeHeading: "Préparez un enregistrement de piano propre" },
    { path: "/de", lang: "de", heading: "Audio-zu-MIDI-Konverter für Klavieraufnahmen", transcribeHeading: "Eine klare Klavieraufnahme vorbereiten" },
  ];
  for (const locale of locales) {
    await page.goto(locale.path);
    await expect(page.locator("html")).toHaveAttribute("lang", locale.lang);
    await expect(page.getByRole("heading", { level: 1, name: locale.heading })).toBeVisible();
    await expect(page.locator("select option")).toHaveCount(8);
    await page.goto(`${locale.path}/transcribe`);
    await expect(page.locator("html")).toHaveAttribute("lang", locale.lang);
    await expect(page.getByRole("heading", { level: 1, name: locale.transcribeHeading })).toBeVisible();
  }
});

test("keeps shared public pages within the 375px viewport", async ({ page }, testInfo) => {
  const paths = ["/", "/zh", "/ja", "/ko", "/es", "/pt-br", "/fr", "/de", "/transcribe", "/zh/transcribe", "/ja/transcribe", "/ko/transcribe", "/es/transcribe", "/pt-br/transcribe", "/fr/transcribe", "/de/transcribe", "/examples", "/zh/examples"];
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
  const languageLabel = path === "/zh" || path.startsWith("/zh/") ? "语言"
    : path === "/ja" || path.startsWith("/ja/") ? "言語"
      : path === "/ko" || path.startsWith("/ko/") ? "언어"
        : path === "/es" || path.startsWith("/es/") || path === "/pt-br" || path.startsWith("/pt-br/") ? "Idioma"
          : path === "/fr" || path.startsWith("/fr/") ? "Langue"
            : path === "/de" || path.startsWith("/de/") ? "Sprache" : "Language";
  await expect(page.getByLabel(languageLabel)).toBeVisible();
  await expect(page.getByText("Loading SongDance...")).toHaveCount(0);
}

async function expectNoHorizontalOverflow(page: Page): Promise<void> {
  const widths = await page.evaluate(() => ({
    client: document.documentElement.clientWidth,
    scroll: document.documentElement.scrollWidth,
  }));
  expect(widths.scroll).toBe(widths.client);
}
