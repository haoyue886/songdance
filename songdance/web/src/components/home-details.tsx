import { getTranslations } from "next-intl/server";
import { Link } from "@/i18n/navigation";

export async function HomeDetails() {
  const t = await getTranslations("home");
  const outputs = [
    ["MIDI", t("midiBody")],
    ["MusicXML", t("musicXmlBody")],
    ["PDF", t("pdfBody")],
  ];
  const faqs = [1, 2, 3, 4, 5].map((index) => [
    t(`faq${index}Question`),
    t(`faq${index}Answer`),
  ]);
  return (
    <>
      <section className="border-y border-[#d9e0da] bg-white">
        <div className="mx-auto w-full max-w-7xl px-5 py-20 sm:px-8 lg:px-10">
          <h2 className="font-display text-4xl">{t("outputsHeading")}</h2>
          <div className="mt-8 grid gap-8 md:grid-cols-3">
            {outputs.map(([title, body]) => (
              <article key={title} className="border-t border-[#aebeb8] pt-5">
                <h3 className="text-xl font-bold">{title}</h3>
                <p className="mt-3 leading-7 text-[#61716c]">{body}</p>
              </article>
            ))}
          </div>
        </div>
      </section>
      <section className="border-t border-[#d9e0da] bg-[#fffdf8]">
        <div className="mx-auto w-full max-w-5xl px-5 py-20 sm:px-8 lg:px-10">
          <h2 className="font-display text-4xl">{t("faqHeading")}</h2>
          <div className="mt-8 divide-y divide-[#cad7d1] border-y border-[#cad7d1]">
            {faqs.map(([question, answer]) => (
              <article key={question} className="py-6">
                <h3 className="text-lg font-bold">{question}</h3>
                <p className="mt-3 max-w-3xl leading-7 text-[#61716c]">{answer}</p>
              </article>
            ))}
          </div>
          <p className="mt-8 text-sm leading-6 text-[#61716c]">
            {t("privacyPrefix")} <Link className="font-semibold text-[#075e55] underline underline-offset-4" href="/privacy">{t("privacyLink")}</Link> {t("privacySuffix")}
          </p>
        </div>
      </section>
    </>
  );
}
