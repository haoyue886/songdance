import { expect, test, type Page } from "@playwright/test";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { createWav } from "./support/audio";

const timeline = {
  schema_version: 1,
  model_version: "basic-pitch-test",
  tempo_bpm: 118,
  beat_grid_seconds: [0, 0.508475, 1.016949, 1.525424],
  downbeat_grid_seconds: [0, 2.033898],
  time_signature: "4/4",
  quality_flags: [],
  notes: [
    { id: "note-1", start_sec: 0, end_sec: 1, pitch: 60, velocity: 90, confidence: 0.9, hand: "right" },
    { id: "note-2", start_sec: 1, end_sec: 4, pitch: 55, velocity: 82, confidence: 0.8, hand: "left" },
  ],
};

const qualitySummary = {
  schema_version: 4,
  quality_report_version: "quality-report-v6",
  postprocess_version: "cleanup-v3/analysis-v2/score-v4",
  raw_note_count: 3,
  cleaned_note_count: 2,
  cleanup: {
    status: "applied",
    version: "cleanup-v3",
    removed_note_count: 1,
    clipped_note_count: 0,
    merged_note_count: 0,
    fallback_used: false,
    error_code: null,
  },
  analysis: {
    status: "analyzed",
    version: "analysis-v2",
    bpm: 118,
    bpm_confidence: 0.82,
    time_signature: "4/4",
    time_signature_confidence: 0.74,
    time_signature_source: "detected",
    key_signature: "G major",
    key_confidence: 0.64,
    key_signature_source: "detected",
    reason_codes: [],
  },
  confidence: { min: 0.5, max: 0.95, mean: 0.84 },
  model: { version: "basic-pitch-test", thresholds: {} },
  reconstruction: { status: "reconstructed", fallback_used: false, error_code: null },
  musicxml_parse: { status: "passed" },
  structure_errors: [],
};

test("shows a high-quality report and remains usable at 375px", async ({ page }) => {
  const job = buildJob("quality-high", qualitySummary, successfulArtifacts());
  const mappedTimeline = JSON.parse(await readFile(
    path.resolve(process.cwd(), "public/examples/mozart-sonata/timeline.json"),
    "utf8",
  ));
  await installJobRoutes(page, job, mappedTimeline);
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto(`/jobs/${job.id}`);

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
  await page.goto(`/jobs/${job.id}`);

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
  await page.goto(`/jobs/${job.id}`);

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
  await page.goto(`/jobs/${job.id}`);

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
  await page.goto(`/jobs/${job.id}`);

  await expect(page.getByText("当前预览：原始模型音符（清洗结果不可用）")).toBeVisible();
  await expect(page.getByText("音符清洗失败，预览已回退到原始模型音符。")).toBeVisible();
  await expect(page.getByRole("img", { name: /钢琴卷帘/ })).toBeVisible();
  await expect(page.getByRole("tab", { name: "五线谱" })).toBeDisabled();
  await expect(page.getByRole("button", { name: /^MusicXML/ })).toBeDisabled();
  await expect(page.getByRole("button", { name: /^PDF/ })).toBeDisabled();
  await expect(page.getByRole("button", { name: /^原始 MIDI/ })).toBeEnabled();
});

type Artifact = {
  type: "raw_midi" | "raw_timeline" | "midi" | "musicxml" | "timeline";
  status: "succeeded" | "failed";
  size_bytes: number;
  mime_type: string;
  error_code: string | null;
};

function successfulArtifacts(): Artifact[] {
  return [
    artifact("raw_midi", "audio/midi"),
    artifact("raw_timeline", "application/json"),
    artifact("midi", "audio/midi"),
    artifact("musicxml", "application/vnd.recordare.musicxml+xml"),
    artifact("timeline", "application/json"),
  ];
}

function artifact(type: Artifact["type"], mimeType: string): Artifact {
  return { type, status: "succeeded", size_bytes: 256, mime_type: mimeType, error_code: null };
}

function buildJob(id: string, summary: object, artifacts: Artifact[]) {
  return {
    id,
    status: "succeeded",
    stage: "completed",
    source_type: "upload",
    start_sec: 0,
    end_sec: 4,
    attempt_count: 1,
    error_code: null,
    error_message: null,
    created_at: "2026-08-07T00:00:00Z",
    updated_at: "2026-08-07T00:00:10Z",
    expires_at: "2026-08-08T00:00:00Z",
    result: {
      tempo: 118,
      time_signature: "4/4",
      note_count: 2,
      quality_flags: "[]",
      model_version: "basic-pitch-test",
    },
    quality_report: {
      report_version: "quality-report-v6",
      summary: JSON.stringify(summary),
    },
    artifacts,
  };
}

async function installJobRoutes(
  page: Page,
  job: ReturnType<typeof buildJob>,
  timelineFixture = timeline,
): Promise<void> {
  const musicXmlPath = path.resolve(process.cwd(), "public/examples/mozart-sonata/score.musicxml");
  const musicXml = await readFile(musicXmlPath, "utf8");
  const wav = createWav(4);
  const handler: Parameters<Page["route"]>[1] = async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === `/jobs/${job.id}`) {
      await route.fulfill({ json: job });
      return;
    }
    const downloadType = url.pathname.match(/\/download-url\/([^/]+)$/)?.[1];
    if (downloadType) {
      await route.fulfill({
        json: { path: `/jobs/${job.id}/files/${downloadType}?ticket=e2e`, expires_at: 4_102_444_800 },
      });
      return;
    }
    const fileType = url.pathname.match(/\/files\/([^/]+)$/)?.[1];
    if (fileType === "timeline" || fileType === "raw_timeline") {
      await route.fulfill({ json: timelineFixture });
      return;
    }
    if (fileType === "musicxml") {
      await route.fulfill({ body: musicXml, contentType: "application/xml" });
      return;
    }
    if (fileType === "source") {
      await route.fulfill({ body: wav, contentType: "audio/wav" });
      return;
    }
    await route.fulfill({ status: 404, json: { detail: "fixture not found" } });
  };
  await page.route(`http://localhost:8000/jobs/${job.id}**`, handler);
  await page.route(`http://127.0.0.1:8002/jobs/${job.id}**`, handler);
}
