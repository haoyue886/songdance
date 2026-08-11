import { Midi } from "@tonejs/midi";
import { expect, test } from "@playwright/test";
import { execFile } from "node:child_process";
import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { promisify } from "node:util";
import { createWav } from "./support/audio";
import { runE2eWorker } from "./support/worker";

const API_URL = "http://127.0.0.1:8002";
const execFileAsync = promisify(execFile);
const infrastructureTimeout = Number(process.env.PLAYWRIGHT_INFRASTRUCTURE_TIMEOUT ?? 30_000);
const infrastructureExpect = expect.configure({ timeout: infrastructureTimeout });

test("renders, plays and exports a real completed transcription", async ({ page }, testInfo) => {
  test.setTimeout(infrastructureTimeout * 2);
  const wavPath = testInfo.outputPath("result-piano.wav");
  await writeFile(wavPath, createWav(5));
  await page.goto("/zh/transcribe");
  await page.getByLabel("选择钢琴音频").setInputFiles(wavPath);
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "创建转录任务" }).click();
  await infrastructureExpect(page).toHaveURL(/\/zh\/jobs\/[A-Za-z0-9_-]{32,}/);
  const jobId = page.url().split("/").at(-1);
  if (!jobId) throw new Error("任务 URL 缺少任务 ID");

  await runE2eWorker();
  await infrastructureExpect(page.getByRole("heading", { name: "钢琴转录结果" })).toBeVisible();
  await infrastructureExpect(page.locator('[aria-label="MusicXML 五线谱"] svg')).toHaveCount(1);
  await infrastructureExpect
    .poll(async () => Number(await page.locator('[aria-label="MusicXML 五线谱"] svg').getAttribute("width")))
    .toBeGreaterThan(0);
  const position = page.getByRole("slider", { name: "播放位置", exact: true });
  const previousMeasure = page.getByRole("button", { name: "上一小节" });
  const nextMeasure = page.getByRole("button", { name: "下一小节" });
  const mappingUnavailable = page.getByText("小节定位不可用");
  if (await mappingUnavailable.isVisible()) {
    await expect(previousMeasure).toBeDisabled();
    await expect(nextMeasure).toBeDisabled();
  } else {
    await expect(page.getByText(/第 1 \/ \d+ 小节/)).toBeVisible();
    await expect(previousMeasure).toBeDisabled();
    if (await page.getByText("第 1 / 1 小节").isVisible()) await expect(nextMeasure).toBeDisabled();
  }
  const scoreProgress = page.getByRole("progressbar", { name: "五线谱播放位置" });
  await position.press("Home");
  await infrastructureExpect(scoreProgress).toHaveAttribute("aria-valuenow", "0");
  await position.press("End");
  expect(Number(await position.inputValue())).toBeGreaterThan(4);
  await infrastructureExpect
    .poll(async () => Number(await scoreProgress.getAttribute("aria-valuenow")))
    .toBeGreaterThan(4);

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
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.getByRole("button", { name: "升半音" }).click();
  await expect(page.getByText("+1", { exact: true })).toBeVisible();
  await page.getByLabel("播放速度").selectOption("1.5");
  await position.press("Home");
  await page.getByRole("button", { name: "播放" }).click();
  await expect(page.getByRole("button", { name: "暂停" })).toBeVisible();
  await page.waitForTimeout(500);
  expect(Number(await position.inputValue())).toBeGreaterThan(0.65);
  await page.getByRole("button", { name: "暂停" }).click();

  await page.getByRole("button", { name: "原音" }).click();
  await page.getByRole("button", { name: "播放" }).click();
  await expect
    .poll(() => page.locator("audio").evaluate((audio) => (audio as HTMLMediaElement).paused))
    .toBe(false);
  await page.getByRole("button", { name: "转录演奏", exact: true }).click();
  await expect
    .poll(() => page.locator("audio").evaluate((audio) => (audio as HTMLMediaElement).paused))
    .toBe(true);
  await page.getByRole("button", { name: "暂停" }).click();

  await page.getByRole("spinbutton", { name: "起点", exact: true }).fill("0.4");
  await page.getByRole("spinbutton", { name: "终点", exact: true }).fill("0.9");
  await page.getByRole("checkbox").check();
  await setRangeValue(position, 0.8);
  await page.getByRole("button", { name: "播放" }).click();
  await expect.poll(async () => Number(await position.inputValue()), { timeout: 1_500 }).toBeLessThan(0.75);
  await page.getByRole("button", { name: "暂停" }).click();

  const ticketResponse = await page.request.get(
    `${API_URL}/jobs/${jobId}/download-url/midi`,
  );
  expect(ticketResponse.ok()).toBe(true);
  const ticket = (await ticketResponse.json()) as { path: string };
  const originalResponse = await page.request.get(`${API_URL}${ticket.path}`);
  expect(originalResponse.ok()).toBe(true);
  const original = new Midi(new Uint8Array(await originalResponse.body()));
  const originalPitches = original.tracks.flatMap((track) => track.notes.map((note) => note.midi));
  const exportPanel = page.getByRole("complementary", { name: "导出", exact: true });
  const midiDownload = page.waitForEvent("download");
  await exportPanel.getByRole("button", { name: /^清洗后 MIDI / }).click();
  const midiPath = testInfo.outputPath("plus-one.mid");
  await (await midiDownload).saveAs(midiPath);
  const exported = new Midi(new Uint8Array(await readFile(midiPath)));
  const exportedPitches = exported.tracks.flatMap((track) => track.notes.map((note) => note.midi));
  expect(exportedPitches).toEqual(originalPitches.map((pitch) => pitch + 1));

  await page.getByRole("tab", { name: "五线谱" }).click();
  await expect(exportPanel.getByRole("button", { name: /^PDF / })).toBeEnabled();
  for (const [name, extension, prefix] of [
    ["MusicXML", "musicxml", "<?xml"],
    ["PDF", "pdf", "%PDF"],
  ] as const) {
    const pending = page.waitForEvent("download");
    await exportPanel.getByRole("button", { name: new RegExp(`^${name} `) }).click();
    const downloadPath = testInfo.outputPath(`plus-one.${extension}`);
    await (await pending).saveAs(downloadPath);
    expect((await readFile(downloadPath)).toString("utf8", 0, prefix.length)).toBe(prefix);
    if (extension === "musicxml") await verifyMusicXml(downloadPath);
    else await verifyPdf(downloadPath, testInfo.outputPath("plus-one-page"));
  }

  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "立即删除音频和结果" }).click();
  await expect(page).toHaveURL(/\/zh\/transcribe\?deleted=1$/);
});

async function verifyMusicXml(musicXmlPath: string): Promise<void> {
  const python = path.resolve(process.cwd(), "../api/.venv/bin/python");
  const script = [
    "from music21 import converter",
    "import sys",
    "score = converter.parse(sys.argv[1])",
    "print(len(score.parts), len(list(score.recurse().notes)), len(list(score.recurse().getElementsByClass('Measure'))))",
  ].join("; ");
  const { stdout } = await execFileAsync(python, ["-c", script, musicXmlPath]);
  const [parts, notes, measures] = stdout.trim().split(/\s+/).map(Number);
  expect(parts).toBeGreaterThan(0);
  expect(notes).toBeGreaterThan(0);
  expect(measures).toBeGreaterThan(0);
}

async function setRangeValue(
  input: import("@playwright/test").Locator,
  value: number,
): Promise<void> {
  await input.evaluate((element: HTMLInputElement, nextValue) => {
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
    setter?.call(element, String(nextValue));
    element.dispatchEvent(new Event("input", { bubbles: true }));
    element.dispatchEvent(new Event("change", { bubbles: true }));
  }, value);
  await expect(input).toHaveValue(String(value));
}

async function verifyPdf(pdfPath: string, renderBase: string): Promise<void> {
  const { stdout } = await execFileAsync("pdfinfo", [pdfPath]);
  expect(stdout).toMatch(/Title:\s+SongDance Piano Transcription/);
  expect(stdout).toMatch(/Pages:\s+1/);
  expect(stdout).toMatch(/Page size:\s+595(?:\.\d+)? x 841(?:\.\d+)? pts \(A4\)/);
  await execFileAsync("pdftoppm", [
    "-f",
    "1",
    "-l",
    "1",
    "-singlefile",
    "-r",
    "36",
    "-gray",
    pdfPath,
    renderBase,
  ]);
  const rendered = await readFile(`${renderBase}.pgm`);
  const imageStart = rendered.indexOf(Buffer.from("\n255\n"));
  expect(imageStart).toBeGreaterThan(0);
  const darkPixels = rendered.subarray(imageStart + 5).filter((value) => value < 245).length;
  expect(darkPixels).toBeGreaterThan(100);
}
