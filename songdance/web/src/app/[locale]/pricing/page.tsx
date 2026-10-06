import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { PricingPanel } from "@/components/billing/pricing-panel";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { isAppLocale, type AppLocale } from "@/i18n/routing";
import { localeAlternates, localePath } from "@/lib/seo/locale";

type PageProps = { params: Promise<{ locale: string }> };

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale: value } = await params;
  const locale: AppLocale = isAppLocale(value) ? value : "en";
  const t = await getTranslations({ locale, namespace: "billing" });
  return {
    title: t("pricingMetaTitle"), description: t("pricingMetaDescription"),
    alternates: localeAlternates(locale, "/pricing"),
    openGraph: { url: localePath(locale, "/pricing"), title: t("pricingMetaTitle"), description: t("pricingMetaDescription") },
  };
}

export default async function PricingPage({ params }: PageProps) {
  const { locale: value } = await params;
  const locale: AppLocale = isAppLocale(value) ? value : "en";
  setRequestLocale(locale);
  return <><SiteHeader /><main className="mx-auto w-full max-w-5xl px-5 pb-20 pt-10 sm:px-8 lg:px-10"><PricingPanel /></main><SiteFooter /></>;
}
