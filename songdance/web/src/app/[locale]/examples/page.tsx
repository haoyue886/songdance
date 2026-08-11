import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { Link } from "@/i18n/navigation";
import { isAppLocale, type AppLocale } from "@/i18n/routing";
import { localeAlternates, localePath } from "@/lib/seo/locale";
import { ExampleClient } from "../../examples/example-client";

type PageProps = { params: Promise<{ locale: string }> };
export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale: value } = await params;
  const locale: AppLocale = isAppLocale(value) ? value : "en";
  const t = await getTranslations({ locale, namespace: "examples" });
  return { title: t("title"), description: t("description"), alternates: localeAlternates(locale, "/examples"), openGraph: { url: localePath(locale, "/examples"), title: t("title"), description: t("description") } };
}
export default async function ExamplesPage({ params }: PageProps) {
  const { locale: value } = await params;
  const locale: AppLocale = isAppLocale(value) ? value : "en";
  setRequestLocale(locale);
  const t = await getTranslations({ locale, namespace: "examples" });
  return <><SiteHeader /><main className="mx-auto w-full max-w-7xl px-5 pb-20 pt-8 sm:px-8 lg:px-10"><section className="mb-10 border-b border-[#d9e3dd] pb-8"><p className="text-xs font-bold uppercase text-[#147d70]">{t("eyebrow")}</p><h1 className="mt-3 font-display text-4xl font-bold leading-tight sm:text-5xl">{t("heading")}</h1><p className="mt-4 max-w-3xl leading-7 text-[#61716c]">{t("intro")}</p><div className="mt-5 flex flex-wrap items-center gap-4 text-sm font-semibold"><a className="text-[#075e55] underline underline-offset-4" href="https://commons.wikimedia.org/wiki/File:%D0%92%D0%B0%D1%80%D0%B2%D0%B0%D1%80%D0%B0_%D0%A1%D0%B5%D0%BC%D0%B5%D0%BD%D1%87%D1%83%D0%BA_-_%D0%9C%D0%BE%D1%86%D0%B0%D1%80%D1%82-%D0%A1%D0%BE%D0%BD%D0%B0%D1%82%D0%B0-c-dur-part1.ogv" target="_blank" rel="noreferrer">{t("sourceLink")}</a><Link className="text-[#075e55] underline underline-offset-4" href="/transcribe">{t("cta")}</Link></div></section><ExampleClient /></main><SiteFooter /></>;
}
