import type { OpenSheetMusicDisplay } from "opensheetmusicdisplay";
import { describe, expect, it } from "vitest";
import { scoreMeasureRect, scoreSelectionRects } from "./score-selection";
import type { ScoreTimeMap } from "./score-time-map";

const anchors = [
  { scoreQuarters: 0, seconds: 0 },
  { scoreQuarters: 4, seconds: 2 },
  { scoreQuarters: 8, seconds: 4 },
];
const map: ScoreTimeMap = {
  measureQuarters: 4,
  quarterSeconds: 0.5,
  offsetQuarters: 0,
  downbeatAnchors: anchors,
  interpolationAnchors: anchors,
};

describe("score selection geometry", () => {
  it("merges adjacent measures into one clipped segment per score system", () => {
    const page = { PositionAndShape: { AbsolutePosition: { x: 0, y: 0 } } };
    const system = (y: number) => ({
      Parent: page,
      PositionAndShape: { AbsolutePosition: { x: 0, y } },
      StaffLines: [
        { PositionAndShape: { RelativePosition: { x: 0, y: 0 } }, StaffHeight: 4 },
        { PositionAndShape: { RelativePosition: { x: 0, y: 8 } }, StaffHeight: 4 },
      ],
    });
    const firstSystem = system(0);
    const secondSystem = system(20);
    const measure = (x: number, parentSystem: ReturnType<typeof system>) => ({
      ParentStaff: { isVisible: () => true },
      ParentMusicSystem: parentSystem,
      PositionAndShape: {
        AbsolutePosition: { x, y: 0 },
        UpperLeftCorner: { x: 1, y: 2 },
        Size: { width: 20, height: 10 },
      },
    });
    const osmd = {
      GraphicSheet: {
        MeasureList: [
          [measure(0, firstSystem)],
          [measure(20, firstSystem)],
          [measure(0, secondSystem)],
        ],
      },
      Drawer: { calculatePixelDistance: (units: number) => units * 10 },
    } as unknown as OpenSheetMusicDisplay;

    const rects = scoreSelectionRects(osmd, map, { start: 1, end: 5 }, 1);

    expect(rects).toEqual([
      { key: "page-0-system-0", left: 100, top: 0, width: 300, height: 120 },
      { key: "page-0-system-1", left: 0, top: 200, width: 100, height: 120 },
    ]);
  });

  it("uses absolute score positions for the active measure", () => {
    const measure = (x: number, y: number) => ({
      ParentStaff: { isVisible: () => true },
      ParentMusicSystem: {
        Parent: { PositionAndShape: { AbsolutePosition: { x: 0, y: 100 } } },
        PositionAndShape: { AbsolutePosition: { x: 0, y } },
        StaffLines: [
          { PositionAndShape: { RelativePosition: { x: 0, y: 0 } }, StaffHeight: 4 },
          { PositionAndShape: { RelativePosition: { x: 0, y: 8 } }, StaffHeight: 4 },
        ],
      },
      PositionAndShape: {
        AbsolutePosition: { x, y: 0 },
        UpperLeftCorner: { x: -1, y: -2 },
        Size: { width: 20, height: 10 },
      },
    });
    const osmd = {
      GraphicSheet: { MeasureList: [[measure(20, 30), measure(20, 42)]] },
      Drawer: { calculatePixelDistance: (units: number) => units * 10 },
    } as unknown as OpenSheetMusicDisplay;

    expect(scoreMeasureRect(osmd, 0, 0.5)).toEqual({
      left: 100,
      top: 650,
      width: 100,
      height: 60,
    });
  });

  it("keeps pickup selections aligned to score quarters", () => {
    const pickupMap: ScoreTimeMap = {
      measureQuarters: 4,
      quarterSeconds: 0.5,
      offsetQuarters: 2.75,
      downbeatAnchors: [
        { scoreQuarters: 4, seconds: 0.625 },
        { scoreQuarters: 8, seconds: 2.625 },
      ],
      interpolationAnchors: [
        { scoreQuarters: 2.75, seconds: 0 },
        { scoreQuarters: 4, seconds: 0.625 },
        { scoreQuarters: 8, seconds: 2.625 },
      ],
    };
    const measure = {
      ParentStaff: { isVisible: () => true },
      ParentMusicSystem: {
        Parent: { PositionAndShape: { AbsolutePosition: { x: 0, y: 0 } } },
        PositionAndShape: { AbsolutePosition: { x: 0, y: 0 } },
        StaffLines: [
          { PositionAndShape: { RelativePosition: { x: 0, y: 0 } }, StaffHeight: 4 },
        ],
      },
      PositionAndShape: {
        AbsolutePosition: { x: 0, y: 0 },
        Size: { width: 20, height: 4 },
      },
    };
    const osmd = {
      GraphicSheet: { MeasureList: [[measure]] },
      Drawer: { calculatePixelDistance: (units: number) => units * 10 },
    } as unknown as OpenSheetMusicDisplay;

    expect(scoreSelectionRects(osmd, pickupMap, { start: 0, end: 0.125 }, 1)).toEqual([
      { key: "page-0-system-0", left: 137.5, top: 0, width: 12.5, height: 40 },
    ]);
  });

});
