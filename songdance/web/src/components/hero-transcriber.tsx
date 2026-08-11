import { getTranslations } from "next-intl/server";
import { Link } from "@/i18n/navigation";

export async function HeroTranscriber() {
  const t = await getTranslations("home");
  const limits = [t("limitPiano"), t("limitDuration"), t("limitDelete")];
  return (
    <section className="mx-auto grid w-full max-w-7xl grid-cols-1 overflow-x-clip px-5 pb-24 pt-14 sm:px-8 lg:grid-cols-[minmax(0,0.92fr)_minmax(0,1.08fr)] lg:items-center lg:gap-12 lg:px-10 lg:pt-20">
      <div className="min-w-0 max-w-2xl">
        <p className="mb-5 inline-flex items-center gap-2 rounded-full border border-[#c9dfd7] bg-white/65 px-3 py-1.5 text-xs font-bold uppercase text-[#147d70]">
          <span className="size-1.5 rounded-full bg-[#147d70]" />{t("eyebrow")}
        </p>
        <h1 className="font-display text-5xl leading-[1.02] text-[#15332f] sm:text-6xl lg:text-7xl">{t("heading")}</h1>
        <p className="mt-7 max-w-xl text-lg leading-8 text-[#53645f] sm:text-xl">{t("intro")}</p>
        <div className="mt-8 flex flex-wrap gap-2.5" aria-label={t("limitsLabel")}>
          {limits.map((limit) => <span key={limit} className="rounded-full bg-[#e5eee9] px-3 py-1.5 text-sm font-semibold text-[#48605a]">{limit}</span>)}
        </div>
      </div>
      <div className="relative mt-12 min-w-0 lg:mt-0">
        <div className="min-w-0 overflow-hidden rounded-lg border border-white/85 bg-white p-3 shadow-[var(--shadow)] sm:p-5">
          <div className="min-w-0 overflow-hidden rounded-lg border border-dashed border-[#a9c9bf] bg-[#fbfcf8] px-4 py-14 text-center sm:px-10 sm:py-16">
            <span className="mx-auto grid size-16 place-items-center rounded-lg bg-[#dff0e9] text-3xl text-[#147d70]">↑</span>
            <h2 className="mt-5 text-lg font-bold sm:text-xl">{t("uploadTitle")}</h2>
            <p className="mx-auto mt-2 max-w-sm text-sm leading-6 text-[#6a7975]">{t("uploadBody")}</p>
            <div className="mt-6 flex flex-wrap justify-center gap-3">
              <Link href="/transcribe" className="inline-flex min-h-11 items-center rounded-full bg-[#147d70] px-5 text-sm font-bold text-white hover:bg-[#075e55]">{t("primaryCta")}</Link>
              <Link href="/examples" className="inline-flex min-h-11 items-center rounded-full border border-[#b9cdc6] px-5 text-sm font-bold text-[#075e55] hover:border-[#147d70]">{t("secondaryCta")}</Link>
            </div>
          </div>
          <div className="mt-3 grid grid-cols-3 gap-2">
            {["MIDI", "MusicXML", "PDF"].map((format) => <div key={format} className="rounded-lg bg-[#f2f5f1] px-3 py-3 text-center text-xs font-bold text-[#57706a]">{format}</div>)}
          </div>
          <p className="px-2 pb-1 pt-4 text-center text-xs leading-5 text-[#6a7975]">{t("rights")}</p>
        </div>
      </div>
    </section>
  );
}
