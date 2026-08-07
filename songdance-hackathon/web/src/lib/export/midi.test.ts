import { Midi } from "@tonejs/midi";
import { describe, expect, it } from "vitest";
import { transposeMidi } from "./midi";

describe("MIDI export transposition", () => {
  it("moves every note by the same preview offset and remains parseable", () => {
    const source = new Midi();
    source.addTrack().addNote({ midi: 48, time: 0, duration: 0.5, velocity: 0.7 });
    source.addTrack().addNote({ midi: 72, time: 1, duration: 1, velocity: 0.9 });
    const input = source.toArray();
    const transposed = new Midi(transposeMidi(new Uint8Array(input).buffer, -3));

    expect(transposed.tracks.flatMap((track) => track.notes.map((note) => note.midi))).toEqual([
      45, 69,
    ]);
    expect(new Midi(input).tracks.flatMap((track) => track.notes.map((note) => note.midi))).toEqual([
      48, 72,
    ]);
  });
});
