import { getTranslations } from "next-intl/server";

export async function FeatureGrid() {
  const t = await getTranslations("home");
  const features = [
    [t("featureEditableTitle"), t("featureEditableBody")],
    [t("featureReviewTitle"), t("featureReviewBody")],
    [t("featureTemporaryTitle"), t("featureTemporaryBody")],
  ];
  return (
    <section id="features" className="border-y border-[#d9e0da] bg-[#fffdf8]">
      <div className="mx-auto w-full max-w-7xl px-5 py-20 sm:px-8 lg:px-10">
        <h2 className="font-display text-4xl">{t("featuresHeading")}</h2>
        <div className="mt-8 grid gap-5 md:grid-cols-3">
          {features.map(([title, body], index) => (
            <article key={title} className="rounded-lg border border-[#e1e6e1] bg-white p-7">
              <span className="font-display text-3xl italic text-[#86b7ab]">0{index + 1}</span>
              <h3 className="mt-10 text-xl font-bold">{title}</h3>
              <p className="mt-3 text-[0.95rem] leading-7 text-[#65736f]">{body}</p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
