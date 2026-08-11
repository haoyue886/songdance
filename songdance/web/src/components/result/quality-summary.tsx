"use client";

import { useTranslations } from "next-intl";
import type { NoteTimeline } from "@/lib/result/timeline";
import {
  cleanupActionCount,
  type TranscriptionQualityReport,
} from "@/lib/result/quality-report";

export function QualitySummary({ report }: { report: TranscriptionQualityReport | null }) {
  const t = useTranslations("result");
  if (!report) {
    return (
      <section
        aria-labelledby="quality-summary-heading"
        className="mt-5 border-y border-[#d9e3dd] py-4"
      >
        <h2 id="quality-summary-heading" className="text-sm font-bold text-[#15332f]">
          {t("qualitySummary")}
        </h2>
        <p className="mt-1 text-sm leading-6 text-[#61716c]">
          {t("qualityMissing")}
        </p>
      </section>
    );
  }
  const facts = [
    [t("rawCleanedNotes"), `${report.rawNoteCount} / ${report.cleanedNoteCount ?? t("notGenerated")}`],
    [t("cleanupActions"), report.cleanup.fallbackUsed ? t("fallback") : t("actionCount", { count: cleanupActionCount(report) })],
    [t("bpmConfidence"), confidenceText(report.analysis.bpmConfidence, t("notEvaluated"))],
    [t("timeConfidence"), confidenceText(report.analysis.timeSignatureConfidence, t("notEvaluated"))],
    [t("key"), report.analysis.keySignature ?? t("notAnalyzed")],
    [t("keyConfidence"), confidenceText(report.analysis.keyConfidence, t("notEvaluated"))],
    [t("noteConfidence"), confidenceText(report.noteConfidenceMean, t("notEvaluated"))],
  ];
  const warnings: string[] = [];
  const reasons = new Set(report.analysis.reasonCodes);
  if (reasons.has("TEMPO_DEFAULTED")) warnings.push(t("tempoDefaulted"));
  if (reasons.has("TIME_SIGNATURE_DEFAULTED_4_4")) warnings.push(t("timeDefaulted"));
  if (reasons.has("KEY_SIGNATURE_DEFAULTED_C_MAJOR")) warnings.push(t("keyDefaulted"));
  if (report.cleanup.fallbackUsed) warnings.push(t("cleanupFallback"));
  if (report.reconstruction.fallbackUsed) warnings.push(t("reconstructionFallback"));
  if (report.musicXmlStatus !== "passed" || report.structureErrors.length > 0) warnings.push(t("structureWarning"));
  return (
    <section
      aria-labelledby="quality-summary-heading"
      className="mt-5 border-y border-[#d9e3dd] py-4"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="quality-summary-heading" className="text-sm font-bold text-[#15332f]">
          {t("qualitySummary")}
        </h2>
        <p className="text-xs text-[#75837f]">{t("qualityDisclaimer")}</p>
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-x-5 gap-y-3 sm:grid-cols-4 lg:grid-cols-7">
        {facts.map(([label, value]) => (
          <div key={label} className="min-w-0">
            <dt className="text-xs text-[#75837f]">{label}</dt>
            <dd className="mt-0.5 break-words text-sm font-bold text-[#15332f]">{value}</dd>
          </div>
        ))}
      </dl>
      <div
        className={`mt-4 border-l-2 pl-3 text-sm leading-6 ${warnings.length > 0 ? "border-[#c96a5d] text-[#7e4038]" : "border-[#65a28d] text-[#52635f]"}`}
      >
        {warnings.length > 0
          ? warnings.map((warning) => <p key={warning}>{warning}</p>)
          : <p>{t("noQualityWarnings")}</p>}
      </div>
    </section>
  );
}

export function VersionSummary({ report, timeline }: {
  report: TranscriptionQualityReport | null;
  timeline: NoteTimeline;
}) {
  const t = useTranslations("result");
  const versions = report ? [
    [t("model"), report.modelVersion],
    [t("postprocess"), report.postprocessVersion],
    [t("qualityReport"), report.reportVersion],
    [t("timeline"), `schema v${timeline.schema_version}`],
  ] : [[t("model"), timeline.model_version], [t("timeline"), `schema v${timeline.schema_version}`]];
  return (
    <aside aria-label={t("artifactVersions")} className="min-w-0 border-t border-[#d9e3dd] pt-5">
      <h2 className="text-sm font-bold uppercase text-[#667772]">{t("artifactVersions")}</h2>
      <dl className="mt-3 grid gap-2 text-xs">
        {versions.map(([label, value]) => (
          <div key={label}>
            <dt className="text-[#75837f]">{label}</dt>
            <dd className="mt-0.5 break-all font-semibold text-[#334b46]">{value}</dd>
          </div>
        ))}
      </dl>
    </aside>
  );
}

export function qualityWarnings(report: TranscriptionQualityReport): string[] {
  const warnings: string[] = [];
  const reasons = new Set(report.analysis.reasonCodes);
  if (reasons.has("TEMPO_DEFAULTED")) warnings.push("BPM 置信度不足，当前速度为系统默认值。");
  if (reasons.has("TIME_SIGNATURE_DEFAULTED_4_4")) warnings.push("拍号置信度不足，当前按 4/4 排版。");
  if (reasons.has("KEY_SIGNATURE_DEFAULTED_C_MAJOR")) warnings.push("调性置信度不足，当前按 C major 排版。");
  if (report.cleanup.fallbackUsed) warnings.push("音符清洗失败，预览已回退到原始模型音符。");
  if (report.reconstruction.fallbackUsed) warnings.push("复杂谱面重建失败，五线谱使用基础排版。");
  if (report.musicXmlStatus !== "passed" || report.structureErrors.length > 0) {
    warnings.push("五线谱结构校验未通过；请优先使用钢琴卷帘、MIDI 和原音校对。");
  }
  return warnings;
}

function confidenceText(value: number | null, missing = "未评估"): string {
  return value === null ? missing : `${Math.round(value * 100)}%`;
}
