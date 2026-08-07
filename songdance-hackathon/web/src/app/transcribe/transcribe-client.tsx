"use client";

import { useRouter } from "next/navigation";
import { useCallback, useRef, useState } from "react";
import { Upload, Video } from "lucide-react";
import { AudioDropzone } from "@/components/audio/audio-dropzone";
import { RightsConfirmation } from "@/components/audio/rights-confirmation";
import { WaveformTrimmer } from "@/components/audio/waveform-trimmer";
import { YoutubeInput } from "@/components/audio/youtube-input";
import { clipDuration, createDefaultClip, type AudioClip } from "@/lib/audio/clip";
import { createClipFile } from "@/lib/audio/clip-file";
import { inspectAudioFile, type AudioInspection } from "@/lib/audio/validation";
import { createJob, sendUploadStartedEvent } from "@/lib/api/jobs";

type InspectionState =
  | { status: "empty" }
  | { status: "loading"; file: File }
  | { status: "error"; message: string }
  | { status: "ready"; file: File; inspection: AudioInspection };

type SubmitState =
  | { status: "idle" }
  | { status: "submitting" }
  | { status: "error"; message: string };

export function TranscribeClient() {
  const router = useRouter();
  const requestIdRef = useRef(0);
  const [inspectionState, setInspectionState] = useState<InspectionState>({ status: "empty" });
  const [clip, setClip] = useState<AudioClip | null>(null);
  const [rightsConfirmed, setRightsConfirmed] = useState(false);
  const [submitState, setSubmitState] = useState<SubmitState>({ status: "idle" });
  const [inputMode, setInputMode] = useState<"upload" | "youtube">("upload");

  const selectFile = async (file: File) => {
    const requestId = ++requestIdRef.current;
    setInspectionState({ status: "loading", file });
    setClip(null);
    setRightsConfirmed(false);
    setSubmitState({ status: "idle" });
    const result = await inspectAudioFile(file);
    if (requestId !== requestIdRef.current) return;
    if (!result.ok) {
      setInspectionState({ status: "error", message: result.error });
      return;
    }
    setClip(createDefaultClip(result.value.duration));
    setInspectionState({ status: "ready", file, inspection: result.value });
  };

  const updateClip = useCallback((nextClip: AudioClip) => {
    setClip(nextClip);
    setSubmitState({ status: "idle" });
  }, []);

  const showWaveformError = useCallback((message: string) => {
    setInspectionState({ status: "error", message });
    setClip(null);
    setSubmitState({ status: "idle" });
  }, []);

  const submitJob = async () => {
    if (inspectionState.status !== "ready" || !clip || !rightsConfirmed) return;
    setSubmitState({ status: "submitting" });
    try {
      const clippedFile = await createClipFile(inspectionState.file, clip);
      await sendUploadStartedEvent().catch(() => undefined);
      const job = await createJob({
        file: clippedFile,
        startSec: 0,
        endSec: clipDuration(clip),
        rightsConfirmed,
      });
      router.push(`/jobs/${job.id}`);
    } catch (error) {
      setSubmitState({
        status: "error",
        message: error instanceof Error ? error.message : "任务创建失败，请重试。",
      });
    }
  };

  const ready = inspectionState.status === "ready" && clip;
  const submitting = submitState.status === "submitting";

  return (
    <div className="mt-10 grid gap-6">
      <div className="flex w-fit rounded-md border border-[#cad8d2] bg-white p-0.5"
        role="tablist" aria-label="音频来源">
        <ModeTab active={inputMode === "upload"} icon={<Upload size={16} />}
          label="本地上传" onClick={() => setInputMode("upload")} />
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
          title="正在检查音频"
          body="验证文件签名并读取时长，通常几秒内完成。"
        />
      )}
      {inspectionState.status === "error" && (
        <StatusCard tone="error" title="这个文件不能使用" body={inspectionState.message} />
      )}

      {ready && (
        <>
          <div className="flex flex-wrap gap-2 text-sm font-semibold text-[#52635f]">
            <span className="rounded-full bg-[#e5eee9] px-3 py-1.5">
              {inspectionState.inspection.format.toUpperCase()}
            </span>
            <span className="rounded-full bg-[#e5eee9] px-3 py-1.5">
              总时长 {inspectionState.inspection.duration.toFixed(2)} 秒
            </span>
            <span className="rounded-full bg-[#e5eee9] px-3 py-1.5">
              本次 {clipDuration(clip).toFixed(2)} 秒
            </span>
          </div>
          <WaveformTrimmer
            file={inspectionState.file}
            duration={inspectionState.inspection.duration}
            clip={clip}
            disabled={submitting}
            onChange={updateClip}
            onError={showWaveformError}
          />
          <RightsConfirmation
            checked={rightsConfirmed}
            disabled={submitting}
            onChange={setRightsConfirmed}
          />
          {submitState.status === "error" && (
            <StatusCard tone="error" title="任务创建失败" body={submitState.message} />
          )}
          <div>
            <button
              type="button"
              disabled={!rightsConfirmed || submitting}
              aria-describedby={!rightsConfirmed ? "rights-required" : undefined}
              onClick={submitJob}
              className="w-full rounded-full bg-[#147d70] px-6 py-3.5 font-bold text-white transition hover:bg-[#075e55] disabled:cursor-not-allowed disabled:bg-[#9aaba6] sm:w-auto"
            >
              {submitting ? "正在创建任务…" : "创建转录任务"}
            </button>
            {!rightsConfirmed && (
              <p id="rights-required" className="mt-2 text-sm text-[#9a493f]">
                确认内容权利后才能继续。
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
