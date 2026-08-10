import type { OpenSheetMusicDisplay } from "opensheetmusicdisplay";
import { describe, expect, it } from "vitest";
import { createScoreHitMap, scoreSecondsAtDomPoint } from "./score-hit-map";
import type { ScoreTimeMap } from "./score-time-map";

const anchors = [
  { scoreQuarters: 0, seconds: 0 },
  { scoreQuarters: 4, seconds: 2 },
  { scoreQuarters: 8, seconds: 4 },
];
const timeMap: ScoreTimeMap = {
  measureQuarters: 4,
  quarterSeconds: 0.5,
  offsetQuarters: 0,
  downbeatAnchors: anchors,
  interpolationAnchors: anchors,
};

function canvas(top = 0, scale = 1): HTMLElement {
  const element = document.createElement("div");
  element.setAttribute("width", "1000");
  element.setAttribute("height", "1000");
  element.getBoundingClientRect = () => ({
    x: 0, y: top, left: 0, top, right: 1000 * scale, bottom: top + 1000 * scale,
    width: 1000 * scale, height: 1000 * scale, toJSON: () => ({}),
  });
  return element;
}

function wrappedSvg(top = 0, scale = 1): HTMLElement {
  const wrapper = document.createElement("div");
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("width", "1000");
  svg.setAttribute("height", "1000");
  svg.getBoundingClientRect = () => ({
    x: 0, y: top, left: 0, top, right: 1000 * scale, bottom: top + 1000 * scale,
    width: 1000 * scale, height: 1000 * scale, toJSON: () => ({}),
  });
  wrapper.append(svg);
  return wrapper;
}

function scorePage(pageNumber: number) {
  return { PageNumber: pageNumber };
}

function scoreSystem(page: ReturnType<typeof scorePage>, y = 0) {
  return {
    Parent: page,
    PositionAndShape: { AbsolutePosition: { x: 0, y } },
    StaffLines: [
      { PositionAndShape: { RelativePosition: { x: 0, y: 0 } }, StaffHeight: 4 },
      { PositionAndShape: { RelativePosition: { x: 0, y: 8 } }, StaffHeight: 4 },
    ],
  };
}

function scoreMeasure(
  system: ReturnType<typeof scoreSystem>,
  startRealValue: number,
  entries: Array<{ x: number; realValue: number }>,
  left = 0,
) {
  return {
    ParentStaff: { isVisible: () => true },
    ParentMusicSystem: system,
    parentSourceMeasure: {
      AbsoluteTimestamp: { RealValue: startRealValue },
      Duration: { RealValue: 1 },
    },
    PositionAndShape: {
      AbsolutePosition: { x: left, y: 0 },
      Size: { width: 20, height: 12 },
    },
    staffEntries: entries.map((entry) => ({
      PositionAndShape: { AbsolutePosition: { x: entry.x, y: system.PositionAndShape.AbsolutePosition.y } },
      getAbsoluteTimestamp: () => ({ RealValue: entry.realValue }),
    })),
  };
}

function scoreOsmd(
  pages: Array<{
    page: ReturnType<typeof scorePage>;
    canvas: HTMLElement;
    measures: ReturnType<typeof scoreMeasure>[];
  }>,
): OpenSheetMusicDisplay {
  return {
    Drawer: {
      calculatePixelDistance: (units: number) => units * 10,
      Backends: pages.map((page) => ({
        graphicalMusicPage: page.page,
        getCanvas: () => page.canvas,
      })),
    },
    GraphicSheet: {
      MeasureList: pages.flatMap((page) => page.measures.map((measure) => [measure])),
      domToSvg: (point: unknown) => point,
      svgToOsmd: (point: unknown) => point,
      tryGetTimeStampFromPosition: () => { throw new Error("cache should handle the point"); },
    },
  } as unknown as OpenSheetMusicDisplay;
}

describe("score hit map", () => {
  it("interpolates continuously between cached score events", () => {
    const page = scorePage(1);
    const measure = scoreMeasure(scoreSystem(page), 0, [
      { x: 5, realValue: 0.25 },
      { x: 15, realValue: 0.75 },
    ]);
    const osmd = scoreOsmd([{ page, canvas: canvas(), measures: [measure] }]);
    const hitMap = createScoreHitMap(osmd, timeMap, 10);
    measure.staffEntries.length = 0;

    expect(scoreSecondsAtDomPoint(hitMap, { x: 100, y: 60 })).toBe(1);
    expect(scoreSecondsAtDomPoint(hitMap, { x: 125, y: 60 })).toBe(1.25);
  });

  it("snaps within eight CSS pixels and interpolates outside the radius", () => {
    const page = scorePage(1);
    const osmd = scoreOsmd([{
      page,
      canvas: canvas(),
      measures: [scoreMeasure(scoreSystem(page), 0, [{ x: 5, realValue: 0.25 }])],
    }]);
    const hitMap = createScoreHitMap(osmd, timeMap, 10);

    expect(scoreSecondsAtDomPoint(hitMap, { x: 57, y: 60 })).toBe(0.5);
    expect(scoreSecondsAtDomPoint(hitMap, { x: 59, y: 60 })).toBeCloseTo(0.59, 5);
  });

  it("keeps CSS-pixel snapping stable when the score canvas is scaled", () => {
    const page = scorePage(1);
    const osmd = scoreOsmd([{
      page,
      canvas: canvas(0, 0.5),
      measures: [scoreMeasure(scoreSystem(page), 0, [{ x: 5, realValue: 0.25 }])],
    }]);
    const hitMap = createScoreHitMap(osmd, timeMap, 10);

    expect(scoreSecondsAtDomPoint(hitMap, { x: 32, y: 30 })).toBe(0.5);
    expect(scoreSecondsAtDomPoint(hitMap, { x: 34, y: 30 })).toBeCloseTo(0.68, 5);
  });

  it("uses SVG dimensions when a scaled backend canvas is a wrapper", () => {
    const page = scorePage(1);
    const secondSystem = scoreSystem(page, 30);
    const osmd = scoreOsmd([{
      page,
      canvas: wrappedSvg(100, 0.5),
      measures: [
        scoreMeasure(scoreSystem(page), 0, [{ x: 5, realValue: 0.25 }]),
        scoreMeasure(secondSystem, 1, [{ x: 5, realValue: 1.25 }]),
      ],
    }]);
    const hitMap = createScoreHitMap(osmd, timeMap, 10);

    expect(scoreSecondsAtDomPoint(hitMap, { x: 25, y: 280 })).toBe(2.5);
  });

  it("limits cached lookup to the backend page under the pointer", () => {
    const pageOne = scorePage(1);
    const pageTwo = scorePage(2);
    const osmd = scoreOsmd([
      {
        page: pageOne,
        canvas: canvas(0),
        measures: [scoreMeasure(scoreSystem(pageOne), 0, [{ x: 10, realValue: 0.5 }])],
      },
      {
        page: pageTwo,
        canvas: canvas(1000),
        measures: [scoreMeasure(scoreSystem(pageTwo), 2, [{ x: 10, realValue: 2.5 }])],
      },
    ]);
    const hitMap = createScoreHitMap(osmd, timeMap, 10);

    expect(scoreSecondsAtDomPoint(hitMap, { x: 100, y: 60 })).toBe(1);
    expect(scoreSecondsAtDomPoint(hitMap, { x: 100, y: 1060 })).toBe(5);
  });

  it("routes points through the cached system and measure geometry", () => {
    const page = scorePage(1);
    const firstSystem = scoreSystem(page);
    const secondSystem = scoreSystem(page, 30);
    const osmd = scoreOsmd([{
      page,
      canvas: canvas(),
      measures: [
        scoreMeasure(firstSystem, 0, [{ x: 5, realValue: 0.25 }]),
        scoreMeasure(firstSystem, 1, [{ x: 25, realValue: 1.5 }], 20),
        scoreMeasure(secondSystem, 2, [{ x: 5, realValue: 2.25 }]),
      ],
    }]);
    const hitMap = createScoreHitMap(osmd, timeMap, 10);

    expect(scoreSecondsAtDomPoint(hitMap, { x: 250, y: 60 })).toBe(3);
    expect(scoreSecondsAtDomPoint(hitMap, { x: 50, y: 360 })).toBe(4.5);
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
    const hitMap = createScoreHitMap(osmd, timeMap, 10);

    expect(scoreSecondsAtDomPoint(hitMap, { x: 10, y: 10 })).toBe(1);
  });
});
