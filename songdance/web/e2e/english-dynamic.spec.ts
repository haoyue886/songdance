import { expect, test } from "@playwright/test";
import { writeFile } from "node:fs/promises";
import { buildJob, installJobRoutes, qualitySummary, successfulArtifacts } from "./support/quality-job";

test("shows English validation for an unsupported upload", async ({ page }, testInfo) => {
  const invalidPath = testInfo.outputPath("not-audio.txt");
  await writeFile(invalidPath, "not audio");
  await page.goto("/transcribe");

  await page.getByLabel("Choose piano audio").setInputFiles(invalidPath);

  await expect(page.getByText("This file cannot be used")).toBeVisible();
  await expect(page.getByText("The request could not be accepted. Check the input and try again.")).toBeVisible();
  await expect(page.getByText("无法使用这个文件")).toHaveCount(0);
});

test("localizes a failed English job without exposing the backend message", async ({ page }) => {
  const jobId = "english-no-notes";
  await page.route(`http://127.0.0.1:8002/jobs/${jobId}`, async (route) => {
    await route.fulfill({
      json: {
        id: jobId,
        status: "failed",
        stage: "transcribing",
        source_type: "upload",
        start_sec: 0,
        end_sec: 4,
        attempt_count: 1,
        error_code: "NO_NOTES_DETECTED",
        error_message: "internal technical message",
        created_at: "2026-08-07T00:00:00Z",
        updated_at: "2026-08-07T00:00:10Z",
        expires_at: "2026-08-08T00:00:00Z",
        result: null,
        quality_report: null,
        artifacts: [],
      },
    });
  });

  await page.goto(`/jobs/${jobId}`);

  await expect(page.getByRole("heading", { name: "No piano notes detected" })).toBeVisible();
  await expect(page.getByText("No usable piano notes were detected in this excerpt.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Retry task" })).toBeVisible();
  await expect(page.getByText("NO_NOTES_DETECTED")).toHaveCount(0);
  await expect(page.getByText("internal technical message")).toHaveCount(0);
});

test("renders an English result and hides artifact error codes", async ({ page }) => {
  const artifacts = successfulArtifacts().map((artifact) =>
    artifact.type === "musicxml"
      ? { ...artifact, status: "failed" as const, size_bytes: 0, error_code: "MUSICXML_PARSE_FAILED" }
      : artifact,
  );
  const summary = {
    ...qualitySummary,
    musicxml_parse: { status: "failed", error_code: "MUSICXML_PARSE_FAILED" },
    structure_errors: ["MUSICXML_PARSE_FAILED"],
  };
  const job = buildJob("english-artifact-failed", summary, artifacts);
  await installJobRoutes(page, job);

  await page.goto(`/jobs/${job.id}`);

  await expect(page.getByRole("heading", { name: "Piano transcription result" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Quality summary" })).toBeVisible();
  await expect(page.getByRole("button", { name: /^Cleaned MIDI/ })).toBeEnabled();
  await expect(page.getByRole("button", { name: "MusicXML Generation failed" })).toBeDisabled();
  await expect(page.getByText("MUSICXML_PARSE_FAILED")).toHaveCount(0);
});
