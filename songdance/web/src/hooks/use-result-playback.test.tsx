import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
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

  afterEach(() => vi.useRealTimers());

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

  it("starts and schedules MIDI within a selected score range", async () => {
    const { result } = renderHook(() => useResultPlayback({
      ...timeline,
      notes: [{ ...timeline.notes[0], end_sec: 8 }],
    }));

    act(() => result.current.setSelection(2, 4));
    await act(async () => result.current.play());

    expect(result.current.selection).toEqual({ start: 2, end: 4 });
    expect(mocks.play).toHaveBeenCalledWith(expect.any(Array), 2, 4, 1);
    act(() => result.current.clearSelection());
    expect(result.current.selection).toBeNull();
  });

  it("starts source audio at the selection and stops at its end when loop is off", async () => {
    vi.useFakeTimers();
    const audio = fakeAudio();
    const { result } = renderHook(() => useResultPlayback({
      ...timeline,
      notes: [{ ...timeline.notes[0], end_sec: 8 }],
    }));
    Object.defineProperty(result.current.audioRef, "current", { configurable: true, value: audio });
    act(() => result.current.setMode("source"));
    act(() => result.current.setSelection(2, 4));
    await act(async () => result.current.play());
    expect(audio.currentTime).toBe(2);
    expect(audio.play).toHaveBeenCalledOnce();

    audio.currentTime = 4.01;
    await act(async () => vi.advanceTimersByTime(60));
    expect(audio.pause).toHaveBeenCalled();
    expect(result.current.playing).toBe(false);
    expect(result.current.currentTime).toBe(4);
  });

  it("loops source audio back to the selection start when loop is on", async () => {
    vi.useFakeTimers();
    const audio = fakeAudio();
    const { result } = renderHook(() => useResultPlayback({
      ...timeline,
      notes: [{ ...timeline.notes[0], end_sec: 8 }],
    }));
    Object.defineProperty(result.current.audioRef, "current", { configurable: true, value: audio });
    act(() => result.current.setMode("source"));
    act(() => result.current.setSelection(2, 4));
    act(() => result.current.setLoopEnabled(true));
    await act(async () => result.current.play());
    audio.currentTime = 4.01;
    await act(async () => vi.advanceTimersByTime(60));
    expect(audio.currentTime).toBe(2);
    expect(audio.play).toHaveBeenCalledTimes(2);
    expect(result.current.playing).toBe(true);
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

function fakeAudio() {
  return {
    currentTime: 0,
    playbackRate: 1,
    play: vi.fn().mockResolvedValue(undefined),
    pause: vi.fn(),
  } as unknown as HTMLAudioElement & { play: ReturnType<typeof vi.fn>; pause: ReturnType<typeof vi.fn> };
}
