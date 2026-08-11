"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useRouter } from "@/i18n/navigation";
import { deleteJob, getJob, JobsApiError, retryJob, type TranscriptionJob } from "@/lib/api/jobs";
import { localizeError, localizeJobError } from "@/lib/i18n/errors";
import { ResultClient } from "./result-client";

const POLL_MS = 2_500;
const SLOW_MS = 10_000;
type ViewState = { status: "loading" } | { status: "ready"; job: TranscriptionJob } | { status: "unavailable" } | { status: "error"; message: string };

export function JobStatusClient({ jobId }: { jobId: string }) {
  const router = useRouter();
  const t = useTranslations("job");
  const errors = useTranslations("errors");
  const [view, setView] = useState<ViewState>({ status: "loading" });
  const [action, setAction] = useState<"idle" | "retrying" | "deleting">("idle");
  const [slow, setSlow] = useState(false);
  const slowTimerRef = useRef<number | undefined>(undefined);
  const progressRef = useRef<string | undefined>(undefined);
  const terminalRef = useRef(false);
  const stageCopy: Record<TranscriptionJob["stage"], string> = {
    upload: t("stageUpload"), queued: t("stageQueued"), preprocessing: t("stagePreprocessing"),
    transcribing: t("stageTranscribing"), score: t("stageScore"), completed: t("stageCompleted"),
  };

  const restartSlowTimer = useCallback(() => {
    setSlow(false);
    window.clearTimeout(slowTimerRef.current);
    slowTimerRef.current = window.setTimeout(() => setSlow(true), SLOW_MS);
  }, []);
  const load = useCallback(async (signal?: AbortSignal) => {
    try {
      const job = await getJob(jobId, signal);
      setView({ status: "ready", job });
      if (job.status === "succeeded" || job.status === "failed") {
        terminalRef.current = true;
        window.clearTimeout(slowTimerRef.current);
        setSlow(false);
      } else {
        const progress = `${job.status}:${job.stage}:${job.updated_at}`;
        if (progressRef.current !== progress) { progressRef.current = progress; restartSlowTimer(); }
      }
    } catch (error) {
      if (signal?.aborted) return;
      if (error instanceof JobsApiError && error.status === 404) setView({ status: "unavailable" });
      else setView({ status: "error", message: localizeError(error, errors) });
    }
  }, [errors, jobId, restartSlowTimer]);

  useEffect(() => {
    const controller = new AbortController();
    const initialLoad = window.setTimeout(() => void load(controller.signal), 0);
    const poll = window.setInterval(() => { if (!terminalRef.current) void load(controller.signal); }, POLL_MS);
    slowTimerRef.current = window.setTimeout(() => setSlow(true), SLOW_MS);
    return () => { controller.abort(); window.clearTimeout(initialLoad); window.clearInterval(poll); window.clearTimeout(slowTimerRef.current); };
  }, [load]);

  const retry = async () => {
    setAction("retrying");
    try {
      const job = await retryJob(jobId);
      terminalRef.current = false; progressRef.current = undefined; restartSlowTimer(); setView({ status: "ready", job });
    } catch (error) { setView({ status: "error", message: localizeError(error, errors) }); }
    finally { setAction("idle"); }
  };
  const remove = async () => {
    if (!window.confirm(t("deleteConfirm"))) return;
    setAction("deleting");
    try { await deleteJob(jobId); router.replace("/transcribe?deleted=1"); }
    catch (error) { setView({ status: "error", message: localizeError(error, errors) }); setAction("idle"); }
  };

  if (view.status === "loading") return <MessageCard title={t("loadingTitle")} body={t("loadingBody")} />;
  if (view.status === "unavailable") return <MessageCard title={t("unavailableTitle")} body={t("unavailableBody")}><Link className="mt-5 inline-flex rounded-full bg-[#147d70] px-5 py-3 font-bold text-white" href="/transcribe">{t("resubmit")}</Link></MessageCard>;
  if (view.status === "error") return <MessageCard title={t("readFailedTitle")} body={view.message}><button className="mt-5 rounded-full bg-[#147d70] px-5 py-3 font-bold text-white" type="button" onClick={() => void load()}>{t("reload")}</button></MessageCard>;

  const { job } = view;
  if (job.status === "succeeded") return <ResultClient job={job} deleting={action === "deleting"} onDelete={() => void remove()} />;
  const noNotes = job.status === "failed" && job.error_code === "NO_NOTES_DETECTED";
  const deletionFailed = job.status === "failed" && job.error_code === "DELETE_FAILED";
  const headline = deletionFailed ? t("deleteIncomplete") : noNotes ? t("noNotes") : job.status === "failed" ? t("transcriptionIncomplete") : stageCopy[job.stage];
  const description = deletionFailed ? t("deleteDescription") : noNotes ? t("noNotesDescription") : job.status === "failed" ? t("failedDescription") : t("runningDescription");
  return (
    <section className="max-w-3xl">
      <p className="text-xs font-bold uppercase text-[#147d70]">{t("eyebrow")}</p>
      <h1 className="mt-3 font-display text-4xl leading-tight sm:text-5xl">{headline}</h1>
      <p className="mt-4 leading-7 text-[#61716c]">{description}</p>
      <div className="mt-8 rounded-lg border border-[#d9e3dd] bg-white p-6 shadow-[var(--shadow)] sm:p-8">
        <div className="flex flex-wrap items-center justify-between gap-3"><span className="rounded-full bg-[#e2f0eb] px-3 py-1.5 text-sm font-bold text-[#075e55]">{job.status === "failed" ? t("processingFailed") : stageCopy[job.stage]}</span><span className="text-sm text-[#667772]">{t("attempt", { count: job.attempt_count })}</span></div>
        <dl className="mt-6 grid gap-4 sm:grid-cols-2"><JobFact label={t("excerpt")} value={t("secondsRange", { start: job.start_sec.toFixed(2), end: job.end_sec.toFixed(2) })} /><JobFact label={t("source")} value={t("localSource")} /></dl>
        {slow && job.status !== "failed" && <p role="status" className="mt-6 rounded-lg bg-[#fff8df] p-4 text-sm leading-6 text-[#705c20]">{t("slow")}</p>}
        {job.status === "failed" && <div role="alert" className="mt-6 rounded-lg border border-[#e4b9b3] bg-[#fff1ef] p-4 text-[#8d372f]"><p className="font-bold">{localizeJobError(job.error_code, errors)}</p>{noNotes && <p className="mt-3 text-sm leading-6">{t("noNotesAdvice")}</p>}{!deletionFailed && job.attempt_count < 3 && <button type="button" disabled={action !== "idle"} onClick={retry} className="mt-4 rounded-full bg-[#8d372f] px-4 py-2 text-sm font-bold text-white disabled:opacity-50">{action === "retrying" ? t("retrying") : t("retry")}</button>}</div>}
        <div className="mt-8 border-t border-[#e1e7e2] pt-5"><button type="button" disabled={action !== "idle"} onClick={remove} className="text-sm font-bold text-[#9a493f] underline underline-offset-4 disabled:opacity-50">{action === "deleting" ? t("deleting") : deletionFailed ? t("continueDelete") : t("delete")}</button></div>
      </div>
    </section>
  );
}

function JobFact({ label, value }: { label: string; value: string }) { return <div className="rounded-lg bg-[#f3f6f3] p-4"><dt className="text-xs font-bold uppercase text-[#75837f]">{label}</dt><dd className="mt-1 font-bold text-[#15332f]">{value}</dd></div>; }
function MessageCard({ title, body, children }: { title: string; body: string; children?: React.ReactNode }) { return <section className="max-w-3xl rounded-lg border border-[#d9e3dd] bg-white p-7 shadow-[var(--shadow)]"><h1 className="font-display text-3xl font-bold">{title}</h1><p className="mt-3 leading-7 text-[#61716c]">{body}</p>{children}</section>; }
