import { render, waitFor } from "@testing-library/react";
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { WaveformTrimmer } from "./waveform-trimmer";

type WaveSurferMock = {
  events: Map<string, (...args: never[]) => void>;
  destroy: ReturnType<typeof vi.fn>;
  loadBlob: ReturnType<typeof vi.fn>;
  on: ReturnType<typeof vi.fn>;
  pause: ReturnType<typeof vi.fn>;
  play: ReturnType<typeof vi.fn>;
};

const mocks = vi.hoisted(() => {
  const regionEvents = new Map<string, (...args: never[]) => void>();
  const instances: WaveSurferMock[] = [];
  const state = { rejectLoads: false };

  function makeWaveSurfer(): WaveSurferMock {
    const events = new Map<string, (...args: never[]) => void>();
    const instance = {
      events,
      destroy: vi.fn(() => events.clear()),
      loadBlob: vi.fn(async () => {
        if (!state.rejectLoads) return;
        events.get("error")?.();
        throw new Error("decode failed");
      }),
      on: vi.fn((event: string, handler: (...args: never[]) => void) => {
        events.set(event, handler);
        return vi.fn();
      }),
      pause: vi.fn(),
      play: vi.fn().mockResolvedValue(undefined),
    };
    instances.push(instance);
    return instance;
  }
  const regions = {
    addRegion: vi.fn(),
    on: vi.fn((event: string, handler: (...args: never[]) => void) => {
      regionEvents.set(event, handler);
      return vi.fn();
    }),
  };
  return { instances, makeWaveSurfer, regionEvents, regions, state, create: vi.fn() };
});

vi.mock("wavesurfer.js", () => ({
  default: { create: mocks.create },
}));

vi.mock("wavesurfer.js/dist/plugins/regions.esm.js", () => ({
  default: { create: () => mocks.regions },
}));

const file = new File(["audio"], "sample.wav", { type: "audio/wav" });
const props = {
  file,
  duration: 30,
  clip: { start: 0, end: 30 },
  onChange: vi.fn(),
  onError: vi.fn(),
};

describe("WaveformTrimmer", () => {
  beforeEach(() => {
    mocks.instances.length = 0;
    mocks.regionEvents.clear();
    mocks.state.rejectLoads = false;
    mocks.create.mockReset().mockImplementation(mocks.makeWaveSurfer);
    mocks.regions.on.mockClear();
    props.onError.mockReset();
  });

  afterEach(() => vi.restoreAllMocks());

  it("loads the File directly without managing an external object URL", async () => {
    const createObjectURL = vi.spyOn(URL, "createObjectURL");
    const revokeObjectURL = vi.spyOn(URL, "revokeObjectURL");
    const view = render(<WaveformTrimmer {...props} />);
    const waveSurfer = mocks.instances[0];

    await waitFor(() => expect(waveSurfer.loadBlob).toHaveBeenCalledWith(file));
    expect(mocks.create.mock.calls[0]?.[0]).not.toHaveProperty("url");
    expect(createObjectURL).not.toHaveBeenCalled();

    view.unmount();
    expect(waveSurfer.destroy).toHaveBeenCalledOnce();
    expect(revokeObjectURL).not.toHaveBeenCalled();
  });

  it("survives Strict Mode remounts and reports load errors", async () => {
    mocks.state.rejectLoads = true;
    const view = render(
      <StrictMode>
        <WaveformTrimmer {...props} />
      </StrictMode>,
    );

    await waitFor(() => expect(mocks.instances).toHaveLength(2));
    const [firstInstance, activeInstance] = mocks.instances;

    expect(firstInstance.loadBlob).toHaveBeenCalledWith(file);
    expect(firstInstance.destroy).toHaveBeenCalledOnce();
    expect(activeInstance.loadBlob).toHaveBeenCalledWith(file);
    expect(activeInstance.destroy).not.toHaveBeenCalled();
    expect(props.onError).toHaveBeenCalledWith("波形加载失败，请重新选择音频。");

    view.unmount();
    expect(activeInstance.destroy).toHaveBeenCalledOnce();
  });
});
