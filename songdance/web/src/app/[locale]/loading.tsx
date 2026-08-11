import { getTranslations } from "next-intl/server";

export default async function Loading() {
  const t = await getTranslations("loading");
  return <main className="grid min-h-screen place-items-center" aria-busy="true" aria-live="polite"><div className="flex items-center gap-3 text-sm font-semibold text-[#53645f]"><span className="size-3 animate-pulse rounded-full bg-[#147d70]" />{t("label")}</div></main>;
}
