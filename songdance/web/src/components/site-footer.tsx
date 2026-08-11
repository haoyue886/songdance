import { getTranslations } from "next-intl/server";
import { Link } from "@/i18n/navigation";
import { BrandMark } from "./brand-mark";

export async function SiteFooter() {
  const t = await getTranslations("common");
  return (
    <footer className="bg-[#15332f] text-white">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-8 px-5 py-10 sm:px-8 md:flex-row md:items-end md:justify-between lg:px-10">
        <div>
          <BrandMark />
          <p className="mt-4 max-w-md text-sm leading-6 text-[#bed0ca]">{t("footerSummary")}</p>
        </div>
        <div className="flex flex-wrap gap-5 text-sm font-semibold text-[#d9e5e1]">
          <Link href="/privacy">{t("privacy")}</Link>
          <Link href="/terms">{t("terms")}</Link>
          <Link href="/examples">{t("transcriptionExample")}</Link>
          <Link href="/#how-it-works">{t("processingFlow")}</Link>
        </div>
      </div>
    </footer>
  );
}
