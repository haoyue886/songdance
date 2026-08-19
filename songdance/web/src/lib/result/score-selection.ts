import type { OpenSheetMusicDisplay } from "opensheetmusicdisplay";
import { notationQuartersToScoreQuarters, secondsToScoreQuarters, type ScoreTimeMap } from "./score-time-map";

export type ScoreSelectionRect = { left: number; top: number; width: number; height: number };
export type ScoreSelectionSegment = ScoreSelectionRect & { key: string };
export type ScoreMeasureFractionResolver = (measureIndex: number, scoreQuarters: number) => number | null;
export function scoreMeasureRect(
  osmd: OpenSheetMusicDisplay,
  measureIndex: number,
  scale: number,
): ScoreSelectionRect | null {
  const staffMeasures = osmd.GraphicSheet.MeasureList[measureIndex];
  if (!staffMeasures?.length) return null;
  const measure = staffMeasures.find((candidate) =>
    candidate.ParentStaff.isVisible() && candidate.ParentMusicSystem?.StaffLines.length > 0);
  const system = measure?.ParentMusicSystem;
  if (!measure || !system) return null;
  const topStaffLine = system.StaffLines[0];
  const bottomStaffLine = system.StaffLines[system.StaffLines.length - 1];
  const pageOffset = scorePageOffset(osmd, system.Parent, scale);
  const left = measure.PositionAndShape.AbsolutePosition.x;
  const top = system.PositionAndShape.AbsolutePosition.y + topStaffLine.PositionAndShape.RelativePosition.y;
  const bottom = system.PositionAndShape.AbsolutePosition.y
    + bottomStaffLine.PositionAndShape.RelativePosition.y
    + bottomStaffLine.StaffHeight;
  return {
    left: osmd.Drawer.calculatePixelDistance(left) * scale + pageOffset.left,
    top: osmd.Drawer.calculatePixelDistance(top) * scale + pageOffset.top,
    width: osmd.Drawer.calculatePixelDistance(measure.PositionAndShape.Size.width) * scale,
    height: osmd.Drawer.calculatePixelDistance(bottom - top) * scale,
  };
}

function scorePageOffset(
  osmd: OpenSheetMusicDisplay,
  page: { PageNumber?: number; PositionAndShape: { AbsolutePosition: { x: number; y: number } } },
  scale: number,
): { left: number; top: number } {
  const drawer = osmd.Drawer as unknown as {
    Backends?: Array<{
      graphicalMusicPage: { PageNumber?: number };
      getCanvas: () => HTMLElement;
    }>;
  };
  const firstCanvas = drawer.Backends?.[0]?.getCanvas();
  const pageCanvas = drawer.Backends?.find((backend) =>
    backend.graphicalMusicPage === page
    || backend.graphicalMusicPage.PageNumber === page.PageNumber)?.getCanvas();
  if (firstCanvas && pageCanvas) {
    const firstRect = firstCanvas.getBoundingClientRect();
    const pageRect = pageCanvas.getBoundingClientRect();
    return { left: pageRect.left - firstRect.left, top: pageRect.top - firstRect.top };
  }
  return {
    left: osmd.Drawer.calculatePixelDistance(page.PositionAndShape.AbsolutePosition.x) * scale,
    top: osmd.Drawer.calculatePixelDistance(page.PositionAndShape.AbsolutePosition.y) * scale,
  };
}

export function scoreSelectionRects(
  osmd: OpenSheetMusicDisplay,
  map: ScoreTimeMap,
  selection: { start: number; end: number },
  scale: number,
  resolveFraction?: ScoreMeasureFractionResolver,
): ScoreSelectionSegment[] {
  const selectionStartQuarters = secondsToScoreQuarters(map, selection.start);
  const selectionEndQuarters = secondsToScoreQuarters(map, selection.end);
  const systemKeys = new Map<object, string>();
  const pageKeys = new Map<object, string>();
  const segments = new Map<object, ScoreSelectionSegment>();
  osmd.GraphicSheet.MeasureList.forEach((staffMeasures, measureIndex) => {
    const measure = staffMeasures.find((candidate) =>
      candidate.ParentStaff.isVisible() && candidate.ParentMusicSystem?.StaffLines.length > 0);
    if (!measure) return;
    const sourceStart = measure.parentSourceMeasure?.AbsoluteTimestamp?.RealValue;
    const sourceDuration = measure.parentSourceMeasure?.Duration?.RealValue;
    const measureStartQuarters = Number.isFinite(sourceStart)
      ? notationQuartersToScoreQuarters(map, sourceStart * 4)
      : measureIndex * map.measureQuarters;
    const measureDurationQuarters = Number.isFinite(sourceDuration) && sourceDuration > 0
      ? sourceDuration * 4
      : map.measureQuarters;
    const measureEndQuarters = measureStartQuarters + measureDurationQuarters;
    if (selectionEndQuarters <= measureStartQuarters || selectionStartQuarters >= measureEndQuarters) return;
    const measureRect = scoreMeasureRect(osmd, measureIndex, scale);
    if (!measureRect) return;
    const startFraction = resolveFraction?.(measureIndex, selectionStartQuarters)
      ?? clamp((selectionStartQuarters - measureStartQuarters) / measureDurationQuarters);
    const endFraction = resolveFraction?.(measureIndex, selectionEndQuarters)
      ?? clamp((selectionEndQuarters - measureStartQuarters) / measureDurationQuarters);
    const left = measureRect.left + measureRect.width * startFraction;
    const right = measureRect.left + measureRect.width * endFraction;
    const system = measure.ParentMusicSystem;
    const current = segments.get(system);
    if (current) {
      const currentRight = current.left + current.width;
      const bottom = Math.max(current.top + current.height, measureRect.top + measureRect.height);
      current.left = Math.min(current.left, left);
      current.top = Math.min(current.top, measureRect.top);
      current.width = Math.max(currentRight, right) - current.left;
      current.height = bottom - current.top;
      return;
    }
    segments.set(system, {
      key: systemKey(system, pageKeys, systemKeys),
      left,
      top: measureRect.top,
      width: Math.max(0, right - left),
      height: measureRect.height,
    });
  });
  return [...segments.values()];
}

function clamp(value: number): number {
  return Math.max(0, Math.min(1, value));
}

function systemKey(
  system: OpenSheetMusicDisplay["GraphicSheet"]["MeasureList"][number][number]["ParentMusicSystem"],
  pageKeys: Map<object, string>,
  systemKeys: Map<object, string>,
): string {
  const existing = systemKeys.get(system);
  if (existing) return existing;
  const page = system.Parent;
  let pageKey = pageKeys.get(page);
  if (!pageKey) {
    const pageNumber = Number.isFinite(page.PageNumber) ? page.PageNumber : pageKeys.size;
    pageKey = `page-${pageNumber}`;
    pageKeys.set(page, pageKey);
  }
  const systemId = Number.isFinite(system.Id) ? system.Id : systemKeys.size;
  const key = `${pageKey}-system-${systemId}`;
  systemKeys.set(system, key);
  return key;
}
