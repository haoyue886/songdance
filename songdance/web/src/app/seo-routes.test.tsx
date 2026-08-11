import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import AudioToMidiPage, { metadata as audioToMidiMetadata } from "./audio-to-midi/page";
import { metadata as jobMetadata } from "./jobs/[jobId]/page";
import { metadata as notFoundMetadata } from "./not-found";
import robots from "./robots";
import sitemap from "./sitemap";

describe("SEO routes", () => {
  it("publishes stable pages without exposing ephemeral jobs", () => {
    const entries = sitemap();
    const urls = entries.map((entry) => entry.url);
    const paths = urls.map((url) => new URL(url).pathname);

    expect(paths).toContain("/audio-to-midi");
    expect(paths).toContain("/examples");
    expect(paths.some((path) => path.startsWith("/jobs/"))).toBe(false);
    expect(new URL(String(robots().sitemap)).pathname).toBe("/sitemap.xml");
    expect(jobMetadata.robots).toMatchObject({ index: false, follow: false, nocache: true });
    expect(jobMetadata.openGraph).toBeNull();
    expect(jobMetadata.twitter).toBeNull();
    expect(notFoundMetadata.openGraph).toBeNull();
    expect(notFoundMetadata.twitter).toBeNull();
  });

  it("renders a crawlable core page with truthful structured data", () => {
    const view = render(<AudioToMidiPage />);

    expect(screen.getByRole("heading", {
      level: 1,
      name: "Audio to MIDI Converter for Piano Recordings",
    })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Convert piano audio" }))
      .toHaveAttribute("href", "/transcribe");
    expect(screen.getByRole("link", { name: "Hear a real example" }))
      .toHaveAttribute("href", "/examples");
    expect(screen.getByText("Is the generated MIDI always accurate?")).toBeInTheDocument();
    expect(audioToMidiMetadata.alternates).toMatchObject({ canonical: "/audio-to-midi" });

    const jsonLd = view.container.querySelector('script[type="application/ld+json"]');
    expect(jsonLd).not.toBeNull();
    const data = JSON.parse(jsonLd?.textContent ?? "{}") as {
      "@graph"?: Array<{
        "@type"?: string;
        url?: string;
        description?: string;
        featureList?: string[];
        offers?: unknown;
        mainEntity?: Array<{
          name: string;
          acceptedAnswer: { text: string };
        }>;
      }>;
    };
    expect(data["@graph"]?.map((entry) => entry["@type"]))
      .toEqual(["WebApplication", "FAQPage"]);
    const [application, faqPage] = data["@graph"] ?? [];
    expect(application).toMatchObject({
      url: "http://localhost:3000/audio-to-midi",
      description: expect.stringContaining("piano"),
      featureList: ["Piano audio to MIDI", "MusicXML export", "PDF sheet music", "Score and piano-roll review"],
    });
    expect(application).not.toHaveProperty("offers");
    expect(faqPage?.mainEntity).toHaveLength(5);
    for (const entry of faqPage?.mainEntity ?? []) {
      expect(screen.getByText(entry.name)).toBeInTheDocument();
      expect(screen.getByText(entry.acceptedAnswer.text)).toBeInTheDocument();
    }
  });
});
