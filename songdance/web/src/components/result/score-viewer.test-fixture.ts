import { vi } from "vitest";

export const cursor = {
  reset: vi.fn(),
  nextMeasure: vi.fn(),
  show: vi.fn(),
  hide: vi.fn(),
};

export class FakePointF2D {
  constructor(public x: number, public y: number) {}
}

const fakePage = {
  PageNumber: 1,
  PositionAndShape: { AbsolutePosition: new FakePointF2D(0, 0) },
};
let staffEntriesReads = 0;
let renderCalls = 0;
export const tryGetTimeStampFromPosition = vi.fn((point: FakePointF2D) =>
  ({ RealValue: point.y > 150 ? 2.5 : point.x < 15 ? 0 : 0.5 }));

function fakeSystem(y: number) {
  return {
    Parent: fakePage,
    PositionAndShape: { AbsolutePosition: new FakePointF2D(0, y) },
    StaffLines: [
      { PositionAndShape: { RelativePosition: new FakePointF2D(0, 0) }, StaffHeight: 4 },
      { PositionAndShape: { RelativePosition: new FakePointF2D(0, 8) }, StaffHeight: 4 },
    ],
  };
}

const fakeSystems = [fakeSystem(10), fakeSystem(30)];

export class FakeGraphicalMeasure {
  parentSourceMeasure: {
    AbsoluteTimestamp: { RealValue: number };
    Duration: { RealValue: number };
  };
  ParentStaff = { isVisible: () => true };
  ParentMusicSystem: (typeof fakeSystems)[number];
  PositionAndShape: {
    AbsolutePosition: FakePointF2D;
    UpperLeftCorner: FakePointF2D;
    Size: { width: number; height: number };
  };
  private entries: Array<{
    PositionAndShape: { AbsolutePosition: FakePointF2D };
    getAbsoluteTimestamp: () => { RealValue: number };
  }>;

  get staffEntries() {
    staffEntriesReads += 1;
    return this.entries;
  }

  constructor(index: number) {
    this.parentSourceMeasure = {
      AbsoluteTimestamp: { RealValue: index },
      Duration: { RealValue: 1 },
    };
    this.ParentMusicSystem = fakeSystems[Math.floor(index / 2)];
    this.PositionAndShape = {
      AbsolutePosition: new FakePointF2D(index % 2 * 20, 0),
      UpperLeftCorner: new FakePointF2D(0, 0),
      Size: { width: 20, height: 12 },
    };
    this.entries = [{
      PositionAndShape: {
        AbsolutePosition: new FakePointF2D(index % 2 * 20 + 5, 10 + Math.floor(index / 2) * 20),
      },
      getAbsoluteTimestamp: () => ({ RealValue: index + 0.5 }),
    }];
  }
}

const measures = [
  [new FakeGraphicalMeasure(0)],
  [new FakeGraphicalMeasure(1)],
  [new FakeGraphicalMeasure(2)],
];

export class FakeOsmd {
  cursor = cursor;
  Drawer: {
    calculatePixelDistance: (units: number) => number;
    Backends: Array<{ graphicalMusicPage: typeof fakePage; getCanvas: () => SVGSVGElement }>;
  } = { calculatePixelDistance: (units: number) => units * 10, Backends: [] };
  GraphicSheet = {
    MeasureList: measures,
    domToSvg: (point: FakePointF2D) => point,
    svgToOsmd: (point: FakePointF2D) => point,
    osmdToSvg: (point: FakePointF2D) => point,
    GetNearestObject: (point: FakePointF2D) => point.x < 15 ? measures[0][0] : measures[1][0],
    tryGetTimeStampFromPosition,
  };

  constructor(private container: HTMLElement) {}

  load = vi.fn().mockResolvedValue({});
  render = vi.fn(() => {
    renderCalls += 1;
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("width", "720");
    svg.setAttribute("height", "900");
    svg.getBoundingClientRect = () => ({
      x: 0, y: 0, left: 0, top: 0, right: 720, bottom: 900,
      width: 720, height: 900, toJSON: () => ({}),
    });
    this.container.append(svg);
    this.Drawer.Backends = [{ graphicalMusicPage: fakePage, getCanvas: () => svg }];
  });
}

export function resetScoreViewerFixture() {
  cursor.reset.mockReset();
  cursor.nextMeasure.mockReset();
  cursor.show.mockReset();
  cursor.hide.mockReset();
  staffEntriesReads = 0;
  renderCalls = 0;
  tryGetTimeStampFromPosition.mockClear();
}

export function getStaffEntriesReads(): number {
  return staffEntriesReads;
}

export function getOsmdRenderCalls(): number {
  return renderCalls;
}
