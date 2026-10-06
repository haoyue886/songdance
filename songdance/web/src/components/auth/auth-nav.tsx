"use client";

import { useEffect, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { Link, usePathname } from "@/i18n/navigation";
import { accessSession, authEnabled } from "@/lib/auth/client";
import { getBillingSummary, type BillingSummary } from "@/lib/api/billing";

export function AuthNav() {
  const t = useTranslations("auth");
  const pathname = usePathname();
  const locale = useLocale();
  const returnTo = `${locale === "en" ? "" : `/${locale}`}${pathname}`;
  const [signedIn, setSignedIn] = useState(false);
  const [summary, setSummary] = useState<BillingSummary | null>(null);
  const billing = useTranslations("billing");
  useEffect(() => {
    let active = true;
    const refresh = () => { if (authEnabled) void accessSession().then(async (session) => {
      if (active) setSignedIn(Boolean(session));
      if (session) { const data = await getBillingSummary(); if (active) setSummary(data); }
      else if (active) setSummary(null);
    }).catch(() => { if (active) setSummary(null); }); };
    refresh();
    window.addEventListener("songdance-billing-change", refresh);
    return () => { active = false; window.removeEventListener("songdance-billing-change", refresh); };
  }, [pathname]);
  if (!authEnabled) return null;
  return <><span className="hidden text-xs font-semibold text-[#64736f] xl:block">{signedIn && summary?.enabled && <>{billing(summary.plan === "pro" ? "proName" : "freeName")} · {summary.unit === "seconds" ? billing("secondsValue", { seconds: summary.remaining ?? 0 }) : summary.remaining}</>}</span><Link href={signedIn ? "/account" : `/login?return_to=${encodeURIComponent(returnTo)}`}
    className="rounded-full border border-[#c8d8d2] bg-white/75 px-4 py-2 text-sm font-bold text-[#075e55] hover:bg-white">
    {signedIn ? t("account") : t("signIn")}
  </Link></>;
}
