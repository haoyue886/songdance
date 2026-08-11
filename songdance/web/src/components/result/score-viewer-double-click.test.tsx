import { fireEvent, render, waitFor } from "@testing-library/react";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { NoteTimeline } from "@/lib/result/timeline";
import {
  FakeGraphicalMeasure,
  FakeOsmd,
  FakePointF2D,
  resetScoreViewerFixture,
} from "./score-viewer.test-fixture";
import { ScoreViewer } from "./score-viewer";

vi.mock("opensheetmusicdisplay", () => ({
  CursorType: { CurrentArea: 3 },
  GraphicalMeasure: FakeGraphicalMeasure,
  OpenSheetMusicDisplay: FakeOsmd,
  PointF2D: FakePointF2D,
}));

const timeline: NoteTimeline = {
  schema_version: 1,
  model_version: "test",
  tempo_bpm: 120,
  downbeat_grid_seconds: [0, 2, 4],
  time_signature: "4/4",
  quality_flags: [],
  notes: [{
    id: "note-1", start_sec: 0, end_sec: 5, pitch: 60,
    velocity: 90, confidence: 0.9, hand: "right",
  }],
};

describe("score viewer double click", () => {
  beforeEach(() => {
    resetScoreViewerFixture();
    vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} });
  });

  it("clears a committed range without seeking and restores normal click positioning", async () => {
    const onSeek = vi.fn();
    const onSelectionChange = vi.fn();
    function Harness() {
      const [selection, setSelection] = useState<{ start: number; end: number } | null>(
        { start: 0.2, end: 0.4 },
      );
      return <ScoreViewer musicXml="<score-partwise/>" currentTime={0} timeline={timeline}
        selection={selection} onSeek={onSeek} onSelectionChange={(next) => {
          onSelectionChange(next);
          setSelection(next);
        }} onRendered={vi.fn()} />;
    }
    const view = render(<Harness />);
    await waitFor(() => expect(view.getByText("第 1 / 3 小节")).toBeInTheDocument());
    const score = view.getByLabelText("MusicXML 五线谱");
    const endHandle = view.container.querySelector('[data-score-selection-handle="end"]');
    expect(endHandle).not.toBeNull();

    fireEvent.click(score, { clientX: 50, clientY: 100 });
    await new Promise((resolve) => window.setTimeout(resolve, 250));
    fireEvent.doubleClick(endHandle!, { clientX: 250, clientY: 100 });
    await waitFor(() => expect(onSelectionChange).toHaveBeenCalledWith(null));
    await new Promise((resolve) => window.setTimeout(resolve, 400));
    expect(onSeek).not.toHaveBeenCalled();
    expect(view.container.querySelector('[data-score-selection-handle="end"]')).toBeNull();

    onSelectionChange.mockClear();
    fireEvent.click(score, { clientX: 250, clientY: 100 });
    expect(onSeek).toHaveBeenCalledOnce();
    expect(onSeek).toHaveBeenCalledWith(3);
    expect(onSelectionChange).not.toHaveBeenCalled();
  });
});
