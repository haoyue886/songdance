"use client";

import { useEffect, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { Link, usePathname } from "@/i18n/navigation";
import { accessSession, authEnabled } from "@/lib/auth/client";

export function AuthNav() {
  const t = useTranslations("auth");
  const pathname = usePathname();
  const locale = useLocale();
  const returnTo = `${locale === "en" ? "" : `/${locale}`}${pathname}`;
  const [signedIn, setSignedIn] = useState(false);
  useEffect(() => {
    let active = true;
    if (authEnabled) void accessSession().then((session) => { if (active) setSignedIn(Boolean(session)); }).catch(() => { if (active) setSignedIn(false); });
    return () => { active = false; };
  }, []);
  if (!authEnabled) return null;
  return <Link href={signedIn ? "/account" : `/login?return_to=${encodeURIComponent(returnTo)}`}
    className="rounded-full border border-[#c8d8d2] bg-white/75 px-4 py-2 text-sm font-bold text-[#075e55] hover:bg-white">
    {signedIn ? t("account") : t("signIn")}
  </Link>;
}
