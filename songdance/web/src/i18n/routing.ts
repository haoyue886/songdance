import { defineRouting } from "next-intl/routing";

export const routing = defineRouting({
  locales: ["en", "zh-CN", "ja", "ko", "es", "pt-BR", "fr", "de"],
  defaultLocale: "en",
  localePrefix: {
    mode: "as-needed",
    prefixes: {
      "zh-CN": "/zh",
      ja: "/ja",
      ko: "/ko",
      es: "/es",
      "pt-BR": "/pt-br",
      fr: "/fr",
      de: "/de",
    },
  },
  localeDetection: false,
});

export type AppLocale = (typeof routing.locales)[number];

export const LOCALE_OPTIONS: ReadonlyArray<{ value: AppLocale; label: string; lang: string }> = [
  { value: "en", label: "English", lang: "en" },
  { value: "zh-CN", label: "简体中文", lang: "zh-CN" },
  { value: "ja", label: "日本語", lang: "ja" },
  { value: "ko", label: "한국어", lang: "ko" },
  { value: "es", label: "Español", lang: "es" },
  { value: "pt-BR", label: "Português (Brasil)", lang: "pt-BR" },
  { value: "fr", label: "Français", lang: "fr" },
  { value: "de", label: "Deutsch", lang: "de" },
];

const LOCALE_PREFIXES: Record<AppLocale, string> = {
  en: "",
  "zh-CN": "/zh",
  ja: "/ja",
  ko: "/ko",
  es: "/es",
  "pt-BR": "/pt-br",
  fr: "/fr",
  de: "/de",
};

export function localePrefix(locale: AppLocale): string {
  return LOCALE_PREFIXES[locale];
}

export function localeFromPathname(pathname: string): AppLocale {
  const match = LOCALE_OPTIONS.find(({ value }) => {
    const prefix = LOCALE_PREFIXES[value];
    return prefix && (pathname === prefix || pathname.startsWith(`${prefix}/`));
  });
  return match?.value ?? "en";
}

export function stripLocalePrefix(pathname: string): string {
  const locale = localeFromPathname(pathname);
  const prefix = LOCALE_PREFIXES[locale];
  if (!prefix) return pathname;
  return pathname.slice(prefix.length) || "/";
}

export function isAppLocale(value: string): value is AppLocale {
  return routing.locales.includes(value as AppLocale);
}
