import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { FeatureGrid } from "@/components/feature-grid";
import { HeroTranscriber } from "@/components/hero-transcriber";
import { HomeDetails } from "@/components/home-details";
import { HowItWorks } from "@/components/how-it-works";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { StructuredData } from "@/components/structured-data";
import { isAppLocale, type AppLocale } from "@/i18n/routing";
import { absoluteUrl, SITE_NAME } from "@/lib/seo/site";
import { localeAlternates, localePath } from "@/lib/seo/locale";

type PageProps = { params: Promise<{ locale: string }> };

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale: value } = await params;
  const locale: AppLocale = isAppLocale(value) ? value : "en";
  const t = await getTranslations({ locale, namespace: "home" });
  return {
    title: { absolute: `${t("title")} | SongDance` },
    description: t("description"),
    alternates: localeAlternates(locale, "/"),
    openGraph: { url: localePath(locale, "/"), title: t("title"), description: t("description") },
  };
}

export default async function Home({ params }: PageProps) {
  const { locale: value } = await params;
  const locale: AppLocale = isAppLocale(value) ? value : "en";
  setRequestLocale(locale);
  const t = await getTranslations({ locale, namespace: "home" });
  const faqs = [1, 2, 3, 4, 5].map((index) => ({
    "@type": "Question",
    name: t(`faq${index}Question`),
    acceptedAnswer: { "@type": "Answer", text: t(`faq${index}Answer`) },
  }));
  const structuredData = {
    "@context": "https://schema.org",
    "@graph": [
      { "@type": "WebApplication", name: `${SITE_NAME} ${t("title")}`, url: absoluteUrl(localePath(locale, "/")), applicationCategory: "MultimediaApplication", operatingSystem: "Web", description: t("description"), featureList: ["MIDI", "MusicXML", "PDF"] },
      { "@type": "FAQPage", mainEntity: faqs },
    ],
  };
  return (
    <>
      <StructuredData data={structuredData} />
      <SiteHeader />
      <main><HeroTranscriber /><FeatureGrid /><HowItWorks /><HomeDetails /></main>
      <SiteFooter />
    </>
  );
}
