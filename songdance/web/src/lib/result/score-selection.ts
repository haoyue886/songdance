import type { OpenSheetMusicDisplay, PointF2D } from "opensheetmusicdisplay";
import { scoreQuartersToSeconds, secondsToScoreQuarters, type ScoreTimeMap } from "./score-time-map";

export type ScoreSelectionRect = { left: number; top: number; width: number; height: number };
type ScorePoint = { x: number; y: number };

type ScoreBackend = {
  graphicalMusicPage: OpenSheetMusicDisplay["GraphicSheet"]["MusicPages"][number];
  getCanvas: () => HTMLElement;
};

export function scoreSecondsAtDomPoint(
  osmd: OpenSheetMusicDisplay,
  domPoint: ScorePoint,
  timeMap: ScoreTimeMap,
  duration: number,
): number | null {
  const backends = (osmd.Drawer as unknown as { Backends?: ScoreBackend[] }).Backends;
  const backend = backends?.length ? nearestBackend(backends, domPoint) : undefined;
  const pagePoint = backend && canvasToOsmd(
    backend.getCanvas(), domPoint, osmd.Drawer.calculatePixelDistance(1),
  );
  const entries = backend && pagePoint
    ? osmd.GraphicSheet.MeasureList.flatMap((staffMeasures) => staffMeasures.flatMap((measure) =>
      measure.ParentStaff.isVisible() && measure.ParentMusicSystem.Parent === backend.graphicalMusicPage
        ? measure.staffEntries
        : []))
    : [];
  const nearestEntry = pagePoint && entries.reduce<(typeof entries)[number] | null>((nearest, entry) => {
    if (!nearest) return entry;
    return pointDistance(entry.PositionAndShape.AbsolutePosition, pagePoint)
      < pointDistance(nearest.PositionAndShape.AbsolutePosition, pagePoint) ? entry : nearest;
  }, null);
  const timestamp = nearestEntry?.getAbsoluteTimestamp()
    ?? osmd.GraphicSheet.tryGetTimeStampFromPosition(
      osmd.GraphicSheet.svgToOsmd(osmd.GraphicSheet.domToSvg(domPoint as PointF2D)),
    );
  if (!timestamp || !Number.isFinite(timestamp.RealValue)) return null;
  return Math.min(duration, scoreQuartersToSeconds(timeMap, timestamp.RealValue * 4));
}

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

function nearestBackend(backends: ScoreBackend[], point: ScorePoint): ScoreBackend {
  return backends.reduce((nearest, backend) =>
    rectDistance(backend.getCanvas().getBoundingClientRect(), point)
      < rectDistance(nearest.getCanvas().getBoundingClientRect(), point) ? backend : nearest);
}

function canvasToOsmd(canvas: HTMLElement, point: ScorePoint, pixelsPerUnit: number): ScorePoint | null {
  const rect = canvas.getBoundingClientRect();
  if (rect.width <= 0 || rect.height <= 0 || pixelsPerUnit <= 0) return null;
  const width = Number(canvas.getAttribute("width")) || rect.width;
  const height = Number(canvas.getAttribute("height")) || rect.height;
  return {
    x: ((point.x - rect.left) * width / rect.width) / pixelsPerUnit,
    y: ((point.y - rect.top) * height / rect.height) / pixelsPerUnit,
  };
}

function rectDistance(rect: DOMRect, point: ScorePoint): number {
  const dx = Math.max(rect.left - point.x, 0, point.x - rect.right);
  const dy = Math.max(rect.top - point.y, 0, point.y - rect.bottom);
  return Math.hypot(dx, dy);
}

function pointDistance(left: ScorePoint, right: ScorePoint): number {
  return Math.hypot(left.x - right.x, left.y - right.y);
}

export function scoreSelectionRects(
  osmd: OpenSheetMusicDisplay,
  map: ScoreTimeMap,
  selection: { start: number; end: number },
  scale: number,
): ScoreSelectionRect[] {
  const selectionStartQuarters = secondsToScoreQuarters(map, selection.start);
  const selectionEndQuarters = secondsToScoreQuarters(map, selection.end);
  return osmd.GraphicSheet.MeasureList.flatMap((staffMeasures, measureIndex) => {
    const measureStartQuarters = measureIndex * map.measureQuarters;
    const measureEndQuarters = measureStartQuarters + map.measureQuarters;
    if (selectionEndQuarters <= measureStartQuarters || selectionStartQuarters >= measureEndQuarters) return [];
    const measureRect = scoreMeasureRect(osmd, measureIndex, scale);
    if (!measureRect) return [];
    const startFraction = clamp((selectionStartQuarters - measureStartQuarters) / map.measureQuarters);
    const endFraction = clamp((selectionEndQuarters - measureStartQuarters) / map.measureQuarters);
    return [{
      left: measureRect.left + measureRect.width * startFraction,
      top: measureRect.top,
      width: measureRect.width * Math.max(0, endFraction - startFraction),
      height: measureRect.height,
    }];
  });
}

function clamp(value: number): number {
  return Math.max(0, Math.min(1, value));
}
