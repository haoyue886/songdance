import { fetchArtifact } from "@/lib/api/jobs";

const MAX_LEADING_QUANTIZATION_SECONDS = 0.25;

export type TimelineHand = "left" | "right" | null;

export type TimelineNote = {
  id: string;
  start_sec: number;
  end_sec: number;
  pitch: number;
  velocity: number;
  confidence: number;
  hand: TimelineHand;
  hand_confidence?: number | null;
};

export type NoteTimeline = {
  schema_version: 1;
  model_version: string;
  tempo_bpm: number;
  beat_grid_seconds?: number[];
  downbeat_grid_seconds?: number[];
  time_signature: string;
  quality_flags: string[];
  notes: TimelineNote[];
};

export async function fetchTimeline(
  jobId: string,
  type: "timeline" | "raw_timeline" = "timeline",
  signal?: AbortSignal,
): Promise<NoteTimeline> {
  const response = await fetchArtifact(jobId, type, signal);
  return parseTimeline(await response.json());
}

export function parseTimeline(input: unknown): NoteTimeline {
  if (!isRecord(input) || input.schema_version !== 1) throw invalidTimeline();
  if (
    typeof input.model_version !== "string" ||
    !positiveNumber(input.tempo_bpm) ||
    typeof input.time_signature !== "string" ||
    !Array.isArray(input.quality_flags) ||
    !input.quality_flags.every((flag) => typeof flag === "string") ||
    !Array.isArray(input.notes)
  ) {
    throw invalidTimeline();
  }
  const notes = input.notes.map(parseNote);
  if (notes.length === 0) throw invalidTimeline("转录结果没有可预览的音符。");
  const beatGridSeconds = parseTimeGrid(input.beat_grid_seconds);
  const downbeatGridSeconds = parseTimeGrid(input.downbeat_grid_seconds);
  return {
    schema_version: 1,
    model_version: input.model_version,
    tempo_bpm: input.tempo_bpm,
    beat_grid_seconds: beatGridSeconds,
    downbeat_grid_seconds: downbeatGridSeconds,
    time_signature: input.time_signature,
    quality_flags: input.quality_flags,
    notes,
  };
}

export function timelineDuration(timeline: NoteTimeline): number {
  return Math.max(...timeline.notes.map((note) => note.end_sec));
}

function parseNote(input: unknown): TimelineNote {
  if (
    !isRecord(input) ||
    typeof input.id !== "string" ||
    !numberBetween(input.start_sec, -MAX_LEADING_QUANTIZATION_SECONDS, Number.MAX_VALUE) ||
    !positiveNumber(input.end_sec) ||
    input.end_sec <= input.start_sec ||
    !integerBetween(input.pitch, 0, 127) ||
    !integerBetween(input.velocity, 1, 127) ||
    !numberBetween(input.confidence, 0, 1) ||
    !["left", "right", null].includes(input.hand as TimelineHand)
  ) {
    throw invalidTimeline();
  }
  if (
    input.hand_confidence !== undefined &&
    input.hand_confidence !== null &&
    !numberBetween(input.hand_confidence, 0, 1)
  ) {
    throw invalidTimeline();
  }
  return {
    id: input.id,
    start_sec: Math.max(0, input.start_sec),
    end_sec: input.end_sec,
    pitch: input.pitch,
    velocity: input.velocity,
    confidence: input.confidence,
    hand: input.hand as TimelineHand,
    hand_confidence:
      typeof input.hand_confidence === "number" ? input.hand_confidence : null,
  };
}

function parseTimeGrid(input: unknown): number[] {
  if (input === undefined) return [];
  if (!Array.isArray(input) || !input.every(nonNegativeNumber)) throw invalidTimeline();
  return input;
}

function isRecord(input: unknown): input is Record<string, unknown> {
  return typeof input === "object" && input !== null;
}

function nonNegativeNumber(input: unknown): input is number {
  return typeof input === "number" && Number.isFinite(input) && input >= 0;
}

function positiveNumber(input: unknown): input is number {
  return nonNegativeNumber(input) && input > 0;
}

function numberBetween(input: unknown, min: number, max: number): input is number {
  return typeof input === "number" && Number.isFinite(input) && input >= min && input <= max;
}

function integerBetween(input: unknown, min: number, max: number): input is number {
  return Number.isInteger(input) && numberBetween(input, min, max);
}

function invalidTimeline(message = "转录结果格式无效，请重新提交音频。"): Error {
  return new Error(message);
}
