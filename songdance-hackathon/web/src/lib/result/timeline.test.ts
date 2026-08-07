import { describe, expect, it } from "vitest";
import { parseTimeline, timelineDuration } from "./timeline";

const valid = {
  schema_version: 1,
  model_version: "test-model",
  tempo_bpm: 120,
  time_signature: "4/4",
  quality_flags: [],
  notes: [
    {
      id: "note-1",
      start_sec: 0,
      end_sec: 0.5,
      pitch: 60,
      velocity: 96,
      confidence: 0.9,
      hand: "right",
      hand_confidence: 0.82,
    },
    {
      id: "note-2",
      start_sec: 1,
      end_sec: 2.25,
      pitch: 48,
      velocity: 72,
      confidence: 0.75,
      hand: "left",
    },
  ],
};

describe("result timeline", () => {
  it("accepts the shared score and piano-roll contract", () => {
    const timeline = parseTimeline(valid);
    expect(timeline.notes).toHaveLength(2);
    expect(timeline.notes[0].hand_confidence).toBe(0.82);
    expect(timeline.notes[1].hand_confidence).toBeNull();
    expect(timelineDuration(timeline)).toBe(2.25);
  });

  it("normalizes a small leading quantization offset to zero", () => {
    const timeline = parseTimeline({
      ...valid,
      notes: [{ ...valid.notes[0], start_sec: -0.04 }],
    });

    expect(timeline.notes[0].start_sec).toBe(0);
  });

  it.each([
    { ...valid, schema_version: 2 },
    { ...valid, notes: [] },
    { ...valid, notes: [{ ...valid.notes[0], pitch: 128 }] },
    { ...valid, notes: [{ ...valid.notes[0], end_sec: 0 }] },
    { ...valid, notes: [{ ...valid.notes[0], start_sec: -0.251 }] },
    { ...valid, notes: [{ ...valid.notes[0], hand_confidence: 1.1 }] },
  ])("rejects malformed or empty artifact data", (input) => {
    expect(() => parseTimeline(input)).toThrow();
  });
});
