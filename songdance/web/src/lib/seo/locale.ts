import type { Metadata } from "next";
import { localePrefix, routing, type AppLocale } from "@/i18n/routing";

const PUBLIC_PATHS = ["/", "/transcribe", "/examples", "/privacy", "/terms"] as const;

export type PublicPath = (typeof PUBLIC_PATHS)[number];

export function localePath(locale: AppLocale, path: string): string {
  const prefix = localePrefix(locale);
  if (!prefix) return path;
  return path === "/" ? prefix : `${prefix}${path}`;
}

export function localeAlternatesMap(path: PublicPath): Record<string, string> {
  return Object.fromEntries([
    ...routing.locales.map((locale) => [locale, localePath(locale, path)]),
    ["x-default", localePath("en", path)],
  ]);
}

export function localeAlternates(locale: AppLocale, path: PublicPath): Metadata["alternates"] {
  return {
    canonical: localePath(locale, path),
    languages: localeAlternatesMap(path),
  };
}

export { PUBLIC_PATHS };
