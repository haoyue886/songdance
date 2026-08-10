import type { TranscriptionJob } from "@/lib/api/jobs";
import { timelineDuration, type NoteTimeline } from "@/lib/result/timeline";

export type ExampleProvenance = {
  clip_duration_sec: number;
  generated_at: string;
  artifacts: Record<"midi" | "musicxml" | "timeline", { size_bytes: number }>;
};

export function buildExampleJob(
  timeline: NoteTimeline,
  provenance: ExampleProvenance,
): TranscriptionJob {
  const artifact = (type: "midi" | "musicxml" | "timeline", mimeType: string) => ({
    type,
    status: "succeeded" as const,
    size_bytes: provenance.artifacts[type].size_bytes,
    mime_type: mimeType,
    error_code: null,
  });
  return {
    id: "example-mozart-sonata",
    status: "succeeded",
    stage: "completed",
    source_type: "public-domain-example",
    start_sec: 0,
    end_sec: Math.max(provenance.clip_duration_sec, timelineDuration(timeline)),
    attempt_count: 1,
    error_code: null,
    error_message: null,
    created_at: provenance.generated_at,
    updated_at: provenance.generated_at,
    expires_at: "2099-01-01T00:00:00Z",
    result: {
      tempo: timeline.tempo_bpm,
      time_signature: timeline.time_signature,
      note_count: timeline.notes.length,
      quality_flags: JSON.stringify(timeline.quality_flags),
      model_version: timeline.model_version,
    },
    quality_report: null,
    artifacts: [
      artifact("midi", "audio/midi"),
      artifact("musicxml", "application/vnd.recordare.musicxml+xml"),
      artifact("timeline", "application/json"),
    ],
  };
}
