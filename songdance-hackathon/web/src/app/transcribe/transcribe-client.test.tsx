import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TranscribeClient } from "./transcribe-client";

const mocks = vi.hoisted(() => ({
  inspectAudioFile: vi.fn(),
  createJob: vi.fn(),
  sendUploadStartedEvent: vi.fn(),
  createClipFile: vi.fn(),
  getYoutubeConfig: vi.fn(),
  createYoutubeJob: vi.fn(),
  push: vi.fn(),
}));

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: mocks.push }) }));

vi.mock("@/lib/api/jobs", () => ({
  createJob: mocks.createJob,
  sendUploadStartedEvent: mocks.sendUploadStartedEvent,
  getYoutubeConfig: mocks.getYoutubeConfig,
  createYoutubeJob: mocks.createYoutubeJob,
}));

vi.mock("@/lib/audio/clip-file", () => ({ createClipFile: mocks.createClipFile }));

vi.mock("@/lib/audio/validation", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/lib/audio/validation")>();
  return { ...original, inspectAudioFile: mocks.inspectAudioFile };
});

vi.mock("@/components/audio/waveform-trimmer", () => ({
  WaveformTrimmer: () => <div aria-label="模拟波形">waveform</div>,
}));

describe("transcription draft", () => {
  beforeEach(() => {
    mocks.inspectAudioFile.mockReset();
    mocks.createJob.mockReset();
    mocks.sendUploadStartedEvent.mockReset().mockResolvedValue(undefined);
    mocks.createClipFile.mockReset();
    mocks.getYoutubeConfig.mockReset().mockResolvedValue({ enabled: true });
    mocks.createYoutubeJob.mockReset().mockResolvedValue({ id: "youtube-job-id" });
    mocks.push.mockReset();
    mocks.inspectAudioFile.mockResolvedValue({
      ok: true,
      value: { format: "wav", duration: 42.5 },
    });
    mocks.createJob.mockResolvedValue({ id: "secure-job-id" });
    mocks.createClipFile.mockResolvedValue(
      new File([new Uint8Array([1, 2, 3])], "piano-clip.wav", { type: "audio/wav" }),
    );
  });

  it("requires rights confirmation and creates a real task", async () => {
    const user = userEvent.setup();
    render(<TranscribeClient />);
    const file = new File([new Uint8Array([1, 2, 3])], "piano.wav", { type: "audio/wav" });

    await user.upload(screen.getByLabelText("选择钢琴音频"), file);
    await screen.findByLabelText("模拟波形");
    const confirmButton = screen.getByRole("button", { name: "创建转录任务" });
    expect(confirmButton).toBeDisabled();
    expect(screen.getByText("确认内容权利后才能继续。")).toBeInTheDocument();

    await user.click(screen.getByRole("checkbox"));
    expect(confirmButton).toBeEnabled();
    await user.click(confirmButton);
    await waitFor(() => expect(mocks.createJob).toHaveBeenCalledTimes(1));
    expect(mocks.createClipFile).toHaveBeenCalledWith(file, { start: 0, end: 30 });
    expect(mocks.sendUploadStartedEvent).toHaveBeenCalledTimes(1);
    expect(mocks.sendUploadStartedEvent.mock.invocationCallOrder[0]).toBeLessThan(
      mocks.createJob.mock.invocationCallOrder[0],
    );
    expect(mocks.createJob).toHaveBeenCalledWith(
      expect.objectContaining({
        file: expect.objectContaining({ name: "piano-clip.wav" }),
        startSec: 0,
        endSec: 30,
        rightsConfirmed: true,
      }),
    );
    expect(mocks.push).toHaveBeenCalledWith("/jobs/secure-job-id");
  });

  it("shows a recoverable API error without losing the selected clip", async () => {
    mocks.createJob.mockRejectedValue(new Error("队列暂时不可用"));
    const user = userEvent.setup();
    render(<TranscribeClient />);
    await user.upload(
      screen.getByLabelText("选择钢琴音频"),
      new File([new Uint8Array([1, 2, 3])], "piano.wav", { type: "audio/wav" }),
    );
    await screen.findByLabelText("模拟波形");
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "创建转录任务" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("队列暂时不可用");
    expect(screen.getByText("总时长 42.50 秒")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "创建转录任务" })).toBeEnabled();
  });

  it("shows a recoverable error and never renders a waveform for invalid input", async () => {
    mocks.inspectAudioFile.mockResolvedValue({ ok: false, error: "文件内容无法识别" });
    const user = userEvent.setup();
    render(<TranscribeClient />);

    await user.upload(
      screen.getByLabelText("选择钢琴音频"),
      new File([new Uint8Array([1])], "bad.wav", { type: "audio/wav" }),
    );

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("文件内容无法识别"));
    expect(screen.queryByLabelText("模拟波形")).not.toBeInTheDocument();
  });

  it("submits an enabled YouTube clip and requires rights confirmation", async () => {
    const user = userEvent.setup();
    render(<TranscribeClient />);

    await user.click(screen.getByRole("tab", { name: "YouTube" }));
    await screen.findByLabelText("YouTube 视频链接");
    await user.type(
      screen.getByLabelText("YouTube 视频链接"),
      "https://youtu.be/dQw4w9WgXcQ",
    );
    await user.clear(screen.getByLabelText("开始秒数"));
    await user.type(screen.getByLabelText("开始秒数"), "12.5");
    await user.clear(screen.getByLabelText("结束秒数"));
    await user.type(screen.getByLabelText("结束秒数"), "42.5");
    const submit = screen.getByRole("button", { name: "导入并创建转录任务" });
    expect(submit).toBeDisabled();
    await user.click(screen.getByRole("checkbox"));
    await user.click(submit);

    await waitFor(() => expect(mocks.createYoutubeJob).toHaveBeenCalledWith({
      url: "https://youtu.be/dQw4w9WgXcQ",
      startSec: 12.5,
      endSec: 42.5,
      rightsConfirmed: true,
    }));
    expect(mocks.push).toHaveBeenCalledWith("/jobs/youtube-job-id");
  });

  it("keeps local upload available when YouTube is disabled", async () => {
    mocks.getYoutubeConfig.mockResolvedValue({ enabled: false });
    const user = userEvent.setup();
    render(<TranscribeClient />);

    await user.click(screen.getByRole("tab", { name: "YouTube" }));
    expect(await screen.findByText("YouTube 导入当前未开放")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "改用本地上传" }));
    expect(screen.getByLabelText("选择钢琴音频")).toBeInTheDocument();
  });
});
