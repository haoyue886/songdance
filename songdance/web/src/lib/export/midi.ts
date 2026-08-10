import { Midi } from "@tonejs/midi";
import { transposePitch } from "./transpose";

export function transposeMidi(source: ArrayBuffer, semitones: number): Uint8Array {
  const midi = new Midi(new Uint8Array(source));
  for (const track of midi.tracks) {
    for (const note of track.notes) note.midi = transposePitch(note.midi, semitones);
  }
  return midi.toArray();
}
