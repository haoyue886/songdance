import { beforeEach, describe, expect, it, vi } from "vitest";

const tone = vi.hoisted(() => ({
  samplerOptions: null as Record<string, unknown> | null,
  samplerTrigger: vi.fn(),
  samplerRelease: vi.fn(),
  samplerDisconnect: vi.fn(),
  samplerDispose: vi.fn(),
  fallbackTrigger: vi.fn(),
  fallbackRelease: vi.fn(),
  fallbackDisconnect: vi.fn(),
  fallbackDispose: vi.fn(),
  samplerShouldFail: false,
  samplerAutoLoad: true,
}));

vi.mock("tone", () => ({
  start: vi.fn().mockResolvedValue(undefined),
  now: vi.fn(() => 10),
  Frequency: vi.fn((pitch: number) => ({ toFrequency: () => pitch })),
  Sampler: class {
    constructor(options: Record<string, unknown>) {
      tone.samplerOptions = options;
      if (!tone.samplerAutoLoad) return;
      queueMicrotask(() => {
        if (tone.samplerShouldFail) {
          (options.onerror as (error: Error) => void)(new Error("load failed"));
        } else {
          (options.onload as () => void)();
        }
      });
    }
    toDestination() {
      return this;
    }
    triggerAttackRelease = tone.samplerTrigger;
    releaseAll = tone.samplerRelease;
    disconnect = tone.samplerDisconnect;
    dispose = tone.samplerDispose;
  },
  Synth: class {},
  PolySynth: class {
    toDestination() {
      return this;
    }
    triggerAttackRelease = tone.fallbackTrigger;
    releaseAll = tone.fallbackRelease;
    disconnect = tone.fallbackDisconnect;
    dispose = tone.fallbackDispose;
  },
}));

import { PIANO_SAMPLE_URLS, TimelineMidiPlayer } from "./player";

const notes = [
  {
    id: "note-1",
    start_sec: 0,
    end_sec: 0.5,
    pitch: 60,
    velocity: 100,
    confidence: 0.9,
    hand: "right" as const,
  },
];

describe("TimelineMidiPlayer", () => {
  beforeEach(() => {
    tone.samplerOptions = null;
    tone.samplerShouldFail = false;
    tone.samplerAutoLoad = true;
    vi.clearAllMocks();
  });

  it("loads local grand-piano samples and reuses the sampler", async () => {
    const player = new TimelineMidiPlayer();

    await expect(player.play(notes, 0, 1, 1)).resolves.toBe("piano");
    await expect(player.play(notes, 0, 1, 1)).resolves.toBe("piano");

    expect(tone.samplerOptions).toMatchObject({
      urls: PIANO_SAMPLE_URLS,
      baseUrl: "/audio/piano/",
    });
    expect(tone.samplerTrigger).toHaveBeenCalledTimes(2);
    expect(tone.fallbackTrigger).not.toHaveBeenCalled();
  });

  it("uses an explicitly reported synth fallback when samples fail", async () => {
    tone.samplerShouldFail = true;
    const player = new TimelineMidiPlayer();

    await expect(player.play(notes, 0, 1, 1)).resolves.toBe("synth-fallback");
    expect(tone.fallbackTrigger).toHaveBeenCalledOnce();
  });

  it("cancels the older request when play is clicked during sample loading", async () => {
    tone.samplerAutoLoad = false;
    const player = new TimelineMidiPlayer();

    const first = player.play(notes, 0, 1, 1);
    await vi.waitFor(() => expect(tone.samplerOptions).not.toBeNull());
    const second = player.play(notes, 0, 1, 1);
    await Promise.resolve();
    (tone.samplerOptions?.onload as () => void)();

    await expect(first).resolves.toBe("cancelled");
    await expect(second).resolves.toBe("piano");
    expect(tone.samplerTrigger).toHaveBeenCalledOnce();
  });

  it("does not schedule notes when disposed during sample loading", async () => {
    tone.samplerAutoLoad = false;
    const player = new TimelineMidiPlayer();

    const play = player.play(notes, 0, 1, 1);
    await vi.waitFor(() => expect(tone.samplerOptions).not.toBeNull());
    player.dispose();
    (tone.samplerOptions?.onload as () => void)();

    await expect(play).resolves.toBe("cancelled");
    expect(tone.samplerTrigger).not.toHaveBeenCalled();
    expect(tone.samplerDispose).toHaveBeenCalled();
  });

  it("disconnects scheduled piano audio immediately when stopped", async () => {
    const player = new TimelineMidiPlayer();
    await player.play(notes, 0, 1, 1);

    player.stop();

    expect(tone.samplerRelease).toHaveBeenCalled();
    expect(tone.samplerDisconnect).toHaveBeenCalled();
  });

  it("disposes the fallback synth so future scheduled notes cannot restart", async () => {
    tone.samplerShouldFail = true;
    const player = new TimelineMidiPlayer();
    await player.play(notes, 0, 1, 1);

    player.stop();

    expect(tone.fallbackDispose).toHaveBeenCalled();
  });
});
