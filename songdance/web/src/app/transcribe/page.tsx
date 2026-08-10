import type { Metadata } from "next";
import { SiteHeader } from "@/components/site-header";
import { TranscribeClient } from "./transcribe-client";

export const metadata: Metadata = {
  title: "准备钢琴转录片段 — SongDance",
  description: "上传钢琴录音并选择最长 90 秒的转录片段。",
};

export default function TranscribePage() {
  return (
    <>
      <SiteHeader />
      <main className="mx-auto w-full max-w-5xl px-5 pb-24 pt-10 sm:px-8 lg:px-10">
        <div className="max-w-2xl">
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#147d70]">Prepare audio</p>
          <h1 className="mt-3 font-display text-4xl leading-tight tracking-[-0.04em] sm:text-5xl">准备一段干净的钢琴录音</h1>
          <p className="mt-4 leading-7 text-[#61716c]">先在浏览器内校验和截取，只有确认片段后才会进入转录任务。</p>
        </div>
        <TranscribeClient />
      </main>
    </>
  );
}
