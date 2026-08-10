import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ScoreSelectionOverlay } from "./score-selection-overlay";

describe("score selection overlay", () => {
  it("keeps keyed system segments mounted while their geometry changes", () => {
    const segments = [
      { key: "page-1-system-1", left: 10, top: 20, width: 30, height: 40 },
      { key: "page-1-system-2", left: 5, top: 80, width: 50, height: 40 },
    ];
    const view = render(
      <ScoreSelectionOverlay width={720} height={900}
        activeMeasure={{ left: 0, top: 0, width: 100, height: 40 }}
        selectionSegments={segments} />,
    );
    const firstBorder = view.container.querySelector(
      '[data-score-selection-segment="page-1-system-1"]',
    );
    expect(firstBorder).not.toBeNull();
    expect(view.getByTestId("score-selection-overlay")).toHaveClass("transition-opacity", "duration-100");
    expect(view.container.querySelectorAll('[data-score-selection-border="true"]')).toHaveLength(2);

    view.rerender(
      <ScoreSelectionOverlay width={720} height={900}
        activeMeasure={{ left: 0, top: 0, width: 100, height: 40 }}
        selectionSegments={[{ ...segments[0], width: 80 }, segments[1]]} />,
    );
    expect(view.container.querySelector(
      '[data-score-selection-segment="page-1-system-1"]',
    )).toBe(firstBorder);
    expect(firstBorder).toHaveAttribute("width", "80");
  });
});
