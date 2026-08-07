import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Transport, type TransportProps } from "./transport";

function props(): TransportProps {
  return {
    mode: "midi",
    onMode: vi.fn(),
    playing: false,
    onPlay: vi.fn(),
    onPause: vi.fn(),
    currentTime: 2,
    duration: 10,
    onSeek: vi.fn(),
    rate: 1,
    onRate: vi.fn(),
    loopEnabled: false,
    onLoopEnabled: vi.fn(),
    loopStart: 0,
    loopEnd: 10,
    onLoopStart: vi.fn(),
    onLoopEnd: vi.fn(),
    transpose: 0,
    onTranspose: vi.fn(),
  };
}

describe("transport", () => {
  it("exposes playback, source, speed, loop and transpose controls", async () => {
    const input = props();
    const user = userEvent.setup();
    render(<Transport {...input} />);

    await user.click(screen.getByRole("button", { name: "播放" }));
    await user.click(screen.getByRole("button", { name: "原音" }));
    await user.click(screen.getByRole("button", { name: "转录演奏" }));
    await user.selectOptions(screen.getByLabelText("播放速度"), "1.5");
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "升半音" }));

    expect(input.onPlay).toHaveBeenCalledOnce();
    expect(input.onMode).toHaveBeenCalledWith("source");
    expect(input.onMode).toHaveBeenCalledWith("midi");
    expect(input.onRate).toHaveBeenCalledWith(1.5);
    expect(input.onLoopEnabled).toHaveBeenCalledWith(true);
    expect(input.onTranspose).toHaveBeenCalledWith(1);
  });
});
