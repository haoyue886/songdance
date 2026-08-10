"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { OpenSheetMusicDisplay } from "opensheetmusicdisplay";
import type { NoteTimeline } from "@/lib/result/timeline";
import { createScoreHitMap, scoreSecondsAtDomPoint, type ScoreHitMap } from "@/lib/result/score-hit-map";
import { scoreMeasureRect, scoreSelectionRects, type ScoreSelectionRect } from "@/lib/result/score-selection";
import { createScoreTimeMap, measureIndexAtTime, measureStartSeconds, scoreTimeMapMatches } from "@/lib/result/score-time-map";
import { ScoreToolbar } from "./score-toolbar";

const SCORE_WIDTH = 720;
const TOOLBAR_FALLBACK_HEIGHT = 72;
export function ScoreViewer({
  musicXml,
  currentTime,
  timeline,
  selection,
  onSeek,
  onSelectionChange,
  onRendered,
}: {
  musicXml: string;
  currentTime: number;
  timeline: NoteTimeline;
  selection?: { start: number; end: number } | null;
  onSeek: (seconds: number) => void;
  onSelectionChange?: (selection: { start: number; end: number } | null) => void;
  onRendered: (container: HTMLDivElement | null) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const frameRef = useRef<HTMLDivElement>(null);
  const viewportRef = useRef<HTMLDivElement>(null);
  const toolbarRef = useRef<HTMLDivElement>(null);
  const osmdRef = useRef<OpenSheetMusicDisplay | null>(null);
  const hitMapRef = useRef<ScoreHitMap | null>(null);
  const activeMeasureRef = useRef(-1);
  const suppressClickRef = useRef(false);
  const dragRef = useRef<{ pointerId: number; seconds: number } | null>(null);
  const selectionMaskId = useId().replaceAll(":", "");
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [scale, setScale] = useState(1);
  const [frameHeight, setFrameHeight] = useState<number | undefined>(undefined);
  const [scoreHeight, setScoreHeight] = useState(520);
  const [measureCount, setMeasureCount] = useState(0);
  const [isDragging, setIsDragging] = useState(false);
  const [activeMeasure, setActiveMeasure] = useState(0);
  const [activeMeasureRect, setActiveMeasureRect] = useState<ScoreSelectionRect | null>(null);
  const [selectionRects, setSelectionRects] = useState<ScoreSelectionRect[]>([]);
  const timeMap = useMemo(() => createScoreTimeMap(timeline), [timeline]);
  const duration = Math.max(...timeline.notes.map((note) => note.end_sec));

  useEffect(() => {
    const osmd = osmdRef.current;
    setSelectionRects(osmd && timeMap && selection && measureCount > 0
      ? scoreSelectionRects(osmd, timeMap, selection, scale)
      : []);
  }, [measureCount, scale, selection, timeMap]);

  useEffect(() => {
    const osmd = osmdRef.current;
    setActiveMeasureRect(osmd && measureCount > 0
      ? scoreMeasureRect(osmd, activeMeasure, scale)
      : null);
  }, [activeMeasure, measureCount, scale]);

  useEffect(() => {
    let cancelled = false;
    let observer: ResizeObserver | null = null;
    const container = containerRef.current;
    const frame = frameRef.current;
    if (!container || !frame) return;
    container.replaceChildren();
    setStatus("loading");
    setMeasureCount(0);
    setActiveMeasure(0);
    setActiveMeasureRect(null);
    activeMeasureRef.current = -1;
    hitMapRef.current = null;
    dragRef.current = null;
    setIsDragging(false);
    onRendered(null);

    void (async () => {
      try {
        const osmdModule = await import("opensheetmusicdisplay");
        if (cancelled) return;
        const osmd = new osmdModule.OpenSheetMusicDisplay(container, {
          autoResize: true,
          backend: "svg",
          cursorsOptions: [{
            type: osmdModule.CursorType.CurrentArea,
            color: "#147d70",
            alpha: 0.18,
            follow: true,
          }],
          drawTitle: true,
          followCursor: false,
          pageFormat: "A4_P",
        });
        await osmd.load(musicXml);
        if (cancelled) return;
        osmd.render();
        osmdRef.current = osmd;
        const nextMeasureCount = osmd.GraphicSheet.MeasureList.length;
        const scoreMeasureStarts = osmd.GraphicSheet.MeasureList.map(
          (staffMeasures) => staffMeasures[0]?.parentSourceMeasure.AbsoluteTimestamp.RealValue,
        ).filter((value): value is number => Number.isFinite(value));
        const mappingValid = timeMap && scoreTimeMapMatches(
          timeMap,
          timeline.downbeat_grid_seconds,
          scoreMeasureStarts,
        );
        setMeasureCount(mappingValid ? nextMeasureCount : 0);
        hitMapRef.current = mappingValid && timeMap
          ? createScoreHitMap(osmd, timeMap, duration)
          : null;
        const updateScale = () => {
          const availableWidth = frame.clientWidth || SCORE_WIDTH;
          const nextScale = Math.min(1, availableWidth / SCORE_WIDTH);
          setScale(nextScale);
          const nextScoreHeight = Math.max(1, container.scrollHeight * nextScale);
          setScoreHeight(nextScoreHeight);
          const toolbarHeight = toolbarRef.current?.offsetHeight ?? TOOLBAR_FALLBACK_HEIGHT;
          setFrameHeight(Math.min(520, nextScoreHeight + 32) + toolbarHeight);
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
        requestAnimationFrame(updateScale);
      } catch {
        if (!cancelled) setStatus("error");
      }
    })();

    return () => {
      cancelled = true;
      observer?.disconnect();
      osmdRef.current?.cursor.hide();
      osmdRef.current = null;
      hitMapRef.current = null;
      onRendered(null);
      container.replaceChildren();
    };
  }, [duration, musicXml, onRendered, timeMap, timeline.downbeat_grid_seconds]);

  useEffect(() => {
    const osmd = osmdRef.current;
    if (status !== "ready" || !osmd || !timeMap || measureCount === 0) return;
    const nextMeasure = measureIndexAtTime(timeMap, currentTime, measureCount);
    setActiveMeasure(nextMeasure);
    if (activeMeasureRef.current === nextMeasure) return;
    activeMeasureRef.current = nextMeasure;
    osmd.cursor.reset();
    for (let index = 0; index < nextMeasure; index += 1) osmd.cursor.nextMeasure();
    osmd.cursor.show();
    const cursorElement = containerRef.current?.querySelector<HTMLImageElement>('img[id^="cursorImg"]');
    cursorElement?.style.setProperty("z-index", "20", "important");
    cursorElement?.style.setProperty("pointer-events", "none");
  }, [currentTime, measureCount, status, timeMap]);

  const seekToMeasure = (measureIndex: number) => {
    if (!timeMap || measureCount === 0) return;
    onSeek(measureStartSeconds(timeMap, measureIndex));
  };
  const locateCurrent = () => {
    const viewport = viewportRef.current;
    const osmd = osmdRef.current;
    const activeRect = osmd ? scoreMeasureRect(osmd, activeMeasure, scale) : null;
    if (!viewport || !activeRect) return;
    const topPixels = activeRect.top + 16;
    const target = Math.max(0, Math.min(viewport.scrollHeight - viewport.clientHeight,
      topPixels - viewport.clientHeight / 2));
    viewport.scrollTo({ top: target, behavior: "smooth" });
  };
  const handleScoreClick = (event: React.MouseEvent<HTMLDivElement>) => {
    if (suppressClickRef.current) {
      suppressClickRef.current = false;
      return;
    }
    const hitMap = hitMapRef.current;
    if (!hitMap || measureCount === 0) return;
    const seconds = scoreSecondsAtDomPoint(hitMap, { x: event.clientX, y: event.clientY });
    if (seconds !== null) onSeek(seconds);
  };
  const secondsAtEvent = (event: React.PointerEvent<HTMLDivElement>) => {
    const hitMap = hitMapRef.current;
    if (!hitMap || measureCount === 0) return null;
    return scoreSecondsAtDomPoint(hitMap, { x: event.clientX, y: event.clientY });
  };
  const handlePointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    const seconds = secondsAtEvent(event);
    if (seconds === null) return;
    if (typeof event.currentTarget.setPointerCapture === "function") {
      event.currentTarget.setPointerCapture(event.pointerId);
    }
    dragRef.current = { pointerId: event.pointerId, seconds };
    setIsDragging(true);
  };
  const handlePointerUp = (event: React.PointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId || !timeMap) return;
    dragRef.current = null;
    setIsDragging(false);
    const dragStart = drag.seconds;
    const endSeconds = secondsAtEvent(event) ?? dragStart;
    if (Math.abs(endSeconds - dragStart) < 0.02) {
      return;
    }
    suppressClickRef.current = true;
    onSelectionChange?.({ start: Math.min(dragStart, endSeconds), end: Math.max(dragStart, endSeconds) });
  };
  const handlePointerCancel = (event: React.PointerEvent<HTMLDivElement>) => {
    if (dragRef.current?.pointerId !== event.pointerId) return;
    dragRef.current = null;
    setIsDragging(false);
  };

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
        <div ref={toolbarRef}>
          <ScoreToolbar activeMeasure={activeMeasure} measureCount={measureCount}
            currentTime={currentTime} duration={duration} activePitches={activePitches}
            onLocate={locateCurrent} onPrevious={() => seekToMeasure(activeMeasure - 1)}
            onNext={() => seekToMeasure(activeMeasure + 1)} />
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
      <div ref={viewportRef} data-testid="score-viewport"
        className="relative max-h-[520px] overflow-auto overscroll-contain p-4">
        {(activeMeasureRect || selectionRects.length > 0) && (
          <svg aria-hidden="true" className="pointer-events-none absolute left-4 top-4 z-10"
            width={SCORE_WIDTH * scale} height={scoreHeight}>
            {activeMeasureRect && <rect data-testid="active-measure-highlight"
              x={activeMeasureRect.left} y={activeMeasureRect.top}
              width={activeMeasureRect.width} height={activeMeasureRect.height}
              fill="rgba(22, 163, 74, .22)" stroke="#15803d" strokeWidth="2" />}
            {selectionRects.length > 0 && <>
              <defs><mask id={selectionMaskId}>
                <rect width="100%" height="100%" fill="white" />
                {selectionRects.map((rect, index) => <rect key={index}
                  x={rect.left} y={rect.top} width={rect.width} height={rect.height} fill="black" />)}
              </mask></defs>
              <rect data-testid="score-selection-overlay" width="100%" height="100%"
                fill="rgba(255,255,255,.74)" mask={`url(#${selectionMaskId})`} />
              {selectionRects.map((rect, index) => <rect key={index} data-score-selection-border="true"
                x={rect.left} y={rect.top} width={rect.width} height={rect.height}
                fill="rgba(255,255,255,0)" stroke="#15803d" strokeWidth="3" />)}
            </>}
          </svg>
        )}
        <div
          ref={containerRef}
          aria-label="MusicXML 五线谱"
          aria-hidden={status !== "ready"}
          onClick={handleScoreClick}
          onPointerDown={handlePointerDown}
          onPointerUp={handlePointerUp}
          onPointerCancel={handlePointerCancel}
          title={measureCount > 0 ? "点击定位，拖动选择谱面区间" : undefined}
          className={`w-[720px] select-none ${measureCount > 0 ? isDragging ? "cursor-grabbing" : "cursor-crosshair" : ""} ${status === "ready" ? "" : "invisible absolute left-0 top-0"}`}
          style={{ transform: `scale(${scale})`, transformOrigin: "top left" }}
        />
      </div>
    </div>
  );
}
function midiName(pitch: number): string {
  const names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
  return `${names[pitch % 12]}${Math.floor(pitch / 12) - 1}`;
}
