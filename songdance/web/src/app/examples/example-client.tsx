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
  | {
      status: "ready";
      timeline: NoteTimeline;
      musicXml: string;
      job: TranscriptionJob;
      provenance: ExampleProvenance;
    };

export function ExampleClient() {
  const t = useTranslations("result");
  const examples = useTranslations("examples");
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
          provenance,
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
  const reviewLabel = (status: ExampleProvenance["review_status"]) =>
    status === "pending"
      ? examples("reviewPending")
      : status === "minor_edits"
        ? examples("reviewMinorEdits")
        : examples("reviewDirectUse");
  return (
    <>
      <section
        aria-label={examples("provenance")}
        className="mb-6 border-y border-[#d9e3dd] bg-[#f5f8f6] px-4 py-4 sm:px-5"
      >
        <dl className="grid gap-4 text-sm sm:grid-cols-3">
          <ProvenanceFact label={examples("currentReview")} value={reviewLabel(state.provenance.review_status)} />
          <ProvenanceFact
            label={examples("completedReview")}
            value={reviewLabel(state.provenance.latest_completed_review.rating)}
          />
          <div>
            <dt className="font-bold text-[#31443f]">{examples("sourcePrefix")}</dt>
            <dd className="mt-1 flex flex-wrap gap-x-2 text-[#52635f]">
              <a
                className="font-semibold text-[#075e55] underline underline-offset-4"
                href={state.provenance.source_page}
                rel="noreferrer"
                target="_blank"
              >
                {examples("sourceLink")}
              </a>
              <a
                className="underline decoration-[#9cafaa] underline-offset-4"
                href={state.provenance.license_url}
                rel="noreferrer"
                target="_blank"
              >
                {state.provenance.license}
              </a>
            </dd>
          </div>
        </dl>
      </section>
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
    </>
  );
}

function ProvenanceFact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="font-bold text-[#31443f]">{label}</dt>
      <dd className="mt-1 text-[#52635f]">{value}</dd>
    </div>
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
