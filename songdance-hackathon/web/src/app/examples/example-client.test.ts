import { describe, expect, it } from "vitest";
import { buildExampleJob } from "./example-job";

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

describe("buildExampleJob", () => {
  it("uses published artifact metadata instead of stale hard-coded values", () => {
    const job = buildExampleJob(timeline, {
      clip_duration_sec: 30,
      generated_at: "2026-08-07T00:00:00Z",
      artifacts: {
        midi: { size_bytes: 10 },
        musicxml: { size_bytes: 20 },
        timeline: { size_bytes: 30 },
      },
    });

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
