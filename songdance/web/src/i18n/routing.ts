import { defineRouting } from "next-intl/routing";

export const routing = defineRouting({
  locales: ["en", "zh", "ja", "ko", "es", "pt-br", "fr", "de"],
  defaultLocale: "en",
  localePrefix: "as-needed",
  localeDetection: false,
  alternateLinks: false,
});

export type AppLocale = (typeof routing.locales)[number];
export type LanguageTag = "en" | "zh-CN" | "ja" | "ko" | "es" | "pt-BR" | "fr" | "de";

export const LOCALE_OPTIONS: ReadonlyArray<{ value: AppLocale; label: string; lang: LanguageTag }> = [
  { value: "en", label: "English", lang: "en" },
  { value: "zh", label: "简体中文", lang: "zh-CN" },
  { value: "ja", label: "日本語", lang: "ja" },
  { value: "ko", label: "한국어", lang: "ko" },
  { value: "es", label: "Español", lang: "es" },
  { value: "pt-br", label: "Português (Brasil)", lang: "pt-BR" },
  { value: "fr", label: "Français", lang: "fr" },
  { value: "de", label: "Deutsch", lang: "de" },
];

const LOCALE_PREFIXES: Record<AppLocale, string> = {
  en: "",
  zh: "/zh",
  ja: "/ja",
  ko: "/ko",
  es: "/es",
  "pt-br": "/pt-br",
  fr: "/fr",
  de: "/de",
};

const LANGUAGE_TAGS: Record<AppLocale, LanguageTag> = Object.fromEntries(
  LOCALE_OPTIONS.map(({ value, lang }) => [value, lang]),
) as Record<AppLocale, LanguageTag>;

export function localePrefix(locale: AppLocale): string {
  return LOCALE_PREFIXES[locale];
}

export function languageTag(locale: AppLocale): LanguageTag {
  return LANGUAGE_TAGS[locale];
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
