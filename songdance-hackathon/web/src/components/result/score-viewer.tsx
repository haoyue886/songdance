"use client";

import { useEffect, useRef, useState } from "react";
import type { NoteTimeline } from "@/lib/result/timeline";

const SCORE_WIDTH = 720;
const PROGRESS_HEIGHT = 54;

export function ScoreViewer({
  musicXml,
  currentTime,
  timeline,
  onRendered,
}: {
  musicXml: string;
  currentTime: number;
  timeline: NoteTimeline;
  onRendered: (container: HTMLDivElement | null) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const frameRef = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [scale, setScale] = useState(1);
  const [frameHeight, setFrameHeight] = useState<number | undefined>(undefined);

  useEffect(() => {
    let cancelled = false;
    let observer: ResizeObserver | null = null;
    const container = containerRef.current;
    const frame = frameRef.current;
    if (!container || !frame) return;
    container.replaceChildren();
    setStatus("loading");
    onRendered(null);

    void (async () => {
      try {
        const { OpenSheetMusicDisplay } = await import("opensheetmusicdisplay");
        if (cancelled) return;
        const osmd = new OpenSheetMusicDisplay(container, {
          autoResize: true,
          backend: "svg",
          drawTitle: true,
          pageFormat: "A4_P",
        });
        await osmd.load(musicXml);
        if (cancelled) return;
        osmd.render();
        const updateScale = () => {
          const nextScale = Math.min(1, frame.clientWidth / SCORE_WIDTH);
          setScale(nextScale);
          setFrameHeight(container.scrollHeight * nextScale + PROGRESS_HEIGHT);
        };
        updateScale();
        observer = new ResizeObserver(updateScale);
        observer.observe(frame);
        if (cancelled) {
          observer.disconnect();
          return;
        }
        setStatus("ready");
        onRendered(container);
      } catch {
        if (!cancelled) setStatus("error");
      }
    })();

    return () => {
      cancelled = true;
      observer?.disconnect();
      onRendered(null);
      container.replaceChildren();
    };
  }, [musicXml, onRendered]);

  const duration = Math.max(...timeline.notes.map((note) => note.end_sec));
  const progress = Math.min(1, Math.max(0, currentTime / duration));
  const activePitches = timeline.notes
    .filter((note) => note.start_sec <= currentTime && note.end_sec > currentTime)
    .map((note) => midiName(note.pitch));

  return (
    <div
      ref={frameRef}
      className="relative min-h-[360px] overflow-hidden rounded-lg border border-[#d9e3dd] bg-white"
      style={status === "ready" ? { height: frameHeight } : undefined}
    >
      {status === "ready" && (
        <div className="border-b border-[#d9e3dd] bg-[#f7faf8] px-4 py-3">
          <div className="flex items-center justify-between gap-3 text-xs font-semibold text-[#52635f]">
            <span>五线谱播放位置</span>
            <span className="tabular-nums">
              {formatTime(currentTime)}
              {activePitches.length > 0 ? ` · ${activePitches.slice(0, 4).join(" ")}` : ""}
            </span>
          </div>
          <div
            role="progressbar"
            aria-label="五线谱播放位置"
            aria-valuemin={0}
            aria-valuemax={duration}
            aria-valuenow={Math.min(currentTime, duration)}
            className="mt-2 h-1.5 overflow-hidden rounded-full bg-[#dfe9e3]"
          >
            <div className="h-full bg-[#147d70] transition-[width]" style={{ width: `${progress * 100}%` }} />
          </div>
        </div>
      )}
      {status === "loading" && (
        <div className="grid min-h-[360px] place-items-center" role="status">
          <p className="text-sm font-semibold text-[#61716c]">正在排版五线谱…</p>
        </div>
      )}
      {status === "error" && (
        <div className="grid min-h-[360px] place-items-center p-8 text-center" role="alert">
          <div>
            <p className="font-bold text-[#8d372f]">五线谱无法显示</p>
            <p className="mt-2 text-sm leading-6 text-[#61716c]">
              MusicXML 产物解析失败。MIDI 和其他可用格式仍可下载。
            </p>
          </div>
        </div>
      )}
      <div
        ref={containerRef}
        aria-label="MusicXML 五线谱"
        aria-hidden={status !== "ready"}
        className={`w-[720px] p-4 ${status === "ready" ? "" : "invisible absolute left-0 top-0"}`}
        style={{ transform: `scale(${scale})`, transformOrigin: "top left" }}
      />
    </div>
  );
}

function midiName(pitch: number): string {
  const names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
  return `${names[pitch % 12]}${Math.floor(pitch / 12) - 1}`;
}

function formatTime(seconds: number): string {
  const safe = Math.max(0, Number.isFinite(seconds) ? seconds : 0);
  return `${Math.floor(safe / 60)}:${Math.floor(safe % 60).toString().padStart(2, "0")}`;
}
