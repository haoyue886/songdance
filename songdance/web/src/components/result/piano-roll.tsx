"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import type { NoteTimeline } from "@/lib/result/timeline";
import { drawWaterfall, seekTimeFromCanvasY } from "./piano-roll-canvas";

export function PianoRoll({
  timeline,
  currentTime,
  duration,
  onSeek,
}: {
  timeline: NoteTimeline;
  currentTime: number;
  duration: number;
  onSeek: (seconds: number) => void;
}) {
  const t = useTranslations("result");
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [reducedMotion, setReducedMotion] = useState(false);

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReducedMotion(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  const redraw = useCallback(() => {
    if (canvasRef.current) {
      drawWaterfall(canvasRef.current, timeline.notes, currentTime, reducedMotion);
    }
  }, [currentTime, reducedMotion, timeline.notes]);

  useEffect(() => {
    redraw();
  }, [redraw]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(redraw);
    observer.observe(canvas);
    return () => observer.disconnect();
  }, [redraw]);

  const seek = (clientY: number) => {
    const bounds = canvasRef.current?.getBoundingClientRect();
    if (!bounds || bounds.height === 0) return;
    onSeek(seekTimeFromCanvasY(clientY - bounds.top, currentTime, bounds.height, duration));
  };

  return (
    <div className="overflow-hidden rounded-lg border border-[#d9e3dd] bg-[#101512] shadow-sm">
      <canvas
        ref={canvasRef}
        aria-label={t("rollLabel")}
        className="block aspect-[4/3] min-h-[330px] w-full cursor-crosshair touch-none sm:min-h-[430px]"
        role="img"
        tabIndex={0}
        onKeyDown={(event) => {
          if (event.key === "ArrowLeft") onSeek(Math.max(0, currentTime - 1));
          if (event.key === "ArrowRight") onSeek(Math.min(duration, currentTime + 1));
        }}
        onPointerDown={(event) => seek(event.clientY)}
      />
    </div>
  );
}
