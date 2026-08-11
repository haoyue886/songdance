"use client";

import { useLocale, useTranslations } from "next-intl";
import type { TranscriptionJob } from "@/lib/api/jobs";

export function TaskSummary({ job, qualityFlags }: {
  job: TranscriptionJob;
  qualityFlags: string[];
}) {
  const t = useTranslations("result");
  const locale = useLocale();
  const facts = [
    [t("excerpt"), t("seconds", { value: (job.end_sec - job.start_sec).toFixed(1) })],
    [t("tempo"), job.result?.tempo ? `${job.result.tempo.toFixed(1)} BPM` : t("notInferred")],
    [t("timeSignature"), job.result?.time_signature ?? t("notInferred")],
    [t("notes"), job.result?.note_count?.toString() ?? "0"],
  ];
  const scoreAssumption = scoreAssumptionText(qualityFlags, locale);
  return (
    <aside className="border-b border-[#d9e3dd] pb-5 lg:border-b-0 lg:border-r lg:pb-0 lg:pr-5">
      <h2 className="text-sm font-bold uppercase text-[#667772]">{t("taskSummary")}</h2>
      <dl className="mt-3 grid grid-cols-2 gap-3 text-sm lg:grid-cols-1">
        {facts.map(([label, value]) => (
          <div key={label}>
            <dt className="text-xs text-[#75837f]">{label}</dt>
            <dd className="mt-0.5 font-bold text-[#15332f]">{value}</dd>
          </div>
        ))}
        {scoreAssumption && (
          <div className="col-span-full border-t border-[#d9e3dd] pt-3">
            <dt className="text-xs text-[#75837f]">{t("scoreNotes")}</dt>
            <dd className="mt-0.5 text-sm leading-5 text-[#4d5e58]">{scoreAssumption}</dd>
          </div>
        )}
      </dl>
    </aside>
  );
}

export function scoreAssumptionText(qualityFlags: string[], locale = "zh-CN"): string | null {
  const en = locale === "en";
  const assumptions: string[] = [];
  if (qualityFlags.includes("TIME_SIGNATURE_ASSUMED_4_4")) {
    assumptions.push(en ? "Time signature laid out as 4/4" : "拍号按 4/4 排版");
  }
  if (qualityFlags.includes("HAND_ASSIGNMENT_MIDDLE_C")) {
    assumptions.push(en ? "Hands split at middle C" : "左右手按中央 C 划分");
  }
  if (qualityFlags.includes("UNKNOWN_HAND_NOTATION_FALLBACK")) {
    assumptions.push(en ? "Notes with unknown hands placed by pitch" : "无法确定分手的音符按音高放入谱表");
  }
  if (qualityFlags.includes("SCORE_RECONSTRUCTION_FALLBACK")) {
    assumptions.push(en ? "Complex reconstruction failed; basic notation generated" : "复杂谱面重建失败，已生成基础谱面");
  }
  return assumptions.length > 0
    ? en ? `${assumptions.join("; ")}. These are layout assumptions, not detected original structure.` : `${assumptions.join("；")}；均为排版假设，并非原曲结构识别。`
    : null;
}
