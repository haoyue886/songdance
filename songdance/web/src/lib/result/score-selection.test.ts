import type { OpenSheetMusicDisplay } from "opensheetmusicdisplay";
import { describe, expect, it } from "vitest";
import { scoreMeasureRect, scoreSecondsAtDomPoint, scoreSelectionRects } from "./score-selection";
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
  it("builds separate clipped rectangles across score systems", () => {
    const measure = (x: number, y: number) => ({
      ParentStaff: { isVisible: () => true },
      ParentMusicSystem: {
        Parent: { PositionAndShape: { AbsolutePosition: { x: 0, y: 0 } } },
        PositionAndShape: { AbsolutePosition: { x: 0, y } },
        StaffLines: [
          { PositionAndShape: { RelativePosition: { x: 0, y: 0 } }, StaffHeight: 4 },
          { PositionAndShape: { RelativePosition: { x: 0, y: 8 } }, StaffHeight: 4 },
        ],
      },
      PositionAndShape: {
        AbsolutePosition: { x, y: 0 },
        UpperLeftCorner: { x: 1, y: 2 },
        Size: { width: 20, height: 10 },
      },
    });
    const osmd = {
      GraphicSheet: { MeasureList: [[measure(0, 0)], [measure(20, 0)], [measure(0, 20)]] },
      Drawer: { calculatePixelDistance: (units: number) => units * 10 },
    } as unknown as OpenSheetMusicDisplay;

    const rects = scoreSelectionRects(osmd, map, { start: 1, end: 5 }, 1);

    expect(rects).toEqual([
      { left: 100, top: 0, width: 100, height: 120 },
      { left: 200, top: 0, width: 200, height: 120 },
      { left: 0, top: 200, width: 100, height: 120 },
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
      { left: 137.5, top: 0, width: 12.5, height: 40 },
    ]);
  });

  it("limits pointer timestamp lookup to the backend page under the pointer", () => {
    const pageOne = { PageNumber: 1 };
    const pageTwo = { PageNumber: 2 };
    const canvas = (top: number) => {
      const element = document.createElement("div");
      element.setAttribute("width", "720");
      element.setAttribute("height", "1000");
      element.getBoundingClientRect = () => ({
        x: 0, y: top, left: 0, top, right: 720, bottom: top + 1000,
        width: 720, height: 1000, toJSON: () => ({}),
      });
      return element;
    };
    const measure = (page: typeof pageOne, timestamp: number) => ({
      ParentStaff: { isVisible: () => true },
      ParentMusicSystem: { Parent: page },
      staffEntries: [{
        PositionAndShape: { AbsolutePosition: { x: 10, y: 10 } },
        getAbsoluteTimestamp: () => ({ RealValue: timestamp }),
      }],
    });
    const osmd = {
      Drawer: {
        calculatePixelDistance: (units: number) => units * 10,
        Backends: [
          { graphicalMusicPage: pageOne, getCanvas: () => canvas(0) },
          { graphicalMusicPage: pageTwo, getCanvas: () => canvas(1000) },
        ],
      },
      GraphicSheet: {
        MeasureList: [[measure(pageOne, 0.5)], [measure(pageTwo, 2.5)]],
        domToSvg: () => { throw new Error("page-aware lookup should not fall back"); },
      },
    } as unknown as OpenSheetMusicDisplay;

    expect(scoreSecondsAtDomPoint(osmd, { x: 100, y: 100 }, map, 10)).toBe(1);
    expect(scoreSecondsAtDomPoint(osmd, { x: 100, y: 1100 }, map, 10)).toBe(5);
  });

  it("falls back to the public position API when no backend is ready", () => {
    const osmd = {
      Drawer: { Backends: [], calculatePixelDistance: (units: number) => units * 10 },
      GraphicSheet: {
        MeasureList: [],
        domToSvg: (point: unknown) => point,
        svgToOsmd: (point: unknown) => point,
        tryGetTimeStampFromPosition: () => ({ RealValue: 0.5 }),
      },
    } as unknown as OpenSheetMusicDisplay;

    expect(scoreSecondsAtDomPoint(osmd, { x: 10, y: 10 }, map, 10)).toBe(1);
  });
});
