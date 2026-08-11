import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { LegalPage } from "@/components/legal-page";
import { isAppLocale, type AppLocale } from "@/i18n/routing";
import { localeAlternates, localePath } from "@/lib/seo/locale";

type PageProps = { params: Promise<{ locale: string }> };
export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale: value } = await params;
  const locale: AppLocale = isAppLocale(value) ? value : "en";
  const t = await getTranslations({ locale, namespace: "privacy" });
  return { title: t("metaTitle"), description: t("metaDescription"), alternates: localeAlternates(locale, "/privacy"), openGraph: { url: localePath(locale, "/privacy"), title: t("metaTitle"), description: t("metaDescription") } };
}
export default async function PrivacyPage({ params }: PageProps) {
  const { locale: value } = await params;
  const locale: AppLocale = isAppLocale(value) ? value : "en";
  setRequestLocale(locale);
  const t = await getTranslations({ locale, namespace: "privacy" });
  const sections = [1, 2, 3, 4].map((index) => ({ heading: t(`section${index}Title`), paragraphs: [t(`section${index}P1`), t(`section${index}P2`)] }));
  return <LegalPage eyebrow={t("eyebrow")} title={t("title")} summary={t("summary")} sections={sections} />;
}
