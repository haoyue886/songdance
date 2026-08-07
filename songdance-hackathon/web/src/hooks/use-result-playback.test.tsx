import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { NoteTimeline } from "@/lib/result/timeline";
import { useResultPlayback } from "./use-result-playback";

const mocks = vi.hoisted(() => ({
  play: vi.fn(),
  stop: vi.fn(),
  dispose: vi.fn(),
  instances: [] as Array<{ disposed: boolean }>,
}));

vi.mock("@/lib/midi/player", () => ({
  TimelineMidiPlayer: class {
    disposed = false;
    constructor() {
      mocks.instances.push(this);
    }
    play = (...args: unknown[]) =>
      this.disposed ? Promise.resolve("cancelled") : mocks.play(...args);
    stop = () => mocks.stop();
    dispose = () => {
      this.disposed = true;
      mocks.dispose();
    };
  },
}));

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

describe("result playback", () => {
  beforeEach(() => {
    mocks.play.mockReset().mockResolvedValue("piano");
    mocks.stop.mockReset();
    mocks.dispose.mockReset();
    mocks.instances = [];
  });

  it("applies transpose, speed and loop bounds to real MIDI scheduling", async () => {
    const { result } = renderHook(() => useResultPlayback(timeline));

    act(() => result.current.setRate(1.5));
    act(() => result.current.setLoopStart(1));
    act(() => result.current.setLoopEnd(2));
    act(() => result.current.setLoopEnabled(true));
    act(() => result.current.setTranspose(1));
    await act(async () => result.current.play());

    expect(mocks.play).toHaveBeenCalledOnce();
    expect(mocks.play).toHaveBeenCalledWith(
      [expect.objectContaining({ pitch: 61 })],
      1,
      2,
      1.5,
    );
  });

  it("reports when piano samples fall back to a basic synth", async () => {
    mocks.play.mockResolvedValue("synth-fallback");
    const { result } = renderHook(() => useResultPlayback(timeline));

    await act(async () => result.current.play());

    expect(result.current.error).toBe("钢琴采样加载失败，当前使用基础合成音。");
  });

  it("recreates the MIDI player after the Strict Mode effect rehearsal", async () => {
    const { result, unmount } = renderHook(() => useResultPlayback(timeline), {
      reactStrictMode: true,
    });

    await act(async () => result.current.play());

    expect(mocks.instances).toHaveLength(2);
    expect(mocks.instances[0]?.disposed).toBe(true);
    expect(mocks.instances[1]?.disposed).toBe(false);
    expect(mocks.play).toHaveBeenCalledOnce();

    unmount();
    expect(mocks.instances[1]?.disposed).toBe(true);
    expect(mocks.dispose).toHaveBeenCalledTimes(2);
  });
});
