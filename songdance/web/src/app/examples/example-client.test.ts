import { describe, expect, it } from "vitest";
import {
  buildExampleJob,
  hasFailedExampleReview,
  type ExampleProvenance,
} from "./example-job";

const timeline = {
  schema_version: 1 as const,
  model_version: "model/current",
  tempo_bpm: 96,
  time_signature: "3/4",
  quality_flags: ["UNKNOWN_HAND_NOTATION_FALLBACK"],
  notes: [
    {
      id: "note-1",
      start_sec: 0,
      end_sec: 2,
      pitch: 60,
      velocity: 90,
      confidence: 0.8,
      hand: null,
    },
  ],
};

const provenance: ExampleProvenance = {
  clip_duration_sec: 30,
  generated_at: "2026-08-07T00:00:00Z",
  source_page: "https://commons.wikimedia.org/wiki/File:example",
  license: "Public domain",
  license_url: "https://commons.wikimedia.org/wiki/File:example",
  review_status: "pending",
  review_state: "review_paused",
  review_resume_condition: "reference_aligned_transcription_ready",
  latest_completed_review: {
    rating: "minor_edits",
    reviewed_at: "2026-08-06T00:00:00Z",
    model_version: "model/baseline",
  },
  artifacts: {
    midi: { size_bytes: 10 },
    musicxml: { size_bytes: 20 },
    timeline: { size_bytes: 30 },
  },
};

describe("buildExampleJob", () => {
  it("uses published artifact metadata instead of stale hard-coded values", () => {
    const job = buildExampleJob(timeline, provenance);

    expect(job.result).toMatchObject({
      tempo: 96,
      time_signature: "3/4",
      note_count: 1,
      model_version: "model/current",
    });
    expect(job.result?.quality_flags).toBe('["UNKNOWN_HAND_NOTATION_FALLBACK"]');
    expect(job.artifacts.map((item) => item.size_bytes)).toEqual([10, 20, 30]);
  });
});

describe("hasFailedExampleReview", () => {
  it("keeps the warning visible while a replacement artifact is pending review", () => {
    expect(
      hasFailedExampleReview({
        ...provenance,
        review_status: "pending",
        latest_completed_review: {
          ...provenance.latest_completed_review,
          rating: "needs_redo",
        },
      }),
    ).toBe(true);
  });
});
