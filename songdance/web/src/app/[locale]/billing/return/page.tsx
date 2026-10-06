import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { SiteHeader } from "@/components/site-header";
import { SiteFooter } from "@/components/site-footer";
import { PaymentReturn } from "@/components/billing/payment-return";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { robots: { index: false, follow: false, nocache: true }, openGraph: null, twitter: null };

export default async function ReturnPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("billing");
  return <><SiteHeader /><main className="mx-auto min-h-[calc(100dvh-5rem)] max-w-4xl px-5 py-10 sm:px-8"><h1 className="font-display text-3xl text-[#15332f]">{t("returnTitle")}</h1><PaymentReturn /></main><SiteFooter /></>;
}
