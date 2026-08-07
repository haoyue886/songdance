import type { TranscriptionJob } from "@/lib/api/jobs";

export function TaskSummary({ job, qualityFlags }: {
  job: TranscriptionJob;
  qualityFlags: string[];
}) {
  const facts = [
    ["片段", `${(job.end_sec - job.start_sec).toFixed(1)} 秒`],
    ["速度", job.result?.tempo ? `${job.result.tempo.toFixed(1)} BPM` : "未推断"],
    ["拍号", job.result?.time_signature ?? "未推断"],
    ["音符", job.result?.note_count?.toString() ?? "0"],
  ];
  const scoreAssumption = scoreAssumptionText(qualityFlags);
  return (
    <aside className="border-b border-[#d9e3dd] pb-5 lg:border-b-0 lg:border-r lg:pb-0 lg:pr-5">
      <h2 className="text-sm font-bold uppercase tracking-[0.12em] text-[#667772]">任务摘要</h2>
      <dl className="mt-3 grid grid-cols-2 gap-3 text-sm lg:grid-cols-1">
        {facts.map(([label, value]) => (
          <div key={label}>
            <dt className="text-xs text-[#75837f]">{label}</dt>
            <dd className="mt-0.5 font-bold text-[#15332f]">{value}</dd>
          </div>
        ))}
        {scoreAssumption && (
          <div className="col-span-full border-t border-[#d9e3dd] pt-3">
            <dt className="text-xs text-[#75837f]">乐谱说明</dt>
            <dd className="mt-0.5 text-sm leading-5 text-[#4d5e58]">{scoreAssumption}</dd>
          </div>
        )}
      </dl>
    </aside>
  );
}

export function scoreAssumptionText(qualityFlags: string[]): string | null {
  const assumptions: string[] = [];
  if (qualityFlags.includes("TIME_SIGNATURE_ASSUMED_4_4")) {
    assumptions.push("拍号按 4/4 排版");
  }
  if (qualityFlags.includes("HAND_ASSIGNMENT_MIDDLE_C")) {
    assumptions.push("左右手按中央 C 划分");
  }
  if (qualityFlags.includes("UNKNOWN_HAND_NOTATION_FALLBACK")) {
    assumptions.push("无法确定分手的音符按音高放入谱表");
  }
  if (qualityFlags.includes("SCORE_RECONSTRUCTION_FALLBACK")) {
    assumptions.push("复杂谱面重建失败，已生成基础谱面");
  }
  return assumptions.length > 0
    ? `${assumptions.join("；")}；均为排版假设，并非原曲结构识别。`
    : null;
}
