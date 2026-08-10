"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { createYoutubeJob, getYoutubeConfig } from "@/lib/api/jobs";
import { RightsConfirmation } from "./rights-confirmation";

type Availability = "checking" | "enabled" | "disabled";

export function YoutubeInput({ onUseUpload }: { onUseUpload: () => void }) {
  const router = useRouter();
  const [availability, setAvailability] = useState<Availability>("checking");
  const [url, setUrl] = useState("");
  const [startSec, setStartSec] = useState(0);
  const [endSec, setEndSec] = useState(30);
  const [rightsConfirmed, setRightsConfirmed] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void getYoutubeConfig()
      .then((config) => {
        if (!cancelled) setAvailability(config.enabled ? "enabled" : "disabled");
      })
      .catch(() => {
        if (!cancelled) setAvailability("disabled");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const submit = async () => {
    if (availability !== "enabled" || !url || !rightsConfirmed || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const job = await createYoutubeJob({ url, startSec, endSec, rightsConfirmed });
      router.push(`/jobs/${job.id}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "YouTube 导入失败，请改用本地上传。");
    } finally {
      setSubmitting(false);
    }
  };

  if (availability === "checking") {
    return <p role="status" className="rounded-lg border border-[#d9e3dd] bg-white p-5 text-[#52635f]">
      正在检查 YouTube 导入能力…
    </p>;
  }
  if (availability === "disabled") {
    return (
      <div className="rounded-lg border border-[#d9e3dd] bg-white p-5">
        <p className="font-bold text-[#15332f]">YouTube 导入当前未开放</p>
        <p className="mt-2 text-sm leading-6 text-[#61716c]">
          本地上传不受影响。下载能力不可用时不会尝试绕过平台限制。
        </p>
        <button type="button" onClick={onUseUpload}
          className="mt-4 rounded-full bg-[#147d70] px-5 py-2.5 text-sm font-bold text-white">
          改用本地上传
        </button>
      </div>
    );
  }

  const clipLength = endSec - startSec;
  const clipValid = startSec >= 0 && clipLength >= 1 && clipLength <= 90;
  return (
    <div className="grid gap-5">
      <label className="grid gap-2 text-sm font-bold text-[#15332f]">
        YouTube 视频链接
        <input type="url" value={url} onChange={(event) => setUrl(event.currentTarget.value)}
          placeholder="https://www.youtube.com/watch?v=…" autoComplete="url"
          className="h-12 rounded-md border border-[#c8d8d2] bg-white px-4 font-normal outline-none focus:border-[#147d70]" />
      </label>
      <div className="grid gap-4 sm:grid-cols-2">
        <TimeInput label="开始秒数" value={startSec} onChange={setStartSec} />
        <TimeInput label="结束秒数" value={endSec} onChange={setEndSec} />
      </div>
      <p className={`text-sm ${clipValid ? "text-[#52635f]" : "text-[#9a493f]"}`}>
        当前片段 {Number.isFinite(clipLength) ? clipLength.toFixed(1) : "0.0"} 秒，必须在 1–90 秒之间。
      </p>
      <RightsConfirmation checked={rightsConfirmed} disabled={submitting}
        onChange={setRightsConfirmed} />
      {error && (
        <div role="alert" className="rounded-lg border border-[#e4b9b3] bg-[#fff1ef] p-4 text-sm text-[#8d372f]">
          <p>{error}</p>
          <button type="button" onClick={onUseUpload}
            className="mt-3 font-bold underline underline-offset-4">改用本地上传</button>
        </div>
      )}
      <button type="button" onClick={() => void submit()}
        disabled={!url || !rightsConfirmed || !clipValid || submitting}
        className="w-full rounded-full bg-[#147d70] px-6 py-3.5 font-bold text-white hover:bg-[#075e55] disabled:cursor-not-allowed disabled:bg-[#9aaba6] sm:w-fit">
        {submitting ? "正在获取所选片段…" : "导入并创建转录任务"}
      </button>
      <p className="text-xs leading-5 text-[#75837f]">
        仅处理公开视频的所选片段；私密、登录、地区、付费、直播或平台拒绝时会停止并提示上传文件。
      </p>
    </div>
  );
}

function TimeInput({ label, value, onChange }: {
  label: string; value: number; onChange: (value: number) => void;
}) {
  return (
    <label className="grid gap-2 text-sm font-bold text-[#15332f]">
      {label}
      <input type="number" min="0" step="0.1" value={value}
        onChange={(event) => onChange(event.currentTarget.valueAsNumber)}
        className="h-12 rounded-md border border-[#c8d8d2] bg-white px-4 font-normal outline-none focus:border-[#147d70]" />
    </label>
  );
}
