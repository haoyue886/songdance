"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { ResultWorkspace } from "@/components/result/result-workspace";
import type { TranscriptionJob } from "@/lib/api/jobs";
import { parseTimeline, type NoteTimeline } from "@/lib/result/timeline";
import { buildExampleJob, type ExampleProvenance } from "./example-job";

const BASE_PATH = "/examples/mozart-sonata";

type ExampleState =
  | { status: "loading" }
  | { status: "error" }
  | { status: "ready"; timeline: NoteTimeline; musicXml: string; job: TranscriptionJob };

export function ExampleClient() {
  const t = useTranslations("result");
  const [state, setState] = useState<ExampleState>({ status: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    void Promise.all([
      fetch(`${BASE_PATH}/timeline.json`, { signal: controller.signal }).then(requireTimeline),
      fetch(`${BASE_PATH}/score.musicxml`, { signal: controller.signal }).then(requireOkText),
      fetch(`${BASE_PATH}/provenance.json`, { signal: controller.signal }).then(requireProvenance),
    ])
      .then(([timeline, musicXml, provenance]) =>
        setState({
          status: "ready",
          timeline,
          musicXml,
          job: buildExampleJob(timeline, provenance),
        }),
      )
      .catch(() => {
        if (!controller.signal.aborted) setState({ status: "error" });
      });
    return () => controller.abort();
  }, []);

  if (state.status === "loading") {
    return <div role="status" className="min-h-96 animate-pulse rounded-lg bg-white" />;
  }
  if (state.status === "error") {
    return (
      <p role="alert" className="rounded-lg border border-[#e4b9b3] bg-[#fff1ef] p-5 text-[#8d372f]">
        {t("exampleLoadError")}
      </p>
    );
  }
  return (
    <ResultWorkspace
      job={state.job}
      timeline={state.timeline}
      musicXml={state.musicXml}
      sourceUrl={`${BASE_PATH}/source.wav`}
      warning={null}
      artifactPaths={{ midi: `${BASE_PATH}/score.mid` }}
      trackEvents={false}
      shareable={false}
      expiresLabel={t("exampleAvailable")}
    />
  );
}

async function requireTimeline(response: Response): Promise<NoteTimeline> {
  if (!response.ok) throw new Error("Example timeline unavailable");
  return parseTimeline(await response.json());
}

async function requireOkText(response: Response): Promise<string> {
  if (!response.ok) throw new Error("Example score unavailable");
  return response.text();
}

async function requireProvenance(response: Response): Promise<ExampleProvenance> {
  if (!response.ok) throw new Error("Example provenance unavailable");
  return (await response.json()) as ExampleProvenance;
}
