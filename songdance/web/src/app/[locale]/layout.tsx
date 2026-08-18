import type { Metadata } from "next";
import { hasLocale, NextIntlClientProvider } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";
import { languageTag, routing } from "@/i18n/routing";
import { getAppMessages } from "@/i18n/messages";
import { SITE_DESCRIPTION, SITE_NAME, SITE_URL } from "@/lib/seo/site";
import "../globals.css";

type LayoutProps = {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
};

export function generateStaticParams() {
  return routing.locales.map((locale) => ({ locale }));
}

export async function generateMetadata({ params }: Omit<LayoutProps, "children">): Promise<Metadata> {
  const { locale } = await params;
  if (!hasLocale(routing.locales, locale)) return {};
  const messages = getAppMessages(locale);
  const isEnglish = locale === "en";
  const description = isEnglish ? SITE_DESCRIPTION : messages.home.description;
  const title = `${messages.home.title} | SongDance`;
  const openGraphLocales: Record<string, string> = {
    en: "en_US",
    zh: "zh_CN",
    ja: "ja_JP",
    ko: "ko_KR",
    es: "es_ES",
    "pt-br": "pt_BR",
    fr: "fr_FR",
    de: "de_DE",
  };
  return {
    metadataBase: SITE_URL,
    title: { default: title, template: "%s | SongDance" },
    description,
    applicationName: SITE_NAME,
    keywords: [messages.home.title, "MIDI", "MusicXML", "piano transcription"],
    openGraph: { type: "website", locale: openGraphLocales[locale] ?? "en_US", siteName: SITE_NAME, title, description },
    twitter: { card: "summary", title, description },
    verification: process.env.NEXT_PUBLIC_GOOGLE_SITE_VERIFICATION
      ? { google: process.env.NEXT_PUBLIC_GOOGLE_SITE_VERIFICATION }
      : undefined,
  };
}

export default async function LocaleLayout({ children, params }: LayoutProps) {
  const { locale } = await params;
  if (!hasLocale(routing.locales, locale)) notFound();
  setRequestLocale(locale);
  const messages = await getMessages();
  return (
    <html lang={languageTag(locale)} data-scroll-behavior="smooth">
      <body>
        <NextIntlClientProvider messages={messages}>{children}</NextIntlClientProvider>
      </body>
    </html>
  );
}
