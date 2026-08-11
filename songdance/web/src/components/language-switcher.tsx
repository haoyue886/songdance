"use client";

import { Languages } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";

function localizedPath(pathname: string, locale: string): string {
  const logicalPath = pathname === "/zh" ? "/" : pathname.replace(/^\/zh(?=\/)/, "");
  if (locale === "zh-CN") return logicalPath === "/" ? "/zh" : `/zh${logicalPath}`;
  return logicalPath;
}

export function LanguageSwitcher() {
  const locale = useLocale();
  const t = useTranslations("common");

  const changeLocale = (nextLocale: string) => {
    if (nextLocale === locale) return;
    document.cookie = `NEXT_LOCALE=${nextLocale}; Path=/; Max-Age=31536000; SameSite=Lax`;
    const nextPath = localizedPath(window.location.pathname, nextLocale);
    window.location.assign(`${nextPath}${window.location.search}${window.location.hash}`);
  };

  return (
    <label className="flex h-10 items-center gap-2 rounded-md border border-[#c8d8d2] bg-white px-2 text-[#075e55]">
      <Languages aria-hidden="true" size={16} />
      <span className="sr-only">{t("language")}</span>
      <select
        aria-label={t("language")}
        className="max-w-[7rem] bg-transparent text-xs font-bold outline-none sm:text-sm"
        value={locale}
        onChange={(event) => changeLocale(event.currentTarget.value)}
      >
        <option value="en">{t("english")}</option>
        <option value="zh-CN">{t("chinese")}</option>
      </select>
    </label>
  );
}
