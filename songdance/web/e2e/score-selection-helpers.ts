import { expect, type Page } from "@playwright/test";

export async function verifyCommittedSelectionResize(page: Page): Promise<void> {
  const startInput = page.getByLabel("循环起点");
  const endInput = page.getByLabel("循环终点");
  const position = page.getByRole("slider", { name: "播放位置", exact: true });
  const endHandle = page.locator('[data-score-selection-handle="end"]');
  const border = page.locator('[data-score-selection-border="true"]').last();
  await expect(endHandle).toHaveCount(1);
  const handleBox = await endHandle.boundingBox();
  const borderBox = await border.boundingBox();
  if (!handleBox || !borderBox) throw new Error("选区终点边界不可见");
  const point = {
    x: handleBox.x + handleBox.width / 2,
    y: handleBox.y + handleBox.height / 2,
  };
  await page.mouse.move(point.x, point.y);
  expect(await page.evaluate(({ x, y }) => {
    const target = document.elementFromPoint(x, y);
    return {
      handle: target?.getAttribute("data-score-selection-handle"),
      cursor: target ? getComputedStyle(target).cursor : null,
    };
  }, point)).toEqual({ handle: "end", cursor: "ew-resize" });
  const before = {
    start: await startInput.inputValue(),
    end: await endInput.inputValue(),
    position: await position.inputValue(),
    pageScroll: await page.evaluate(() => window.scrollY),
  };

  await page.mouse.down();
  await page.mouse.up();
  expect(await startInput.inputValue()).toBe(before.start);
  expect(await endInput.inputValue()).toBe(before.end);
  expect(await position.inputValue()).toBe(before.position);

  await page.mouse.move(point.x, point.y);
  await page.mouse.down();
  await page.mouse.move(point.x + 32, point.y, { steps: 8 });
  await expect.poll(async () => {
    const draftBox = await border.boundingBox();
    return draftBox ? draftBox.x + draftBox.width : 0;
  }).toBeGreaterThan(borderBox.x + borderBox.width + 10);
  expect(await startInput.inputValue()).toBe(before.start);
  expect(await endInput.inputValue()).toBe(before.end);
  await page.mouse.up();
  await expect.poll(async () => Number(await endInput.inputValue()))
    .toBeGreaterThan(Number(before.end));
  expect(await startInput.inputValue()).toBe(before.start);
  expect(await position.inputValue()).toBe(before.position);
  expect(await page.evaluate(() => window.scrollY)).toBe(before.pageScroll);

  const committedEnd = await endInput.inputValue();
  const resizedHandleBox = await endHandle.boundingBox();
  if (!resizedHandleBox) throw new Error("调整后的选区终点边界不可见");
  await page.mouse.move(
    resizedHandleBox.x + resizedHandleBox.width / 2,
    resizedHandleBox.y + resizedHandleBox.height / 2,
  );
  await page.mouse.down();
  await page.mouse.move(resizedHandleBox.x - 32, point.y, { steps: 6 });
  await page.keyboard.press("Escape");
  await page.mouse.up();
  expect(await startInput.inputValue()).toBe(before.start);
  expect(await endInput.inputValue()).toBe(committedEnd);

  const startHandle = page.locator('[data-score-selection-handle="start"]');
  const fixedStartBox = await startHandle.boundingBox();
  const currentEndBox = await endHandle.boundingBox();
  const firstPageBox = await page.locator("#osmdSvgPage1").boundingBox();
  if (!fixedStartBox || !currentEndBox || !firstPageBox) {
    throw new Error("同系统选区边界不可见");
  }
  const earlierX = Math.max(firstPageBox.x + 20, fixedStartBox.x - 120);
  await page.mouse.move(
    currentEndBox.x + currentEndBox.width / 2,
    currentEndBox.y + currentEndBox.height / 2,
  );
  await page.mouse.down();
  await page.mouse.move(earlierX, fixedStartBox.y + fixedStartBox.height / 2, { steps: 8 });
  await expect.poll(async () => (await startHandle.boundingBox())?.x ?? fixedStartBox.x)
    .toBeLessThan(fixedStartBox.x - 5);
  await expect.poll(async () => {
    const fixedBox = await endHandle.boundingBox();
    return Math.abs((fixedBox?.x ?? 0) - fixedStartBox.x);
  }).toBeLessThanOrEqual(10);
  expect(await startInput.inputValue()).toBe(before.start);
  expect(await endInput.inputValue()).toBe(committedEnd);
  await page.mouse.up();
  await expect.poll(async () => Number(await startInput.inputValue()))
    .toBeLessThan(Number(before.start));
  expect(Number(await endInput.inputValue())).toBeCloseTo(Number(before.start), 1);
}

export async function verifyDoubleClickClearsSelection(page: Page): Promise<void> {
  const viewport = page.getByTestId("score-viewport");
  const position = page.getByRole("slider", { name: "播放位置", exact: true });
  const startInput = page.getByLabel("循环起点");
  const endInput = page.getByLabel("循环终点");
  const border = page.locator('[data-score-selection-border="true"]').first();
  const borderBox = await border.boundingBox();
  if (!borderBox) throw new Error("双击清除前的谱面选区不可见");
  const before = {
    position: await position.inputValue(),
    start: Number(await startInput.inputValue()),
    end: Number(await endInput.inputValue()),
    pageScroll: await page.evaluate(() => window.scrollY),
    scoreScroll: await viewport.evaluate((element) => element.scrollTop),
  };

  const point = { x: borderBox.x + borderBox.width / 2, y: borderBox.y + borderBox.height / 2 };
  await page.mouse.dblclick(point.x, point.y);
  await expect(page.locator('[data-score-selection-border="true"]')).toHaveCount(0);
  await expect(page.getByText(/谱面选区：/)).toHaveCount(0);
  expect(await position.inputValue()).toBe(before.position);
  expect(Number(await startInput.inputValue())).toBe(0);
  expect(Number(await endInput.inputValue())).toBeGreaterThan(before.end);
  expect(await page.evaluate(() => window.scrollY)).toBe(before.pageScroll);
  expect(await viewport.evaluate((element) => element.scrollTop)).toBe(before.scoreScroll);
}

export async function verifyCrossPageSelectionResize(page: Page): Promise<void> {
  const viewport = page.getByTestId("score-viewport");
  const startInput = page.getByLabel("循环起点");
  const endInput = page.getByLabel("循环终点");
  const endHandle = page.locator('[data-score-selection-handle="end"]');
  const before = {
    start: Number(await startInput.inputValue()),
    end: Number(await endInput.inputValue()),
    scrollTop: await viewport.evaluate((element) => element.scrollTop),
    pageScroll: await page.evaluate(() => window.scrollY),
  };
  const viewportBox = await viewport.boundingBox();
  let handleBox = await endHandle.boundingBox();
  if (!viewportBox || !handleBox) throw new Error("跨页选区终点不可见");

  await page.mouse.move(
    handleBox.x + handleBox.width / 2,
    handleBox.y + handleBox.height / 2,
  );
  await page.mouse.down();
  await page.mouse.move(handleBox.x + handleBox.width / 2, viewportBox.y + 2, { steps: 6 });
  await expect.poll(() => viewport.evaluate((element) => element.scrollTop))
    .toBeLessThan(before.scrollTop);
  expect(Number(await startInput.inputValue())).toBe(before.start);
  expect(Number(await endInput.inputValue())).toBe(before.end);
  expect(await page.evaluate(() => window.scrollY)).toBe(before.pageScroll);
  await page.keyboard.press("Escape");
  await page.mouse.up();
  expect(Number(await startInput.inputValue())).toBe(before.start);
  expect(Number(await endInput.inputValue())).toBe(before.end);

  await viewport.evaluate((element, scrollTop) => { element.scrollTop = scrollTop; }, before.scrollTop);
  handleBox = await endHandle.boundingBox();
  if (!handleBox) throw new Error("恢复后的跨页终点不可见");
  await page.mouse.move(
    handleBox.x + handleBox.width / 2,
    handleBox.y + handleBox.height / 2,
  );
  expect(await page.evaluate(({ x, y }) => document.elementFromPoint(x, y)
    ?.getAttribute("data-score-selection-handle"), {
    x: handleBox.x + handleBox.width / 2,
    y: handleBox.y + handleBox.height / 2,
  })).toBe("end");
  await viewport.evaluate((element) => {
    element.addEventListener("gotpointercapture", (event) => {
      element.dataset.capturedPointer = String((event as PointerEvent).pointerId);
    }, { once: true });
  });
  await page.mouse.down();
  await page.mouse.move(
    handleBox.x + handleBox.width / 2 + 1,
    handleBox.y + handleBox.height / 2,
  );
  await expect.poll(() => viewport.getAttribute("data-captured-pointer")).not.toBeNull();
  await viewport.evaluate((element) => { element.scrollTop = 0; });
  expect(await viewport.evaluate((element) => element.hasPointerCapture(
    Number(element.dataset.capturedPointer),
  ))).toBe(true);
  const fixedStart = await page.locator('[data-score-selection-handle="start"]')
    .boundingBox();
  const firstPage = await page.locator("#osmdSvgPage1").boundingBox();
  if (!fixedStart || !firstPage) throw new Error("跨页端点调整目标不可见");
  const targetX = Math.min(firstPage.x + firstPage.width - 20, fixedStart.x + 120);
  await page.mouse.move(
    targetX,
    fixedStart.y + fixedStart.height / 2,
    { steps: 8 },
  );
  await expect.poll(async () => {
    const draftEnd = await endHandle.boundingBox();
    return draftEnd?.x ?? fixedStart.x;
  }).toBeGreaterThan(fixedStart.x + 5);
  expect(Number(await startInput.inputValue())).toBe(before.start);
  expect(Number(await endInput.inputValue())).toBe(before.end);
  await page.mouse.up();
  expect(Number(await startInput.inputValue())).toBe(before.start);
  const committedEnd = Number(await endInput.inputValue());
  expect(committedEnd).toBeGreaterThan(before.start);
  expect(committedEnd).toBeLessThan(before.end);
  expect(await page.evaluate(() => window.scrollY)).toBe(before.pageScroll);
}
