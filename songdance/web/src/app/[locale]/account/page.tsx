import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { SiteHeader } from "@/components/site-header";
import { AuthPanel } from "@/components/auth/auth-panel";
import { SiteFooter } from "@/components/site-footer";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { robots: { index: false, follow: false, nocache: true }, openGraph: null, twitter: null };
export default async function AccountPage({ params, searchParams }: { params: Promise<{ locale: string }>; searchParams: Promise<{ return_to?: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("auth");
  return <><SiteHeader /><main className="mx-auto min-h-[calc(100dvh-5rem)] max-w-4xl px-5 py-10 sm:px-8"><h1 className="font-display text-3xl text-[#15332f]">{t("accountTitle")}</h1><AuthPanel mode="account" returnTo={(await searchParams).return_to} /></main><SiteFooter /></>;
}
