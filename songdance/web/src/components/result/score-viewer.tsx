"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { OpenSheetMusicDisplay } from "opensheetmusicdisplay";
import { useScoreRangeDrag } from "@/hooks/use-score-range-drag";
import type { NoteTimeline } from "@/lib/result/timeline";
import {
  createScoreHitMap,
  scoreMeasureFractionAtQuarters,
  scoreSecondsAtDomPoint,
  type ScoreHitMap,
} from "@/lib/result/score-hit-map";
import { scoreMeasureRect, scoreSelectionRects } from "@/lib/result/score-selection";
import { createScoreTimeMap, measureIndexAtTime, measureStartSeconds, scoreTimeMapMatches } from "@/lib/result/score-time-map";
import { ScoreSelectionOverlay } from "./score-selection-overlay";
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
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [scale, setScale] = useState(1);
  const [frameHeight, setFrameHeight] = useState<number | undefined>(undefined);
  const [scoreHeight, setScoreHeight] = useState(520);
  const [measureCount, setMeasureCount] = useState(0);
  const [renderedOsmd, setRenderedOsmd] = useState<OpenSheetMusicDisplay | null>(null);
  const [renderedHitMap, setRenderedHitMap] = useState<ScoreHitMap | null>(null);
  const [activeMeasure, setActiveMeasure] = useState(0);
  const timeMap = useMemo(() => createScoreTimeMap(timeline), [timeline]);
  const duration = Math.max(...timeline.notes.map((note) => note.end_sec));
  const secondsAtPoint = useCallback((point: { x: number; y: number }) => {
    const hitMap = hitMapRef.current;
    return hitMap && measureCount > 0 ? scoreSecondsAtDomPoint(hitMap, point) : null;
  }, [measureCount]);
  const {
    draftSelection,
    isDragging,
    consumeClickSuppression,
    pointerHandlers,
  } = useScoreRangeDrag({
    enabled: measureCount > 0,
    viewportRef,
    secondsAtPoint,
    onCommit: onSelectionChange ?? undefined,
  });
  const visibleSelection = draftSelection ?? selection;
  const selectionRects = useMemo(() => {
    return renderedOsmd && timeMap && visibleSelection && measureCount > 0
      ? scoreSelectionRects(renderedOsmd, timeMap, visibleSelection, scale,
        renderedHitMap ? (measureIndex, quarters) =>
          scoreMeasureFractionAtQuarters(renderedHitMap, measureIndex, quarters) : undefined)
      : [];
  }, [measureCount, renderedHitMap, renderedOsmd, scale, timeMap, visibleSelection]);
  const activeMeasureRect = useMemo(() => renderedOsmd && measureCount > 0
    ? scoreMeasureRect(renderedOsmd, activeMeasure, scale)
    : null, [activeMeasure, measureCount, renderedOsmd, scale]);

  useEffect(() => {
    let cancelled = false;
    let observer: ResizeObserver | null = null;
    const container = containerRef.current;
    const frame = frameRef.current;
    if (!container || !frame) return;
    container.replaceChildren();
    setStatus("loading");
    setMeasureCount(0);
    setRenderedOsmd(null);
    setRenderedHitMap(null);
    setActiveMeasure(0);
    activeMeasureRef.current = -1;
    hitMapRef.current = null;
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
        setRenderedOsmd(osmd);
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
        setRenderedHitMap(hitMapRef.current);
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
    if (consumeClickSuppression()) return;
    const seconds = secondsAtPoint({ x: event.clientX, y: event.clientY });
    if (seconds !== null) onSeek(seconds);
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
        <ScoreSelectionOverlay width={SCORE_WIDTH * scale} height={scoreHeight}
          activeMeasure={activeMeasureRect} selectionSegments={selectionRects} />
        <div
          ref={containerRef}
          aria-label="MusicXML 五线谱"
          aria-hidden={status !== "ready"}
          onClick={handleScoreClick}
          {...pointerHandlers}
          title={measureCount > 0 ? "点击定位，拖动选择谱面区间" : undefined}
          className={`w-[720px] touch-pan-y select-none ${measureCount > 0 ? isDragging ? "cursor-grabbing" : "cursor-crosshair" : ""} ${status === "ready" ? "" : "invisible absolute left-0 top-0"}`}
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
