export const MIN_CLIP_SECONDS = 1;
export const MAX_CLIP_SECONDS = 90;
export const DEFAULT_CLIP_SECONDS = 30;

export type AudioClip = {
  start: number;
  end: number;
};

const roundTime = (value: number) => Math.round(value * 100) / 100;

export function createDefaultClip(duration: number): AudioClip {
  if (!Number.isFinite(duration) || duration < MIN_CLIP_SECONDS) {
    throw new Error("音频时长必须至少为 1 秒");
  }

  return { start: 0, end: roundTime(Math.min(duration, DEFAULT_CLIP_SECONDS)) };
}

export function normalizeClip(
  candidate: AudioClip,
  duration: number,
  changedEdge: "start" | "end" = "end",
): AudioClip {
  if (!Number.isFinite(duration) || duration < MIN_CLIP_SECONDS) {
    throw new Error("音频时长必须至少为 1 秒");
  }

  const safeStart = Math.max(0, Math.min(candidate.start, duration - MIN_CLIP_SECONDS));
  const safeEnd = Math.max(MIN_CLIP_SECONDS, Math.min(candidate.end, duration));
  let start = safeStart;
  let end = safeEnd;

  if (end - start < MIN_CLIP_SECONDS) {
    if (changedEdge === "start") {
      start = Math.max(0, end - MIN_CLIP_SECONDS);
    } else {
      end = Math.min(duration, start + MIN_CLIP_SECONDS);
    }
  }

  if (end - start > MAX_CLIP_SECONDS) {
    if (changedEdge === "start") {
      start = end - MAX_CLIP_SECONDS;
    } else {
      end = start + MAX_CLIP_SECONDS;
    }
  }

  return { start: roundTime(start), end: roundTime(end) };
}

export function clipDuration(clip: AudioClip): number {
  return roundTime(clip.end - clip.start);
}
