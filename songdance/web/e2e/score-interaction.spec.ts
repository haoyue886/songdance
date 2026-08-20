import { expect, test } from "@playwright/test";
import { buildJob, installJobRoutes, mappedTimeline, qualitySummary, successfulArtifacts } from "./support/quality-job";

test("keeps mapped score navigation, selection and loop controls working", async ({ page }) => {
  const job = buildJob("mapped-score-interaction", qualitySummary, successfulArtifacts());
  await installJobRoutes(page, job, mappedTimeline);
  await page.goto(`/zh/jobs/${job.id}`);

  const score = page.getByLabel("MusicXML 五线谱");
  const position = page.getByRole("slider", { name: "播放位置", exact: true });
  await expect(page.getByText("第 1 / 17 小节")).toBeVisible();
  await expect(page.getByRole("button", { name: "上一小节" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "下一小节" })).toBeEnabled();
  await score.locator("text").filter({ hasText: /^2$/ }).first().click();
  await expect.poll(async () => Number(await position.inputValue())).toBeGreaterThan(1);
  await expect(page.getByText("第 2 / 17 小节")).toBeVisible();

  const selectionStart = await score.locator("svg").first().boundingBox();
  expect(selectionStart).not.toBeNull();
  if (!selectionStart) throw new Error("映射谱面未渲染");
  await page.mouse.move(selectionStart.x + 180, selectionStart.y + 160);
  await page.mouse.down();
  await page.mouse.move(selectionStart.x + 300, selectionStart.y + 160, { steps: 8 });
  await page.mouse.up();
  await expect(page.getByText(/谱面选区：/)).toBeVisible();
  await expect(page.locator('[data-score-selection-border="true"]')).not.toHaveCount(0);

  const start = Number(await page.getByRole("spinbutton", { name: "起点", exact: true }).inputValue());
  const endInput = page.getByRole("spinbutton", { name: "终点", exact: true });
  await endInput.fill(String(start + 2));
  const end = Number(await endInput.inputValue());
  expect(end - start).toBeGreaterThan(1);
  await page.getByRole("checkbox", { name: /循环/ }).check();
  await expect(page.getByRole("checkbox", { name: /循环/ })).toBeChecked();
  await page.getByRole("button", { name: "原音" }).click();
  await expect.poll(() => page.locator("audio").evaluate((audio) => (audio as HTMLMediaElement).readyState)).toBeGreaterThan(0);
  await page.getByRole("slider", { name: "播放位置", exact: true }).fill(String(start));
  await page.getByRole("button", { name: "播放" }).click();
  await expect(page.getByRole("button", { name: "暂停" })).toBeVisible();
  await page.locator("audio").evaluate((audio, boundary) => {
    (audio as HTMLAudioElement).currentTime = boundary;
  }, end);
  await expect.poll(async () => Number(await page.getByRole("slider", { name: "播放位置", exact: true }).inputValue()))
    .toBeLessThan(end - 0.05);
  expect(Number(await page.getByRole("slider", { name: "播放位置", exact: true }).inputValue()))
    .toBeGreaterThanOrEqual(start);
  await page.getByRole("button", { name: "暂停" }).click();
  await page.getByRole("button", { name: "清除选区" }).click();
  await expect(page.getByText(/谱面选区：/)).toHaveCount(0);
  await expect(page.getByRole("button", { name: "下一小节" })).toBeEnabled();
});
