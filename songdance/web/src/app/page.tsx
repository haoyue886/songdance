import { FeatureGrid } from "@/components/feature-grid";
import { HeroTranscriber } from "@/components/hero-transcriber";
import { HowItWorks } from "@/components/how-it-works";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";

export default function Home() {
  return (
    <>
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
