import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { SiteHeader } from "@/components/site-header";
import { AuthPanel } from "@/components/auth/auth-panel";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { robots: { index: false, follow: false, nocache: true }, openGraph: null, twitter: null };
export default async function LoginPage({ params, searchParams }: { params: Promise<{ locale: string }>; searchParams: Promise<{ return_to?: string; auth_error?: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("auth");
  const search = await searchParams;
  return <><SiteHeader /><main className="mx-auto min-h-[calc(100dvh-5rem)] max-w-3xl px-5 py-10 sm:px-8"><h1 className="font-display text-4xl text-[#15332f]">{t("title")}</h1><p className="mt-4 text-[#64736f]">{t("subtitle")}</p><AuthPanel mode="login" returnTo={search.return_to} initialError={search.auth_error === "1"} /></main></>;
}
