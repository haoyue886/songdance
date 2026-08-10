import { fireEvent, render, waitFor } from "@testing-library/react";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { NoteTimeline } from "@/lib/result/timeline";
import {
  cursor,
  FakeGraphicalMeasure,
  FakeOsmd,
  FakePointF2D,
  getStaffEntriesReads,
  resetScoreViewerFixture,
  tryGetTimeStampFromPosition,
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
  notes: [
    {
      id: "note-1",
      start_sec: 0,
      end_sec: 5,
      pitch: 60,
      velocity: 90,
      confidence: 0.9,
      hand: "right",
    },
  ],
};

describe("score viewer", () => {
  beforeEach(() => {
    resetScoreViewerFixture();
    vi.stubGlobal(
      "ResizeObserver",
      class {
        observe() {}
        disconnect() {}
      },
    );
  });

  it("shows score progress and active pitches from the shared timeline", async () => {
    const onRendered = vi.fn();
    const view = render(
      <ScoreViewer
        musicXml="<score-partwise/>"
        currentTime={0}
        timeline={timeline}
        onSeek={vi.fn()}
        onRendered={onRendered}
      />,
    );

    await waitFor(() => expect(onRendered).toHaveBeenCalledWith(expect.any(HTMLDivElement)));
    const progress = view.getByRole("progressbar", { name: "五线谱播放位置" });
    expect(progress).toHaveAttribute("aria-valuenow", "0");
    expect(view.getByText(/C4/)).toBeInTheDocument();

    view.rerender(
      <ScoreViewer
        musicXml="<score-partwise/>"
        currentTime={2}
        timeline={timeline}
        onSeek={vi.fn()}
        onRendered={onRendered}
      />,
    );
    expect(progress).toHaveAttribute("aria-valuenow", "2");
    expect(progress.firstElementChild).toHaveStyle({ width: "40%" });
  });

  it("highlights, clicks and navigates measures through OSMD public APIs", async () => {
    const onSeek = vi.fn();
    const onRendered = vi.fn();
    const view = render(
      <ScoreViewer musicXml="<score-partwise/>" currentTime={0} timeline={timeline}
        onSeek={onSeek} onRendered={onRendered} />,
    );

    await waitFor(() => expect(view.getByText("第 1 / 3 小节")).toBeInTheDocument());
    await waitFor(() => expect(view.getByTestId("active-measure-highlight"))
      .toHaveAttribute("fill", "rgba(22, 163, 74, .22)"));
    expect(view.getByTestId("active-measure-highlight")).toHaveAttribute("y", "100");
    expect(view.getByRole("button", { name: "上一小节" })).toBeDisabled();
    fireEvent.click(view.getByRole("button", { name: "下一小节" }));
    expect(onSeek).toHaveBeenCalledWith(2);

    fireEvent.click(view.getByLabelText("MusicXML 五线谱"), { clientX: 50, clientY: 100 });
    expect(onSeek).toHaveBeenLastCalledWith(1);
    const cachedEntryReads = getStaffEntriesReads();
    fireEvent.click(view.getByLabelText("MusicXML 五线谱"), { clientX: 250, clientY: 100 });
    expect(onSeek).toHaveBeenLastCalledWith(3);
    expect(getStaffEntriesReads()).toBe(cachedEntryReads);
    expect(tryGetTimeStampFromPosition).not.toHaveBeenCalled();
    expect(cursor.show).toHaveBeenCalled();

    view.rerender(
      <ScoreViewer musicXml="<score-partwise/>" currentTime={4.1} timeline={timeline}
        onSeek={onSeek} onRendered={onRendered} />,
    );
    await waitFor(() => expect(view.getByText("第 3 / 3 小节")).toBeInTheDocument());
    expect(view.getByRole("button", { name: "下一小节" })).toBeDisabled();
    expect(cursor.nextMeasure).toHaveBeenCalled();
  });

  it("locates the active highlight from score geometry instead of measure index ratio", async () => {
    const view = render(
      <ScoreViewer musicXml="<score-partwise/>" currentTime={2.1} timeline={timeline}
        onSeek={vi.fn()} onRendered={vi.fn()} />,
    );
    await waitFor(() => expect(view.getByText("第 2 / 3 小节")).toBeInTheDocument());
    const viewport = view.getByTestId("score-viewport");
    Object.defineProperties(viewport, {
      clientHeight: { configurable: true, value: 100 },
      scrollHeight: { configurable: true, value: 500 },
    });
    const scrollTo = vi.fn();
    Object.defineProperty(viewport, "scrollTo", { configurable: true, value: scrollTo });
    fireEvent.click(view.getByRole("button", { name: "定位当前高亮" }));
    expect(scrollTo).toHaveBeenCalledWith({ top: 66, behavior: "smooth" });
  });

  it("keeps the score readable and disables navigation without a time mapping", async () => {
    const view = render(
      <ScoreViewer musicXml="<score-partwise/>" currentTime={0}
        timeline={{ ...timeline, time_signature: "free" }} onSeek={vi.fn()}
        onRendered={vi.fn()} />,
    );

    await waitFor(() => expect(view.getByText("小节定位不可用")).toBeInTheDocument());
    expect(view.getByRole("button", { name: "上一小节" })).toBeDisabled();
    expect(view.getByRole("button", { name: "下一小节" })).toBeDisabled();
    expect(view.getByLabelText("MusicXML 五线谱").querySelector("svg")).not.toBeNull();
  });

  it("disables score interaction when OSMD has fewer measures than the timeline", async () => {
    const onSeek = vi.fn();
    const view = render(
      <ScoreViewer musicXml="<score-partwise/>" currentTime={0}
        timeline={{ ...timeline, downbeat_grid_seconds: [0, 2, 4, 6] }} onSeek={onSeek}
        onRendered={vi.fn()} />,
    );
    await waitFor(() => expect(view.getByText("小节定位不可用")).toBeInTheDocument());
    fireEvent.click(view.getByLabelText("MusicXML 五线谱"), { clientX: 20, clientY: 20 });
    expect(onSeek).not.toHaveBeenCalled();
    expect(view.getByLabelText("MusicXML 五线谱").querySelector("svg")).not.toBeNull();
  });

  it("emits a shared timeline range only after dragging across measures", async () => {
    const onSelectionChange = vi.fn();
    const onSeek = vi.fn();
    const view = render(
      <ScoreViewer musicXml="<score-partwise/>" currentTime={0} timeline={timeline}
        onSeek={onSeek} onSelectionChange={onSelectionChange} onRendered={vi.fn()} />,
    );
    await waitFor(() => expect(view.getByText("第 1 / 3 小节")).toBeInTheDocument());
    const score = view.getByLabelText("MusicXML 五线谱");
    expect(score).toHaveClass("cursor-crosshair");
    fireEvent.pointerDown(score, pointer(1, 10, 10));
    fireEvent.pointerMove(score, pointer(1, 14, 10));
    expect(score).toHaveClass("cursor-crosshair");
    fireEvent.pointerUp(score, pointer(1, 10, 10));
    expect(score).toHaveClass("cursor-crosshair");
    expect(onSelectionChange).not.toHaveBeenCalled();
    fireEvent.click(score, { clientX: 10, clientY: 10 });
    expect(onSeek).toHaveBeenCalledWith(0.2);

    fireEvent.pointerDown(score, pointer(2, 10, 10));
    fireEvent.pointerMove(score, pointer(2, 20, 20));
    expect(score).toHaveClass("cursor-grabbing");
    await waitFor(() => expect(view.getByTestId("score-selection-overlay")).toBeInTheDocument());
    expect(onSelectionChange).not.toHaveBeenCalled();
    fireEvent.pointerUp(score, pointer(2, 20, 20));
    expect(onSelectionChange).toHaveBeenCalledWith({ start: 0.2, end: 0.4 });
  });

  it("clears an active drag when the pointer is cancelled", async () => {
    const onSelectionChange = vi.fn();
    const view = render(
      <ScoreViewer musicXml="<score-partwise/>" currentTime={0} timeline={timeline}
        onSeek={vi.fn()} onSelectionChange={onSelectionChange} onRendered={vi.fn()} />,
    );
    await waitFor(() => expect(view.getByText("第 1 / 3 小节")).toBeInTheDocument());
    const score = view.getByLabelText("MusicXML 五线谱");
    fireEvent.pointerDown(score, pointer(4, 10, 10));
    fireEvent.pointerMove(score, pointer(4, 20, 20));
    expect(score).toHaveClass("cursor-grabbing");
    fireEvent.pointerCancel(score, pointer(4, 20, 20));
    expect(score).toHaveClass("cursor-crosshair");
    fireEvent.pointerUp(score, pointer(4, 20, 20));
    expect(onSelectionChange).not.toHaveBeenCalled();
  });

  it("renders a padding-aligned mask with separate rectangles across score systems", async () => {
    function Harness() {
      const [selection, setSelection] = useState<{ start: number; end: number } | null>(null);
      return <ScoreViewer musicXml="<score-partwise/>" currentTime={0} timeline={timeline}
        selection={selection} onSeek={vi.fn()} onSelectionChange={setSelection} onRendered={vi.fn()} />;
    }
    const view = render(<Harness />);
    await waitFor(() => expect(view.getByText("第 1 / 3 小节")).toBeInTheDocument());
    const score = view.getByLabelText("MusicXML 五线谱");
    fireEvent.pointerDown(score, pointer(3, 10, 10));
    fireEvent.pointerMove(score, pointer(3, 10, 350));
    await waitFor(() => expect(view.getByTestId("score-selection-overlay")).toBeInTheDocument());
    fireEvent.pointerUp(score, pointer(3, 10, 350));
    const maskOverlay = await waitFor(() => {
      const element = view.container.querySelector("svg.pointer-events-none");
      expect(element).not.toBeNull();
      return element as SVGSVGElement;
    });
    expect(maskOverlay).toHaveClass("left-4", "top-4");
    expect(maskOverlay.querySelectorAll('rect[data-score-selection-border="true"]')).toHaveLength(3);
    expect(view.getByTestId("score-selection-overlay")).toHaveAttribute("fill", "rgba(255,255,255,.74)");
  });
});

function pointer(pointerId: number, clientX: number, clientY: number) {
  return { pointerId, clientX, clientY, pointerType: "mouse", button: 0, isPrimary: true };
}
