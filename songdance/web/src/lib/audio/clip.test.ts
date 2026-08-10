import { describe, expect, it } from "vitest";
import { clipDuration, createDefaultClip, normalizeClip } from "./clip";

describe("audio clip rules", () => {
  it("uses the whole file below 30 seconds and defaults to 30 seconds otherwise", () => {
    expect(createDefaultClip(12.34)).toEqual({ start: 0, end: 12.34 });
    expect(createDefaultClip(120)).toEqual({ start: 0, end: 30 });
  });

  it("limits a changed end to 90 seconds", () => {
    expect(normalizeClip({ start: 10, end: 140 }, 180, "end")).toEqual({ start: 10, end: 100 });
  });

  it("keeps at least one second when either edge moves", () => {
    expect(normalizeClip({ start: 5, end: 5.2 }, 20, "end")).toEqual({ start: 5, end: 6 });
    expect(normalizeClip({ start: 8.8, end: 9 }, 20, "start")).toEqual({ start: 8, end: 9 });
  });

  it("rounds displayed clip duration to hundredths", () => {
    expect(clipDuration({ start: 1.111, end: 4.999 })).toBe(3.89);
  });
});
