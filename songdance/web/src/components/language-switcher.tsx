"use client";

import { Languages } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { localePrefix, LOCALE_OPTIONS, stripLocalePrefix, type AppLocale } from "@/i18n/routing";

function localizedPath(pathname: string, locale: AppLocale): string {
  const logicalPath = stripLocalePrefix(pathname);
  const prefix = localePrefix(locale);
  return prefix ? (logicalPath === "/" ? prefix : `${prefix}${logicalPath}`) : logicalPath;
}

export function LanguageSwitcher() {
  const locale = useLocale();
  const t = useTranslations("common");

  const changeLocale = (nextLocale: string) => {
    if (nextLocale === locale) return;
    document.cookie = `NEXT_LOCALE=${nextLocale}; Path=/; Max-Age=31536000; SameSite=Lax`;
    const nextPath = localizedPath(window.location.pathname, nextLocale as AppLocale);
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
        {LOCALE_OPTIONS.map((option) => (
          <option key={option.value} value={option.value}>{option.label}</option>
        ))}
      </select>
    </label>
  );
}
