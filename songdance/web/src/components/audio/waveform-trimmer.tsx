"use client";

import { useEffect, useRef, useState } from "react";
import WaveSurfer from "wavesurfer.js";
import RegionsPlugin, { type Region } from "wavesurfer.js/dist/plugins/regions.esm.js";
import { clipDuration, normalizeClip, type AudioClip } from "@/lib/audio/clip";

type WaveformTrimmerProps = {
  file: File;
  duration: number;
  clip: AudioClip;
  disabled?: boolean;
  onChange: (clip: AudioClip) => void;
  onError: (message: string) => void;
};

const formatTime = (value: number) => `${value.toFixed(2)} 秒`;

export function WaveformTrimmer({ file, duration, clip, disabled, onChange, onError }: WaveformTrimmerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const waveSurferRef = useRef<WaveSurfer | null>(null);
  const regionRef = useRef<Region | null>(null);
  const clipRef = useRef(clip);
  const [isReady, setIsReady] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);

  useEffect(() => {
    clipRef.current = clip;
  }, [clip]);

  useEffect(() => {
    if (!containerRef.current) return;
    const regions = RegionsPlugin.create();
    const waveSurfer = WaveSurfer.create({
      container: containerRef.current,
      height: 112,
      waveColor: "#9dc7bc",
      progressColor: "#147d70",
      cursorColor: "#075e55",
      barWidth: 2,
      barGap: 2,
      barRadius: 2,
      normalize: true,
      plugins: [regions],
    });
    waveSurferRef.current = waveSurfer;

    waveSurfer.on("ready", () => {
      setIsReady(true);
      const initialClip = clipRef.current;
      regionRef.current = regions.addRegion({
        id: "transcription-clip",
        start: initialClip.start,
        end: initialClip.end,
        minLength: 1,
        maxLength: 90,
        color: "rgba(20, 125, 112, 0.18)",
        drag: true,
        resize: true,
      });
    });
    waveSurfer.on("error", () => onError("波形加载失败，请重新选择音频"));
    waveSurfer.on("pause", () => setIsPlaying(false));
    waveSurfer.on("finish", () => setIsPlaying(false));
    regions.on("region-updated", (region, side) => {
      onChange(normalizeClip({ start: region.start, end: region.end }, duration, side ?? "end"));
    });
    void waveSurfer.loadBlob(file).catch(() => undefined);

    return () => {
      waveSurfer.destroy();
      waveSurferRef.current = null;
      regionRef.current = null;
    };
  }, [duration, file, onChange, onError]);

  useEffect(() => {
    regionRef.current?.setOptions({ drag: !disabled, resize: !disabled });
  }, [disabled]);

  useEffect(() => {
    const region = regionRef.current;
    if (!region) return;
    if (Math.abs(region.start - clip.start) > 0.01 || Math.abs(region.end - clip.end) > 0.01) {
      region.setOptions({ start: clip.start, end: clip.end });
    }
  }, [clip]);

  const togglePlayback = async () => {
    const waveSurfer = waveSurferRef.current;
    if (!waveSurfer || !isReady) return;
    if (isPlaying) {
      waveSurfer.pause();
      setIsPlaying(false);
      return;
    }
    await waveSurfer.play(clip.start, clip.end);
    setIsPlaying(true);
  };

  return (
    <section aria-label="音频片段截取" className="rounded-3xl border border-[#d9e3dd] bg-white p-5 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold">选择转录片段</h2>
          <p className="mt-1 text-sm text-[#667772]">拖动绿色区域或输入时间，最长 90 秒。</p>
        </div>
        <button
          type="button"
          disabled={!isReady || disabled}
          onClick={togglePlayback}
          className="rounded-full bg-[#e2f0eb] px-4 py-2 text-sm font-bold text-[#075e55] disabled:opacity-50"
        >
          {isPlaying ? "暂停" : "播放选区"}
        </button>
      </div>
      <div className="relative mt-5 min-h-28 overflow-hidden rounded-2xl bg-[#eff4f0]">
        {!isReady && <p className="absolute inset-0 grid place-items-center text-sm text-[#667772]">正在生成波形…</p>}
        <div ref={containerRef} className="relative z-10" />
      </div>
      <div className="mt-5 grid gap-4 sm:grid-cols-3">
        <TimeInput
          label="开始时间"
          value={clip.start}
          max={Math.max(0, duration - 1)}
          disabled={disabled}
          onChange={(start) => onChange(normalizeClip({ start, end: clip.end }, duration, "start"))}
        />
        <TimeInput
          label="结束时间"
          value={clip.end}
          max={duration}
          disabled={disabled}
          onChange={(end) => onChange(normalizeClip({ start: clip.start, end }, duration, "end"))}
        />
        <div className="rounded-xl bg-[#f3f6f3] px-4 py-3">
          <p className="text-xs font-bold uppercase tracking-[0.12em] text-[#75837f]">片段时长</p>
          <p className="mt-1 font-bold text-[#15332f]">{formatTime(clipDuration(clip))}</p>
        </div>
      </div>
    </section>
  );
}

type TimeInputProps = {
  label: string;
  value: number;
  max: number;
  disabled?: boolean;
  onChange: (value: number) => void;
};

function TimeInput({ label, value, max, disabled, onChange }: TimeInputProps) {
  return (
    <label className="rounded-xl bg-[#f3f6f3] px-4 py-3">
      <span className="block text-xs font-bold uppercase tracking-[0.12em] text-[#75837f]">{label}</span>
      <span className="mt-1 flex items-center gap-2">
        <input
          type="number"
          min={0}
          max={max}
          step={0.1}
          value={value}
          disabled={disabled}
          onChange={(event) => onChange(Number(event.currentTarget.value))}
          className="min-w-0 flex-1 bg-transparent font-bold outline-none"
        />
        <span className="text-sm text-[#75837f]">秒</span>
      </span>
    </label>
  );
}
