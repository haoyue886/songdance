import type { OpenSheetMusicDisplay, PointF2D } from "opensheetmusicdisplay";
import { notationQuartersToScoreQuarters, scoreQuartersToSeconds, type ScoreTimeMap } from "./score-time-map";
const EVENT_SNAP_RADIUS_PX = 8;
export type ScorePoint = { x: number; y: number };
type ScoreBackend = {
  graphicalMusicPage: OpenSheetMusicDisplay["GraphicSheet"]["MusicPages"][number];
  getCanvas: () => HTMLElement;
};
type HitAnchor = { x: number; scoreQuarters: number; isEvent: boolean };
type HitRect = { left: number; top: number; right: number; bottom: number };
type HitMeasure = HitRect & { measureIndex: number; anchors: HitAnchor[] };
type HitSystem = HitRect & { measures: HitMeasure[] };
type HitPage = { backend: ScoreBackend; systems: HitSystem[] };
export type ScoreHitMap = {
  osmd: OpenSheetMusicDisplay;
  timeMap: ScoreTimeMap;
  duration: number;
  pages: HitPage[];
  pixelsPerUnit: number;
};
export function createScoreHitMap(
  osmd: OpenSheetMusicDisplay,
  timeMap: ScoreTimeMap,
  duration: number,
): ScoreHitMap {
  const pixelsPerUnit = osmd.Drawer.calculatePixelDistance(1);
  const backends = (osmd.Drawer as unknown as { Backends?: ScoreBackend[] }).Backends ?? [];
  return {
    osmd,
    timeMap,
    duration,
    pixelsPerUnit,
    pages: backends.map((backend) => ({
      backend,
      systems: buildPageSystems(osmd, backend.graphicalMusicPage, timeMap),
    })),
  };
}
export function scoreSecondsAtDomPoint(hitMap: ScoreHitMap, domPoint: ScorePoint): number | null {
  const page = hitMap.pages.length ? nearestPage(hitMap.pages, domPoint) : null;
  const pagePoint = page
    ? canvasToOsmd(page.backend.getCanvas(), domPoint, hitMap.pixelsPerUnit)
    : null;
  const system = pagePoint && page?.systems.length
    ? nearestByRect(page.systems, pagePoint)
    : null;
  const measure = pagePoint && system?.measures.length
    ? nearestByRect(system.measures, pagePoint)
    : null;

  if (page && pagePoint && measure) {
    const cssPixelsPerUnit = canvasCssPixelsPerOsmdUnit(page.backend.getCanvas(), hitMap.pixelsPerUnit);
    const event = nearestEvent(measure.anchors, pagePoint.x);
    const scoreQuarters = event && Math.abs(event.x - pagePoint.x) * cssPixelsPerUnit <= EVENT_SNAP_RADIUS_PX
      ? event.scoreQuarters
      : interpolateScoreQuarters(measure.anchors, pagePoint.x);
    if (scoreQuarters !== null) return secondsFromQuarters(hitMap, scoreQuarters);
  }

  return fallbackSecondsAtDomPoint(hitMap, domPoint);
}

export function scoreMeasureFractionAtQuarters(
  hitMap: ScoreHitMap,
  measureIndex: number,
  scoreQuarters: number,
): number | null {
  const measure = hitMap.pages
    .flatMap((page) => page.systems)
    .flatMap((system) => system.measures)
    .find((candidate) => candidate.measureIndex === measureIndex);
  if (!measure || measure.right <= measure.left) return null;
  const times = measure.anchors.map((anchor) => anchor.scoreQuarters);
  if (scoreQuarters < Math.min(...times)) return 0;
  if (scoreQuarters > Math.max(...times)) return 1;
  const x = interpolateAnchorX(measure.anchors, scoreQuarters);
  return x === null ? null : clamp((x - measure.left) / (measure.right - measure.left));
}

function buildPageSystems(
  osmd: OpenSheetMusicDisplay,
  page: OpenSheetMusicDisplay["GraphicSheet"]["MusicPages"][number],
  timeMap: ScoreTimeMap,
): HitSystem[] {
  const systems = new Map<object, Map<number, OpenSheetMusicDisplay["GraphicSheet"]["MeasureList"][number]>>();
  osmd.GraphicSheet.MeasureList.forEach((staffMeasures, measureIndex) => {
    for (const measure of staffMeasures) {
      if (!measure.ParentStaff.isVisible() || measure.ParentMusicSystem.Parent !== page) continue;
      const system = measure.ParentMusicSystem;
      const measures = systems.get(system) ?? new Map();
      const grouped = measures.get(measureIndex) ?? [];
      grouped.push(measure);
      measures.set(measureIndex, grouped);
      systems.set(system, measures);
    }
  });

  return [...systems.entries()].map(([systemValue, measures]) => {
    const system = systemValue as OpenSheetMusicDisplay["GraphicSheet"]["MeasureList"][number][number]["ParentMusicSystem"];
    const hitMeasures = [...measures.entries()]
      .sort(([left], [right]) => left - right)
      .map(([measureIndex, staffMeasures]) => buildMeasure(staffMeasures, measureIndex, timeMap));
    const topStaffLine = system.StaffLines[0];
    const bottomStaffLine = system.StaffLines[system.StaffLines.length - 1];
    const top = system.PositionAndShape.AbsolutePosition.y
      + (topStaffLine?.PositionAndShape.RelativePosition.y ?? 0);
    const bottom = system.PositionAndShape.AbsolutePosition.y
      + (bottomStaffLine?.PositionAndShape.RelativePosition.y ?? 0)
      + (bottomStaffLine?.StaffHeight ?? 0);
    return {
      left: Math.min(...hitMeasures.map((measure) => measure.left)),
      top,
      right: Math.max(...hitMeasures.map((measure) => measure.right)),
      bottom,
      measures: hitMeasures,
    };
  }).filter((system) => system.measures.length > 0);
}

function buildMeasure(
  staffMeasures: OpenSheetMusicDisplay["GraphicSheet"]["MeasureList"][number],
  measureIndex: number,
  timeMap: ScoreTimeMap,
): HitMeasure {
  const measure = staffMeasures[0];
  const left = measure.PositionAndShape.AbsolutePosition.x;
  const right = left + measure.PositionAndShape.Size.width;
  const notationStart = finiteQuarters(measure.parentSourceMeasure.AbsoluteTimestamp.RealValue);
  const start = notationStart === null
    ? measureIndex * timeMap.measureQuarters
    : notationQuartersToScoreQuarters(timeMap, notationStart);
  const duration = finiteQuarters(measure.parentSourceMeasure.Duration?.RealValue)
    ?? timeMap.measureQuarters;
  const eventAnchors = staffMeasures.flatMap((staffMeasure) => staffMeasure.staffEntries.map((entry) => ({
    x: entry.PositionAndShape.AbsolutePosition.x,
    scoreQuarters: notationQuartersToScoreQuarters(
      timeMap,
      entry.getAbsoluteTimestamp().RealValue * 4,
    ),
    isEvent: true,
  }))).filter(isFiniteAnchor);
  const anchors = dedupeAnchors([
    { x: left, scoreQuarters: start, isEvent: false },
    ...eventAnchors,
    { x: right, scoreQuarters: start + duration, isEvent: false },
  ]);
  const system = measure.ParentMusicSystem;
  const topStaffLine = system.StaffLines[0];
  const bottomStaffLine = system.StaffLines[system.StaffLines.length - 1];
  const top = system.PositionAndShape.AbsolutePosition.y
    + (topStaffLine?.PositionAndShape.RelativePosition.y ?? 0);
  const bottom = system.PositionAndShape.AbsolutePosition.y
    + (bottomStaffLine?.PositionAndShape.RelativePosition.y ?? 0)
    + (bottomStaffLine?.StaffHeight ?? 0);
  return { measureIndex, left, top, right, bottom, anchors };
}

function dedupeAnchors(anchors: HitAnchor[]): HitAnchor[] {
  const byTimestamp = new Map<string, HitAnchor>();
  for (const anchor of anchors.filter(isFiniteAnchor)) {
    const key = anchor.scoreQuarters.toFixed(9);
    const current = byTimestamp.get(key);
    if (!current || anchor.isEvent) byTimestamp.set(key, anchor);
  }
  return [...byTimestamp.values()].sort((left, right) =>
    left.x - right.x || left.scoreQuarters - right.scoreQuarters);
}

function nearestPage(pages: HitPage[], point: ScorePoint): HitPage {
  return pages.reduce((nearest, page) =>
    rectDistance(scoreSurface(page.backend.getCanvas()).getBoundingClientRect(), point)
      < rectDistance(scoreSurface(nearest.backend.getCanvas()).getBoundingClientRect(), point) ? page : nearest);
}

function nearestByRect<T extends HitRect>(items: T[], point: ScorePoint): T {
  return items.reduce((nearest, item) =>
    hitRectDistance(item, point) < hitRectDistance(nearest, point) ? item : nearest);
}

function nearestEvent(anchors: HitAnchor[], x: number): HitAnchor | null {
  return anchors.filter((anchor) => anchor.isEvent).reduce<HitAnchor | null>((nearest, anchor) =>
    !nearest || Math.abs(anchor.x - x) < Math.abs(nearest.x - x) ? anchor : nearest, null);
}

function interpolateScoreQuarters(anchors: HitAnchor[], x: number): number | null {
  if (anchors.length === 0) return null;
  if (x <= anchors[0].x) return anchors[0].scoreQuarters;
  const last = anchors[anchors.length - 1];
  if (x >= last.x) return last.scoreQuarters;
  for (let index = 1; index < anchors.length; index += 1) {
    const right = anchors[index];
    if (x > right.x) continue;
    const left = anchors[index - 1];
    if (right.x <= left.x) return right.scoreQuarters;
    const progress = (x - left.x) / (right.x - left.x);
    return left.scoreQuarters + (right.scoreQuarters - left.scoreQuarters) * progress;
  }
  return last.scoreQuarters;
}

function interpolateAnchorX(anchors: HitAnchor[], scoreQuarters: number): number | null {
  if (anchors.length === 0) return null;
  const byTime = [...anchors].sort((left, right) =>
    left.scoreQuarters - right.scoreQuarters || left.x - right.x);
  if (scoreQuarters <= byTime[0].scoreQuarters) return byTime[0].x;
  const last = byTime[byTime.length - 1];
  if (scoreQuarters >= last.scoreQuarters) return last.x;
  const rightIndex = byTime.findIndex((anchor) => anchor.scoreQuarters >= scoreQuarters);
  const left = byTime[rightIndex - 1];
  const right = byTime[rightIndex];
  const span = right.scoreQuarters - left.scoreQuarters;
  if (span <= 0) return right.x;
  return left.x + (right.x - left.x) * ((scoreQuarters - left.scoreQuarters) / span);
}

function fallbackSecondsAtDomPoint(hitMap: ScoreHitMap, domPoint: ScorePoint): number | null {
  try {
    const timestamp = hitMap.osmd.GraphicSheet.tryGetTimeStampFromPosition(
      hitMap.osmd.GraphicSheet.svgToOsmd(
        hitMap.osmd.GraphicSheet.domToSvg(domPoint as PointF2D),
      ),
    );
    return timestamp && Number.isFinite(timestamp.RealValue)
      ? secondsFromQuarters(
        hitMap,
        notationQuartersToScoreQuarters(hitMap.timeMap, timestamp.RealValue * 4),
      )
      : null;
  } catch {
    return null;
  }
}

function secondsFromQuarters(hitMap: ScoreHitMap, scoreQuarters: number): number {
  return Math.max(0, Math.min(
    hitMap.duration,
    scoreQuartersToSeconds(hitMap.timeMap, scoreQuarters),
  ));
}

function canvasToOsmd(canvas: HTMLElement, point: ScorePoint, pixelsPerUnit: number): ScorePoint | null {
  const surface = scoreSurface(canvas);
  const rect = surface.getBoundingClientRect();
  if (rect.width <= 0 || rect.height <= 0 || pixelsPerUnit <= 0) return null;
  const width = surfaceDimension(surface, "width", rect.width);
  const height = surfaceDimension(surface, "height", rect.height);
  return {
    x: ((point.x - rect.left) * width / rect.width) / pixelsPerUnit,
    y: ((point.y - rect.top) * height / rect.height) / pixelsPerUnit,
  };
}

function canvasCssPixelsPerOsmdUnit(canvas: HTMLElement, pixelsPerUnit: number): number {
  const surface = scoreSurface(canvas);
  const rect = surface.getBoundingClientRect();
  const width = surfaceDimension(surface, "width", rect.width);
  return width > 0 ? pixelsPerUnit * rect.width / width : pixelsPerUnit;
}

function scoreSurface(canvas: HTMLElement): HTMLElement | SVGSVGElement {
  return canvas.matches("svg") ? canvas : canvas.querySelector<SVGSVGElement>("svg") ?? canvas;
}

function surfaceDimension(
  surface: HTMLElement | SVGSVGElement,
  dimension: "width" | "height",
  fallback: number,
): number {
  const attribute = Number(surface.getAttribute(dimension));
  if (Number.isFinite(attribute) && attribute > 0) return attribute;
  if (surface instanceof SVGSVGElement) {
    const viewBoxDimension = surface.viewBox.baseVal[dimension];
    if (Number.isFinite(viewBoxDimension) && viewBoxDimension > 0) return viewBoxDimension;
  }
  return fallback;
}

function rectDistance(rect: DOMRect, point: ScorePoint): number {
  const dx = Math.max(rect.left - point.x, 0, point.x - rect.right);
  const dy = Math.max(rect.top - point.y, 0, point.y - rect.bottom);
  return Math.hypot(dx, dy);
}

function hitRectDistance(rect: HitRect, point: ScorePoint): number {
  const dx = Math.max(rect.left - point.x, 0, point.x - rect.right);
  const dy = Math.max(rect.top - point.y, 0, point.y - rect.bottom);
  return Math.hypot(dx, dy);
}

function finiteQuarters(realValue: number | undefined): number | null {
  return Number.isFinite(realValue) ? (realValue as number) * 4 : null;
}

function isFiniteAnchor(anchor: HitAnchor): boolean {
  return Number.isFinite(anchor.x) && Number.isFinite(anchor.scoreQuarters);
}

function clamp(value: number): number {
  return Math.max(0, Math.min(1, value));
}
