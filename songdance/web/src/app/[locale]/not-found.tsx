import { getTranslations } from "next-intl/server";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { Link } from "@/i18n/navigation";

export default async function NotFound() {
  const t = await getTranslations("notFound");
  return <><SiteHeader /><main className="mx-auto flex min-h-[60vh] w-full max-w-7xl items-center px-5 py-20 sm:px-8 lg:px-10"><div className="max-w-2xl"><p className="text-xs font-bold uppercase text-[#147d70]">404</p><h1 className="mt-4 font-display text-5xl leading-tight sm:text-6xl">{t("title")}</h1><p className="mt-5 text-lg leading-8 text-[#61716c]">{t("body")}</p><div className="mt-8 flex flex-wrap gap-3"><Link href="/" className="inline-flex min-h-12 items-center rounded-full bg-[#147d70] px-6 text-sm font-bold text-white">{t("home")}</Link><Link href="/examples" className="inline-flex min-h-12 items-center rounded-full border border-[#b9cdc6] bg-white px-6 text-sm font-bold text-[#075e55]">{t("guide")}</Link></div></div></main><SiteFooter /></>;
}
