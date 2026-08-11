"use client";

import { Minus, Pause, Piano, Play, Plus, Repeat2, RotateCcw, Volume2 } from "lucide-react";
import { useTranslations } from "next-intl";
import type { PlaybackMode } from "@/hooks/use-result-playback";

export type TransportProps = {
  mode: PlaybackMode;
  onMode: (mode: PlaybackMode) => void;
  playing: boolean;
  onPlay: () => void;
  onPause: () => void;
  currentTime: number;
  duration: number;
  onSeek: (seconds: number) => void;
  rate: number;
  onRate: (rate: number) => void;
  loopEnabled: boolean;
  onLoopEnabled: (enabled: boolean) => void;
  loopStart: number;
  loopEnd: number;
  onLoopStart: (seconds: number) => void;
  onLoopEnd: (seconds: number) => void;
  transpose: number;
  onTranspose: (semitones: number) => void;
  selection?: { start: number; end: number } | null;
  onClearSelection?: () => void;
};

export function Transport(props: TransportProps) {
  const t = useTranslations("result");
  return (
    <section aria-label={t("transport")} className="rounded-lg border border-[#cad8d2] bg-white p-3 shadow-sm">
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          aria-label={props.playing ? t("pause") : t("play")}
          title={props.playing ? t("pause") : t("play")}
          className="grid size-10 shrink-0 place-items-center rounded-md bg-[#147d70] text-white hover:bg-[#075e55]"
          onClick={props.playing ? props.onPause : props.onPlay}
        >
          {props.playing ? <Pause size={18} /> : <Play size={18} fill="currentColor" />}
        </button>
        <span className="w-[92px] text-center text-sm font-semibold tabular-nums text-[#52635f]">
          {formatTime(props.currentTime)} / {formatTime(props.duration)}
        </span>
        <input
          aria-label={t("position")}
          className="min-w-[160px] flex-1 accent-[#147d70]"
          type="range"
          min={0}
          max={props.duration}
          step={0.01}
          value={Math.min(props.currentTime, props.duration)}
          onChange={(event) => props.onSeek(Number(event.target.value))}
        />
        <div className="flex rounded-md border border-[#cad8d2] p-0.5" aria-label={t("sourceSelector")}>
          <ModeButton
            active={props.mode === "source"}
            label={t("sourceMode")}
            icon={<Volume2 size={15} />}
            onClick={() => props.onMode("source")}
          />
          <ModeButton
            active={props.mode === "midi"}
            label={t("midiMode")}
            icon={<Piano size={15} />}
            onClick={() => props.onMode("midi")}
          />
        </div>
        <label className="flex items-center gap-2 text-sm font-semibold text-[#52635f]">
          {t("speed")}
          <select
            aria-label={t("playbackSpeed")}
            className="h-9 rounded-md border border-[#cad8d2] bg-white px-2"
            value={props.rate}
            onChange={(event) => props.onRate(Number(event.target.value))}
          >
            {[0.5, 0.75, 1, 1.25, 1.5].map((rate) => (
              <option key={rate} value={rate}>
                {rate}×
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="mt-3 grid gap-3 border-t border-[#e1e7e2] pt-3 md:grid-cols-[minmax(0,1fr)_auto]">
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2 text-sm font-semibold text-[#52635f]">
            <input
              type="checkbox"
              className="size-4 accent-[#147d70]"
              checked={props.loopEnabled}
              onChange={(event) => props.onLoopEnabled(event.target.checked)}
            />
            <Repeat2 size={16} /> {t("loop")}
          </label>
          <TimeInput label={t("start")} value={props.loopStart} max={props.loopEnd - 0.5} onChange={props.onLoopStart} />
          <TimeInput label={t("end")} value={props.loopEnd} min={props.loopStart + 0.5} max={props.duration} onChange={props.onLoopEnd} />
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-[#52635f]">{t("transpose")}</span>
          <IconButton label={t("downSemitone")} onClick={() => props.onTranspose(Math.max(-12, props.transpose - 1))}>
            <Minus size={16} />
          </IconButton>
          <span className="w-11 text-center text-sm font-bold tabular-nums text-[#15332f]">
            {props.transpose > 0 ? `+${props.transpose}` : props.transpose}
          </span>
          <IconButton label={t("upSemitone")} onClick={() => props.onTranspose(Math.min(12, props.transpose + 1))}>
            <Plus size={16} />
          </IconButton>
          <IconButton label={t("resetTranspose")} onClick={() => props.onTranspose(0)}>
            <RotateCcw size={16} />
          </IconButton>
        </div>
      </div>
      {props.selection && (
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-[#e1e7e2] pt-3 text-xs font-semibold text-[#52635f]">
          <span aria-live="polite">{t("selection", { start: formatTime(props.selection.start), end: formatTime(props.selection.end) })}</span>
          <button type="button" className="rounded border border-[#cad8d2] px-2 py-1 text-[#075e55] hover:bg-[#edf4f0]"
            onClick={props.onClearSelection}>{t("clearSelection")}</button>
        </div>
      )}
    </section>
  );
}

function ModeButton({
  active,
  label,
  icon,
  onClick,
}: {
  active: boolean;
  label: string;
  icon: React.ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      className={`flex h-8 items-center gap-1.5 rounded px-2.5 text-xs font-bold ${active ? "bg-[#d9efe7] text-[#075e55]" : "text-[#667772]"}`}
      onClick={onClick}
    >
      {icon} {label}
    </button>
  );
}

function TimeInput({
  label,
  value,
  min = 0,
  max,
  onChange,
}: {
  label: string;
  value: number;
  min?: number;
  max: number;
  onChange: (value: number) => void;
}) {
  return (
    <label className="flex items-center gap-1.5 text-xs font-semibold text-[#667772]">
      {label}
      <input
        type="number"
        aria-label={label}
        className="h-8 w-20 rounded-md border border-[#cad8d2] px-2 tabular-nums"
        min={min}
        max={max}
        step={0.1}
        value={value.toFixed(1)}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </label>
  );
}

function IconButton({ label, onClick, children }: { label: string; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      className="grid size-8 place-items-center rounded-md border border-[#cad8d2] text-[#52635f] hover:bg-[#edf4f0]"
      onClick={onClick}
    >
      {children}
    </button>
  );
}

function formatTime(seconds: number): string {
  const safe = Math.max(0, Number.isFinite(seconds) ? seconds : 0);
  const minutes = Math.floor(safe / 60);
  return `${minutes}:${Math.floor(safe % 60).toString().padStart(2, "0")}`;
}
