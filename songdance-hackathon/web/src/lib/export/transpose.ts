import type { NoteTimeline } from "@/lib/result/timeline";

const NOTE_NAMES = [
  { step: "C", alter: 0 },
  { step: "C", alter: 1 },
  { step: "D", alter: 0 },
  { step: "D", alter: 1 },
  { step: "E", alter: 0 },
  { step: "F", alter: 0 },
  { step: "F", alter: 1 },
  { step: "G", alter: 0 },
  { step: "G", alter: 1 },
  { step: "A", alter: 0 },
  { step: "A", alter: 1 },
  { step: "B", alter: 0 },
] as const;

const STEP_SEMITONES: Record<string, number> = {
  C: 0,
  D: 2,
  E: 4,
  F: 5,
  G: 7,
  A: 9,
  B: 11,
};

export function transposeTimeline(timeline: NoteTimeline, semitones: number): NoteTimeline {
  validateOffset(semitones);
  return {
    ...timeline,
    notes: timeline.notes.map((note) => ({
      ...note,
      pitch: transposePitch(note.pitch, semitones),
    })),
  };
}

export function transposeMusicXml(source: string, semitones: number): string {
  validateOffset(semitones);
  if (semitones === 0) return source;
  const parser = new DOMParser();
  const document = parser.parseFromString(source, "application/xml");
  if (document.querySelector("parsererror")) throw new Error("MusicXML 文件无法解析。");

  for (const pitch of document.querySelectorAll("note > pitch")) {
    const stepNode = pitch.querySelector(":scope > step");
    const octaveNode = pitch.querySelector(":scope > octave");
    if (!stepNode || !octaveNode) throw new Error("MusicXML 音高数据不完整。");
    const base = STEP_SEMITONES[stepNode.textContent ?? ""];
    const octave = Number(octaveNode.textContent);
    const alterNode = pitch.querySelector(":scope > alter");
    const alter = Number(alterNode?.textContent ?? "0");
    if (base === undefined || !Number.isInteger(octave) || !Number.isInteger(alter)) {
      throw new Error("MusicXML 音高数据无效。");
    }
    const midi = transposePitch((octave + 1) * 12 + base + alter, semitones);
    const spelling = NOTE_NAMES[midi % 12];
    const accidentalNode = pitch.parentElement?.querySelector(":scope > accidental");
    stepNode.textContent = spelling.step;
    octaveNode.textContent = String(Math.floor(midi / 12) - 1);
    if (spelling.alter === 0) {
      alterNode?.remove();
      accidentalNode?.remove();
    } else if (alterNode) {
      alterNode.textContent = String(spelling.alter);
      if (accidentalNode) accidentalNode.textContent = "sharp";
    } else {
      const created = document.createElementNS(pitch.namespaceURI, "alter");
      created.textContent = String(spelling.alter);
      pitch.insertBefore(created, octaveNode);
      if (accidentalNode) accidentalNode.textContent = "sharp";
    }
  }
  return new XMLSerializer().serializeToString(document);
}

export function transposePitch(pitch: number, semitones: number): number {
  validateOffset(semitones);
  const result = pitch + semitones;
  if (!Number.isInteger(pitch) || result < 0 || result > 127) {
    throw new Error("转调后音高超出 MIDI 范围。");
  }
  return result;
}

function validateOffset(semitones: number): void {
  if (!Number.isInteger(semitones) || semitones < -12 || semitones > 12) {
    throw new Error("转调范围必须在 -12 到 +12 半音之间。");
  }
}
