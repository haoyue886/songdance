import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { SiteHeader } from "@/components/site-header";
import { isAppLocale, type AppLocale } from "@/i18n/routing";
import { JobStatusClient } from "../../../jobs/[jobId]/job-status-client";

type PageProps = { params: Promise<{ locale: string; jobId: string }> };
export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale: value } = await params;
  const locale: AppLocale = isAppLocale(value) ? value : "en";
  const t = await getTranslations({ locale, namespace: "job" });
  return { title: t("title"), description: t("description"), robots: { index: false, follow: false, nocache: true }, openGraph: null, twitter: null };
}
export default async function JobPage({ params }: PageProps) {
  const { locale: value, jobId } = await params;
  const locale: AppLocale = isAppLocale(value) ? value : "en";
  setRequestLocale(locale);
  return <><SiteHeader /><main className="mx-auto w-full max-w-7xl px-5 pb-24 pt-10 sm:px-8 lg:px-10"><JobStatusClient jobId={jobId} /></main></>;
}
