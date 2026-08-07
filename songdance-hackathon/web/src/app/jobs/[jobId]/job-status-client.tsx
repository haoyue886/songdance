"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  deleteJob,
  getJob,
  JobsApiError,
  retryJob,
  type TranscriptionJob,
} from "@/lib/api/jobs";
import { ResultClient } from "./result-client";

const POLL_MS = 2_500;
const SLOW_MS = 10_000;

const STAGE_COPY: Record<TranscriptionJob["stage"], string> = {
  upload: "正在接收音频",
  queued: "等待处理",
  preprocessing: "正在清理和分析音频",
  transcribing: "正在识别钢琴音符",
  score: "正在生成乐谱",
  completed: "转录完成",
};

type ViewState =
  | { status: "loading" }
  | { status: "ready"; job: TranscriptionJob }
  | { status: "unavailable" }
  | { status: "error"; message: string };

export function JobStatusClient({ jobId }: { jobId: string }) {
  const router = useRouter();
  const [view, setView] = useState<ViewState>({ status: "loading" });
  const [action, setAction] = useState<"idle" | "retrying" | "deleting">("idle");
  const [slow, setSlow] = useState(false);
  const slowTimerRef = useRef<number | undefined>(undefined);
  const progressRef = useRef<string | undefined>(undefined);
  const terminalRef = useRef(false);

  const restartSlowTimer = useCallback(() => {
    setSlow(false);
    window.clearTimeout(slowTimerRef.current);
    slowTimerRef.current = window.setTimeout(() => setSlow(true), SLOW_MS);
  }, []);

  const load = useCallback(
    async (signal?: AbortSignal) => {
      try {
        const job = await getJob(jobId, signal);
        setView({ status: "ready", job });
        if (job.status === "succeeded" || job.status === "failed") {
          terminalRef.current = true;
          window.clearTimeout(slowTimerRef.current);
          setSlow(false);
        } else {
          const progress = `${job.status}:${job.stage}:${job.updated_at}`;
          if (progressRef.current !== progress) {
            progressRef.current = progress;
            restartSlowTimer();
          }
        }
      } catch (error) {
        if (signal?.aborted) return;
        if (error instanceof JobsApiError && error.status === 404) {
          setView({ status: "unavailable" });
          return;
        }
        setView({
          status: "error",
          message: error instanceof Error ? error.message : "无法读取任务状态。",
        });
      }
    },
    [jobId, restartSlowTimer],
  );

  useEffect(() => {
    const controller = new AbortController();
    const initialLoad = window.setTimeout(() => void load(controller.signal), 0);
    const poll = window.setInterval(() => {
      if (!terminalRef.current) void load(controller.signal);
    }, POLL_MS);
    slowTimerRef.current = window.setTimeout(() => setSlow(true), SLOW_MS);
    return () => {
      controller.abort();
      window.clearTimeout(initialLoad);
      window.clearInterval(poll);
      window.clearTimeout(slowTimerRef.current);
    };
  }, [load]);

  const retry = async () => {
    setAction("retrying");
    try {
      const job = await retryJob(jobId);
      terminalRef.current = false;
      progressRef.current = undefined;
      restartSlowTimer();
      setView({ status: "ready", job });
    } catch (error) {
      setView({
        status: "error",
        message: error instanceof Error ? error.message : "任务重试失败。",
      });
    } finally {
      setAction("idle");
    }
  };

  const remove = async () => {
    if (!window.confirm("立即删除后，音频和任务记录将无法恢复。确定删除吗？")) return;
    setAction("deleting");
    try {
      await deleteJob(jobId);
      router.replace("/transcribe?deleted=1");
    } catch (error) {
      setView({
        status: "error",
        message: error instanceof Error ? error.message : "任务删除失败。",
      });
      setAction("idle");
    }
  };

  if (view.status === "loading") {
    return <MessageCard title="正在恢复任务" body="正在读取最新状态，不会重复上传音频。" />;
  }
  if (view.status === "unavailable") {
    return (
      <MessageCard title="任务不可用" body="这个任务不存在、已删除或已过期。">
        <Link
          className="mt-5 inline-flex rounded-full bg-[#147d70] px-5 py-3 font-bold text-white"
          href="/transcribe"
        >
          重新提交音频
        </Link>
      </MessageCard>
    );
  }
  if (view.status === "error") {
    return (
      <MessageCard title="暂时无法读取任务" body={view.message}>
        <button
          className="mt-5 rounded-full bg-[#147d70] px-5 py-3 font-bold text-white"
          type="button"
          onClick={() => void load()}
        >
          重新加载
        </button>
      </MessageCard>
    );
  }

  const { job } = view;
  if (job.status === "succeeded") {
    return (
      <ResultClient
        job={job}
        deleting={action === "deleting"}
        onDelete={() => void remove()}
      />
    );
  }
  const noNotes = job.status === "failed" && job.error_code === "NO_NOTES_DETECTED";
  const deletionFailed = job.status === "failed" && job.error_code === "DELETE_FAILED";
  const headline = deletionFailed
    ? "删除未完成"
    : noNotes
    ? "没有检测到钢琴音符"
    : job.status === "failed"
      ? "转录未完成"
      : STAGE_COPY[job.stage];
  const description =
    deletionFailed
      ? "部分临时文件仍未删除。请继续删除；这个状态不能重试转录。"
      : noNotes
      ? "这个片段没有形成可用音符。换一个钢琴更清晰、音量更稳定的片段后重新提交。"
      : job.status === "failed"
      ? "任务已停止。你可以查看错误后重试，或立即删除音频和任务记录。"
      : "任务会在后台继续；保存当前网址，关闭或刷新页面都不会重复执行。";
  return (
    <section className="max-w-3xl">
      <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#147d70]">
        Transcription job
      </p>
      <h1 className="mt-3 font-display text-4xl leading-tight tracking-[-0.04em] sm:text-5xl">
        {headline}
      </h1>
      <p className="mt-4 leading-7 text-[#61716c]">{description}</p>

      <div className="mt-8 rounded-3xl border border-[#d9e3dd] bg-white p-6 shadow-[var(--shadow)] sm:p-8">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <span className="rounded-full bg-[#e2f0eb] px-3 py-1.5 text-sm font-bold text-[#075e55]">
            {job.status === "failed" ? "处理失败" : STAGE_COPY[job.stage]}
          </span>
          <span className="text-sm text-[#667772]">第 {job.attempt_count} 次尝试</span>
        </div>
        <dl className="mt-6 grid gap-4 sm:grid-cols-2">
          <JobFact
            label="转录片段"
            value={`${job.start_sec.toFixed(2)}–${job.end_sec.toFixed(2)} 秒`}
          />
          <JobFact label="来源" value="本地音频片段" />
        </dl>

        {slow && job.status !== "failed" && (
          <p
            role="status"
            className="mt-6 rounded-2xl bg-[#fff8df] p-4 text-sm leading-6 text-[#705c20]"
          >
            当前排队时间比平常久。任务仍在后台，不需要重新上传；你可以稍后刷新这个网址。
          </p>
        )}
        {job.status === "failed" && (
          <div
            role="alert"
            className="mt-6 rounded-2xl border border-[#e4b9b3] bg-[#fff1ef] p-4 text-[#8d372f]"
          >
            <p className="font-bold">{job.error_message ?? "转录没有完成"}</p>
            <p className="mt-1 text-sm">错误码：{job.error_code ?? "UNKNOWN"}</p>
            {noNotes && (
              <p className="mt-3 text-sm leading-6">
                建议避开长静音、鼓声和人声，选择至少 1 秒的独奏钢琴片段，并确认录音音量可听。
              </p>
            )}
            {!deletionFailed && job.attempt_count < 3 && (
              <button
                type="button"
                disabled={action !== "idle"}
                onClick={retry}
                className="mt-4 rounded-full bg-[#8d372f] px-4 py-2 text-sm font-bold text-white disabled:opacity-50"
              >
                {action === "retrying" ? "正在重试…" : "重试任务"}
              </button>
            )}
          </div>
        )}

        <div className="mt-8 border-t border-[#e1e7e2] pt-5">
          <button
            type="button"
            disabled={action !== "idle"}
            onClick={remove}
            className="text-sm font-bold text-[#9a493f] underline decoration-[#d7aaa4] underline-offset-4 disabled:opacity-50"
          >
            {action === "deleting"
              ? "正在删除…"
              : deletionFailed
                ? "继续删除音频和任务"
                : "立即删除音频和任务"}
          </button>
        </div>
      </div>
    </section>
  );
}

function JobFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl bg-[#f3f6f3] p-4">
      <dt className="text-xs font-bold uppercase tracking-[0.12em] text-[#75837f]">{label}</dt>
      <dd className="mt-1 font-bold text-[#15332f]">{value}</dd>
    </div>
  );
}

function MessageCard({
  title,
  body,
  children,
}: {
  title: string;
  body: string;
  children?: React.ReactNode;
}) {
  return (
    <section className="max-w-3xl rounded-3xl border border-[#d9e3dd] bg-white p-7 shadow-[var(--shadow)]">
      <h1 className="font-display text-3xl font-bold">{title}</h1>
      <p className="mt-3 leading-7 text-[#61716c]">{body}</p>
      {children}
    </section>
  );
}
