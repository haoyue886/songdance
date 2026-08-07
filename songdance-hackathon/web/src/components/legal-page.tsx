import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";

type LegalSection = { heading: string; paragraphs: string[] };

export function LegalPage({
  eyebrow,
  title,
  summary,
  sections,
}: {
  eyebrow: string;
  title: string;
  summary: string;
  sections: LegalSection[];
}) {
  return (
    <>
      <SiteHeader />
      <main className="mx-auto w-full max-w-4xl px-5 pb-24 pt-10 sm:px-8 lg:px-10">
        <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#147d70]">{eyebrow}</p>
        <h1 className="mt-3 max-w-3xl font-display text-4xl leading-tight sm:text-5xl">{title}</h1>
        <p className="mt-5 max-w-2xl text-base leading-8 text-[#61716c]">{summary}</p>
        <div className="mt-12 border-t border-[#d9e3dd]">
          {sections.map((section) => (
            <section
              key={section.heading}
              className="grid gap-4 border-b border-[#d9e3dd] py-8 md:grid-cols-[220px_minmax(0,1fr)]"
            >
              <h2 className="font-display text-2xl font-bold">{section.heading}</h2>
              <div className="space-y-4 text-sm leading-7 text-[#52635f]">
                {section.paragraphs.map((paragraph) => (
                  <p key={paragraph}>{paragraph}</p>
                ))}
              </div>
            </section>
          ))}
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
