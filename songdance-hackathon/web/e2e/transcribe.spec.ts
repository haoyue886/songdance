import { expect, test } from "@playwright/test";
import { execFile } from "node:child_process";
import { writeFile } from "node:fs/promises";
import { promisify } from "node:util";
import { createWav } from "./support/audio";

const execFileAsync = promisify(execFile);

test("uploads, creates, restores and deletes a real WAV job", async ({ page }, testInfo) => {
  const wavPath = testInfo.outputPath("phase2-piano.wav");
  await writeFile(wavPath, createWav(2));
  await page.goto("/transcribe");

  await page.getByLabel("选择钢琴音频").setInputFiles(wavPath);
  await expect(page.getByText("phase2-piano.wav")).toBeVisible();
  await expect(page.getByText("总时长 2.00 秒")).toBeVisible();
  await expect(page.locator("canvas")).toHaveCount(2);

  const endInput = page.getByLabel("结束时间");
  const rightHandle = page.locator('[part~="region-handle-right"]');
  await expect(rightHandle).toBeVisible();
  const handleBox = await rightHandle.boundingBox();
  if (!handleBox) throw new Error("WaveSurfer 右侧选区手柄没有布局尺寸");
  await rightHandle.hover();
  await page.mouse.down();
  await page.mouse.move(handleBox.x - 300, handleBox.y + handleBox.height / 2, { steps: 8 });
  await page.mouse.up();
  await expect.poll(async () => Number(await endInput.inputValue())).toBeLessThan(2);

  await page.getByRole("button", { name: "播放选区" }).click();
  await expect(page.getByRole("button", { name: "暂停" })).toBeVisible();
  await expect(page.getByRole("button", { name: "播放选区" })).toBeVisible({ timeout: 4_000 });

  const confirmButton = page.getByRole("button", { name: "创建转录任务" });
  await expect(confirmButton).toBeDisabled();
  await page.getByRole("checkbox").check();
  await expect(confirmButton).toBeEnabled();
  await confirmButton.click();
  await expect(page).toHaveURL(/\/jobs\/[A-Za-z0-9_-]{32,}/);
  await expect(page.getByRole("heading", { name: "等待处理" })).toBeVisible();
  const jobUrl = page.url();
  const jobId = jobUrl.split("/").at(-1);
  if (!jobId) throw new Error("任务 URL 缺少任务 ID");

  await page.reload();
  await expect(page).toHaveURL(jobUrl);
  await expect(page.getByRole("heading", { name: "等待处理" })).toBeVisible();

  await page.screenshot({ path: testInfo.outputPath("desktop.png"), fullPage: true });

  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "立即删除音频和任务" }).click();
  await expect(page).toHaveURL(/\/transcribe\?deleted=1$/);
  const deleted = await page.request.get(`http://127.0.0.1:8002/jobs/${jobId}`);
  expect(deleted.status()).toBe(404);
});

test("accepts browser-decodable MP3 and M4A files", async ({ page }, testInfo) => {
  const wavPath = testInfo.outputPath("source.wav");
  await writeFile(wavPath, createWav(2));
  const formats = [
    { extension: "mp3", codec: "libmp3lame", label: "MP3" },
    { extension: "m4a", codec: "aac", label: "M4A" },
  ];

  for (const format of formats) {
    const outputPath = testInfo.outputPath(`phase2-piano.${format.extension}`);
    await execFileAsync("ffmpeg", [
      "-hide_banner",
      "-loglevel",
      "error",
      "-i",
      wavPath,
      "-c:a",
      format.codec,
      "-y",
      outputPath,
    ]);
    await page.goto("/transcribe");
    await page.getByLabel("选择钢琴音频").setInputFiles(outputPath);
    await expect(page.getByText(`phase2-piano.${format.extension}`)).toBeVisible();
    await expect(page.getByText(format.label, { exact: true })).toBeVisible();
    await expect(page.getByText(/总时长 2\.0\d 秒/)).toBeVisible();
  }
});

test("caps a manually expanded real clip at 90 seconds", async ({ page }, testInfo) => {
  const wavPath = testInfo.outputPath("long-piano.wav");
  await writeFile(wavPath, createWav(120));
  await page.goto("/transcribe");
  await page.getByLabel("选择钢琴音频").setInputFiles(wavPath);

  const endInput = page.getByLabel("结束时间");
  await expect(endInput).toHaveValue("30");
  await endInput.fill("120");
  await expect(endInput).toHaveValue("90");
  await expect(page.getByText("90.00 秒", { exact: true })).toBeVisible();
});

test("keeps the upload flow usable at 375px", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/transcribe");

  const widths = await page.evaluate(() => ({
    client: document.documentElement.clientWidth,
    scroll: document.documentElement.scrollWidth,
  }));
  expect(widths.scroll).toBe(widths.client);
  await expect(page.getByRole("button", { name: "选择文件" })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("mobile.png"), fullPage: true });
});
