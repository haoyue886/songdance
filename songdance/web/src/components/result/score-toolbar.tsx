import { ChevronLeft, ChevronRight } from "lucide-react";
import { useTranslations } from "next-intl";

export function ScoreToolbar({ activeMeasure, measureCount, currentTime, duration,
  activePitches, onLocate, onPrevious, onNext }: {
  activeMeasure: number; measureCount: number; currentTime: number; duration: number;
  activePitches: string[]; onLocate: () => void; onPrevious: () => void; onNext: () => void;
}) {
  const t = useTranslations("result");
  const progress = Math.min(1, Math.max(0, currentTime / duration));
  return (
    <div className="border-b border-[#d9e3dd] bg-[#f7faf8] px-4 py-3">
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs font-semibold text-[#52635f]">
        <div className="flex min-w-0 items-center gap-2">
          <span>{t("scorePosition")}</span>
          <span className="whitespace-nowrap tabular-nums" aria-live="polite">
            {measureCount > 0 ? t("measure", { current: activeMeasure + 1, total: measureCount }) : t("measureUnavailable")}
          </span>
        </div>
        <div className="flex items-center gap-1">
          <MeasureButton label={t("locate")} disabled={measureCount === 0} onClick={onLocate}>
            <span className="text-[10px] font-bold">{t("locateShort")}</span>
          </MeasureButton>
          <MeasureButton label={t("previousMeasure")} disabled={measureCount === 0 || activeMeasure === 0} onClick={onPrevious}>
            <ChevronLeft size={16} />
          </MeasureButton>
          <MeasureButton label={t("nextMeasure")} disabled={measureCount === 0 || activeMeasure >= measureCount - 1} onClick={onNext}>
            <ChevronRight size={16} />
          </MeasureButton>
          <span className="ml-1 whitespace-nowrap tabular-nums">
            {formatTime(currentTime)}{activePitches.length > 0 ? ` · ${activePitches.slice(0, 4).join(" ")}` : ""}
          </span>
        </div>
      </div>
      <div role="progressbar" aria-label={t("scorePosition")} aria-valuemin={0}
        aria-valuemax={duration} aria-valuenow={Math.min(currentTime, duration)}
        className="mt-2 h-1.5 overflow-hidden rounded-full bg-[#dfe9e3]">
        <div className="h-full bg-[#147d70] transition-[width]" style={{ width: `${progress * 100}%` }} />
      </div>
    </div>
  );
}

function MeasureButton({ label, disabled, onClick, children }: {
  label: string; disabled: boolean; onClick: () => void; children: React.ReactNode;
}) {
  return <button type="button" aria-label={label} title={label} disabled={disabled} onClick={onClick}
    className="grid size-8 shrink-0 place-items-center rounded border border-[#cad8d2] bg-white text-[#075e55] transition hover:border-[#147d70] disabled:cursor-not-allowed disabled:opacity-40">
    {children}
  </button>;
}

function formatTime(seconds: number): string {
  const safe = Math.max(0, Number.isFinite(seconds) ? seconds : 0);
  return `${Math.floor(safe / 60)}:${Math.floor(safe % 60).toString().padStart(2, "0")}`;
}
