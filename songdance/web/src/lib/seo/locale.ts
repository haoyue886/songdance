import type { Metadata } from "next";
import type { AppLocale } from "@/i18n/routing";

const PUBLIC_PATHS = ["/", "/transcribe", "/examples", "/privacy", "/terms"] as const;

export type PublicPath = (typeof PUBLIC_PATHS)[number];

export function localePath(locale: AppLocale, path: string): string {
  if (locale === "en") return path;
  return path === "/" ? "/zh" : `/zh${path}`;
}

export function localeAlternates(locale: AppLocale, path: PublicPath): Metadata["alternates"] {
  return {
    canonical: localePath(locale, path),
    languages: {
      en: localePath("en", path),
      "zh-CN": localePath("zh-CN", path),
      "x-default": localePath("en", path),
    },
  };
}

export { PUBLIC_PATHS };
