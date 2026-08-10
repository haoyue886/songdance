import { Frequency, PolySynth, Sampler, Synth, now, start } from "tone";
import type { TimelineNote } from "@/lib/result/timeline";

const PIANO_SAMPLE_BASE_URL = "/audio/piano/";

export const PIANO_SAMPLE_URLS = {
  A0: "A0.mp3",
  C1: "C1.mp3",
  "D#1": "Ds1.mp3",
  "F#1": "Fs1.mp3",
  A1: "A1.mp3",
  C2: "C2.mp3",
  "D#2": "Ds2.mp3",
  "F#2": "Fs2.mp3",
  A2: "A2.mp3",
  C3: "C3.mp3",
  "D#3": "Ds3.mp3",
  "F#3": "Fs3.mp3",
  A3: "A3.mp3",
  C4: "C4.mp3",
  "D#4": "Ds4.mp3",
  "F#4": "Fs4.mp3",
  A4: "A4.mp3",
  C5: "C5.mp3",
  "D#5": "Ds5.mp3",
  "F#5": "Fs5.mp3",
  A5: "A5.mp3",
  C6: "C6.mp3",
  "D#6": "Ds6.mp3",
  "F#6": "Fs6.mp3",
  A6: "A6.mp3",
  C7: "C7.mp3",
  "D#7": "Ds7.mp3",
  "F#7": "Fs7.mp3",
  A7: "A7.mp3",
  C8: "C8.mp3",
} as const;

export type PlaybackResult = "piano" | "synth-fallback" | "cancelled";

function createFallbackSynth() {
  return new PolySynth(Synth);
}

export class TimelineMidiPlayer {
  private piano: Sampler | null = null;
  private pianoLoad: Promise<Sampler> | null = null;
  private fallback: ReturnType<typeof createFallbackSynth> | null = null;
  private requestId = 0;
  private disposed = false;

  async play(
    notes: TimelineNote[],
    from: number,
    to: number,
    rate: number,
  ): Promise<PlaybackResult> {
    const requestId = ++this.requestId;
    this.releaseAll();
    await start();
    if (!this.isActive(requestId)) return "cancelled";
    let instrument: Sampler | ReturnType<typeof createFallbackSynth>;
    let timbre: PlaybackResult = "piano";
    try {
      instrument = await this.loadPiano();
    } catch {
      if (!this.isActive(requestId)) return "cancelled";
      this.fallback ??= createFallbackSynth();
      instrument = this.fallback;
      timbre = "synth-fallback";
    }
    if (!this.isActive(requestId)) return "cancelled";
    instrument.toDestination();
    const baseTime = now() + 0.04;
    for (const note of notes) {
      if (note.end_sec <= from || note.start_sec >= to) continue;
      const onset = Math.max(note.start_sec, from);
      const release = Math.min(note.end_sec, to);
      const delay = (onset - from) / rate;
      const duration = Math.max(0.03, (release - onset) / rate);
      instrument.triggerAttackRelease(
        Frequency(note.pitch, "midi").toFrequency(),
        duration,
        baseTime + delay,
        note.velocity / 127,
      );
    }
    return timbre;
  }

  stop(): void {
    this.requestId += 1;
    this.releaseAll();
  }

  private releaseAll(): void {
    this.piano?.releaseAll();
    this.piano?.disconnect();
    this.fallback?.dispose();
    this.fallback = null;
  }

  dispose(): void {
    this.disposed = true;
    this.stop();
    this.piano?.dispose();
    this.fallback?.dispose();
    this.piano = null;
    this.fallback = null;
    this.pianoLoad = null;
  }

  private loadPiano(): Promise<Sampler> {
    if (this.piano) return Promise.resolve(this.piano);
    if (this.pianoLoad) return this.pianoLoad;

    this.pianoLoad = new Promise<Sampler>((resolve, reject) => {
      const sampler = new Sampler({
        urls: PIANO_SAMPLE_URLS,
        baseUrl: PIANO_SAMPLE_BASE_URL,
        attack: 0,
        release: 1.2,
        onload: () => {
          if (this.disposed) {
            sampler.dispose();
            this.pianoLoad = null;
            reject(new Error("播放器已释放"));
            return;
          }
          this.piano = sampler;
          resolve(sampler);
        },
        onerror: (error) => {
          sampler.dispose();
          this.pianoLoad = null;
          reject(error);
        },
      });
    });
    return this.pianoLoad;
  }

  private isActive(requestId: number): boolean {
    return !this.disposed && requestId === this.requestId;
  }
}
