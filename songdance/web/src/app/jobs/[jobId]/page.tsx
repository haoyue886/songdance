import type { Metadata } from "next";
import { SiteHeader } from "@/components/site-header";
import { JobStatusClient } from "./job-status-client";

export const metadata: Metadata = {
  title: "转录任务",
  description: "查看钢琴转录任务状态。",
  robots: { index: false, follow: false, nocache: true },
  openGraph: null,
  twitter: null,
};

export default async function JobPage({
  params,
}: {
  params: Promise<{ jobId: string }>;
}) {
  const { jobId } = await params;
  return (
    <>
      <SiteHeader />
      <main className="mx-auto w-full max-w-7xl px-5 pb-24 pt-10 sm:px-8 lg:px-10">
        <JobStatusClient jobId={jobId} />
      </main>
    </>
  );
}
