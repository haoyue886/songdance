import type { Metadata } from "next";
import { SITE_DESCRIPTION, SITE_NAME, SITE_URL } from "@/lib/seo/site";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: SITE_URL,
  title: {
    default: "Piano Audio to MIDI Converter | SongDance",
    template: "%s | SongDance",
  },
  description: SITE_DESCRIPTION,
  applicationName: SITE_NAME,
  keywords: ["audio to MIDI converter", "piano audio to MIDI", "piano transcription", "MusicXML"],
  openGraph: {
    type: "website",
    locale: "en_US",
    siteName: SITE_NAME,
    title: "Piano Audio to MIDI Converter | SongDance",
    description: SITE_DESCRIPTION,
  },
  twitter: {
    card: "summary",
    title: "Piano Audio to MIDI Converter | SongDance",
    description: SITE_DESCRIPTION,
  },
  verification: process.env.NEXT_PUBLIC_GOOGLE_SITE_VERIFICATION
    ? { google: process.env.NEXT_PUBLIC_GOOGLE_SITE_VERIFICATION }
    : undefined,
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" data-scroll-behavior="smooth">
      <body>{children}</body>
    </html>
  );
}
