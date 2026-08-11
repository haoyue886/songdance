import type { MetadataRoute } from "next";
import { absoluteUrl } from "@/lib/seo/site";

const PUBLIC_ROUTES = [
  { path: "/", changeFrequency: "weekly", priority: 1 },
  { path: "/audio-to-midi", changeFrequency: "weekly", priority: 0.9 },
  { path: "/transcribe", changeFrequency: "monthly", priority: 0.8 },
  { path: "/examples", changeFrequency: "monthly", priority: 0.7 },
  { path: "/privacy", changeFrequency: "yearly", priority: 0.2 },
  { path: "/terms", changeFrequency: "yearly", priority: 0.2 },
] as const;

export default function sitemap(): MetadataRoute.Sitemap {
  return PUBLIC_ROUTES.map((route) => ({
    url: absoluteUrl(route.path),
    changeFrequency: route.changeFrequency,
    priority: route.priority,
  }));
}
