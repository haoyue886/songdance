import { Midi } from "@tonejs/midi";
import { expect, test } from "@playwright/test";
import { execFile } from "node:child_process";
import { readFile } from "node:fs/promises";
import { promisify } from "node:util";
import {
  verifyCommittedSelectionResize,
  verifyCrossPageSelectionResize,
  verifyDoubleClickClearsSelection,
} from "./score-selection-helpers";

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

test("plays, switches views and exports the public-domain example", async ({ page }, testInfo) => {
  test.setTimeout(infrastructureTimeout * 2);
  await page.goto("/zh/examples");
  await expect(page.getByRole("heading", { name: "先听原音，再检查转录结果" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Musopen 录音与乐谱" }))
    .toHaveAttribute("href", /commons\.wikimedia\.org/);
  const scorePages = page.locator('[aria-label="MusicXML 五线谱"] svg');
  await infrastructureExpect.poll(() => scorePages.count()).toBeGreaterThan(0);
  await infrastructureExpect
    .poll(async () => Number(await scorePages.first().getAttribute("width")))
    .toBeGreaterThan(0);

  const position = page.getByRole("slider", { name: "播放位置", exact: true });
  const score = page.getByLabel("MusicXML 五线谱");
  await expect(page.getByText(/第 1 \/ \d+ 小节/)).toBeVisible();
  await expect(page.getByText("小节定位不可用")).toHaveCount(0);
  const activeMeasureHighlight = page.getByTestId("active-measure-highlight");
  await expect(activeMeasureHighlight).toBeVisible();
  const activeHighlightBox = await activeMeasureHighlight.boundingBox();
  expect(activeHighlightBox?.width).toBeGreaterThan(0);
  expect(activeHighlightBox?.height).toBeGreaterThan(0);
  await score.locator("text").filter({ hasText: /^2$/ }).first().click();
  await expect.poll(async () => Number(await position.inputValue())).toBeGreaterThan(0);
  const scoreViewport = page.getByTestId("score-viewport");
  const scrollBeforePlaybackMoves = await page.evaluate(() => ({
    page: window.scrollY,
    score: document.querySelector<HTMLElement>('[data-testid="score-viewport"]')?.scrollTop ?? -1,
  }));
  const laterDownbeats = [
    2.321995, 4.017052, 5.828209, 7.639365, 9.427302, 11.331338,
    13.165714, 14.976871, 16.764807, 18.599184, 20.3639, 22.105397,
    23.893333, 25.72771, 27.538866,
  ];
  for (let measure = 3; measure <= 17; measure += 1) {
    await setRangeValue(position, laterDownbeats[measure - 3] + 0.01);
    await expect(page.getByText(`第 ${measure} / 18 小节`)).toBeVisible();
  }
  await setRangeValue(position, 29.360023);
  await expect(page.getByText("第 18 / 18 小节")).toBeVisible();
  const lastHighlightBox = await activeMeasureHighlight.boundingBox();
  const lastCursorBox = await score.locator('img[id^="cursorImg"]').boundingBox();
  expect(lastHighlightBox).not.toBeNull();
  expect(lastCursorBox).not.toBeNull();
  expect(Math.abs((lastHighlightBox?.x ?? 0) - (lastCursorBox?.x ?? 0))).toBeLessThan(2);
  expect(Math.abs((lastHighlightBox?.y ?? 0) - (lastCursorBox?.y ?? 0))).toBeLessThan(2);
  expect(Number(await position.inputValue())).toBeCloseTo(29.360023, 1);
  expect(await page.evaluate(() => ({
    page: window.scrollY,
    score: document.querySelector<HTMLElement>('[data-testid="score-viewport"]')?.scrollTop ?? -1,
  }))).toEqual(scrollBeforePlaybackMoves);
  await expect(scoreViewport).toBeVisible();
  await position.press("Home");
  await expect(page.getByText("第 1 / 18 小节")).toBeVisible();
  const selectionBorders = page.locator('svg.pointer-events-none rect[data-score-selection-border="true"]');
  const selectionOverlay = page.getByTestId("score-selection-overlay");
  const loopStartInput = page.getByRole("spinbutton", { name: "起点", exact: true });
  const loopEndInput = page.getByRole("spinbutton", { name: "终点", exact: true });
  const openingHighlightBox = await activeMeasureHighlight.boundingBox();
  expect(openingHighlightBox).not.toBeNull();
  if (!openingHighlightBox) throw new Error("弱起小节高亮不可见");
  const dragStartX = openingHighlightBox.x + openingHighlightBox.width * 0.7;
  const dragEndX = openingHighlightBox.x + openingHighlightBox.width * 0.9;
  const dragY = openingHighlightBox.y + openingHighlightBox.height * 0.35;
  await page.mouse.move(dragStartX, dragY);
  await expect(score).toHaveCSS("cursor", "crosshair");
  const loopBoundsBeforeDraft = {
    start: await loopStartInput.inputValue(),
    end: await loopEndInput.inputValue(),
  };
  await page.mouse.down();
  await page.mouse.move(
    dragStartX + 3,
    dragY,
  );
  await expect(score).toHaveCSS("cursor", "crosshair");
  await page.mouse.move(
    dragEndX,
    dragY,
    { steps: 8 },
  );
  await expect(score).toHaveCSS("cursor", "grabbing");
  await expect(selectionBorders).not.toHaveCount(0);
  await expect(selectionOverlay).toHaveAttribute("fill", "rgba(255,255,255,.74)");
  expect(await loopStartInput.inputValue()).toBe(loopBoundsBeforeDraft.start);
  expect(await loopEndInput.inputValue()).toBe(loopBoundsBeforeDraft.end);
  const rapidUntil = Date.now() + 2_000;
  while (Date.now() < rapidUntil) {
    await page.mouse.move(Date.now() % 2 ? dragEndX : dragStartX + 10, dragY);
    await page.waitForTimeout(16);
  }
  await page.mouse.move(dragEndX, dragY);
  const draftBorderBox = await selectionBorders.first().boundingBox();
  expect(draftBorderBox).not.toBeNull();
  expect(Math.abs((draftBorderBox?.x ?? 0) - dragStartX)).toBeLessThanOrEqual(10);
  expect(Math.abs((draftBorderBox?.x ?? 0) + (draftBorderBox?.width ?? 0) - dragEndX)).toBeLessThanOrEqual(10);
  await expect(selectionBorders.first()).toHaveCSS("stroke", "rgb(21, 128, 61)");
  await page.screenshot({ path: testInfo.outputPath("score-selection-draft.png"), fullPage: false });
  await page.mouse.up();
  await expect(score).toHaveCSS("cursor", "crosshair");
  await expect(selectionBorders).not.toHaveCount(0);
  const openingBorderBox = await selectionBorders.first().boundingBox();
  expect(openingBorderBox).not.toBeNull();
  expect(((openingBorderBox?.x ?? 0) - openingHighlightBox.x) / openingHighlightBox.width)
    .toBeGreaterThan(0.5);
  expect(await loopStartInput.inputValue()).not.toBe(loopBoundsBeforeDraft.start);
  await verifyCommittedSelectionResize(page);
  await page.screenshot({ path: testInfo.outputPath("score-selection-resized.png"), fullPage: false });
  await verifyDoubleClickClearsSelection(page);

  await scoreViewport.evaluate((element) => { element.scrollTop = 0; });
  const viewportBox = await scoreViewport.boundingBox();
  expect(viewportBox).not.toBeNull();
  if (!viewportBox) throw new Error("谱面滚动视口不可见");
  const pageScrollBeforeEdgeDrag = await page.evaluate(() => window.scrollY);
  await page.mouse.move(
    openingHighlightBox.x + openingHighlightBox.width * 0.5,
    openingHighlightBox.y + openingHighlightBox.height * 0.5,
  );
  await page.mouse.down();
  await page.mouse.move(
    openingHighlightBox.x + openingHighlightBox.width * 0.7,
    viewportBox.y + viewportBox.height - 2,
  );
  await expect.poll(() => scoreViewport.evaluate((element) => element.scrollTop)).toBeGreaterThan(0);
  expect(await page.evaluate(() => window.scrollY)).toBe(pageScrollBeforeEdgeDrag);
  await page.mouse.up();
  await page.getByRole("button", { name: "清除选区" }).click();
  await scoreViewport.evaluate((element) => { element.scrollTop = 0; });

  const crossPageStart = await score.locator("#osmdSvgPage1 text").filter({ hasText: /^2$/ }).first().boundingBox();
  expect(crossPageStart).not.toBeNull();
  if (!crossPageStart) throw new Error("跨页选区起点不可见");
  await page.mouse.move(crossPageStart.x + crossPageStart.width / 2, crossPageStart.y + crossPageStart.height / 2);
  await page.mouse.down();
  await scoreViewport.evaluate((element) => { element.scrollTop = 950; });
  const crossPageEnd = await score.locator("#osmdSvgPage2 text").filter({ hasText: /^4$/ }).first().boundingBox();
  expect(crossPageEnd).not.toBeNull();
  if (!crossPageEnd) throw new Error("跨页选区终点不可见");
  await page.mouse.move(crossPageEnd.x + 250, crossPageEnd.y + 40, { steps: 8 });
  await expect(selectionBorders).not.toHaveCount(0);
  await expect(selectionOverlay).toBeVisible();
  await page.mouse.up();
  await expect(selectionBorders).not.toHaveCount(0);
  const firstPageHeight = Number(await scorePages.first().getAttribute("height"));
  const crossPageBorderYs = await selectionBorders.evaluateAll((elements) =>
    elements.map((element) => Number(element.getAttribute("y"))));
  const crossPageSegmentKeys = await selectionBorders.evaluateAll((elements) =>
    elements.map((element) => element.getAttribute("data-score-selection-segment")));
  const crossPageStartSeconds = Number(await page.getByRole("spinbutton", { name: "起点", exact: true }).inputValue());
  const crossPageEndSeconds = Number(await page.getByRole("spinbutton", { name: "终点", exact: true }).inputValue());
  expect(Math.max(...crossPageBorderYs)).toBeGreaterThan(firstPageHeight);
  expect(new Set(crossPageSegmentKeys).size).toBe(crossPageSegmentKeys.length);
  expect(crossPageEndSeconds - crossPageStartSeconds).toBeGreaterThan(3);
  await verifyCrossPageSelectionResize(page);
  await page.getByRole("button", { name: "清除选区" }).click();
  await scoreViewport.evaluate((element) => { element.scrollTop = 0; });

  const selectionStart = await score.locator("text").filter({ hasText: /^2$/ }).first().boundingBox();
  expect(selectionStart).not.toBeNull();
  if (!selectionStart) throw new Error("谱面选区起点不可见");
  await page.mouse.move(selectionStart.x + selectionStart.width / 2, selectionStart.y + selectionStart.height / 2);
  await page.mouse.down();
  await page.mouse.move(selectionStart.x + 120, selectionStart.y + selectionStart.height / 2, { steps: 8 });
  await page.mouse.up();
  await expect(page.getByText(/谱面选区：/)).toBeVisible();
  await expect(selectionBorders).not.toHaveCount(0);
  await expect(selectionOverlay)
    .toHaveAttribute("fill", "rgba(255,255,255,.74)");
  const selectionLayerHeight = Number(await selectionBorders.first().locator("xpath=..").getAttribute("height"));
  const scoreContentHeight = await score.evaluate((element) => element.scrollHeight);
  expect(selectionLayerHeight).toBeGreaterThanOrEqual(scoreContentHeight - 1);
  const shortSelectionBorderBox = await selectionBorders.first().boundingBox();
  expect(shortSelectionBorderBox?.width).toBeLessThan(200);
  await page.screenshot({ path: testInfo.outputPath("score-selection.png"), fullPage: false });
  const selectedStartSeconds = Number(await page.getByRole("spinbutton", { name: "起点", exact: true }).inputValue());
  const selectedEndSeconds = Number(await page.getByRole("spinbutton", { name: "终点", exact: true }).inputValue());
  const selectedDuration = selectedEndSeconds - selectedStartSeconds;
  expect(selectedDuration).toBeGreaterThan(0);
  expect(selectedDuration).toBeLessThan(2);

  await page.getByRole("button", { name: "原音" }).click();
  await position.press("Home");
  await page.getByRole("button", { name: "播放" }).click();
  await expect.poll(async () => Number(await position.inputValue())).toBeGreaterThan(0);
  await page.locator("audio").evaluate((audio, boundary) => {
    (audio as HTMLAudioElement).currentTime = boundary;
  }, selectedEndSeconds);
  await expect(page.getByRole("button", { name: "播放" })).toBeVisible();

  await page.getByRole("checkbox", { name: /循环/ }).check();
  await position.press("Home");
  await page.getByRole("button", { name: "播放" }).click();
  await page.locator("audio").evaluate((audio, boundary) => {
    (audio as HTMLAudioElement).currentTime = boundary;
  }, selectedEndSeconds);
  await expect(page.getByRole("button", { name: "暂停" })).toBeVisible();
  await expect.poll(async () => Number(await position.inputValue())).toBeLessThan(selectedStartSeconds + 1);
  await page.getByRole("button", { name: "暂停" }).click();
  await page.getByRole("checkbox", { name: /循环/ }).uncheck();
  await page.getByRole("button", { name: "转录演奏", exact: true }).click();

  await page.getByRole("button", { name: "清除选区" }).click();
  await expect(page.getByText(/谱面选区：/)).toHaveCount(0);

  await position.press("Home");
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

async function setRangeValue(input: import("@playwright/test").Locator, value: number): Promise<void> {
  await input.evaluate((element: HTMLInputElement, nextValue) => {
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
    setter?.call(element, String(nextValue));
    element.dispatchEvent(new Event("input", { bubbles: true }));
    element.dispatchEvent(new Event("change", { bubbles: true }));
  }, value);
}
