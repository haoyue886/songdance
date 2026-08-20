import { Midi } from "@tonejs/midi";
import { expect, test } from "@playwright/test";
import { execFile } from "node:child_process";
import { readFile } from "node:fs/promises";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);
const infrastructureTimeout = Number(process.env.PLAYWRIGHT_INFRASTRUCTURE_TIMEOUT ?? 30_000);
const infrastructureExpect = expect.configure({ timeout: infrastructureTimeout });

test("keeps local upload available when the YouTube flag is off", async ({ page }) => {
  await page.goto("/zh/transcribe");
  await page.getByRole("tab", { name: "YouTube" }).click();
  await expect(page.getByText("YouTube 导入当前未开放")).toBeVisible();
  await page.getByRole("button", { name: "改用本地上传" }).click();
  await expect(page.getByLabel("选择钢琴音频")).toBeVisible();
});

test("keeps the failed public-domain example available for review", async ({ page }, testInfo) => {
  test.setTimeout(infrastructureTimeout * 2);
  await page.goto("/zh/examples");
  await expect(page.getByRole("heading", { name: "公开示例正在质量复核" })).toBeVisible();
  for (const label of ["当前产物", "待人工复评", "最近完成人工评级", "需要重新转录"])
    await expect(page.getByText(label)).toBeVisible();
  await expect(page.getByRole("link", { name: "Wikimedia Commons 录音" })).toHaveAttribute("href", /commons\.wikimedia\.org/);
  await expect(page.getByText("Public domain")).toBeVisible();
  const scorePages = page.locator('[aria-label="MusicXML 五线谱"] svg');
  await infrastructureExpect.poll(() => scorePages.count()).toBeGreaterThan(0);
  await infrastructureExpect
    .poll(async () => Number(await scorePages.first().getAttribute("width")))
    .toBeGreaterThan(0);

  await expect(page.getByText("小节定位不可用")).toBeVisible();
  await expect(page.getByRole("button", { name: "上一小节" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "下一小节" })).toBeDisabled();
  const position = page.getByRole("slider", { name: "播放位置", exact: true });
  await position.press("End");
  await expect.poll(async () => Number(await position.inputValue())).toBeGreaterThan(20);
  await page.getByRole("button", { name: "播放" }).click();
  await expect(page.getByRole("button", { name: /^(播放|暂停)$/ })).toHaveCount(1);
  await position.fill("0");
  await page.getByRole("button", { name: "原音" }).click();
  await infrastructureExpect
    .poll(() => page.locator("audio").evaluate((audio) => (audio as HTMLMediaElement).readyState))
    .toBeGreaterThan(0);
  await page.getByRole("button", { name: "播放" }).click();
  await expect.poll(() => page.locator("audio").evaluate((audio) => (audio as HTMLMediaElement).paused)).toBe(false);
  const sourcePause = page.getByRole("button", { name: "暂停" });
  if (await sourcePause.isVisible().catch(() => false)) await sourcePause.click({ timeout: 2_000 }).catch(() => undefined);

  await page.getByRole("tab", { name: "钢琴卷帘" }).click();
  const pianoRoll = page.getByRole("img", { name: /钢琴卷帘/ });
  await expect(pianoRoll).toBeVisible();
  expect(await pianoRoll.evaluate((element) => element.tagName)).toBe("CANVAS");
  await infrastructureExpect
    .poll(() => pianoRoll.evaluate((element) => Number(element.getAttribute("width") ?? 0)))
    .toBeGreaterThan(0);
  await page.setViewportSize({ width: 375, height: 812 });
  await expect(pianoRoll).toBeVisible();
  const rollWidths = await page.evaluate(() => ({
    client: document.documentElement.clientWidth,
    scroll: document.documentElement.scrollWidth,
  }));
  expect(rollWidths.scroll).toBe(rollWidths.client);
  await page.screenshot({ path: testInfo.outputPath("example-roll-mobile.png"), fullPage: true });
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.getByRole("tab", { name: "五线谱" }).click();

  const exportPanel = page.getByRole("complementary", { name: "导出", exact: true });
  const midiDownload = page.waitForEvent("download");
  await exportPanel.getByRole("button", { name: /^清洗后 MIDI / }).click();
  const midiPath = testInfo.outputPath("example.mid");
  await (await midiDownload).saveAs(midiPath);
  const midi = new Midi(new Uint8Array(await readFile(midiPath)));
  expect(midi.tracks.flatMap((track) => track.notes)).not.toHaveLength(0);

  for (const [name, extension, prefix] of [
    ["MusicXML", "musicxml", "<?xml"],
    ["PDF", "pdf", "%PDF"],
  ] as const) {
    const pending = page.waitForEvent("download");
    await exportPanel.getByRole("button", { name: new RegExp(`^${name} `) }).click();
    const downloadPath = testInfo.outputPath(`example.${extension}`);
    await (await pending).saveAs(downloadPath);
    const bytes = await readFile(downloadPath);
    expect(bytes.toString("utf8", 0, prefix.length)).toBe(prefix);
    if (extension === "pdf") {
      const { stdout } = await execFileAsync("pdfinfo", [downloadPath]);
      const pages = Number(stdout.match(/Pages:\s+(\d+)/)?.[1] ?? 0);
      expect(pages).toBeGreaterThan(0);
      expect(stdout).toMatch(/Page size:\s+595(?:\.\d+)? x 841(?:\.\d+)? pts \(A4\)/);
    }
  }
});
