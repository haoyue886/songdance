import { expect, test } from "@playwright/test";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { buildJob, installJobRoutes, qualitySummary, successfulArtifacts, timeline } from "./support/quality-job";

test("shows a high-quality report and remains usable at 375px", async ({ page }) => {
  const job = buildJob("quality-high", qualitySummary, successfulArtifacts());
  const mappedTimeline = JSON.parse(await readFile(
    path.resolve(process.cwd(), "public/examples/mozart-sonata/timeline.json"),
    "utf8",
  ));
  await installJobRoutes(page, job, mappedTimeline);
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto(`/zh/jobs/${job.id}`);

  await expect(page.getByRole("heading", { name: "质量摘要" })).toBeVisible();
  const position = page.getByRole("slider", { name: "播放位置", exact: true });
  const score = page.getByLabel("MusicXML 五线谱");
  const cursor = score.locator('img[id^="cursorImg"]');
  await expect(page.getByText(/第 1 \/ \d+ 小节/)).toBeVisible();
  await expect(page.getByRole("button", { name: "上一小节" })).toBeDisabled();
  await expect(cursor).toBeVisible();
  const firstCursorBox = await cursor.boundingBox();
  expect(firstCursorBox).not.toBeNull();
  const firstScroll = await page.evaluate(() => ({ x: window.scrollX, y: window.scrollY }));
  const firstCursorPosition = firstCursorBox
    ? { x: firstCursorBox.x + firstScroll.x, y: firstCursorBox.y + firstScroll.y }
    : null;
  await page.getByRole("button", { name: "下一小节" }).click();
  await expect.poll(async () => Number(await position.inputValue())).toBeCloseTo(0.580499, 1);
  await expect.poll(async () => {
    const nextCursorBox = await cursor.boundingBox();
    const scroll = await page.evaluate(() => ({ x: window.scrollX, y: window.scrollY }));
    return nextCursorBox && firstCursorPosition
      ? Math.hypot(
        nextCursorBox.x + scroll.x - firstCursorPosition.x,
        nextCursorBox.y + scroll.y - firstCursorPosition.y,
      )
      : 0;
  }).toBeGreaterThan(1);
  await position.press("Home");
  await expect.poll(async () => {
    const currentCursorBox = await cursor.boundingBox();
    const scroll = await page.evaluate(() => ({ x: window.scrollX, y: window.scrollY }));
    return currentCursorBox && firstCursorPosition
      ? Math.hypot(
        currentCursorBox.x + scroll.x - firstCursorPosition.x,
        currentCursorBox.y + scroll.y - firstCursorPosition.y,
      )
      : Number.POSITIVE_INFINITY;
  }).toBeLessThan(1);
  await score.locator("text").filter({ hasText: /^2$/ }).first().click();
  await expect.poll(async () => Number(await position.inputValue())).toBeGreaterThan(0);
  await expect(page.getByText("3 / 2")).toBeVisible();
  await expect(page.getByText("84%")).toBeVisible();
  await expect(page.getByText("自动分析仅供校对，不代表人工谱面级准确率")).toBeVisible();
  await expect(page.getByRole("button", { name: /^清洗后 MIDI/ })).toBeEnabled();
  const widths = await page.evaluate(() => ({
    client: document.documentElement.clientWidth,
    scroll: document.documentElement.scrollWidth,
  }));
  expect(widths.scroll).toBe(widths.client);
});

test("keeps the score, playback and downloads when measure mapping is unavailable", async ({ page }) => {
  const job = buildJob("quality-unmapped-score", qualitySummary, successfulArtifacts());
  await installJobRoutes(page, job, { ...timeline, time_signature: "free" });
  await page.goto(`/zh/jobs/${job.id}`);

  await expect(page.locator('[aria-label="MusicXML 五线谱"] svg')).toHaveCount(6);
  await expect(page.getByText("小节定位不可用")).toBeVisible();
  await expect(page.getByRole("button", { name: "上一小节" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "下一小节" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "播放" })).toBeEnabled();
  await expect(page.getByRole("button", { name: /^清洗后 MIDI/ })).toBeEnabled();
  await expect(page.getByRole("button", { name: /^MusicXML/ })).toBeEnabled();
});

test("shows low-confidence defaults from the backend report", async ({ page }) => {
  const summary = {
    ...qualitySummary,
    analysis: {
      ...qualitySummary.analysis,
      bpm_confidence: 0,
      time_signature_confidence: 0.2,
      key_confidence: 0.1,
      reason_codes: [
        "TEMPO_DEFAULTED",
        "TIME_SIGNATURE_DEFAULTED_4_4",
        "KEY_SIGNATURE_DEFAULTED_C_MAJOR",
      ],
    },
  };
  const job = buildJob("quality-low", summary, successfulArtifacts());
  await installJobRoutes(page, job);
  await page.goto(`/zh/jobs/${job.id}`);

  await expect(page.getByText("BPM 置信度不足，当前速度为系统默认值。")).toBeVisible();
  await expect(page.getByText("拍号置信度不足，当前按 4/4 排版。")).toBeVisible();
  await expect(page.getByText("调性置信度不足，当前按 C major 排版。")).toBeVisible();
});

test("keeps roll, MIDI and source playback when MusicXML failed", async ({ page }) => {
  const summary = {
    ...qualitySummary,
    musicxml_parse: { status: "failed", error_code: "MUSICXML_PARSE_FAILED" },
    structure_errors: ["MUSICXML_PARSE_FAILED"],
  };
  const artifacts = successfulArtifacts().map((artifact) =>
    artifact.type === "musicxml"
      ? { ...artifact, status: "failed" as const, size_bytes: 0, error_code: "MUSICXML_PARSE_FAILED" }
      : artifact,
  );
  const job = buildJob("quality-musicxml-failed", summary, artifacts);
  await installJobRoutes(page, job);
  await page.goto(`/zh/jobs/${job.id}`);

  await expect(page.getByRole("img", { name: /钢琴卷帘/ })).toBeVisible();
  await expect(page.getByRole("tab", { name: "五线谱" })).toBeDisabled();
  await expect(page.getByRole("button", { name: /^原始 MIDI/ })).toBeEnabled();
  await expect(page.getByRole("button", { name: /^清洗后 MIDI/ })).toBeEnabled();
  await expect(page.getByRole("button", { name: "原音" })).toBeEnabled();
  await expect(page.getByText(/五线谱生成失败/)).toBeVisible();
});

test("uses raw timeline and labels the preview when cleanup falls back", async ({ page }) => {
  const summary = {
    ...qualitySummary,
    cleaned_note_count: 3,
    cleanup: {
      ...qualitySummary.cleanup,
      status: "failed",
      removed_note_count: 0,
      fallback_used: true,
      error_code: "NOTE_CLEANUP_FAILED",
    },
  };
  const job = buildJob("quality-cleanup-fallback", summary, successfulArtifacts());
  await installJobRoutes(page, job);
  await page.goto(`/zh/jobs/${job.id}`);

  await expect(page.getByText("当前预览：原始模型音符（清洗结果不可用）")).toBeVisible();
  await expect(page.getByText("音符清洗失败，预览已回退到原始模型音符。")).toBeVisible();
  await expect(page.getByRole("img", { name: /钢琴卷帘/ })).toBeVisible();
  await expect(page.getByRole("tab", { name: "五线谱" })).toBeDisabled();
  await expect(page.getByRole("button", { name: /^MusicXML/ })).toBeDisabled();
  await expect(page.getByRole("button", { name: /^PDF/ })).toBeDisabled();
  await expect(page.getByRole("button", { name: /^原始 MIDI/ })).toBeEnabled();
});
