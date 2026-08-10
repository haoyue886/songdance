import type { OpenSheetMusicDisplay } from "opensheetmusicdisplay";
import { secondsToScoreQuarters, type ScoreTimeMap } from "./score-time-map";

export type ScoreSelectionRect = { left: number; top: number; width: number; height: number };
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
