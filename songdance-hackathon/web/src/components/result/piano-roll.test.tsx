import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { NoteTimeline } from "@/lib/result/timeline";
import { drawWaterfall, getPianoRange, seekTimeFromCanvasY } from "./piano-roll-canvas";
import { PianoRoll } from "./piano-roll";

const timeline: NoteTimeline = {
  schema_version: 1,
  model_version: "test",
  tempo_bpm: 120,
  time_signature: "4/4",
  quality_flags: [],
  notes: [
    {
      id: "left",
      start_sec: 0,
      end_sec: 1,
      pitch: 48,
      velocity: 80,
      confidence: 0.8,
      hand: "left",
    },
    {
      id: "right",
      start_sec: 5,
      end_sec: 7,
      pitch: 72,
      velocity: 100,
      confidence: 0.9,
      hand: "right",
    },
  ],
};

describe("piano roll", () => {
  it("renders the shared notes on an accessible canvas and supports keyboard seeking", () => {
    const seek = vi.fn();
    render(<PianoRoll timeline={timeline} currentTime={5} duration={10} onSeek={seek} />);

    const roll = screen.getByRole("img", { name: /钢琴卷帘/ });
    expect(roll.tagName).toBe("CANVAS");
    fireEvent.keyDown(roll, { key: "ArrowRight" });
    expect(seek).toHaveBeenCalledWith(6);
  });

  it("keeps a responsive canvas contract for narrow layouts", () => {
    render(<PianoRoll timeline={timeline} currentTime={0} duration={10} onSeek={vi.fn()} />);
    const roll = screen.getByRole("img", { name: /钢琴卷帘/ });
    expect(roll).toHaveClass("aspect-[4/3]");
    expect(roll).toHaveClass("w-full");
  });

  it("keeps a playable piano range and maps canvas height to a relative seek", () => {
    const range = getPianoRange(timeline.notes);

    expect(range.whiteKeys.length).toBeGreaterThan(0);
    expect(range.high - range.low + 1).toBeGreaterThanOrEqual(24);
    expect(seekTimeFromCanvasY(0, 5, 400, 10)).toBeGreaterThan(5);
    expect(seekTimeFromCanvasY(400, 5, 400, 10)).toBeLessThan(5);
  });

  it("draws notes, the strike line, keyboard, and a neutral fallback hand color", () => {
    const recorder = createCanvasRecorder();
    const previousDevicePixelRatio = window.devicePixelRatio;
    Object.defineProperty(window, "devicePixelRatio", { configurable: true, value: 2 });

    drawWaterfall(
      recorder.canvas,
      [
        ...timeline.notes,
        {
          id: "unassigned",
          start_sec: 0,
          end_sec: 3,
          pitch: 60,
          velocity: 64,
          confidence: 0.7,
          hand: null,
        },
      ],
      0.5,
      false,
    );

    expect(recorder.canvas.width).toBe(600);
    expect(recorder.canvas.height).toBe(800);
    expect(recorder.fillColors).toContainEqual(expect.stringMatching(/^rgba\(25, 184, 209,/));
    expect(recorder.fillColors).toContainEqual(expect.stringMatching(/^rgba\(32, 189, 130,/));
    expect(recorder.fillColors).toContainEqual(expect.stringMatching(/^rgba\(143, 153, 148,/));
    expect(recorder.fillColors).toContain("#38d9ef");
    expect(recorder.fillColors).toContain("#b6c0ba");
    expect(recorder.fillColors).toContain("#dce8e0");

    Object.defineProperty(window, "devicePixelRatio", {
      configurable: true,
      value: previousDevicePixelRatio,
    });
  });

  it("seeks relative to the strike line when the canvas is pressed", () => {
    const seek = vi.fn();
    render(<PianoRoll timeline={timeline} currentTime={5} duration={10} onSeek={seek} />);
    const roll = screen.getByRole("img", { name: /钢琴卷帘/ });
    vi.spyOn(roll, "getBoundingClientRect").mockReturnValue({
      bottom: 500,
      height: 400,
      left: 0,
      right: 600,
      top: 100,
      width: 600,
      x: 0,
      y: 100,
      toJSON: () => ({}),
    });

    fireEvent.pointerDown(roll, { clientY: 100 });

    expect(seek).toHaveBeenCalledWith(seekTimeFromCanvasY(0, 5, 400, 10));
  });
});

function createCanvasRecorder(): {
  canvas: HTMLCanvasElement;
  fillColors: string[];
} {
  const fillColors: string[] = [];
  const context = {
    beginPath: vi.fn(),
    clearRect: vi.fn(),
    clip: vi.fn(),
    createLinearGradient: vi.fn(() => ({ addColorStop: vi.fn() })),
    fill: vi.fn(),
    fillRect: vi.fn(),
    fillText: vi.fn(),
    lineTo: vi.fn(),
    moveTo: vi.fn(),
    rect: vi.fn(),
    restore: vi.fn(),
    roundRect: vi.fn(),
    save: vi.fn(),
    setTransform: vi.fn(),
    stroke: vi.fn(),
    strokeRect: vi.fn(),
  } as unknown as CanvasRenderingContext2D;
  Object.defineProperty(context, "fillStyle", {
    set: (color: string | CanvasGradient | CanvasPattern) => fillColors.push(String(color)),
  });
  const canvas = {
    getBoundingClientRect: () => ({ height: 400, width: 300 }),
    getContext: () => context,
    height: 0,
    width: 0,
  } as unknown as HTMLCanvasElement;

  return { canvas, fillColors };
}
