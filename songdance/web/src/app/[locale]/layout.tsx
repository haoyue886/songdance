import type { Metadata } from "next";
import { hasLocale, NextIntlClientProvider } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";
import { routing } from "@/i18n/routing";
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
  const isEnglish = locale === "en";
  const description = isEnglish
    ? SITE_DESCRIPTION
    : "将钢琴录音转换为可编辑的 MIDI、MusicXML 和可读乐谱。";
  const title = isEnglish
    ? "Audio to MIDI Converter for Piano Recordings | SongDance"
    : "钢琴音频转 MIDI 转换器 | SongDance";
  return {
    metadataBase: SITE_URL,
    title: { default: title, template: "%s | SongDance" },
    description,
    applicationName: SITE_NAME,
    keywords: isEnglish
      ? ["audio to MIDI converter", "piano audio to MIDI", "piano transcription", "MusicXML"]
      : ["音频转 MIDI", "钢琴音频转 MIDI", "钢琴转录", "MusicXML"],
    openGraph: { type: "website", locale: isEnglish ? "en_US" : "zh_CN", siteName: SITE_NAME, title, description },
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
    <html lang={locale} data-scroll-behavior="smooth">
      <body>
        <NextIntlClientProvider messages={messages}>{children}</NextIntlClientProvider>
      </body>
    </html>
  );
}
