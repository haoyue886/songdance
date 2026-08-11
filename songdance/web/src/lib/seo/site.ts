const LOCAL_SITE_URL = "http://localhost:3000";

function configuredSiteUrl(): string {
  const explicit = process.env.NEXT_PUBLIC_SITE_URL?.trim();
  if (explicit) return explicit;
  const vercelDomain = process.env.VERCEL_PROJECT_PRODUCTION_URL?.trim();
  return vercelDomain ? `https://${vercelDomain}` : LOCAL_SITE_URL;
}

export const SITE_NAME = "SongDance";
export const SITE_URL = new URL(configuredSiteUrl());
export const SITE_DESCRIPTION =
  "Convert piano recordings to editable MIDI, MusicXML and readable sheet music.";

export function absoluteUrl(path: string): string {
  return new URL(path, SITE_URL).toString();
}
