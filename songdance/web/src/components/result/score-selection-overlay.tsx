"use client";

import { useId, type PointerEvent as ReactPointerEvent, type PointerEventHandler } from "react";
import type { ScoreSelectionRect, ScoreSelectionSegment } from "@/lib/result/score-selection";

export type ScoreSelectionBoundary = "start" | "end";
export type ScoreSelectionBoundaryHandlers = {
  onPointerDown: (
    boundary: ScoreSelectionBoundary,
    event: ReactPointerEvent<SVGLineElement>,
  ) => void;
  onPointerMove: PointerEventHandler<SVGLineElement>;
  onPointerUp: PointerEventHandler<SVGLineElement>;
  onPointerCancel: PointerEventHandler<SVGLineElement>;
  onLostPointerCapture: PointerEventHandler<SVGLineElement>;
};

export function ScoreSelectionOverlay({
  width,
  height,
  activeMeasure,
  selectionSegments,
  boundaryHandlers,
}: {
  width: number;
  height: number;
  activeMeasure: ScoreSelectionRect | null;
  selectionSegments: ScoreSelectionSegment[];
  boundaryHandlers?: ScoreSelectionBoundaryHandlers;
}) {
  const maskId = useId().replaceAll(":", "");
  if (!activeMeasure && selectionSegments.length === 0) return null;
  return (
    <svg
      aria-hidden="true"
      data-testid="score-overlay-layer"
      className="pointer-events-none absolute left-4 top-4 z-10"
      width={width}
      height={height}
    >
      {activeMeasure && (
        <rect
          data-testid="active-measure-highlight"
          x={activeMeasure.left}
          y={activeMeasure.top}
          width={activeMeasure.width}
          height={activeMeasure.height}
          fill="rgba(22, 163, 74, .22)"
          stroke="#15803d"
          strokeWidth="2"
        />
      )}
      {selectionSegments.length > 0 && (
        <>
          <defs>
            <mask id={maskId}>
              <rect width="100%" height="100%" fill="white" />
              {selectionSegments.map((segment) => (
                <rect key={segment.key} data-score-selection-mask={segment.key}
                  x={segment.left} y={segment.top} width={segment.width} height={segment.height}
                  fill="black" />
              ))}
            </mask>
          </defs>
          <rect
            data-testid="score-selection-overlay"
            className="transition-opacity duration-100"
            width="100%"
            height="100%"
            fill="rgba(255,255,255,.74)"
            mask={`url(#${maskId})`}
          />
          {selectionSegments.map((segment) => (
            <rect key={segment.key} data-score-selection-border="true"
              data-score-selection-segment={segment.key}
              x={segment.left} y={segment.top} width={segment.width} height={segment.height}
              fill="rgba(255,255,255,0)" stroke="#15803d" strokeWidth="3" />
          ))}
          {boundaryHandlers && ([
            {
              boundary: "start" as const,
              x: selectionSegments[0].left,
              segment: selectionSegments[0],
            },
            {
              boundary: "end" as const,
              x: selectionSegments[selectionSegments.length - 1].left
                + selectionSegments[selectionSegments.length - 1].width,
              segment: selectionSegments[selectionSegments.length - 1],
            },
          ]).map(({ boundary, x, segment }) => (
            <line key={boundary}
              data-score-selection-handle={boundary}
              x1={x} x2={x} y1={segment.top} y2={segment.top + segment.height}
              stroke="transparent" strokeWidth="16" pointerEvents="stroke"
              style={{ cursor: "ew-resize" }}
              onClick={(event) => event.stopPropagation()}
              onPointerDown={(event) => boundaryHandlers.onPointerDown(boundary, event)}
              onPointerMove={boundaryHandlers.onPointerMove}
              onPointerUp={boundaryHandlers.onPointerUp}
              onPointerCancel={boundaryHandlers.onPointerCancel}
              onLostPointerCapture={boundaryHandlers.onLostPointerCapture} />
          ))}
        </>
      )}
    </svg>
  );
}
