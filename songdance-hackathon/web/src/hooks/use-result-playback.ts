"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { TimelineMidiPlayer } from "@/lib/midi/player";
import { transposeTimeline } from "@/lib/export/transpose";
import { timelineDuration, type NoteTimeline } from "@/lib/result/timeline";

export type PlaybackMode = "source" | "midi";

export function useResultPlayback(timeline: NoteTimeline) {
  const duration = timelineDuration(timeline);
  const audioRef = useRef<HTMLAudioElement>(null);
  const midiRef = useRef<TimelineMidiPlayer | null>(null);
  const timelineRef = useRef(timeline);
  const currentRef = useRef(0);
  const playingRef = useRef(false);
  const selectionRef = useRef<{ start: number; end: number } | null>(null);
  const anchorRef = useRef({ wallTime: 0, timelineTime: 0 });
  const configRef = useRef({
    mode: "midi" as PlaybackMode,
    rate: 1,
    loopEnabled: false,
    loopStart: 0,
    loopEnd: duration,
    transpose: 0,
  });
  const [mode, setMode] = useState<PlaybackMode>("midi");
  const [playing, setPlayingState] = useState(false);
  const [currentTime, setCurrentTimeState] = useState(0);
  const [rate, setRate] = useState(1);
  const [loopEnabled, setLoopEnabled] = useState(false);
  const [loopStart, setLoopStart] = useState(0);
  const [loopEnd, setLoopEnd] = useState(duration);
  const [transpose, setTranspose] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [selection, setSelectionState] = useState<{ start: number; end: number } | null>(null);

  useEffect(() => {
    const midi = new TimelineMidiPlayer();
    const audio = audioRef.current;
    midiRef.current = midi;
    return () => {
      audio?.pause();
      midi.dispose();
      if (midiRef.current === midi) midiRef.current = null;
    };
  }, []);

  useEffect(() => {
    timelineRef.current = timeline;
  }, [timeline]);

  useEffect(() => {
    configRef.current = { mode, rate, loopEnabled, loopStart, loopEnd, transpose };
  }, [loopEnabled, loopEnd, loopStart, mode, rate, transpose]);

  const setPlaying = useCallback((value: boolean) => {
    playingRef.current = value;
    setPlayingState(value);
  }, []);

  const setCurrentTime = useCallback((value: number) => {
    currentRef.current = value;
    setCurrentTimeState(value);
  }, []);

  const setSelection = useCallback((start: number, end: number) => {
    const nextStart = Math.max(0, Math.min(start, duration - 0.1));
    const nextEnd = Math.min(duration, Math.max(end, nextStart + 0.1));
    const next = { start: nextStart, end: nextEnd };
    selectionRef.current = next;
    setSelectionState(next);
    setLoopStart(nextStart);
    setLoopEnd(nextEnd);
    setCurrentTime(nextStart);
  }, [duration, setCurrentTime]);

  const clearSelection = useCallback(() => {
    selectionRef.current = null;
    setSelectionState(null);
    setLoopStart(0);
    setLoopEnd(duration);
  }, [duration]);

  const stopEngines = useCallback(() => {
    audioRef.current?.pause();
    midiRef.current?.stop();
  }, []);

  const startAt = useCallback(
    async (at: number) => {
      const config = configRef.current;
      const selectionState = selectionRef.current;
      const startBoundary = selectionState?.start ?? (config.loopEnabled ? config.loopStart : 0);
      const boundary = selectionState?.end ?? (config.loopEnabled ? config.loopEnd : duration);
      const next = Math.max(startBoundary, Math.min(at, boundary));
      stopEngines();
      setError(null);
      try {
        if (config.mode === "source") {
          const audio = audioRef.current;
          if (!audio) throw new Error("原音频播放器尚未就绪。");
          audio.currentTime = next;
          audio.playbackRate = config.rate;
          await audio.play();
        } else {
          const midi = midiRef.current;
          if (!midi) throw new Error("转录演奏播放器尚未就绪。");
          const shifted = transposeTimeline(timelineRef.current, config.transpose);
          const timbre = await midi.play(shifted.notes, next, boundary, config.rate);
          if (timbre === "cancelled") return false;
          if (timbre === "synth-fallback") {
            setError("钢琴采样加载失败，当前使用基础合成音。");
          }
          anchorRef.current = { wallTime: performance.now(), timelineTime: next };
        }
        setCurrentTime(next);
        setPlaying(true);
        return true;
      } catch (playbackError) {
        stopEngines();
        setPlaying(false);
        setError(playbackError instanceof Error ? playbackError.message : "播放器启动失败。");
        return false;
      }
    },
    [duration, setCurrentTime, setPlaying, stopEngines],
  );

  const pause = useCallback(() => {
    const config = configRef.current;
    if (config.mode === "source" && audioRef.current) {
      setCurrentTime(audioRef.current.currentTime);
    } else if (playingRef.current) {
      const elapsed = ((performance.now() - anchorRef.current.wallTime) / 1000) * config.rate;
      setCurrentTime(Math.min(duration, anchorRef.current.timelineTime + elapsed));
    }
    stopEngines();
    setPlaying(false);
  }, [duration, setCurrentTime, setPlaying, stopEngines]);

  const seek = useCallback(
    (seconds: number) => {
      const next = Math.max(0, Math.min(duration, seconds));
      setCurrentTime(next);
      if (audioRef.current) audioRef.current.currentTime = next;
      if (playingRef.current) void startAt(next);
    },
    [duration, setCurrentTime, startAt],
  );

  useEffect(() => {
    if (playingRef.current) void startAt(currentRef.current);
  }, [loopEnabled, loopEnd, loopStart, mode, rate, selection, startAt, transpose]);

  useEffect(() => {
    if (!playing) return;
    const tick = window.setInterval(() => {
      const config = configRef.current;
      const value =
        config.mode === "source" && audioRef.current
          ? audioRef.current.currentTime
          : anchorRef.current.timelineTime +
            ((performance.now() - anchorRef.current.wallTime) / 1000) * config.rate;
      const selectionState = selectionRef.current;
      const boundary = selectionState?.end ?? (config.loopEnabled ? config.loopEnd : duration);
      if (value >= boundary - 0.02) {
        if (config.loopEnabled) void startAt(selectionState?.start ?? config.loopStart);
        else {
          stopEngines();
          setCurrentTime(boundary);
          setPlaying(false);
        }
      } else {
        setCurrentTime(value);
      }
    }, 50);
    return () => window.clearInterval(tick);
  }, [duration, playing, setCurrentTime, setPlaying, startAt, stopEngines]);

  return {
    audioRef,
    duration,
    mode,
    setMode,
    playing,
    play: () => {
      const selected = selectionRef.current;
      const start = selected?.start ?? (currentRef.current >= duration ? 0 : currentRef.current);
      return startAt(start);
    },
    pause,
    currentTime,
    seek,
    rate,
    setRate,
    loopEnabled,
    setLoopEnabled,
    loopStart,
    setLoopStart: (value: number) => setLoopStart(Math.max(0, Math.min(value, loopEnd - 0.5))),
    loopEnd,
    setLoopEnd: (value: number) =>
      setLoopEnd(Math.min(duration, Math.max(value, loopStart + 0.5))),
    transpose,
    setTranspose,
    error,
    selection,
    setSelection,
    clearSelection,
  };
}
