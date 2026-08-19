import { describe, expect, it } from "vitest";
import {
  createScoreTimeMap,
  measureIndexAtTime,
  scoreQuartersToSeconds,
  secondsToScoreQuarters,
  scoreTimeMapMatches,
} from "./score-time-map";
import type { NoteTimeline } from "./timeline";

const timeline: NoteTimeline = {
  schema_version: 1,
  model_version: "test",
  tempo_bpm: 120,
  time_signature: "4/4",
  downbeat_grid_seconds: [0, 2, 4],
  quality_flags: [],
  notes: [{ id: "n", start_sec: 0, end_sec: 5, pitch: 60, velocity: 80, confidence: 1, hand: null }],
};

describe("score time map", () => {
  it("accepts aligned OSMD measure timestamps and rejects stale timeline grids", () => {
    const map = createScoreTimeMap(timeline);
    expect(map).not.toBeNull();
    if (!map) return;
    expect(scoreTimeMapMatches(map, timeline.downbeat_grid_seconds, [0, 1, 2])).toBe(true);
    expect(scoreTimeMapMatches(map, [0, 2], [0, 1, 2])).toBe(false);
    expect(scoreTimeMapMatches(map, [0, 2, 4], [0, 0.5, 1])).toBe(false);
    expect(scoreTimeMapMatches(map, [0, 2, 4], [0])).toBe(false);
    expect(scoreTimeMapMatches(map, undefined, [0, 1, 2])).toBe(false);

    const staleTimeline = { ...timeline, downbeat_grid_seconds: [0, 2.8, 5.6] };
    const staleMap = createScoreTimeMap(staleTimeline);
    expect(staleMap && scoreTimeMapMatches(staleMap, staleTimeline.downbeat_grid_seconds, [0, 1, 2])).toBe(false);

    const uniformlySlowTimeline = { ...timeline, downbeat_grid_seconds: [0, 2.4, 4.8] };
    const uniformlySlowMap = createScoreTimeMap(uniformlySlowTimeline);
    expect(uniformlySlowMap
      && scoreTimeMapMatches(uniformlySlowMap, uniformlySlowTimeline.downbeat_grid_seconds, [0, 1, 2]))
      .toBe(false);
    expect(scoreTimeMapMatches(map, timeline.downbeat_grid_seconds,
      Array.from({ length: 100 }, (_, index) => index))).toBe(false);
  });

  it("aligns the first downbeat after a partial opening measure", () => {
    const pickupTimeline = {
      ...timeline,
      downbeat_grid_seconds: [0.625, 2.625],
    };
    const map = createScoreTimeMap(pickupTimeline);
    expect(map).not.toBeNull();
    if (!map) return;

    expect(map.offsetQuarters).toBe(2.75);
    expect(secondsToScoreQuarters(map, 0)).toBe(2.75);
    expect(secondsToScoreQuarters(map, 0.125)).toBe(3);
    expect(scoreTimeMapMatches(map, pickupTimeline.downbeat_grid_seconds, [0, 0.3125, 1.3125]))
      .toBe(true);
    expect(scoreTimeMapMatches(map, pickupTimeline.downbeat_grid_seconds, [0, 0.5, 1.5]))
      .toBe(false);
    expect(scoreTimeMapMatches(map, pickupTimeline.downbeat_grid_seconds, [0, 1])).toBe(false);
  });

  it("interpolates the public example through every variable-tempo downbeat", () => {
    const downbeats = [
      0.580499, 2.321995, 4.017052, 5.828209, 7.639365, 9.427302,
      11.331338, 13.165714, 14.976871, 16.764807, 18.599184,
      20.3639, 22.105397, 23.893333, 25.72771, 27.538866, 29.350023,
    ];
    const map = createScoreTimeMap({
      ...timeline,
      tempo_bpm: 135.999178,
      downbeat_grid_seconds: downbeats,
    });
    expect(map).not.toBeNull();
    if (!map) return;

    const scoreMeasureStarts = [
      0,
      ...Array.from({ length: 17 }, (_, index) => 0.3125 + index),
    ];
    expect(scoreTimeMapMatches(map, downbeats, scoreMeasureStarts)).toBe(true);
    expect(scoreQuartersToSeconds(map, 4)).toBeCloseTo(downbeats[0], 6);
    expect(scoreQuartersToSeconds(map, 36)).toBeCloseTo(downbeats[8], 6);
    expect(scoreQuartersToSeconds(map, 68)).toBeCloseTo(downbeats[16], 6);
    expect(measureIndexAtTime(map, downbeats[8], 18)).toBe(9);
  });
});
