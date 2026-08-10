import type { NoteTimeline } from "@/lib/result/timeline";
import {
  cleanupActionCount,
  type TranscriptionQualityReport,
} from "@/lib/result/quality-report";

export function QualitySummary({ report }: { report: TranscriptionQualityReport | null }) {
  if (!report) {
    return (
      <section
        aria-labelledby="quality-summary-heading"
        className="mt-5 border-y border-[#d9e3dd] py-4"
      >
        <h2 id="quality-summary-heading" className="text-sm font-bold text-[#15332f]">
          质量摘要
        </h2>
        <p className="mt-1 text-sm leading-6 text-[#61716c]">
          此任务未保存可读取的质量报告。预览和可用产物不受影响，结果仍需人工校对。
        </p>
      </section>
    );
  }
  const facts = [
    ["原始 / 清洗音符", `${report.rawNoteCount} / ${report.cleanedNoteCount ?? "未生成"}`],
    ["清洗动作", report.cleanup.fallbackUsed ? "已回退" : `${cleanupActionCount(report)} 次`],
    ["BPM 置信度", confidenceText(report.analysis.bpmConfidence)],
    ["拍号置信度", confidenceText(report.analysis.timeSignatureConfidence)],
    ["调性", report.analysis.keySignature ?? "未分析"],
    ["调性置信度", confidenceText(report.analysis.keyConfidence)],
    ["音符平均置信度", confidenceText(report.noteConfidenceMean)],
  ];
  const warnings = qualityWarnings(report);
  return (
    <section
      aria-labelledby="quality-summary-heading"
      className="mt-5 border-y border-[#d9e3dd] py-4"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="quality-summary-heading" className="text-sm font-bold text-[#15332f]">
          质量摘要
        </h2>
        <p className="text-xs text-[#75837f]">自动分析仅供校对，不代表人工谱面级准确率</p>
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
          : <p>未记录结构或回退警告；自动转录仍可能需要人工校对。</p>}
      </div>
    </section>
  );
}

export function VersionSummary({ report, timeline }: {
  report: TranscriptionQualityReport | null;
  timeline: NoteTimeline;
}) {
  const versions = report ? [
    ["模型", report.modelVersion],
    ["后处理", report.postprocessVersion],
    ["质量报告", report.reportVersion],
    ["时间线", `schema v${timeline.schema_version}`],
  ] : [["模型", timeline.model_version], ["时间线", `schema v${timeline.schema_version}`]];
  return (
    <aside aria-label="产物版本" className="min-w-0 border-t border-[#d9e3dd] pt-5">
      <h2 className="text-sm font-bold uppercase tracking-[0.12em] text-[#667772]">产物版本</h2>
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

function confidenceText(value: number | null): string {
  return value === null ? "未评估" : `${Math.round(value * 100)}%`;
}
