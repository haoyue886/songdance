"use client";

import { useId } from "react";
import type { ScoreSelectionRect, ScoreSelectionSegment } from "@/lib/result/score-selection";

export function ScoreSelectionOverlay({
  width,
  height,
  activeMeasure,
  selectionSegments,
}: {
  width: number;
  height: number;
  activeMeasure: ScoreSelectionRect | null;
  selectionSegments: ScoreSelectionSegment[];
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
        </>
      )}
    </svg>
  );
}
