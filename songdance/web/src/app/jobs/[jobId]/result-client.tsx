"use client";

import { useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { ResultWorkspace } from "@/components/result/result-workspace";
import { fetchArtifact, getDownloadUrl, type TranscriptionJob } from "@/lib/api/jobs";
import { fetchTimeline, type NoteTimeline } from "@/lib/result/timeline";
import { parseQualityReport } from "@/lib/result/quality-report";

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | {
      status: "ready";
      timeline: NoteTimeline;
      musicXml: string | null;
      sourceUrl: string;
      warning: string | null;
      previewKind: "cleaned" | "raw";
    };

export function ResultClient({
  job,
  deleting,
  onDelete,
}: {
  job: TranscriptionJob;
  deleting: boolean;
  onDelete: () => void;
}) {
  const t = useTranslations("result");
  const errors = useTranslations("errors");
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const sourceRefreshPending = useRef(false);
  const lastSourceRefreshAt = useRef(0);

  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      try {
        const qualityReport = parseQualityReport(job.quality_report);
        const cleanupFallback = qualityReport?.cleanup.fallbackUsed === true;
        const cleanedTimeline = job.artifacts.some(
          (artifact) => artifact.type === "timeline" && artifact.status === "succeeded",
        );
        const rawTimeline = job.artifacts.some(
          (artifact) => artifact.type === "raw_timeline" && artifact.status === "succeeded",
        );
        const useRawTimeline = rawTimeline && (cleanupFallback || !cleanedTimeline);
        const [timeline, sourceUrl] = await Promise.all([
          fetchTimeline(job.id, useRawTimeline ? "raw_timeline" : "timeline", controller.signal),
          getDownloadUrl(job.id, "source", controller.signal),
        ]);
        const musicXmlArtifact = useRawTimeline || cleanupFallback
          ? undefined
          : job.artifacts.find(
              (artifact) => artifact.type === "musicxml" && artifact.status === "succeeded",
            );
        let musicXml: string | null = null;
        const warnings: string[] = [];
        if (cleanupFallback) {
          warnings.push(t("rawCleanupWarning"));
        } else if (useRawTimeline) {
          warnings.push(t("rawTimelineWarning"));
        }
        if (musicXmlArtifact) {
          try {
            musicXml = await (await fetchArtifact(job.id, "musicxml", controller.signal)).text();
          } catch {
            warnings.push(t("scoreReadWarning"));
          }
        } else if (
          job.artifacts.some(
            (artifact) => artifact.type === "musicxml" && artifact.status === "failed",
          )
        ) {
          warnings.push(t("scoreGenerationWarning"));
        }
        setState({
          status: "ready",
          timeline,
          musicXml,
          sourceUrl,
          warning: warnings.length > 0 ? warnings.join(" ") : null,
          previewKind: useRawTimeline || cleanupFallback ? "raw" : "cleaned",
        });
      } catch {
        if (!controller.signal.aborted) {
          setState({
            status: "error",
            message: errors("service"),
          });
        }
      }
    })();
    return () => controller.abort();
  }, [errors, job, t]);

  const refreshSourceUrl = async () => {
    const now = Date.now();
    if (sourceRefreshPending.current || now - lastSourceRefreshAt.current < 5_000) return;
    sourceRefreshPending.current = true;
    lastSourceRefreshAt.current = now;
    try {
      const sourceUrl = await getDownloadUrl(job.id, "source");
      setState((current) =>
        current.status === "ready" ? { ...current, sourceUrl } : current,
      );
    } catch {
      setState((current) =>
        current.status === "ready"
          ? { ...current, warning: t("sourceRefreshWarning") }
          : current,
      );
    } finally {
      sourceRefreshPending.current = false;
    }
  };

  if (state.status === "loading") {
    return (
      <section className="grid min-h-[420px] place-items-center" role="status">
        <div className="w-full max-w-xl animate-pulse space-y-4" aria-label={t("resultLoading")}>
          <div className="h-8 w-2/3 rounded bg-[#dfe9e3]" />
          <div className="h-72 rounded-lg bg-white" />
          <div className="h-16 rounded-lg bg-white" />
        </div>
      </section>
    );
  }
  if (state.status === "error") {
    return (
      <section className="mx-auto max-w-xl rounded-lg border border-[#e4b9b3] bg-[#fff1ef] p-6" role="alert">
        <h1 className="font-display text-3xl font-bold text-[#8d372f]">{t("resultFailed")}</h1>
        <p className="mt-3 leading-7 text-[#70534f]">{state.message}</p>
      </section>
    );
  }
  return (
    <ResultWorkspace
      job={job}
      timeline={state.timeline}
      musicXml={state.musicXml}
      sourceUrl={state.sourceUrl}
      warning={state.warning}
      previewKind={state.previewKind}
      deleting={deleting}
      onDelete={onDelete}
      onSourceError={() => void refreshSourceUrl()}
    />
  );
}
