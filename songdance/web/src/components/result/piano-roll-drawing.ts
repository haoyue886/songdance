import type { TimelineHand, TimelineNote } from "@/lib/result/timeline";
import { isBlackKey, type PianoRange, type WaterfallMetrics } from "./piano-roll-canvas";

type KeyPosition = { x: number; width: number };

export function drawWaterfallScene(
  context: CanvasRenderingContext2D,
  notes: TimelineNote[],
  currentTime: number,
  width: number,
  range: PianoRange,
  metrics: WaterfallMetrics,
  keyWidth: number,
  blackKeyWidth: number,
  reducedMotion: boolean,
): void {
  const whiteIndices = new Map(range.whiteKeys.map((pitch, index) => [pitch, index]));
  const activeHands = getActiveHands(notes, currentTime);

  drawBackground(context, width, metrics.strikeY, range, whiteIndices, keyWidth);
  drawNotes(
    context,
    notes,
    currentTime,
    width,
    metrics,
    whiteIndices,
    keyWidth,
    blackKeyWidth,
    reducedMotion,
  );
  drawStrikeLine(context, width, metrics.strikeY, reducedMotion);
  drawKeyboard(
    context,
    range,
    whiteIndices,
    activeHands,
    width,
    metrics,
    keyWidth,
    blackKeyWidth,
  );
}

function drawBackground(
  context: CanvasRenderingContext2D,
  width: number,
  strikeY: number,
  range: PianoRange,
  whiteIndices: Map<number, number>,
  keyWidth: number,
): void {
  context.fillStyle = "#101512";
  context.fillRect(0, 0, width, strikeY);
  for (const pitch of range.whiteKeys) {
    const index = whiteIndices.get(pitch);
    if (index === undefined) continue;
    const x = index * keyWidth;
    context.fillStyle = pitch % 12 === 0 ? "rgba(102, 210, 180, 0.045)" : "rgba(255,255,255,0.015)";
    context.fillRect(x, 0, keyWidth, strikeY);
    context.strokeStyle = "rgba(226, 243, 234, 0.08)";
    context.lineWidth = 1;
    context.beginPath();
    context.moveTo(x + 0.5, 0);
    context.lineTo(x + 0.5, strikeY);
    context.stroke();
  }
}

function drawNotes(
  context: CanvasRenderingContext2D,
  notes: TimelineNote[],
  currentTime: number,
  width: number,
  metrics: WaterfallMetrics,
  whiteIndices: Map<number, number>,
  keyWidth: number,
  blackKeyWidth: number,
  reducedMotion: boolean,
): void {
  context.save();
  context.beginPath();
  context.rect(0, 0, width, metrics.strikeY);
  context.clip();

  for (const note of notes) {
    const position = keyPosition(note.pitch, whiteIndices, keyWidth, blackKeyWidth);
    if (!position) continue;
    const height = Math.max(5, (note.end_sec - note.start_sec) * metrics.pixelsPerSecond);
    const bottom = metrics.strikeY + (currentTime - note.start_sec) * metrics.pixelsPerSecond;
    const y = bottom - height;
    if (bottom < 0 || y > metrics.strikeY) continue;

    const active = currentTime >= note.start_sec && currentTime < note.end_sec;
    const color = noteColor(note.hand);
    context.save();
    if (active && !reducedMotion) {
      context.shadowColor = color;
      context.shadowBlur = 20;
    }
    context.fillStyle = colorWithAlpha(color, noteOpacity(note.velocity, active));
    roundedRect(context, position.x + 1, y + 1, position.width - 2, height - 2, 4);
    context.fill();
    if (active) {
      context.fillStyle = "rgba(255,255,255,0.38)";
      roundedRect(context, position.x + 2, Math.max(y + 2, 0), position.width - 4, 3, 2);
      context.fill();
    }
    context.restore();
  }
  context.restore();
}

function drawStrikeLine(
  context: CanvasRenderingContext2D,
  width: number,
  strikeY: number,
  reducedMotion: boolean,
): void {
  const glow = context.createLinearGradient(0, strikeY - 26, 0, strikeY + 10);
  glow.addColorStop(0, "rgba(87, 235, 191, 0)");
  glow.addColorStop(0.72, "rgba(87, 235, 191, 0.3)");
  glow.addColorStop(1, "rgba(87, 235, 191, 0)");
  context.fillStyle = glow;
  context.fillRect(0, strikeY - 26, width, 36);
  context.save();
  if (!reducedMotion) {
    context.shadowColor = "rgba(87, 235, 191, 0.9)";
    context.shadowBlur = 15;
  }
  context.strokeStyle = "#b6ffdf";
  context.lineWidth = 2;
  context.beginPath();
  context.moveTo(0, strikeY);
  context.lineTo(width, strikeY);
  context.stroke();
  context.restore();
}

function drawKeyboard(
  context: CanvasRenderingContext2D,
  range: PianoRange,
  whiteIndices: Map<number, number>,
  activeHands: Map<number, TimelineHand>,
  width: number,
  metrics: WaterfallMetrics,
  keyWidth: number,
  blackKeyWidth: number,
): void {
  context.fillStyle = "#dce8e0";
  context.fillRect(0, metrics.strikeY, width, metrics.keyboardHeight);
  for (const pitch of range.whiteKeys) {
    const index = whiteIndices.get(pitch);
    if (index === undefined) continue;
    const activeHand = activeHands.get(pitch);
    const isActive = activeHands.has(pitch);
    const x = index * keyWidth;
    context.fillStyle = isActive ? keyFill(activeHand ?? null) : "#f6fbf7";
    context.fillRect(x, metrics.strikeY + 1, keyWidth - 1, metrics.keyboardHeight - 1);
    context.strokeStyle = "rgba(18, 37, 29, 0.35)";
    context.lineWidth = 1;
    context.strokeRect(x + 0.5, metrics.strikeY + 0.5, keyWidth - 1, metrics.keyboardHeight - 1);
    if (pitch % 12 === 0 && keyWidth > 18) {
      context.fillStyle = "#486057";
      context.font = "600 10px system-ui";
      context.textAlign = "center";
      context.fillText(noteName(pitch), x + keyWidth / 2, metrics.strikeY + metrics.keyboardHeight - 8);
    }
  }
  for (let pitch = range.low; pitch <= range.high; pitch += 1) {
    if (!isBlackKey(pitch)) continue;
    const position = keyPosition(pitch, whiteIndices, keyWidth, blackKeyWidth);
    if (!position) continue;
    const activeHand = activeHands.get(pitch);
    const isActive = activeHands.has(pitch);
    const blackHeight = metrics.keyboardHeight * 0.62;
    context.save();
    if (isActive) {
      context.shadowColor = keyFill(activeHand ?? null);
      context.shadowBlur = 12;
    }
    context.fillStyle = isActive ? keyFill(activeHand ?? null) : "#17201b";
    roundedRect(context, position.x, metrics.strikeY, position.width, blackHeight, 2);
    context.fill();
    context.restore();
  }
}

function getActiveHands(notes: TimelineNote[], currentTime: number): Map<number, TimelineHand> {
  return new Map(
    notes
      .filter((note) => currentTime >= note.start_sec && currentTime < note.end_sec)
      .map((note) => [note.pitch, note.hand]),
  );
}

function keyPosition(
  pitch: number,
  whiteIndices: Map<number, number>,
  keyWidth: number,
  blackKeyWidth: number,
): KeyPosition | null {
  if (!isBlackKey(pitch)) {
    const index = whiteIndices.get(pitch);
    return index === undefined ? null : { x: index * keyWidth, width: keyWidth };
  }
  let previousWhite = pitch - 1;
  while (isBlackKey(previousWhite)) previousWhite -= 1;
  const index = whiteIndices.get(previousWhite);
  return index === undefined
    ? null
    : { x: (index + 1) * keyWidth - blackKeyWidth / 2, width: blackKeyWidth };
}

function noteColor(hand: TimelineHand): string {
  if (hand === "left") return "#19b8d1";
  if (hand === "right") return "#20bd82";
  return "#8f9994";
}

function keyFill(hand: TimelineHand): string {
  if (hand === "left") return "#38d9ef";
  if (hand === "right") return "#42d9a0";
  return "#b6c0ba";
}

function colorWithAlpha(color: string, alpha: number): string {
  const value = color.replace("#", "");
  const red = Number.parseInt(value.slice(0, 2), 16);
  const green = Number.parseInt(value.slice(2, 4), 16);
  const blue = Number.parseInt(value.slice(4, 6), 16);
  return `rgba(${red}, ${green}, ${blue}, ${alpha})`;
}

function noteOpacity(velocity: number, active: boolean): number {
  const velocityOpacity = 0.5 + Math.min(127, Math.max(0, velocity)) / 127 * 0.34;
  return active ? Math.min(0.98, velocityOpacity + 0.14) : velocityOpacity;
}

function noteName(pitch: number): string {
  return `C${Math.floor(pitch / 12) - 1}`;
}

function roundedRect(
  context: CanvasRenderingContext2D,
  x: number,
  y: number,
  width: number,
  height: number,
  radius: number,
): void {
  const safeRadius = Math.max(0, Math.min(radius, width / 2, height / 2));
  context.beginPath();
  context.roundRect(x, y, Math.max(0, width), Math.max(0, height), safeRadius);
}
