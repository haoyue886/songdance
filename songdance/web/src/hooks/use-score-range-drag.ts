"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
  type RefObject,
} from "react";

const DRAG_THRESHOLD_PX = 4;
const EDGE_ZONE_PX = 36;
const MIN_EDGE_SCROLL_PX = 4;
const MAX_EDGE_SCROLL_PX = 18;
const MIN_SELECTION_SECONDS = 0.02;

export type ScoreRange = { start: number; end: number };
export type ScorePointer = { x: number; y: number };

type ActiveDrag = {
  mode: "create" | "resize";
  pointerId: number;
  anchorSeconds: number;
  focusSeconds: number;
  start: ScorePointer;
  latest: ScorePointer;
  target: Element;
  dragging: boolean;
};

export function useScoreRangeDrag({
  enabled,
  viewportRef,
  secondsAtPoint,
  onCommit,
}: {
  enabled: boolean;
  viewportRef: RefObject<HTMLElement | null>;
  secondsAtPoint: (point: ScorePointer) => number | null;
  onCommit?: (selection: ScoreRange) => void;
}) {
  const activeRef = useRef<ActiveDrag | null>(null);
  const animationFrameRef = useRef<number | null>(null);
  const runFrameRef = useRef<FrameRequestCallback>(() => undefined);
  const suppressClickRef = useRef(false);
  const suppressTimerRef = useRef<number | null>(null);
  const secondsAtPointRef = useRef(secondsAtPoint);
  const onCommitRef = useRef(onCommit);
  const [draftSelection, setDraftSelection] = useState<ScoreRange | null>(null);
  const [isDragging, setIsDragging] = useState(false);

  useEffect(() => {
    secondsAtPointRef.current = secondsAtPoint;
    onCommitRef.current = onCommit;
  }, [onCommit, secondsAtPoint]);

  const cancelFrame = useCallback(() => {
    if (animationFrameRef.current === null) return;
    cancelAnimationFrame(animationFrameRef.current);
    animationFrameRef.current = null;
  }, []);

  const scheduleFrame = useCallback(() => {
    if (animationFrameRef.current !== null) return;
    animationFrameRef.current = requestAnimationFrame((timestamp) => runFrameRef.current(timestamp));
  }, []);

  const suppressNextClick = useCallback(() => {
    suppressClickRef.current = true;
    if (suppressTimerRef.current !== null) window.clearTimeout(suppressTimerRef.current);
    suppressTimerRef.current = window.setTimeout(() => {
      suppressClickRef.current = false;
      suppressTimerRef.current = null;
    }, 0);
  }, []);

  const releaseCapture = useCallback((drag: ActiveDrag) => {
    if (typeof drag.target.hasPointerCapture === "function"
      && !drag.target.hasPointerCapture(drag.pointerId)) return;
    drag.target.releasePointerCapture?.(drag.pointerId);
  }, []);

  const cancelDrag = useCallback((release = true) => {
    const active = activeRef.current;
    activeRef.current = null;
    cancelFrame();
    setDraftSelection(null);
    setIsDragging(false);
    if (active?.dragging) suppressNextClick();
    if (active && release) releaseCapture(active);
  }, [cancelFrame, releaseCapture, suppressNextClick]);

  const startDrag = useCallback((
    event: ReactPointerEvent<Element>,
    anchorSeconds: number,
    focusSeconds: number,
    mode: ActiveDrag["mode"],
    captureTarget = event.currentTarget,
  ) => {
    if (!enabled || activeRef.current || event.isPrimary === false) return false;
    if (event.pointerType === "mouse" && event.button !== 0) return false;
    const point = { x: event.clientX, y: event.clientY };
    captureTarget.setPointerCapture?.(event.pointerId);
    activeRef.current = {
      mode,
      pointerId: event.pointerId,
      anchorSeconds,
      focusSeconds,
      start: point,
      latest: point,
      target: captureTarget,
      dragging: false,
    };
    return true;
  }, [enabled]);

  useEffect(() => {
    runFrameRef.current = () => {
      animationFrameRef.current = null;
      const active = activeRef.current;
      if (!active?.dragging) return;
      const didScroll = scrollViewportAtEdge(viewportRef.current, active.latest.y);
      const seconds = secondsAtPointRef.current(active.latest);
      if (seconds !== null) {
        active.focusSeconds = seconds;
        const next = normalizeRange(active.anchorSeconds, seconds);
        setDraftSelection((current) => sameRange(current, next) ? current : next);
      }
      if (didScroll) scheduleFrame();
    };
  }, [scheduleFrame, viewportRef]);

  const handlePointerDown = useCallback((event: ReactPointerEvent<HTMLElement>) => {
    const point = { x: event.clientX, y: event.clientY };
    const seconds = secondsAtPointRef.current(point);
    if (seconds === null) return;
    startDrag(event, seconds, seconds, "create");
  }, [startDrag]);

  const beginBoundaryResize = useCallback((
    event: ReactPointerEvent<Element>,
    boundary: "start" | "end",
    selection: ScoreRange,
  ) => {
    const anchorSeconds = boundary === "start" ? selection.end : selection.start;
    const focusSeconds = boundary === "start" ? selection.start : selection.end;
    if (!Number.isFinite(anchorSeconds) || !Number.isFinite(focusSeconds)) return;
    if (startDrag(event, anchorSeconds, focusSeconds, "resize",
      viewportRef.current ?? event.currentTarget)) {
      event.stopPropagation();
    }
  }, [startDrag, viewportRef]);

  const handlePointerMove = useCallback((event: ReactPointerEvent<Element>) => {
    const active = activeRef.current;
    if (!active || active.pointerId !== event.pointerId) return;
    active.latest = { x: event.clientX, y: event.clientY };
    if (!active.dragging) {
      const distance = Math.hypot(
        active.latest.x - active.start.x,
        active.latest.y - active.start.y,
      );
      if (distance <= DRAG_THRESHOLD_PX) return;
      active.dragging = true;
      setIsDragging(true);
    }
    event.preventDefault();
    scheduleFrame();
  }, [scheduleFrame]);

  const handlePointerUp = useCallback((event: ReactPointerEvent<Element>) => {
    const active = activeRef.current;
    if (!active || active.pointerId !== event.pointerId) return;
    active.latest = { x: event.clientX, y: event.clientY };
    activeRef.current = null;
    cancelFrame();
    setDraftSelection(null);
    setIsDragging(false);
    releaseCapture(active);
    if (!active.dragging) return;
    suppressNextClick();
    const focusSeconds = secondsAtPointRef.current(active.latest) ?? active.focusSeconds;
    if (Math.abs(focusSeconds - active.anchorSeconds) < MIN_SELECTION_SECONDS) return;
    onCommitRef.current?.(normalizeRange(active.anchorSeconds, focusSeconds));
  }, [cancelFrame, releaseCapture, suppressNextClick]);

  const handlePointerCancel = useCallback((event: ReactPointerEvent<Element>) => {
    if (activeRef.current?.pointerId === event.pointerId) cancelDrag(false);
  }, [cancelDrag]);

  const handleLostPointerCapture = useCallback((event: ReactPointerEvent<Element>) => {
    if (activeRef.current?.pointerId === event.pointerId) cancelDrag(false);
  }, [cancelDrag]);

  const cancelBoundaryResize = useCallback(() => {
    if (activeRef.current?.mode === "resize") cancelDrag();
  }, [cancelDrag]);

  const consumeClickSuppression = useCallback(() => {
    if (!suppressClickRef.current) return false;
    suppressClickRef.current = false;
    if (suppressTimerRef.current !== null) window.clearTimeout(suppressTimerRef.current);
    suppressTimerRef.current = null;
    return true;
  }, []);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && activeRef.current) cancelDrag();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [cancelDrag]);

  useEffect(() => () => cancelDrag(), [cancelDrag, enabled]);

  useEffect(() => () => {
    if (suppressTimerRef.current !== null) window.clearTimeout(suppressTimerRef.current);
  }, []);

  return {
    draftSelection,
    isDragging,
    beginBoundaryResize,
    cancelBoundaryResize,
    consumeClickSuppression,
    pointerHandlers: {
      onPointerDown: handlePointerDown,
      onPointerMove: handlePointerMove,
      onPointerUp: handlePointerUp,
      onPointerCancel: handlePointerCancel,
      onLostPointerCapture: handleLostPointerCapture,
    },
  };
}

function normalizeRange(anchor: number, focus: number): ScoreRange {
  return { start: Math.min(anchor, focus), end: Math.max(anchor, focus) };
}

function sameRange(left: ScoreRange | null, right: ScoreRange): boolean {
  return left?.start === right.start && left.end === right.end;
}

function scrollViewportAtEdge(viewport: HTMLElement | null, clientY: number): boolean {
  if (!viewport) return false;
  const rect = viewport.getBoundingClientRect();
  let direction = 0;
  let depth = 0;
  if (clientY >= rect.top && clientY < rect.top + EDGE_ZONE_PX) {
    direction = -1;
    depth = (rect.top + EDGE_ZONE_PX - clientY) / EDGE_ZONE_PX;
  } else if (clientY <= rect.bottom && clientY > rect.bottom - EDGE_ZONE_PX) {
    direction = 1;
    depth = (clientY - (rect.bottom - EDGE_ZONE_PX)) / EDGE_ZONE_PX;
  }
  if (direction === 0) return false;
  const speed = MIN_EDGE_SCROLL_PX
    + (MAX_EDGE_SCROLL_PX - MIN_EDGE_SCROLL_PX) * Math.max(0, Math.min(1, depth));
  const maximum = Math.max(0, viewport.scrollHeight - viewport.clientHeight);
  const next = Math.max(0, Math.min(maximum, viewport.scrollTop + direction * speed));
  if (next === viewport.scrollTop) return false;
  viewport.scrollTop = next;
  return true;
}
