import { act, fireEvent, render } from "@testing-library/react";
import { useRef } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useScoreRangeDrag, type ScorePointer, type ScoreRange } from "./use-score-range-drag";

let nextFrameId = 1;
let frames = new Map<number, FrameRequestCallback>();

function Harness({
  secondsAtPoint,
  onCommit,
  enabled = true,
}: {
  secondsAtPoint: (point: ScorePointer) => number | null;
  onCommit: (selection: ScoreRange) => void;
  enabled?: boolean;
}) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const drag = useScoreRangeDrag({ enabled, viewportRef, secondsAtPoint, onCommit });
  return (
    <div ref={viewportRef} data-testid="viewport">
      <div
        data-testid="score"
        data-dragging={String(drag.isDragging)}
        data-draft={drag.draftSelection
          ? `${drag.draftSelection.start}:${drag.draftSelection.end}`
          : "none"}
        {...drag.pointerHandlers}
      />
    </div>
  );
}

describe("score range drag", () => {
  beforeEach(() => {
    nextFrameId = 1;
    frames = new Map();
    vi.stubGlobal("requestAnimationFrame", vi.fn((callback: FrameRequestCallback) => {
      const id = nextFrameId;
      nextFrameId += 1;
      frames.set(id, callback);
      return id;
    }));
    vi.stubGlobal("cancelAnimationFrame", vi.fn((id: number) => frames.delete(id)));
  });

  afterEach(() => vi.unstubAllGlobals());

  it("starts after four pixels, coalesces moves and commits only on release", () => {
    const secondsAtPoint = vi.fn((point: ScorePointer) => point.x / 10);
    const onCommit = vi.fn();
    const view = render(<Harness secondsAtPoint={secondsAtPoint} onCommit={onCommit} />);
    const score = view.getByTestId("score");

    fireEvent.pointerDown(score, pointer(1, 0, 100));
    secondsAtPoint.mockClear();
    fireEvent.pointerMove(score, pointer(1, 4, 100));
    expect(score).toHaveAttribute("data-dragging", "false");
    fireEvent.pointerMove(score, pointer(1, 5, 100));
    fireEvent.pointerMove(score, pointer(1, 10, 100));
    fireEvent.pointerMove(score, pointer(1, 20, 100));
    expect(score).toHaveAttribute("data-dragging", "true");
    expect(score).toHaveAttribute("data-draft", "none");
    expect(frames).toHaveLength(1);
    expect(secondsAtPoint).not.toHaveBeenCalled();

    flushFrame();
    expect(score).toHaveAttribute("data-draft", "0:2");
    expect(secondsAtPoint).toHaveBeenCalledOnce();
    expect(onCommit).not.toHaveBeenCalled();

    fireEvent.pointerUp(score, pointer(1, 20, 100));
    expect(score).toHaveAttribute("data-draft", "none");
    expect(score).toHaveAttribute("data-dragging", "false");
    expect(onCommit).toHaveBeenCalledOnce();
    expect(onCommit).toHaveBeenCalledWith({ start: 0, end: 2 });
  });

  it("normalizes the live range when the pointer crosses the anchor", () => {
    const view = render(<Harness secondsAtPoint={(point) => point.x / 10} onCommit={vi.fn()} />);
    const score = view.getByTestId("score");
    fireEvent.pointerDown(score, pointer(2, 20, 100));
    fireEvent.pointerMove(score, pointer(2, 5, 100));
    flushFrame();
    expect(score).toHaveAttribute("data-draft", "0.5:2");

    fireEvent.pointerMove(score, pointer(2, 30, 100));
    flushFrame();
    expect(score).toHaveAttribute("data-draft", "2:3");
  });

  it.each([
    ["pointerCancel", (score: HTMLElement) => fireEvent.pointerCancel(score, pointer(3, 20, 100))],
    ["lostPointerCapture", (score: HTMLElement) => fireEvent.lostPointerCapture(score, pointer(3, 20, 100))],
    ["Escape", () => fireEvent.keyDown(window, { key: "Escape" })],
  ])("cancels the draft on %s without committing", (_label, cancel) => {
    const onCommit = vi.fn();
    const view = render(<Harness secondsAtPoint={(point) => point.x / 10} onCommit={onCommit} />);
    const score = view.getByTestId("score");
    fireEvent.pointerDown(score, pointer(3, 0, 100));
    fireEvent.pointerMove(score, pointer(3, 20, 100));
    flushFrame();
    expect(score).toHaveAttribute("data-draft", "0:2");

    cancel(score);
    expect(score).toHaveAttribute("data-draft", "none");
    expect(score).toHaveAttribute("data-dragging", "false");
    expect(onCommit).not.toHaveBeenCalled();
  });

  it("scrolls only the score viewport at edge-dependent speed and stops after release", () => {
    const onCommit = vi.fn();
    const view = render(<Harness secondsAtPoint={(point) => point.x / 10} onCommit={onCommit} />);
    const viewport = view.getByTestId("viewport");
    const score = view.getByTestId("score");
    Object.defineProperties(viewport, {
      clientHeight: { configurable: true, value: 200 },
      scrollHeight: { configurable: true, value: 1000 },
      scrollTop: { configurable: true, writable: true, value: 100 },
    });
    viewport.getBoundingClientRect = () => ({
      x: 0, y: 100, left: 0, top: 100, right: 400, bottom: 300,
      width: 400, height: 200, toJSON: () => ({}),
    });
    const pageScroll = window.scrollY;

    fireEvent.pointerDown(score, pointer(4, 0, 150));
    fireEvent.pointerMove(score, pointer(4, 20, 135));
    flushFrame();
    const slowScrollTop = viewport.scrollTop;
    expect(slowScrollTop).toBeLessThan(96);
    fireEvent.pointerMove(score, pointer(4, 20, 101));
    flushFrame();
    expect(slowScrollTop - viewport.scrollTop).toBeGreaterThan(17);
    expect(window.scrollY).toBe(pageScroll);
    expect(frames).toHaveLength(1);

    const edgeScrollTop = viewport.scrollTop;
    fireEvent.pointerMove(score, pointer(4, 20, 150));
    flushFrame();
    expect(viewport.scrollTop).toBe(edgeScrollTop);
    expect(frames).toHaveLength(0);

    fireEvent.pointerMove(score, pointer(4, 20, 101));
    expect(frames).toHaveLength(1);
    fireEvent.pointerUp(score, pointer(4, 20, 101));
    expect(frames).toHaveLength(0);
    expect(onCommit).toHaveBeenCalledWith({ start: 0, end: 2 });
  });

  it("leaves touch vertical gestures to browser scrolling", () => {
    const onCommit = vi.fn();
    const view = render(<Harness secondsAtPoint={(point) => point.x / 10} onCommit={onCommit} />);
    const score = view.getByTestId("score");
    fireEvent.pointerDown(score, pointer(5, 0, 100, "touch"));
    fireEvent.pointerMove(score, pointer(5, 50, 150, "touch"));
    flushFrame();
    fireEvent.pointerUp(score, pointer(5, 50, 150, "touch"));

    expect(score).toHaveAttribute("data-draft", "none");
    expect(score).toHaveAttribute("data-dragging", "false");
    expect(onCommit).not.toHaveBeenCalled();
  });
});

function pointer(pointerId: number, clientX: number, clientY: number, pointerType = "mouse") {
  return { pointerId, clientX, clientY, pointerType, button: 0, isPrimary: true };
}

function flushFrame() {
  const pending = [...frames.entries()];
  frames.clear();
  act(() => pending.forEach(([, callback]) => callback(performance.now())));
}
