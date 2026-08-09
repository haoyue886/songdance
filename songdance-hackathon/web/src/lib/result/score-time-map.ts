import type { NoteTimeline } from "./timeline";

const GRID_DIVISIONS = 4;

export type ScoreTimeMap = {
  measureQuarters: number;
  quarterSeconds: number;
  offsetQuarters: number;
  downbeatAnchors: Array<{ scoreQuarters: number; seconds: number }>;
  interpolationAnchors: Array<{ scoreQuarters: number; seconds: number }>;
};

export function createScoreTimeMap(timeline: NoteTimeline): ScoreTimeMap | null {
  const match = /^(\d+)\/(\d+)$/.exec(timeline.time_signature);
  if (!match) return null;
  const measureQuarters = Number(match[1]) * (4 / Number(match[2]));
  const measureUnits = measureQuarters * GRID_DIVISIONS;
  if (!Number.isInteger(measureUnits) || measureUnits <= 0 || timeline.tempo_bpm <= 0) return null;
  const quarterSeconds = 60 / timeline.tempo_bpm;
  const firstDownbeat = timeline.downbeat_grid_seconds?.[0] ?? 0;
  const downbeatUnits = Math.round((firstDownbeat / quarterSeconds) * GRID_DIVISIONS);
  const offsetUnits = ((-downbeatUnits % measureUnits) + measureUnits) % measureUnits;
  const offsetQuarters = offsetUnits / GRID_DIVISIONS;
  const firstDownbeatMeasure = offsetQuarters === 0 ? 0 : 1;
  const downbeatAnchors = (timeline.downbeat_grid_seconds ?? []).map((seconds, index) => ({
    scoreQuarters: (index + firstDownbeatMeasure) * measureQuarters,
    seconds,
  }));
  const interpolationAnchors = offsetQuarters > 0 && firstDownbeat > 0
    ? [{ scoreQuarters: offsetQuarters, seconds: 0 }, ...downbeatAnchors]
    : downbeatAnchors;
  return { measureQuarters, quarterSeconds, offsetQuarters, downbeatAnchors, interpolationAnchors };
}

export function measureIndexAtTime(map: ScoreTimeMap, seconds: number, measureCount: number): number {
  const scoreQuarters = secondsToScoreQuarters(map, Math.max(0, seconds));
  const boundaryEpsilon = 0.000001;
  return Math.min(measureCount - 1, Math.max(0,
    Math.floor((scoreQuarters + boundaryEpsilon) / map.measureQuarters)));
}

export function measureStartSeconds(map: ScoreTimeMap, measureIndex: number): number {
  const scoreQuarters = Math.max(0, measureIndex) * map.measureQuarters;
  return scoreQuartersToSeconds(map, scoreQuarters);
}

export function scorePositionSeconds(map: ScoreTimeMap, measureIndex: number, fraction = 0): number {
  const scoreQuarters = (Math.max(0, measureIndex) + Math.max(0, Math.min(1, fraction))) * map.measureQuarters;
  return scoreQuartersToSeconds(map, scoreQuarters);
}

export function scoreQuartersToSeconds(map: ScoreTimeMap, scoreQuarters: number): number {
  if (map.interpolationAnchors.length < 2) {
    return Math.max(0, (scoreQuarters - map.offsetQuarters) * map.quarterSeconds);
  }
  return Math.max(0, interpolate(
    map.interpolationAnchors,
    scoreQuarters,
    (anchor) => anchor.scoreQuarters,
    (anchor) => anchor.seconds,
  ));
}

export function secondsToScoreQuarters(map: ScoreTimeMap, seconds: number): number {
  if (map.interpolationAnchors.length < 2) {
    return seconds / map.quarterSeconds + map.offsetQuarters;
  }
  return interpolate(
    map.interpolationAnchors,
    seconds,
    (anchor) => anchor.seconds,
    (anchor) => anchor.scoreQuarters,
  );
}

export function scoreTimeMapMatches(
  map: ScoreTimeMap,
  downbeats: number[] | undefined,
  scoreMeasureStarts: number[],
): boolean {
  if (!downbeats?.length || scoreMeasureStarts.length === 0) return false;
  // A non-zero notation offset creates a partial opening measure before the
  // first detected downbeat. In that case downbeat 0 belongs to measure 1,
  // rather than the partial measure at score timestamp 0.
  const firstDownbeatMeasure = map.offsetQuarters === 0 ? 0 : 1;
  const requiredMeasureCount = downbeats.length + firstDownbeatMeasure;
  if (scoreMeasureStarts.length < requiredMeasureCount || scoreMeasureStarts.length > requiredMeasureCount + 1) {
    return false;
  }
  if (map.downbeatAnchors.length !== downbeats.length) return false;
  const expectedMeasureSeconds = map.measureQuarters * map.quarterSeconds;
  const expectedMeasureDuration = map.measureQuarters / 4;
  const downbeatIntervals: number[] = [];
  for (let index = 1; index < scoreMeasureStarts.length; index += 1) {
    const actualMeasureDuration = scoreMeasureStarts[index] - scoreMeasureStarts[index - 1];
    if (Math.abs(actualMeasureDuration - expectedMeasureDuration) > 0.001) return false;
  }
  for (let index = 0; index < downbeats.length; index += 1) {
    const seconds = downbeats[index];
    const anchor = map.downbeatAnchors[index];
    const scoreMeasureIndex = index + firstDownbeatMeasure;
    if (!Number.isFinite(seconds) || seconds < 0 || Math.abs(anchor.seconds - seconds) > 0.000001) return false;
    if (Math.abs(scoreMeasureStarts[scoreMeasureIndex] * 4 - anchor.scoreQuarters) > 0.001) return false;
    if (index === 0) continue;
    const interval = seconds - downbeats[index - 1];
    downbeatIntervals.push(interval);
    if (interval <= 0 || interval < expectedMeasureSeconds * 0.75 || interval > expectedMeasureSeconds * 1.25) {
      return false;
    }
  }
  if (downbeatIntervals.length > 0) {
    const sortedIntervals = [...downbeatIntervals].sort((left, right) => left - right);
    const middle = Math.floor(sortedIntervals.length / 2);
    const median = sortedIntervals.length % 2 === 0
      ? (sortedIntervals[middle - 1] + sortedIntervals[middle]) / 2
      : sortedIntervals[middle];
    const average = downbeatIntervals.reduce((total, interval) => total + interval, 0) / downbeatIntervals.length;
    if (Math.abs(median - expectedMeasureSeconds) > expectedMeasureSeconds * 0.15
      || Math.abs(average - expectedMeasureSeconds) > expectedMeasureSeconds * 0.15) {
      return false;
    }
  }
  return true;
}

function interpolate<T>(
  anchors: T[],
  value: number,
  input: (anchor: T) => number,
  output: (anchor: T) => number,
): number {
  let rightIndex = anchors.findIndex((anchor) => input(anchor) >= value);
  if (rightIndex < 0) rightIndex = anchors.length - 1;
  const leftIndex = rightIndex === 0 ? 0 : rightIndex - 1;
  if (leftIndex === rightIndex) {
    rightIndex = Math.min(anchors.length - 1, rightIndex + 1);
  }
  const left = anchors[leftIndex];
  const right = anchors[rightIndex];
  const inputSpan = input(right) - input(left);
  if (inputSpan === 0) return output(left);
  const ratio = (value - input(left)) / inputSpan;
  return output(left) + ratio * (output(right) - output(left));
}
