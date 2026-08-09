import { Midi } from "@tonejs/midi";
import { expect, test } from "@playwright/test";
import { execFile } from "node:child_process";
import { readFile } from "node:fs/promises";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);
const infrastructureTimeout = Number(process.env.PLAYWRIGHT_INFRASTRUCTURE_TIMEOUT ?? 30_000);
const infrastructureExpect = expect.configure({ timeout: infrastructureTimeout });

test("keeps local upload available when the YouTube flag is off", async ({ page }) => {
  await page.goto("/transcribe");
  await page.getByRole("tab", { name: "抖音" }).click();
  await expect(page.getByText("抖音导入当前未开放")).toBeVisible();
  await page.getByRole("button", { name: "改用本地上传" }).click();
  await expect(page.getByLabel("选择钢琴音频")).toBeVisible();
});

test("plays, switches views and exports the public-domain example", async ({ page }, testInfo) => {
  await page.goto("/examples");
  await expect(page.getByRole("heading", { name: "先听一段真实钢琴转录" })).toBeVisible();
  await expect(page.getByRole("link", { name: "查看录音来源与许可证" }))
    .toHaveAttribute("href", /commons\.wikimedia\.org/);
  const scorePages = page.locator('[aria-label="MusicXML 五线谱"] svg');
  await infrastructureExpect.poll(() => scorePages.count()).toBeGreaterThan(0);
  await infrastructureExpect
    .poll(async () => Number(await scorePages.first().getAttribute("width")))
    .toBeGreaterThan(0);

  const position = page.getByRole("slider", { name: "播放位置", exact: true });
  await page.getByRole("button", { name: "播放" }).click();
  await expect.poll(async () => Number(await position.inputValue())).toBeGreaterThan(0.2);
  await page.getByRole("button", { name: "暂停" }).click();
  await page.getByRole("button", { name: "原音" }).click();
  await page.getByRole("button", { name: "播放" }).click();
  await expect.poll(() => page.locator("audio").evaluate((audio) => ({
    currentTime: (audio as HTMLMediaElement).currentTime,
    readyState: (audio as HTMLMediaElement).readyState,
  }))).toMatchObject({ currentTime: expect.any(Number), readyState: 4 });
  await expect.poll(() => page.locator("audio").evaluate(
    (audio) => (audio as HTMLMediaElement).currentTime,
  )).toBeGreaterThan(0.2);
  await page.getByRole("button", { name: "暂停" }).click();
  await page.getByRole("button", { name: "转录演奏", exact: true }).click();

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

  const exportPanel = page.getByRole("complementary", { name: "格式导出" });
  const midiDownload = page.waitForEvent("download");
  await exportPanel.getByRole("button", { name: /^MIDI / }).click();
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
