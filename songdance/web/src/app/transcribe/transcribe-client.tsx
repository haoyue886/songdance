"use client";

import { useLocale, useTranslations } from "next-intl";
import { useCallback, useRef, useState } from "react";
import { Upload, Video } from "lucide-react";
import { AudioDropzone } from "@/components/audio/audio-dropzone";
import { RightsConfirmation } from "@/components/audio/rights-confirmation";
import { WaveformTrimmer } from "@/components/audio/waveform-trimmer";
import { YoutubeInput } from "@/components/audio/youtube-input";
import { clipDuration, createDefaultClip, type AudioClip } from "@/lib/audio/clip";
import { createClipFile } from "@/lib/audio/clip-file";
import { inspectAudioFile, type AudioInspection } from "@/lib/audio/validation";
import { createJob, JobsApiError, sendUploadStartedEvent } from "@/lib/api/jobs";
import { Link, useRouter } from "@/i18n/navigation";
import { localizeError } from "@/lib/i18n/errors";
import { useUploadBilling } from "@/components/billing/use-upload-billing";
import { estimatedSeconds } from "@/lib/api/billing";

type InspectionState =
  | { status: "empty" }
  | { status: "loading"; file: File }
  | { status: "error"; message: string }
  | { status: "ready"; file: File; inspection: AudioInspection };

type SubmitState =
  | { status: "idle" }
  | { status: "submitting" }
  | { status: "error"; message: string; canReplay: boolean };

type SubmissionDraft = {
  file: File;
  clip: AudioClip;
  key: string;
  clippedFile?: File;
};

export function TranscribeClient() {
  const router = useRouter();
  const locale = useLocale();
  const t = useTranslations("transcribe");
  const errors = useTranslations("errors");
  const billing = useTranslations("billing");
  const usage = useUploadBilling();
  const requestIdRef = useRef(0);
  const submissionRef = useRef<SubmissionDraft | null>(null);
  const submittingRef = useRef(false);
  const [inspectionState, setInspectionState] = useState<InspectionState>({ status: "empty" });
  const [clip, setClip] = useState<AudioClip | null>(null);
  const [rightsConfirmed, setRightsConfirmed] = useState(false);
  const [submitState, setSubmitState] = useState<SubmitState>({ status: "idle" });
  const [inputMode, setInputMode] = useState<"upload" | "youtube">("upload");

  const selectFile = async (file: File) => {
    if (submittingRef.current) return;
    submissionRef.current = null;
    const requestId = ++requestIdRef.current;
    setInspectionState({ status: "loading", file });
    setClip(null);
    setRightsConfirmed(false);
    setSubmitState({ status: "idle" });
    const result = await inspectAudioFile(file);
    if (requestId !== requestIdRef.current) return;
    if (!result.ok) {
      setInspectionState({ status: "error", message: locale === "zh" ? result.error : errors("invalidInput") });
      return;
    }
    setClip(createDefaultClip(result.value.duration));
    setInspectionState({ status: "ready", file, inspection: result.value });
  };

  const updateClip = useCallback((nextClip: AudioClip) => {
    if (submittingRef.current) return;
    const draft = submissionRef.current;
    if (draft && draft.clip.start === nextClip.start && draft.clip.end === nextClip.end) return;
    submissionRef.current = null;
    setClip(nextClip);
    setSubmitState({ status: "idle" });
  }, []);

  const showWaveformError = useCallback((message: string) => {
    submissionRef.current = null;
    setInspectionState({ status: "error", message });
    setClip(null);
    setSubmitState({ status: "idle" });
  }, []);

  const submitJob = async () => {
    if (submittingRef.current || inspectionState.status !== "ready" || !clip || !rightsConfirmed) return;
    submittingRef.current = true;
    setSubmitState({ status: "submitting" });
    let createStarted = false;
    try {
      const draft = submissionRef.current ??= {
        file: inspectionState.file,
        clip: { ...clip },
        key: crypto.randomUUID(),
      };
      draft.clippedFile ??= await createClipFile(draft.file, draft.clip);
      await sendUploadStartedEvent().catch(() => undefined);
      createStarted = true;
      const job = await createJob({
        file: draft.clippedFile,
        submissionKey: draft.key,
        startSec: 0,
        endSec: clipDuration(draft.clip),
        rightsConfirmed,
      });
      router.push(`/jobs/${job.id}`);
    } catch (error) {
      submittingRef.current = false;
      setSubmitState({
        status: "error",
        message: localizeError(error, errors),
        canReplay: createStarted && error instanceof JobsApiError && (error.status === 0 || error.status === 408 || error.status >= 500),
      });
      usage.refresh();
    }
  };

  const ready = inspectionState.status === "ready" && clip;
  const submitting = submitState.status === "submitting";
  const length = clip ? clipDuration(clip) : 0;
  const metered = usage.data?.config.usage_enabled;
  const summary = usage.data?.summary;
  const estimate = usage.data ? estimatedSeconds(length, usage.data.config) : 0;
  const exhausted = metered && summary?.enabled && (summary.remaining ?? 0) < (summary.unit === "seconds" ? estimate : 1);
  const suspended = summary?.sync_state === "review_required" || summary?.state === "frozen" || summary?.state === "revoked";
  const overLimit = length > usage.maxSeconds;
  // Replaying the unchanged request can recover a job that already reserved quota.
  // Any file/clip change clears this exception; the server still checks new jobs.
  const canReplay = submitState.status === "error" && submitState.canReplay;

  return (
    <div className="mt-10 grid gap-6">
      <div className="flex w-fit rounded-md border border-[#cad8d2] bg-white p-0.5"
        role="tablist" aria-label={t("sourceLabel")}>
        <ModeTab active={inputMode === "upload"} icon={<Upload size={16} />}
          label={t("localUpload")} onClick={() => setInputMode("upload")} />
        <ModeTab active={inputMode === "youtube"} icon={<Video size={16} />}
          label="YouTube" onClick={() => setInputMode("youtube")} />
      </div>
      {inputMode === "youtube" ? (
        <YoutubeInput onUseUpload={() => setInputMode("upload")} />
      ) : (
        <>
      <AudioDropzone
        disabled={inspectionState.status === "loading" || submitting}
        fileName={
          inspectionState.status === "ready" || inspectionState.status === "loading"
            ? inspectionState.file.name
            : undefined
        }
        onFile={selectFile}
      />

      {inspectionState.status === "loading" && (
        <StatusCard
          tone="neutral"
          title={t("checkingTitle")}
          body={t("checkingBody")}
        />
      )}
      {inspectionState.status === "error" && (
        <StatusCard tone="error" title={t("invalidTitle")} body={inspectionState.message} />
      )}

      {ready && (
        <>
          {(usage.pending || usage.failed) && <p role="status" className="text-sm text-[#64736f]">{billing(usage.failed ? "loadError" : "loading")}{usage.failed && <button type="button" className="ml-3 font-semibold underline" onClick={usage.refresh}>{billing("refresh")}</button>}</p>}
          {metered && <div className="border-y border-[#dce3dc] py-4 text-sm leading-6">
            <p className="font-semibold">{summary?.plan === "pro" ? billing("estimateSeconds", { seconds: estimate }) : summary ? billing("estimateJobs") : billing("clipLimit", { seconds: usage.maxSeconds })}</p>
            {summary?.enabled && <p className="mt-1 text-[#64736f]">{summary.unit === "seconds" ? billing("remainingSeconds", { seconds: summary.remaining ?? 0 }) : billing("remainingJobs", { count: summary.remaining ?? 0 })}</p>}
            <p className="mt-2 text-[#64736f]">{billing("partialFormats")}</p>
            {!summary && <Link href={`/login?return_to=${encodeURIComponent(`${locale === "en" ? "" : `/${locale}`}/transcribe`)}`} className="mt-2 inline-block font-semibold text-[#075e55] underline">{billing("signIn")}</Link>}
          </div>}
          {(overLimit || exhausted || suspended) && <p role="alert" className="text-sm text-[#9a493f]">{billing(suspended ? "reviewRequired" : overLimit ? "clipLimit" : "balanceEmpty", { seconds: usage.maxSeconds })}</p>}
          <div className="flex flex-wrap gap-2 text-sm font-semibold text-[#52635f]">
            <span className="rounded-full bg-[#e5eee9] px-3 py-1.5">
              {inspectionState.inspection.format.toUpperCase()}
            </span>
            <span className="rounded-full bg-[#e5eee9] px-3 py-1.5">
              {t("totalDuration", { seconds: inspectionState.inspection.duration.toFixed(2) })}
            </span>
            <span className="rounded-full bg-[#e5eee9] px-3 py-1.5">
              {t("clipDuration", { seconds: clipDuration(clip).toFixed(2) })}
            </span>
          </div>
          <WaveformTrimmer
            file={inspectionState.file}
            duration={inspectionState.inspection.duration}
            clip={clip}
            disabled={submitting}
            maxClipSeconds={usage.maxSeconds}
            onChange={updateClip}
            onError={showWaveformError}
          />
          <RightsConfirmation
            checked={rightsConfirmed}
            disabled={submitting}
            onChange={setRightsConfirmed}
          />
          {submitState.status === "error" && (
            <StatusCard tone="error" title={t("createFailed")} body={submitState.message} />
          )}
          <div>
            <button
              type="button"
              disabled={!rightsConfirmed || submitting || overLimit || Boolean(suspended) || (!canReplay && (usage.pending || usage.failed || Boolean(exhausted)))}
              aria-describedby={!rightsConfirmed ? "rights-required" : undefined}
              onClick={submitJob}
              className="w-full rounded-full bg-[#147d70] px-6 py-3.5 font-bold text-white transition hover:bg-[#075e55] disabled:cursor-not-allowed disabled:bg-[#9aaba6] sm:w-auto"
            >
              {submitting ? t("creating") : t("create")}
            </button>
            {!rightsConfirmed && (
              <p id="rights-required" className="mt-2 text-sm text-[#9a493f]">
                {t("rightsRequired")}
              </p>
            )}
          </div>
        </>
      )}
        </>
      )}
    </div>
  );
}

function ModeTab({ active, icon, label, onClick }: {
  active: boolean; icon: React.ReactNode; label: string; onClick: () => void;
}) {
  return (
    <button type="button" role="tab" aria-selected={active} onClick={onClick}
      className={`flex h-10 items-center gap-2 rounded px-4 text-sm font-bold ${
        active ? "bg-[#d9efe7] text-[#075e55]" : "text-[#667772]"
      }`}>
      {icon} {label}
    </button>
  );
}

function StatusCard({
  tone,
  title,
  body,
}: {
  tone: "neutral" | "error";
  title: string;
  body: string;
}) {
  const colors =
    tone === "error"
      ? "border-[#e4b9b3] bg-[#fff1ef] text-[#8d372f]"
      : "border-[#d9e3dd] bg-white text-[#52635f]";
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={`rounded-2xl border p-4 ${colors}`}
    >
      <p className="font-bold">{title}</p>
      <p className="mt-1 text-sm leading-6">{body}</p>
    </div>
  );
}
