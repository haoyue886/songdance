import { render, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { NoteTimeline } from "@/lib/result/timeline";
import { ScoreViewer } from "./score-viewer";

class FakeOsmd {
  constructor(private container: HTMLElement) {
  }

  load = vi.fn().mockResolvedValue({});
  render = vi.fn(() => {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("width", "720");
    svg.setAttribute("height", "900");
    this.container.append(svg);
  });
}

vi.mock("opensheetmusicdisplay", () => ({ OpenSheetMusicDisplay: FakeOsmd }));

const timeline: NoteTimeline = {
  schema_version: 1,
  model_version: "test",
  tempo_bpm: 120,
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
        onRendered={onRendered}
      />,
    );
    expect(progress).toHaveAttribute("aria-valuenow", "2");
    expect(progress.firstElementChild).toHaveStyle({ width: "40%" });
  });
});
