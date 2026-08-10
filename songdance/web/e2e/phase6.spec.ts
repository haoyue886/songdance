import { expect, test } from "@playwright/test";
import { writeFile } from "node:fs/promises";
import { createWav } from "./support/audio";

const API_URL = "http://127.0.0.1:8002";

test("shows a recoverable 429 while the same IP has an active job", async ({ page }, testInfo) => {
  const wav = createWav(2);
  const first = await page.request.post(`${API_URL}/jobs`, {
    multipart: {
      start_sec: "0",
      end_sec: "1.5",
      rights_confirmed: "true",
      audio_file: { name: "active.wav", mimeType: "audio/wav", buffer: wav },
    },
  });
  expect(first.status()).toBe(201);
  const jobId = ((await first.json()) as { id: string }).id;

  const path = testInfo.outputPath("blocked.wav");
  await writeFile(path, wav);
  await page.goto("/transcribe");
  await page.getByLabel("选择钢琴音频").setInputFiles(path);
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "创建转录任务" }).click();

  try {
    const alert = page.getByText("任务创建失败").locator("..");
    await expect(alert).toContainText("请等待当前任务结束后再提交");
    await expect(alert).toContainText("30 秒后重试");
    expect(page.url()).toContain("/transcribe");
  } finally {
    const deleted = await page.request.delete(`${API_URL}/jobs/${jobId}`);
    expect(deleted.status()).toBe(204);
  }
});

test("publishes privacy and terms pages without mobile overflow", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/privacy");
  await expect(page.getByRole("heading", { name: "你的音频只为这次转录而处理" })).toBeVisible();
  await expect(page.getByText(/24 小时后自动删除/)).toBeVisible();
  await expect(page.getByText(/不用于训练模型/)).toBeVisible();
  await expectNoHorizontalOverflow(page);

  await page.getByRole("link", { name: "使用条款" }).first().click();
  await expect(page).toHaveURL(/\/terms$/);
  await expect(page.getByRole("heading", { name: "只处理你有权处理的内容" })).toBeVisible();
  await expect(page.getByText(/每个 IP 默认每小时最多创建 3 个任务/)).toBeVisible();
  await expectNoHorizontalOverflow(page);
});

async function expectNoHorizontalOverflow(page: import("@playwright/test").Page): Promise<void> {
  const widths = await page.evaluate(() => ({
    client: document.documentElement.clientWidth,
    scroll: document.documentElement.scrollWidth,
  }));
  expect(widths.scroll).toBe(widths.client);
}
