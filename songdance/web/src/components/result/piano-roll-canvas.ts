import type { TimelineNote } from "@/lib/result/timeline";
import { drawWaterfallScene } from "./piano-roll-drawing";

const BLACK_KEY_CLASSES = new Set([1, 3, 6, 8, 10]);
const RANGE_PADDING = 2;
const MINIMUM_RANGE = 24;
const VISIBLE_FUTURE_SECONDS = 5;

export type PianoRange = {
  low: number;
  high: number;
  whiteKeys: number[];
};

export type WaterfallMetrics = {
  keyboardHeight: number;
  strikeY: number;
  pixelsPerSecond: number;
};

export function isBlackKey(pitch: number): boolean {
  return BLACK_KEY_CLASSES.has(((pitch % 12) + 12) % 12);
}

export function getPianoRange(notes: TimelineNote[]): PianoRange {
  if (notes.length === 0) {
    return {
      low: 48,
      high: 71,
      whiteKeys: Array.from({ length: 24 }, (_, index) => 48 + index).filter(
        (pitch) => !isBlackKey(pitch),
      ),
    };
  }
  const lowest = Math.min(...notes.map((note) => note.pitch));
  const highest = Math.max(...notes.map((note) => note.pitch));
  let low = Math.max(0, lowest - RANGE_PADDING);
  let high = Math.min(127, highest + RANGE_PADDING);

  const missing = Math.max(0, MINIMUM_RANGE - (high - low + 1));
  low = Math.max(0, low - Math.floor(missing / 2));
  high = Math.min(127, high + Math.ceil(missing / 2));
  while (isBlackKey(low) && low > 0) low -= 1;
  while (isBlackKey(high) && high < 127) high += 1;

  return {
    low,
    high,
    whiteKeys: Array.from({ length: high - low + 1 }, (_, index) => low + index).filter(
      (pitch) => !isBlackKey(pitch),
    ),
  };
}

export function getWaterfallMetrics(height: number): WaterfallMetrics {
  const keyboardHeight = Math.max(64, Math.min(92, height * 0.2));
  const strikeY = Math.max(1, height - keyboardHeight);
  return {
    keyboardHeight,
    strikeY,
    pixelsPerSecond: strikeY / VISIBLE_FUTURE_SECONDS,
  };
}

export function seekTimeFromCanvasY(
  canvasY: number,
  currentTime: number,
  height: number,
  duration: number,
): number {
  const { pixelsPerSecond, strikeY } = getWaterfallMetrics(height);
  const target = currentTime + (strikeY - canvasY) / pixelsPerSecond;
  return Math.max(0, Math.min(duration, target));
}

export function drawWaterfall(
  canvas: HTMLCanvasElement,
  notes: TimelineNote[],
  currentTime: number,
  reducedMotion: boolean,
): void {
  const bounds = canvas.getBoundingClientRect();
  const width = Math.round(bounds.width);
  const height = Math.round(bounds.height);
  if (width === 0 || height === 0) return;
  const context = canvas.getContext("2d");
  if (!context) return;

  const devicePixelRatio = Math.min(window.devicePixelRatio || 1, 2);
  const pixelWidth = Math.round(width * devicePixelRatio);
  const pixelHeight = Math.round(height * devicePixelRatio);
  if (canvas.width !== pixelWidth || canvas.height !== pixelHeight) {
    canvas.width = pixelWidth;
    canvas.height = pixelHeight;
  }
  context.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
  context.clearRect(0, 0, width, height);

  const range = getPianoRange(notes);
  const metrics = getWaterfallMetrics(height);
  const keyWidth = width / range.whiteKeys.length;
  const blackKeyWidth = keyWidth * 0.62;
  drawWaterfallScene(
    context,
    notes,
    currentTime,
    width,
    range,
    metrics,
    keyWidth,
    blackKeyWidth,
    reducedMotion,
  );
}
