"use client";

import { BarChart3, Check, Copy, Music2 } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useResultPlayback } from "@/hooks/use-result-playback";
import { trackEvent } from "@/lib/analytics/events";
import { fetchArtifact, type TranscriptionJob } from "@/lib/api/jobs";
import { downloadBytes } from "@/lib/export/download";
import { transposeMidi } from "@/lib/export/midi";
import { createScorePdf } from "@/lib/export/pdf";
import { transposeMusicXml, transposeTimeline } from "@/lib/export/transpose";
import { parseQualityReport } from "@/lib/result/quality-report";
import type { NoteTimeline } from "@/lib/result/timeline";
import { ArtifactDownloads } from "./artifact-downloads";
import { PianoRoll } from "./piano-roll";
import { QualitySummary, VersionSummary } from "./quality-summary";
import { ScoreViewer } from "./score-viewer";
import { TaskSummary } from "./task-summary";
import { Transport } from "./transport";

export function ResultWorkspace({
  job,
  timeline,
  musicXml,
  sourceUrl,
  warning,
  previewKind = "cleaned",
  deleting = false,
  onDelete,
  onSourceError,
  artifactPaths,
  trackEvents = true,
  expiresLabel,
  shareable = true,
}: {
  job: TranscriptionJob;
  timeline: NoteTimeline;
  musicXml: string | null;
  sourceUrl: string;
  warning: string | null;
  previewKind?: "cleaned" | "raw";
  deleting?: boolean;
  onDelete?: () => void;
  onSourceError?: () => void;
  artifactPaths?: { midi?: string };
  trackEvents?: boolean;
  expiresLabel?: string;
  shareable?: boolean;
}) {
  const t = useTranslations("result");
  const errors = useTranslations("errors");
  const locale = useLocale();
  const {
    audioRef,
    duration,
    mode,
    setMode,
    playing,
    play,
    pause,
    currentTime,
    seek,
    rate,
    setRate,
    loopEnabled,
    setLoopEnabled,
    loopStart,
    setLoopStart,
    loopEnd,
    setLoopEnd,
    transpose,
    setTranspose,
    error: playbackError,
    selection,
    setSelection,
    clearSelection,
  } = useResultPlayback(timeline);
  const initialView = musicXml ? "score" : "roll";
  const qualityReport = useMemo(
    () => parseQualityReport(job.quality_report),
    [job.quality_report],
  );
  const [view, setView] = useState<"score" | "roll">(initialView);
  const [scoreContainer, setScoreContainer] = useState<HTMLDivElement | null>(null);
  const [busy, setBusy] = useState<"raw_midi" | "midi" | "musicxml" | "pdf" | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  const [shareState, setShareState] = useState<"idle" | "copied" | "error">("idle");
  const shiftedTimeline = useMemo(
    () => transposeTimeline(timeline, transpose),
    [timeline, transpose],
  );
  const shiftedMusicXml = useMemo(
    () => (musicXml ? transposeMusicXml(musicXml, transpose) : null),
    [musicXml, transpose],
  );
  const onScoreRendered = useCallback((container: HTMLDivElement | null) => {
    setScoreContainer(container);
  }, []);

  useEffect(() => {
    if (trackEvents) trackEvent(job.id, "result_viewed", { view: initialView });
  }, [initialView, job.id, trackEvents]);

  const changeView = (nextView: "score" | "roll") => {
    setView(nextView);
    if (trackEvents) trackEvent(job.id, "view_changed", { view: nextView });
  };

  const download = async (kind: "raw_midi" | "midi" | "musicxml" | "pdf") => {
    setBusy(kind);
    setExportError(null);
    try {
      if (kind === "midi" || kind === "raw_midi") {
        const response = artifactPaths?.midi
          ? await fetch(artifactPaths.midi, { cache: "force-cache" })
          : await fetchArtifact(job.id, kind);
        if (!response.ok) throw new Error("MIDI unavailable");
        const source = await response.arrayBuffer();
        downloadBytes(
          kind === "midi" ? transposeMidi(source, transpose) : source,
          "audio/midi",
          fileName(job.id, "mid"),
        );
      } else if (kind === "musicxml") {
        if (!shiftedMusicXml) throw new Error("MusicXML unavailable");
        downloadBytes(
          shiftedMusicXml,
          "application/vnd.recordare.musicxml+xml",
          fileName(job.id, "musicxml"),
        );
      } else {
        if (!scoreContainer) throw new Error("Score unavailable");
        const pdf = await createScorePdf("SongDance Piano Transcription", scoreContainer);
        downloadBytes(pdf, "application/pdf", fileName(job.id, "pdf"));
      }
      if (trackEvents) trackEvent(job.id, "format_downloaded", { format: kind });
    } catch {
      setExportError(errors("service"));
    } finally {
      setBusy(null);
    }
  };

  const copyShareLink = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setShareState("copied");
    } catch {
      setShareState("error");
    }
  };

  return (
    <section className="min-w-0">
      <audio
        ref={audioRef}
        src={sourceUrl}
        preload="metadata"
        className="hidden"
        onError={onSourceError}
      />
      <div className="flex flex-wrap items-end justify-between gap-3 border-b border-[#d9e3dd] pb-5">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-[#147d70]">
            {t("title")}
          </p>
          <h1 className="mt-2 font-display text-3xl font-bold leading-tight sm:text-4xl">
            {t("title")}
          </h1>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-3 text-sm text-[#61716c]">
          <p>{expiresLabel ?? t("savedUntil", { date: formatDate(job.expires_at, locale) })}</p>
          {shareable && (
            <button type="button" onClick={() => void copyShareLink()}
              className="inline-flex h-9 items-center gap-2 rounded-md border border-[#cad8d2] bg-white px-3 font-bold text-[#075e55]">
              {shareState === "copied" ? <Check size={15} /> : <Copy size={15} />}
              {shareState === "copied" ? t("copiedLink") : t("copyLink")}
            </button>
          )}
        </div>
      </div>

      <QualitySummary report={qualityReport} />

      <div className="mt-6 grid min-w-0 gap-6 lg:grid-cols-[190px_minmax(0,1fr)_220px]">
        <TaskSummary job={job} qualityFlags={timeline.quality_flags} />
        <div className="min-w-0">
          <div
            className="mb-3 flex w-fit rounded-md border border-[#cad8d2] bg-white p-0.5"
            role="tablist"
            aria-label={t("views")}
          >
            <ViewTab active={view === "score"} disabled={!musicXml} icon={<Music2 size={16} />}
              label={t("score")} onClick={() => changeView("score")} />
            <ViewTab active={view === "roll"} icon={<BarChart3 size={16} />}
              label={t("pianoRoll")} onClick={() => changeView("roll")} />
          </div>
          <p className="mb-3 text-xs font-semibold text-[#61716c]">
            {previewKind === "cleaned" ? t("cleanedPreview") : t("rawPreview")}
          </p>
          {view === "score" && shiftedMusicXml ? (
            <>
              <div className="sticky top-2 z-10 mb-3">
                <Transport mode={mode} onMode={setMode} playing={playing}
                  onPlay={() => {
                    void play().then((started) => {
                      if (started && trackEvents) trackEvent(job.id, "playback_started", { mode });
                    });
                  }} onPause={pause}
                  currentTime={currentTime} duration={duration} onSeek={seek}
                  rate={rate} onRate={setRate} loopEnabled={loopEnabled}
                  onLoopEnabled={setLoopEnabled} loopStart={loopStart} loopEnd={loopEnd}
                  onLoopStart={setLoopStart} onLoopEnd={setLoopEnd}
                  transpose={transpose} onTranspose={setTranspose}
                  selection={selection} onClearSelection={clearSelection} />
              </div>
              <ScoreViewer musicXml={shiftedMusicXml} currentTime={currentTime}
                timeline={shiftedTimeline} selection={selection} onSeek={seek}
                onSelectionChange={(next) => {
                  if (next) setSelection(next.start, next.end);
                  else clearSelection();
                }}
                onRendered={onScoreRendered} />
            </>
          ) : (
            <PianoRoll timeline={shiftedTimeline} currentTime={currentTime}
              duration={duration} onSeek={seek} />
          )}
          {view !== "score" && <div className="mt-3">
            <Transport mode={mode} onMode={setMode} playing={playing}
              onPlay={() => {
                void play().then((started) => {
                  if (started && trackEvents) trackEvent(job.id, "playback_started", { mode });
                });
              }} onPause={pause}
              currentTime={currentTime} duration={duration}
              onSeek={seek} rate={rate} onRate={setRate}
              loopEnabled={loopEnabled} onLoopEnabled={setLoopEnabled}
              loopStart={loopStart} loopEnd={loopEnd}
              onLoopStart={setLoopStart} onLoopEnd={setLoopEnd}
              transpose={transpose} onTranspose={setTranspose}
              selection={selection} onClearSelection={clearSelection} />
          </div>}
        </div>
        <div className="grid content-start gap-6">
          <ArtifactDownloads artifacts={job.artifacts} busy={busy}
            musicXmlReady={Boolean(shiftedMusicXml)}
            pdfReady={Boolean(scoreContainer && shiftedMusicXml)}
            onDownload={(kind) => void download(kind)} />
          <VersionSummary report={qualityReport} timeline={timeline} />
          {onDelete && (
            <button type="button" disabled={deleting} onClick={onDelete}
              className="text-left text-sm font-bold text-[#9a493f] underline decoration-[#d7aaa4] underline-offset-4 disabled:opacity-50">
              {deleting ? t("deleting") : t("delete")}
            </button>
          )}
        </div>
      </div>

      {(playbackError || exportError || warning) && (
        <p role="alert" className="mt-4 rounded-lg border border-[#e4b9b3] bg-[#fff1ef] p-3 text-sm text-[#8d372f]">
          {playbackError ? errors("service") : exportError ?? warning}
        </p>
      )}
      {shareState === "error" && (
        <p role="alert" className="mt-4 text-sm text-[#8d372f]">
          {t("copyFailed")}
        </p>
      )}
    </section>
  );
}

function ViewTab({ active, disabled = false, icon, label, onClick }: {
  active: boolean; disabled?: boolean; icon: React.ReactNode; label: string; onClick: () => void;
}) {
  return (
    <button type="button" role="tab" aria-selected={active} disabled={disabled}
      className={`flex h-9 items-center gap-2 rounded px-3 text-sm font-bold ${active ? "bg-[#d9efe7] text-[#075e55]" : "text-[#667772]"} disabled:opacity-40`}
      onClick={onClick}>
      {icon} {label}
    </button>
  );
}

function fileName(jobId: string, extension: string): string {
  return `songdance-${jobId.slice(0, 8)}.${extension}`;
}

function formatDate(value: string, locale: string): string {
  return new Intl.DateTimeFormat(locale, {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  }).format(new Date(value));
}
