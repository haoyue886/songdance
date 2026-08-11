import type { Page } from "@playwright/test";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { createWav } from "./audio";

export const timeline = {
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

export const qualitySummary = {
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

type Artifact = {
  type: "raw_midi" | "raw_timeline" | "midi" | "musicxml" | "timeline";
  status: "succeeded" | "failed";
  size_bytes: number;
  mime_type: string;
  error_code: string | null;
};

export function successfulArtifacts(): Artifact[] {
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

export function buildJob(id: string, summary: object, artifacts: Artifact[]) {
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

export async function installJobRoutes(
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
