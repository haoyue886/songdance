"use client";
import { useTranslations } from "next-intl";

export default function ErrorPage({ reset }: { reset: () => void }) {
  const t = useTranslations("errorPage");
  return <main className="grid min-h-screen place-items-center px-5 text-center"><div className="max-w-md rounded-lg border border-[#dce3dc] bg-white p-8 shadow-[var(--shadow)]"><p className="text-sm font-bold text-[#147d70]">{t("eyebrow")}</p><h1 className="mt-3 text-3xl font-bold">{t("title")}</h1><p className="mt-3 text-sm leading-6 text-[#64736f]">{t("body")}</p><button onClick={reset} className="mt-6 rounded-full bg-[#147d70] px-5 py-2.5 text-sm font-bold text-white">{t("retry")}</button></div></main>;
}
