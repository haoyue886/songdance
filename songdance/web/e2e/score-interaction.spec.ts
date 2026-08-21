import { expect, test } from "@playwright/test";
import { readFile } from "node:fs/promises";
import path from "node:path";
import type { NoteTimeline } from "../src/lib/result/timeline";
import {
  buildJob,
  installJobRoutes,
  mappedReferenceTimeline,
  qualitySummary,
  successfulArtifacts,
} from "./support/quality-job";

async function loadReferenceTimeline(): Promise<NoteTimeline> {
  return JSON.parse(await readFile(
    path.resolve(process.cwd(), "public/examples/mozart-sonata/timeline.json"),
    "utf8",
  ));
}

test("keeps mapped score navigation, selection and loop controls working", async ({ page }) => {
  const job = buildJob("mapped-score-interaction", qualitySummary, successfulArtifacts());
  const referenceTimeline = mappedReferenceTimeline(await loadReferenceTimeline());
  expect(referenceTimeline.notes).toHaveLength(320);
  expect(referenceTimeline.notes[0]?.id).toBe("note-1");
  expect(referenceTimeline.notes.at(-1)?.id).toBe("note-320");
  expect(referenceTimeline.downbeat_grid_seconds).toHaveLength(17);
  await installJobRoutes(page, job, referenceTimeline);
  await page.goto(`/zh/jobs/${job.id}`);

  const score = page.getByLabel("MusicXML 五线谱");
  const position = page.getByRole("slider", { name: "播放位置", exact: true });
  await expect(page.getByText("第 1 / 17 小节")).toBeVisible();
  await expect(page.getByRole("button", { name: "上一小节" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "下一小节" })).toBeEnabled();
  await page.getByRole("button", { name: "下一小节" }).click();
  const measureSeconds = (60 / referenceTimeline.tempo_bpm) * 4;
  await expect.poll(async () => Number(await position.inputValue()))
    .toBeCloseTo(measureSeconds, 1);
  await expect(page.getByText("第 2 / 17 小节")).toBeVisible();

  await position.press("Home");
  await expect(page.getByText("第 1 / 17 小节")).toBeVisible();
  await score.scrollIntoViewIfNeeded();
  const selectionStart = await page.getByTestId("active-measure-highlight").boundingBox();
  const scoreBox = await score.boundingBox();
  expect(selectionStart).not.toBeNull();
  expect(scoreBox).not.toBeNull();
  if (!selectionStart || !scoreBox) throw new Error("映射谱面未渲染");
  const dragY = Math.max(scoreBox.y + 20, selectionStart.y + selectionStart.height * 0.5);
  await page.mouse.move(selectionStart.x + selectionStart.width * 0.2, dragY);
  await page.mouse.down();
  await page.mouse.move(Math.min(
    scoreBox.x + scoreBox.width - 4,
    selectionStart.x + selectionStart.width * 1.8,
  ), dragY, { steps: 8 });
  await page.mouse.up();
  await expect(page.getByText(/谱面选区：/)).toBeVisible();
  await expect(page.locator('[data-score-selection-border="true"]')).not.toHaveCount(0);

  const start = Number(await page.getByRole("spinbutton", { name: "起点", exact: true }).inputValue());
  const endBeforeLoop = Number(await page.getByRole("spinbutton", { name: "终点", exact: true }).inputValue());
  expect(start).toBeGreaterThanOrEqual(0);
  expect(start).toBeLessThan(measureSeconds);
  expect(endBeforeLoop).toBeLessThanOrEqual(measureSeconds * 2);
  expect(endBeforeLoop).toBeGreaterThan(start);
  const end = endBeforeLoop;
  expect(end - start).toBeGreaterThan(1);
  const loop = page.getByRole("checkbox", { name: /循环/ });
  await page.getByRole("button", { name: "原音" }).click();
  await expect.poll(() => page.locator("audio").evaluate((audio) => ({
    duration: (audio as HTMLMediaElement).duration,
    readyState: (audio as HTMLMediaElement).readyState,
  }))).toMatchObject({ readyState: 4 });
  await expect.poll(() => page.locator("audio").evaluate((audio) => (audio as HTMLMediaElement).duration))
    .toBeGreaterThan(3);
  const playbackPosition = page.getByRole("slider", { name: "播放位置", exact: true });
  await playbackPosition.fill(String(start));
  await page.getByRole("button", { name: "播放" }).click();
  await expect(page.getByRole("button", { name: "暂停" })).toBeVisible();
  await playbackPosition.fill(String(end));
  await expect.poll(async () => Number(await playbackPosition.inputValue()))
    .toBeCloseTo(end, 1);
  await page.getByRole("button", { name: "暂停" }).click();

  await loop.check();
  await expect(loop).toBeChecked();
  await playbackPosition.fill(String(start));
  await page.evaluate(() => {
    const input = document.querySelector<HTMLInputElement>('input[aria-label="播放位置"]');
    const samples: number[] = [];
    if (!input) throw new Error("播放位置 slider 不存在");
    (window as typeof window & { __e2ePlaybackSamples?: number[] }).__e2ePlaybackSamples = samples;
    window.setInterval(() => samples.push(Number(input.value)), 25);
  });
  await page.getByRole("button", { name: "播放" }).click();
  await expect(page.getByRole("button", { name: "暂停" })).toBeVisible();
  await page.waitForTimeout((end - start) * 1_000 + 1_000);
  const samples = await page.evaluate(() =>
    (window as typeof window & { __e2ePlaybackSamples?: number[] }).__e2ePlaybackSamples ?? []);
  const maxSample = Math.max(...samples);
  const maxIndex = samples.findIndex((sample) => sample === maxSample);
  expect(maxSample).toBeGreaterThan(end - 0.2);
  expect(Math.min(...samples.slice(maxIndex + 1))).toBeLessThan(start + 0.5);
  await page.getByRole("button", { name: "暂停" }).click();
  await page.getByRole("button", { name: "清除选区" }).click();
  await expect(page.getByText(/谱面选区：/)).toHaveCount(0);
  await expect(page.getByRole("button", { name: "下一小节" })).toBeEnabled();
});
