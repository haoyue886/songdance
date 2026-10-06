import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TranscribeClient } from "./transcribe-client";
import { JobsApiError } from "@/lib/api/jobs";
import type { useUploadBilling } from "@/components/billing/use-upload-billing";

const mocks = vi.hoisted(() => ({
  inspectAudioFile: vi.fn(),
  createJob: vi.fn(),
  sendUploadStartedEvent: vi.fn(),
  createClipFile: vi.fn(),
  getYoutubeConfig: vi.fn(),
  createYoutubeJob: vi.fn(),
  push: vi.fn(),
  usage: vi.fn(),
  refresh: vi.fn(),
}));

vi.mock("@/i18n/navigation", () => ({
  Link: ({ href, children }: { href: string; children: React.ReactNode }) => <a href={href}>{children}</a>,
  useRouter: () => ({ push: mocks.push }),
}));

vi.mock("@/lib/api/jobs", async (importOriginal) => ({
  ...await importOriginal<typeof import("@/lib/api/jobs")>(),
  createJob: mocks.createJob,
  sendUploadStartedEvent: mocks.sendUploadStartedEvent,
  getYoutubeConfig: mocks.getYoutubeConfig,
  createYoutubeJob: mocks.createYoutubeJob,
}));

vi.mock("@/lib/audio/clip-file", () => ({ createClipFile: mocks.createClipFile }));
vi.mock("@/components/billing/use-upload-billing", () => ({
  useUploadBilling: mocks.usage,
}));

vi.mock("@/lib/audio/validation", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/lib/audio/validation")>();
  return { ...original, inspectAudioFile: mocks.inspectAudioFile };
});

vi.mock("@/components/audio/waveform-trimmer", () => ({
  WaveformTrimmer: ({ onChange, disabled }: { onChange: (clip: { start: number; end: number }) => void; disabled: boolean }) => <div aria-label="模拟波形">waveform<button disabled={disabled} onClick={() => onChange({ start: 5, end: 25 })}>change clip</button><button disabled={disabled} onClick={() => onChange({ start: 0, end: 30 })}>same clip</button></div>,
}));

function meteredUsage(remaining: number): ReturnType<typeof useUploadBilling> {
  return {
    failed: false, pending: false, refresh: mocks.refresh, maxSeconds: 90,
    data: {
      config: {
        usage_enabled: true, checkout_enabled: false, mode: "test",
        pro: { price_minor: 100, currency: "USD", seconds: 600, max_clip_seconds: 90, min_charge_seconds: 1 },
        free: { monthly_jobs: 3, max_clip_seconds: 90 }, guest: { max_clip_seconds: 90 },
        retention_hours: 24, support_email: null,
      },
      summary: { enabled: true, plan: "free", unit: "jobs", remaining, state: "active" },
    },
  };
}

async function prepareUpload() {
  const user = userEvent.setup();
  await user.upload(screen.getByLabelText("选择钢琴音频"), new File(["audio"], "piano.wav", { type: "audio/wav" }));
  await screen.findByLabelText("模拟波形");
  await user.click(screen.getByRole("checkbox"));
  return user;
}

describe("transcription draft", () => {
  beforeEach(() => {
    mocks.inspectAudioFile.mockReset();
    mocks.createJob.mockReset();
    mocks.sendUploadStartedEvent.mockReset().mockResolvedValue(undefined);
    mocks.createClipFile.mockReset();
    mocks.getYoutubeConfig.mockReset().mockResolvedValue({ enabled: true });
    mocks.createYoutubeJob.mockReset().mockResolvedValue({ id: "youtube-job-id" });
    mocks.push.mockReset();
    mocks.refresh.mockReset();
    mocks.usage.mockReset().mockReturnValue({ data: null, failed: false, pending: false, refresh: mocks.refresh, maxSeconds: 90 });
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

    expect(await screen.findByRole("alert")).toHaveTextContent("操作失败，请重试");
    expect(screen.getByText("总时长 42.50 秒")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "创建转录任务" })).toBeEnabled();
  });

  it.each([0, 503])("replays the same bytes and key after status %i even when the first job reserved the last allowance", async (status) => {
    mocks.usage.mockReturnValue(meteredUsage(1));
    mocks.refresh.mockImplementation(() => mocks.usage.mockReturnValue(meteredUsage(0)));
    mocks.createJob.mockRejectedValueOnce(new JobsApiError("Lost response", status, status ? "SUBMISSION_UNAVAILABLE" : "NETWORK_ERROR"));
    const view = render(<TranscribeClient />);
    const user = await prepareUpload();
    await user.click(screen.getByRole("button", { name: "创建转录任务" }));
    await waitFor(() => expect(mocks.refresh).toHaveBeenCalledTimes(1));
    view.rerender(<TranscribeClient />);
    await user.click(screen.getByRole("button", { name: "same clip" }));
    const retry = screen.getByRole("button", { name: "创建转录任务" });
    expect(retry).toBeEnabled();
    await user.click(retry);
    await waitFor(() => expect(mocks.createJob).toHaveBeenCalledTimes(2));
    const [first, replay] = mocks.createJob.mock.calls.map(([input]) => input);
    expect(first.submissionKey).toMatch(/^[a-f0-9-]{36}$/);
    expect(replay.submissionKey).toBe(first.submissionKey);
    expect(replay.file).toBe(first.file);
    expect(mocks.createClipFile).toHaveBeenCalledTimes(1);
    expect(mocks.push).toHaveBeenCalledWith("/jobs/secure-job-id");
  });

  it("resets the replay allowance on clip changes and keeps new over-quota drafts blocked", async () => {
    mocks.usage.mockReturnValue(meteredUsage(1));
    mocks.createJob.mockRejectedValue(new JobsApiError("Lost", 0, "NETWORK_ERROR"));
    const view = render(<TranscribeClient />);
    const user = await prepareUpload();
    await user.click(screen.getByRole("button", { name: "创建转录任务" }));
    await waitFor(() => expect(mocks.refresh).toHaveBeenCalledTimes(1));
    mocks.usage.mockReturnValue(meteredUsage(0));
    view.rerender(<TranscribeClient />);
    expect(screen.getByRole("button", { name: "创建转录任务" })).toBeEnabled();
    await user.click(screen.getByRole("button", { name: "change clip" }));
    expect(screen.getByRole("button", { name: "创建转录任务" })).toBeDisabled();
    expect(mocks.createJob).toHaveBeenCalledTimes(1);
  });

  it.each(["frozen", "over-limit", "rejected"])("does not bypass the %s gate after an error", async (gate) => {
    mocks.usage.mockReturnValue(meteredUsage(1));
    mocks.createJob.mockRejectedValue(new JobsApiError("Failure", gate === "rejected" ? 409 : 0));
    const view = render(<TranscribeClient />);
    const user = await prepareUpload();
    await user.click(screen.getByRole("button", { name: "创建转录任务" }));
    await waitFor(() => expect(mocks.refresh).toHaveBeenCalledTimes(1));
    const usage = meteredUsage(0);
    if (gate === "frozen") usage.data!.summary!.state = "frozen";
    if (gate === "over-limit") usage.maxSeconds = 10;
    mocks.usage.mockReturnValue(usage);
    view.rerender(<TranscribeClient />);
    expect(screen.getByRole("button", { name: "创建转录任务" })).toBeDisabled();
  });

  it("creates a new key and clipped file for each changed clip or selected file", async () => {
    mocks.createJob.mockRejectedValue(new JobsApiError("Lost", 0));
    mocks.createClipFile.mockImplementation(async () => new File([crypto.randomUUID()], "clip.wav"));
    render(<TranscribeClient />);
    const user = await prepareUpload();
    await user.click(screen.getByRole("button", { name: "创建转录任务" }));
    await waitFor(() => expect(mocks.refresh).toHaveBeenCalledTimes(1));
    await user.click(screen.getByRole("button", { name: "change clip" }));
    await user.click(screen.getByRole("button", { name: "创建转录任务" }));
    await waitFor(() => expect(mocks.refresh).toHaveBeenCalledTimes(2));
    await user.upload(screen.getByLabelText("选择钢琴音频"), new File(["new audio"], "other.wav", { type: "audio/wav" }));
    await screen.findByLabelText("模拟波形");
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "创建转录任务" }));
    await waitFor(() => expect(mocks.refresh).toHaveBeenCalledTimes(3));
    const inputs = mocks.createJob.mock.calls.map(([input]) => input);
    expect(new Set(inputs.map((input) => input.submissionKey)).size).toBe(3);
    expect(new Set(inputs.map((input) => input.file)).size).toBe(3);
    expect(inputs.map((input) => input.endSec)).toEqual([30, 20, 30]);
  });

  it("allows only one in-flight submission even before React updates the button", async () => {
    let finishClip!: (file: File) => void;
    mocks.createClipFile.mockImplementation(() => new Promise<File>((resolve) => { finishClip = resolve; }));
    render(<TranscribeClient />);
    await prepareUpload();
    const submit = screen.getByRole("button", { name: "创建转录任务" });
    act(() => { fireEvent.click(submit); fireEvent.click(submit); });
    expect(mocks.createClipFile).toHaveBeenCalledTimes(1);
    await act(async () => { finishClip(new File(["clip"], "clip.wav")); });
    expect(mocks.createJob).toHaveBeenCalledTimes(1);
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
