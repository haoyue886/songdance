import type { Metadata } from "next";
import Link from "next/link";
import { StructuredData } from "@/components/structured-data";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { absoluteUrl, SITE_DESCRIPTION, SITE_NAME } from "@/lib/seo/site";

export const metadata: Metadata = {
  title: "Audio to MIDI Converter for Piano Recordings",
  description:
    "Convert a piano recording to editable MIDI, MusicXML and PDF sheet music. Upload MP3, WAV or M4A, review the result, then export.",
  alternates: { canonical: "/audio-to-midi" },
  openGraph: {
    type: "website",
    url: "/audio-to-midi",
    title: "Audio to MIDI Converter for Piano Recordings",
    description: SITE_DESCRIPTION,
  },
  twitter: {
    card: "summary",
    title: "Audio to MIDI Converter for Piano Recordings",
    description: SITE_DESCRIPTION,
  },
};

const OUTPUTS = [
  ["MIDI", "Open the transcription in a DAW and continue editing notes, timing and velocity."],
  ["MusicXML", "Move the score into compatible notation software for detailed engraving."],
  ["PDF sheet music", "Keep a readable reference generated from the current transcription."],
];

const STEPS = [
  ["Prepare a piano recording", "Choose an MP3, WAV or M4A file and trim a 1–90 second excerpt."],
  ["Run the transcription", "SongDance detects piano notes and builds editable score data."],
  ["Review before exporting", "Compare the source audio with the score and piano roll, then download the useful formats."],
];

const FAQS = [
  ["Can I convert any audio recording to MIDI?", "The current version is designed for piano-focused recordings. Full mixes, vocals and other instruments are not presented as supported inputs yet."],
  ["Which audio formats can I upload?", "You can upload MP3, WAV and M4A files up to 25 MB, then select a 1–90 second excerpt."],
  ["Is the generated MIDI always accurate?", "No automatic transcription is perfect. Dense chords, pedal, noise and overlapping notes can produce errors, so SongDance includes score and playback views for review."],
  ["Can I export sheet music too?", "Yes. Successful jobs can provide MusicXML for notation software and a PDF generated from the current score."],
  ["How long are files stored?", "The product is designed around temporary jobs. Task data is deleted after 24 hours, and an immediate delete action is available on the task page."],
];

const structuredData = {
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "WebApplication",
      name: `${SITE_NAME} Audio to MIDI Converter`,
      url: absoluteUrl("/audio-to-midi"),
      applicationCategory: "MultimediaApplication",
      operatingSystem: "Web",
      description: SITE_DESCRIPTION,
      featureList: ["Piano audio to MIDI", "MusicXML export", "PDF sheet music", "Score and piano-roll review"],
    },
    {
      "@type": "FAQPage",
      mainEntity: FAQS.map(([question, answer]) => ({
        "@type": "Question",
        name: question,
        acceptedAnswer: { "@type": "Answer", text: answer },
      })),
    },
  ],
};

export default function AudioToMidiPage() {
  return (
    <>
      <StructuredData data={structuredData} />
      <SiteHeader />
      <main lang="en">
        <section className="mx-auto w-full max-w-7xl px-5 pb-16 pt-12 sm:px-8 lg:px-10 lg:pb-20 lg:pt-20">
          <div className="max-w-4xl">
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#147d70]">Piano transcription tool</p>
            <h1 className="mt-4 font-display text-5xl leading-[1.02] sm:text-6xl lg:text-7xl">
              Audio to MIDI Converter for Piano Recordings
            </h1>
            <p className="mt-6 max-w-3xl text-lg leading-8 text-[#53645f] sm:text-xl">
              Turn a piano recording into editable MIDI, MusicXML and PDF sheet music. Review the detected notes against the original audio before you export.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link href="/transcribe" className="inline-flex min-h-12 items-center rounded-full bg-[#147d70] px-6 text-sm font-bold text-white transition hover:bg-[#075e55]">
                Convert piano audio
              </Link>
              <Link href="/examples" className="inline-flex min-h-12 items-center rounded-full border border-[#b9cdc6] bg-white px-6 text-sm font-bold text-[#075e55] transition hover:border-[#147d70]">
                Hear a real example
              </Link>
            </div>
            <dl className="mt-10 grid border-y border-[#cad7d1] sm:grid-cols-3">
              <Fact label="Input" value="MP3, WAV, M4A" />
              <Fact label="Excerpt" value="1–90 seconds" />
              <Fact label="Outputs" value="MIDI, MusicXML, PDF" />
            </dl>
          </div>
        </section>

        <section className="border-y border-[#d9e0da] bg-[#fffdf8]">
          <div className="mx-auto w-full max-w-7xl px-5 py-16 sm:px-8 lg:px-10">
            <h2 className="font-display text-4xl">Editable outputs, not a flattened preview</h2>
            <div className="mt-8 grid gap-8 md:grid-cols-3">
              {OUTPUTS.map(([title, body]) => (
                <article key={title} className="border-t border-[#aebeb8] pt-5">
                  <h3 className="text-xl font-bold">{title}</h3>
                  <p className="mt-3 leading-7 text-[#61716c]">{body}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="mx-auto grid w-full max-w-7xl gap-12 px-5 py-20 sm:px-8 lg:grid-cols-[0.72fr_1.28fr] lg:px-10">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#147d70]">How it works</p>
            <h2 className="mt-4 font-display text-4xl">From recording to notes in three steps</h2>
            <p className="mt-5 leading-7 text-[#61716c]">Use the score, piano roll and playback controls to decide what needs correction. SongDance does not claim automatic output is publication-ready.</p>
          </div>
          <ol className="divide-y divide-[#cad7d1] border-y border-[#cad7d1]">
            {STEPS.map(([title, body], index) => (
              <li key={title} className="grid grid-cols-[2.75rem_1fr] gap-4 py-7 sm:grid-cols-[3rem_13rem_1fr]">
                <span className="font-display text-2xl italic text-[#77aa9e]">0{index + 1}</span>
                <h3 className="text-lg font-bold">{title}</h3>
                <p className="col-start-2 leading-7 text-[#61716c] sm:col-start-auto">{body}</p>
              </li>
            ))}
          </ol>
        </section>

        <section className="border-t border-[#d9e0da] bg-white">
          <div className="mx-auto w-full max-w-5xl px-5 py-20 sm:px-8 lg:px-10">
            <h2 className="font-display text-4xl">Audio to MIDI questions</h2>
            <div className="mt-8 divide-y divide-[#cad7d1] border-y border-[#cad7d1]">
              {FAQS.map(([question, answer]) => (
                <article key={question} className="py-6">
                  <h3 className="text-lg font-bold">{question}</h3>
                  <p className="mt-3 max-w-3xl leading-7 text-[#61716c]">{answer}</p>
                </article>
              ))}
            </div>
            <p className="mt-8 text-sm leading-6 text-[#61716c]">
              Before uploading, review the <Link className="font-semibold text-[#075e55] underline underline-offset-4" href="/privacy">privacy policy</Link> and confirm you have the rights needed to process the recording.
            </p>
          </div>
        </section>
      </main>
      <SiteFooter />
    </>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="px-1 py-5 sm:border-l sm:border-[#cad7d1] sm:px-5 sm:first:border-l-0">
      <dt className="text-xs font-bold uppercase tracking-[0.14em] text-[#6a7975]">{label}</dt>
      <dd className="mt-2 font-semibold">{value}</dd>
    </div>
  );
}
