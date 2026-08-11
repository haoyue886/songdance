import type { Metadata } from "next";
import Link from "next/link";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { ExampleClient } from "./example-client";

export const metadata: Metadata = {
  title: "Real Piano Audio to MIDI Transcription Example",
  description: "Hear a real public-domain piano recording and inspect its MIDI, MusicXML, PDF, sheet music and piano-roll transcription.",
  alternates: { canonical: "/examples" },
  openGraph: {
    type: "website",
    url: "/examples",
    title: "Real Piano Audio to MIDI Transcription Example",
    description: "Review a real piano transcription before converting your own recording.",
  },
  twitter: {
    card: "summary",
    title: "Real Piano Audio to MIDI Transcription Example",
    description: "Review a real piano transcription before converting your own recording.",
  },
};

export default function ExamplesPage() {
  return (
    <>
      <SiteHeader />
      <main className="mx-auto w-full max-w-7xl px-5 pb-20 pt-8 sm:px-8 lg:px-10">
        <section className="mb-10 border-b border-[#d9e3dd] pb-8">
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-[#147d70]">
            Public domain example
          </p>
          <h1 className="mt-3 font-display text-4xl font-bold leading-tight sm:text-5xl">
            先听一段真实钢琴转录
          </h1>
          <p className="mt-4 max-w-3xl leading-7 text-[#61716c]">
            W.A. Mozart C 大调奏鸣曲，取自 Wikimedia Commons 公共领域录音。下方内容由当前
            Basic Pitch 与乐谱管线真实生成，可直接播放、切换视图并下载三种格式。
          </p>
          <div className="mt-5 flex flex-wrap items-center gap-4 text-sm font-semibold">
            <a className="text-[#075e55] underline underline-offset-4"
              href="https://commons.wikimedia.org/wiki/File:%D0%92%D0%B0%D1%80%D0%B2%D0%B0%D1%80%D0%B0_%D0%A1%D0%B5%D0%BC%D0%B5%D0%BD%D1%87%D1%83%D0%BA_-_%D0%9C%D0%BE%D1%86%D0%B0%D1%80%D1%82-%D0%A1%D0%BE%D0%BD%D0%B0%D1%82%D0%B0-c-dur-part1.ogv"
              target="_blank" rel="noreferrer">
              查看录音来源与许可证
            </a>
            <Link className="text-[#075e55] underline underline-offset-4" href="/transcribe">
              转录你自己的音频
            </Link>
          </div>
        </section>
        <ExampleClient />
      </main>
      <SiteFooter />
    </>
  );
}
