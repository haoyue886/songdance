"use client";

import { useEffect, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { Mail, RefreshCw } from "lucide-react";
import { Link } from "@/i18n/navigation";
import { getBillingConfig, type BillingConfig } from "@/lib/api/billing";
import { SECONDARY, SURFACE } from "./styles";

export function supportMailto(email: string | null, subject?: string): string | null {
  if (typeof email !== "string" || email.length > 254 || !/^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$/i.test(email)) return null;
  const address = encodeURIComponent(email).replace("%40", "@");
  return `mailto:${address}${subject ? `?subject=${encodeURIComponent(subject)}` : ""}`;
}

export function SupportPanel({ mode }: { mode: "contact" | "refund" }) {
  const t = useTranslations("billing");
  const locale = useLocale();
  const [config, setConfig] = useState<BillingConfig | null>(null);
  const [error, setError] = useState(false);
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    void getBillingConfig(controller.signal)
      .then((value) => { if (!controller.signal.aborted) setConfig(value); })
      .catch(() => { if (!controller.signal.aborted) setError(true); });
    return () => controller.abort();
  }, [revision]);

  const mailto = supportMailto(config?.support_email ?? null, t("contactSubject"));
  const refundSections = [
    { title: t("refundPolicyTitle"), body: t("refundPolicyBody") },
    { title: t("refundReviewTitle"), body: t("refundReviewBody") },
    { title: t("refundCancelTitle"), body: t("refundCancelBody") },
    { title: t("refundFilesTitle"), body: t("refundFilesBody") },
  ];

  return <>
    <h1 className="font-display text-3xl font-bold leading-tight sm:text-4xl">{t(mode === "contact" ? "contactTitle" : "refundTitle")}</h1>
    <p className="mt-4 max-w-2xl text-base leading-7 text-[#61716c]">{t(mode === "contact" ? "contactSummary" : "refundSummary")}</p>
    {locale !== "en" && locale !== "zh" && <p className="mt-5 border-l-2 border-[#9a7031] pl-4 text-sm leading-6 text-[#765527]" lang="en">{t("localeFallback")}</p>}

    {mode === "refund" ? <div className="mt-10 border-t border-[#dce3dc]">
      {refundSections.map((section) => <section key={section.title} className="grid gap-3 border-b border-[#dce3dc] py-7 md:grid-cols-[200px_minmax(0,1fr)] md:gap-8">
        <h2 className="text-lg font-semibold">{section.title}</h2>
        <div className="space-y-3 text-sm leading-7 text-[#52635f]"><p>{section.body}</p>{section.title === t("refundFilesTitle") && config && <p>{t("retention", { hours: config.retention_hours })}</p>}</div>
      </section>)}
    </div> : <section className={`${SURFACE} mt-10`}>
      <h2 className="text-lg font-semibold">{t("contactDetailsTitle")}</h2>
      <p className="mt-3 max-w-2xl text-sm leading-7 text-[#52635f]">{t("contactDetails")}</p>
      <p className="mt-3 max-w-2xl text-sm leading-7 text-[#52635f]">{t("contactFiles")}</p>
    </section>}

    <section aria-label={t("contactSupport")} className="mt-8">
      {!config ? <>
        <p role={error ? "alert" : "status"} className="text-sm leading-6 text-[#52635f]">{t(error ? "loadError" : "loading")}</p>
        {error && <button type="button" className={`${SECONDARY} mt-4`} title={t("refresh")} onClick={() => { setConfig(null); setError(false); setRevision((value) => value + 1); }}><RefreshCw size={16} aria-hidden="true" />{t("refresh")}</button>}
      </> : mailto ? <>
        <a href={mailto} className={SECONDARY}><Mail size={17} aria-hidden="true" />{t("contactEmail")}</a>
        <p className="mt-3 break-all text-sm text-[#52635f]">{config.support_email}</p>
      </> : <>
        <p role="status" className="text-sm leading-6 text-[#52635f]">{t("supportUnavailable")}</p>
        <p className="mt-2 text-sm leading-6 text-[#52635f]">{t("contactUnavailableNote")}</p>
      </>}
    </section>

    <nav className="mt-8 flex flex-wrap gap-x-6 gap-y-3 text-sm font-semibold text-[#075e55]" aria-label={t("contactDetailsTitle")}>
      <Link href="/pricing" className="underline underline-offset-4">{t("plans")}</Link>
      {mode === "refund" ? <Link href="/account" className="underline underline-offset-4">{t("accountLink")}</Link> : <Link href="/refund" className="underline underline-offset-4">{t("refundLink")}</Link>}
      <Link href="/privacy" className="underline underline-offset-4">{t("privacyLink")}</Link>
    </nav>
  </>;
}
