import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { TranscriptionJob } from "@/lib/api/jobs";
import { JobStatusClient } from "./job-status-client";

const mocks = vi.hoisted(() => ({
  getJob: vi.fn(),
  retryJob: vi.fn(),
  deleteJob: vi.fn(),
  replace: vi.fn(),
}));

vi.mock("@/i18n/navigation", () => ({
  Link: ({ href, children }: { href: string; children: React.ReactNode }) => <a href={href}>{children}</a>,
  useRouter: () => ({ replace: mocks.replace }),
}));
vi.mock("./result-client", () => ({
  ResultClient: ({ job }: { job: TranscriptionJob }) => <div>结果工作台 {job.id}</div>,
}));

vi.mock("@/lib/api/jobs", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/lib/api/jobs")>();
  return {
    ...original,
    getJob: mocks.getJob,
    retryJob: mocks.retryJob,
    deleteJob: mocks.deleteJob,
  };
});

const queuedJob: TranscriptionJob = {
  id: "secure-job-id",
  status: "queued",
  stage: "queued",
  source_type: "upload",
  start_sec: 0,
  end_sec: 30,
  attempt_count: 1,
  error_code: null,
  error_message: null,
  created_at: "2026-07-28T00:00:00Z",
  updated_at: "2026-07-28T00:00:00Z",
  expires_at: "2026-07-29T00:00:00Z",
  result: null,
  quality_report: null,
  artifacts: [],
};

describe("job status", () => {
  beforeEach(() => {
    mocks.getJob.mockReset();
    mocks.retryJob.mockReset();
    mocks.deleteJob.mockReset();
    mocks.replace.mockReset();
    mocks.getJob.mockResolvedValue(queuedJob);
    mocks.deleteJob.mockResolvedValue(undefined);
    vi.spyOn(window, "confirm").mockReturnValue(true);
  });

  it("restores a queued job by id without creating another task", async () => {
    render(<JobStatusClient jobId="secure-job-id" />);

    expect(await screen.findByRole("heading", { name: "等待处理" })).toBeInTheDocument();
    expect(screen.getByText("0.00–30.00 秒")).toBeInTheDocument();
    expect(mocks.getJob).toHaveBeenCalledWith("secure-job-id", expect.any(AbortSignal));
  });

  it("shows an honest still-processing hint after ten seconds", async () => {
    vi.useFakeTimers();
    try {
      render(<JobStatusClient jobId="secure-job-id" />);
      await act(() => vi.advanceTimersByTimeAsync(0));
      expect(screen.getByRole("heading", { name: "等待处理" })).toBeInTheDocument();

      await act(() => vi.advanceTimersByTimeAsync(10_000));
      expect(screen.getByRole("status")).toHaveTextContent("当前排队时间比平常久");
    } finally {
      vi.useRealTimers();
    }
  });

  it("restarts the ten-second clock when real progress arrives", async () => {
    vi.useFakeTimers();
    try {
      render(<JobStatusClient jobId="secure-job-id" />);
      await act(() => vi.advanceTimersByTimeAsync(0));
      await act(() => vi.advanceTimersByTimeAsync(5_000));
      mocks.getJob.mockResolvedValue({
        ...queuedJob,
        status: "running",
        stage: "preprocessing",
        updated_at: "2026-07-28T00:00:07Z",
      });
      await act(() => vi.advanceTimersByTimeAsync(2_500));
      expect(screen.getByRole("heading", { name: "正在清理和分析音频" })).toBeInTheDocument();

      await act(() => vi.advanceTimersByTimeAsync(2_500));
      expect(screen.queryByText("当前排队时间比平常久")).not.toBeInTheDocument();
      await act(() => vi.advanceTimersByTimeAsync(7_500));
      expect(screen.getByRole("status")).toHaveTextContent("当前排队时间比平常久");
    } finally {
      vi.useRealTimers();
    }
  });

  it("stops polling after the task reaches a terminal result", async () => {
    vi.useFakeTimers();
    try {
      mocks.getJob.mockResolvedValue({
        ...queuedJob,
        status: "succeeded",
        stage: "completed",
        result: {
          tempo: 120,
          time_signature: "4/4",
          note_count: 20,
          quality_flags: "[]",
          model_version: "test",
        },
      });
      render(<JobStatusClient jobId="secure-job-id" />);
      await act(() => vi.advanceTimersByTimeAsync(0));
      expect(screen.getByText(/结果工作台/)).toBeInTheDocument();

      await act(() => vi.advanceTimersByTimeAsync(5_000));
      expect(mocks.getJob).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it("retries a failed job and renders the returned queued state", async () => {
    const failedJob: TranscriptionJob = {
      ...queuedJob,
      status: "failed",
      error_code: "MODEL_FAILED",
      error_message: "模型处理失败",
    };
    mocks.getJob.mockResolvedValue(failedJob);
    mocks.retryJob.mockResolvedValue({ ...queuedJob, attempt_count: 2 });
    const user = userEvent.setup();
    render(<JobStatusClient jobId="secure-job-id" />);

    expect(await screen.findByRole("heading", { name: "转录未完成" })).toBeInTheDocument();
    expect(screen.getByText(/任务已停止/)).toBeInTheDocument();
    expect(screen.queryByText("MODEL_FAILED")).not.toBeInTheDocument();
    expect(screen.queryByText("模型处理失败")).not.toBeInTheDocument();
    expect(screen.queryByText(/任务会在后台继续/)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "重试任务" }));

    await waitFor(() => expect(mocks.retryJob).toHaveBeenCalledWith("secure-job-id"));
    expect(screen.getByText("第 2 次尝试")).toBeInTheDocument();
  });

  it("gives actionable input advice when no notes are detected", async () => {
    mocks.getJob.mockResolvedValue({
      ...queuedJob,
      status: "failed",
      error_code: "NO_NOTES_DETECTED",
      error_message: "没有检测到可用的钢琴音符",
    });
    render(<JobStatusClient jobId="secure-job-id" />);

    expect(
      await screen.findByRole("heading", { name: "没有检测到钢琴音符" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("避开长静音、鼓声和人声");
    expect(screen.getByRole("alert")).toHaveTextContent("至少 1 秒的独奏钢琴片段");
  });

  it("offers only deletion recovery after a partial delete failure", async () => {
    mocks.getJob.mockResolvedValue({
      ...queuedJob,
      status: "failed",
      error_code: "DELETE_FAILED",
      error_message: "部分文件删除失败，请重试删除",
    });
    render(<JobStatusClient jobId="secure-job-id" />);

    expect(await screen.findByRole("heading", { name: "删除未完成" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "重试任务" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "继续删除音频和任务" })).toBeInTheDocument();
  });

  it("confirms immediate deletion and leaves the expired URL", async () => {
    const user = userEvent.setup();
    render(<JobStatusClient jobId="secure-job-id" />);

    await user.click(await screen.findByRole("button", { name: "立即删除音频和任务" }));

    await waitFor(() => expect(mocks.deleteJob).toHaveBeenCalledWith("secure-job-id"));
    expect(mocks.replace).toHaveBeenCalledWith("/transcribe?deleted=1");
  });
});
