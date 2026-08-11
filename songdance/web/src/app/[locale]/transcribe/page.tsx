import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { SiteHeader } from "@/components/site-header";
import { isAppLocale, type AppLocale } from "@/i18n/routing";
import { localeAlternates, localePath } from "@/lib/seo/locale";
import { TranscribeClient } from "../../transcribe/transcribe-client";

type PageProps = { params: Promise<{ locale: string }> };

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale: value } = await params;
  const locale: AppLocale = isAppLocale(value) ? value : "en";
  const t = await getTranslations({ locale, namespace: "transcribe" });
  return { title: t("title"), description: t("description"), alternates: localeAlternates(locale, "/transcribe"), openGraph: { url: localePath(locale, "/transcribe"), title: t("title"), description: t("description") } };
}

export default async function TranscribePage({ params }: PageProps) {
  const { locale: value } = await params;
  const locale: AppLocale = isAppLocale(value) ? value : "en";
  setRequestLocale(locale);
  const t = await getTranslations({ locale, namespace: "transcribe" });
  return <><SiteHeader /><main className="mx-auto w-full max-w-5xl px-5 pb-24 pt-10 sm:px-8 lg:px-10"><div className="max-w-2xl"><p className="text-xs font-bold uppercase text-[#147d70]">{t("eyebrow")}</p><h1 className="mt-3 font-display text-4xl leading-tight sm:text-5xl">{t("heading")}</h1><p className="mt-4 leading-7 text-[#61716c]">{t("intro")}</p></div><TranscribeClient /></main></>;
}
