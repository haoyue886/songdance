import { getTranslations } from "next-intl/server";
import { Link } from "@/i18n/navigation";
import { BrandMark } from "./brand-mark";
import { LanguageSwitcher } from "./language-switcher";

export async function SiteHeader() {
  const t = await getTranslations("common");
  const navItems = [
    { href: "/#features", label: t("features") },
    { href: "/#how-it-works", label: t("howItWorks") },
    { href: "/examples", label: t("examples") },
    { href: "/privacy", label: t("privacy") },
  ] as const;
  return (
    <header className="mx-auto flex w-full max-w-7xl items-center justify-between gap-3 px-5 py-5 sm:px-8 lg:px-10">
      <Link href="/" aria-label={t("brandHome")}><BrandMark /></Link>
      <nav aria-label={t("navLabel")} className="hidden items-center gap-7 md:flex">
        {navItems.map((item) => (
          <Link key={item.href} href={item.href}
            className="text-sm font-semibold text-[#52635f] transition-colors hover:text-[#075e55]">
            {item.label}
          </Link>
        ))}
      </nav>
      <div className="flex shrink-0 items-center gap-2">
        <LanguageSwitcher />
        <Link href="/#how-it-works"
          className="hidden rounded-full border border-[#c8d8d2] bg-white/75 px-4 py-2 text-sm font-bold text-[#075e55] transition hover:border-[#147d70] hover:bg-white sm:inline-flex">
          {t("viewProcess")}
        </Link>
      </div>
    </header>
  );
}
