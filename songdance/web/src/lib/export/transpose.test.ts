import { describe, expect, it } from "vitest";
import type { NoteTimeline } from "@/lib/result/timeline";
import { transposeMusicXml, transposeTimeline } from "./transpose";

const timeline: NoteTimeline = {
  schema_version: 1,
  model_version: "test",
  tempo_bpm: 120,
  time_signature: "4/4",
  quality_flags: [],
  notes: [
    {
      id: "note-1",
      start_sec: 0,
      end_sec: 1,
      pitch: 60,
      velocity: 100,
      confidence: 0.9,
      hand: "right",
    },
  ],
};

const musicXml = `<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0"><part-list/><part id="P1"><measure number="1"><note><pitch><step>B</step><octave>3</octave></pitch><duration>1</duration></note><note><pitch><step>E</step><alter>-1</alter><octave>4</octave></pitch><duration>1</duration><accidental>flat</accidental></note></measure></part></score-partwise>`;

describe("shared transposition", () => {
  it("uses the same semitone offset for the timeline preview", () => {
    expect(transposeTimeline(timeline, 3).notes[0].pitch).toBe(63);
    expect(timeline.notes[0].pitch).toBe(60);
  });

  it("transposes structured MusicXML pitches without string replacement", () => {
    const document = new DOMParser().parseFromString(transposeMusicXml(musicXml, 2), "text/xml");
    const pitches = [...document.querySelectorAll("pitch")].map((pitch) => ({
      step: pitch.querySelector("step")?.textContent,
      alter: pitch.querySelector("alter")?.textContent ?? "0",
      octave: pitch.querySelector("octave")?.textContent,
    }));
    expect(pitches).toEqual([
      { step: "C", alter: "1", octave: "4" },
      { step: "F", alter: "0", octave: "4" },
    ]);
    expect(document.querySelector("accidental")).toBeNull();
  });

  it("rejects offsets and pitches outside the supported MIDI range", () => {
    expect(() => transposeTimeline(timeline, 13)).toThrow("-12 到 +12");
    expect(() =>
      transposeTimeline({ ...timeline, notes: [{ ...timeline.notes[0], pitch: 127 }] }, 1),
    ).toThrow("MIDI 范围");
  });
});
