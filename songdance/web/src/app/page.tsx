import type { Metadata } from "next";
import { FeatureGrid } from "@/components/feature-grid";
import { HeroTranscriber } from "@/components/hero-transcriber";
import { HowItWorks } from "@/components/how-it-works";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { StructuredData } from "@/components/structured-data";
import { absoluteUrl, SITE_DESCRIPTION } from "@/lib/seo/site";

export const metadata: Metadata = {
  alternates: { canonical: "/" },
  openGraph: {
    type: "website",
    url: "/",
    title: "Piano Audio to MIDI Converter | SongDance",
    description: SITE_DESCRIPTION,
  },
};

const structuredData = {
  "@context": "https://schema.org",
  "@type": "WebApplication",
  name: "SongDance Piano Audio to MIDI Converter",
  url: absoluteUrl("/"),
  applicationCategory: "MultimediaApplication",
  operatingSystem: "Web",
  description: SITE_DESCRIPTION,
  featureList: ["Piano audio to MIDI", "MusicXML export", "PDF sheet music", "Score and piano-roll review"],
};

export default function Home() {
  return (
    <>
      <StructuredData data={structuredData} />
      <SiteHeader />
      <main>
        <HeroTranscriber />
        <FeatureGrid />
        <HowItWorks />
      </main>
      <SiteFooter />
    </>
  );
}
