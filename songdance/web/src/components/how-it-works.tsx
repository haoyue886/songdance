import { getTranslations } from "next-intl/server";

export async function HowItWorks() {
  const t = await getTranslations("home");
  const steps = [
    [t("stepSelectTitle"), t("stepSelectBody")],
    [t("stepTranscribeTitle"), t("stepTranscribeBody")],
    [t("stepExportTitle"), t("stepExportBody")],
  ];
  return (
    <section id="how-it-works" className="mx-auto w-full max-w-7xl px-5 py-24 sm:px-8 lg:px-10">
      <div className="grid gap-14 lg:grid-cols-[0.7fr_1.3fr]">
        <div>
          <h2 className="font-display text-4xl leading-tight sm:text-5xl">{t("processHeading")}</h2>
          <p className="mt-5 max-w-md leading-7 text-[#61716c]">{t("processBody")}</p>
        </div>
        <ol className="divide-y divide-[#cad7d1] border-y border-[#cad7d1]">
          {steps.map(([title, body], index) => (
            <li key={title} className="grid grid-cols-[2.6rem_1fr] gap-4 py-7 sm:grid-cols-[3.5rem_12rem_1fr] sm:items-center">
              <span className="font-display text-2xl italic text-[#77aa9e]">0{index + 1}</span>
              <h3 className="text-lg font-bold">{title}</h3>
              <p className="col-start-2 text-sm leading-6 text-[#65736f] sm:col-start-auto">{body}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
