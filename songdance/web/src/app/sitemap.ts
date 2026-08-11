import type { MetadataRoute } from "next";
import { absoluteUrl } from "@/lib/seo/site";
import { PUBLIC_PATHS, localePath } from "@/lib/seo/locale";

const ROUTE_SETTINGS = {
  "/": { changeFrequency: "weekly", priority: 1 },
  "/transcribe": { changeFrequency: "monthly", priority: 0.8 },
  "/examples": { changeFrequency: "monthly", priority: 0.7 },
  "/privacy": { changeFrequency: "yearly", priority: 0.2 },
  "/terms": { changeFrequency: "yearly", priority: 0.2 },
} as const;

export default function sitemap(): MetadataRoute.Sitemap {
  return PUBLIC_PATHS.flatMap((path) => (["en", "zh-CN"] as const).map((locale) => ({
    url: absoluteUrl(localePath(locale, path)),
    changeFrequency: ROUTE_SETTINGS[path].changeFrequency,
    priority: ROUTE_SETTINGS[path].priority,
    alternates: { languages: { en: absoluteUrl(localePath("en", path)), "zh-CN": absoluteUrl(localePath("zh-CN", path)), "x-default": absoluteUrl(localePath("en", path)) } },
  })));
}
