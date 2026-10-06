"use client";

import { useEffect, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { ArrowRight, Info, RefreshCw } from "lucide-react";
import { Link } from "@/i18n/navigation";
import { getBillingConfig, type BillingConfig } from "@/lib/api/billing";
import { accessSession, authEnabled } from "@/lib/auth/client";
import { CheckoutButton } from "./checkout-button";
import { PRIMARY, SECONDARY, SURFACE } from "./styles";

export function PricingPanel() {
  const t = useTranslations("billing");
  const locale = useLocale();
  const [config, setConfig] = useState<BillingConfig | null>(null);
  const [error, setError] = useState(false);
  const [revision, setRevision] = useState(0);
  const [signedIn, setSignedIn] = useState(false);

  useEffect(() => {
    let active = true;
    if (authEnabled) void accessSession()
      .then((session) => { if (active) setSignedIn(Boolean(session)); })
      .catch(() => { /* Public plan details do not require a session. */ });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void getBillingConfig(controller.signal)
      .then((value) => { if (!controller.signal.aborted) setConfig(value); })
      .catch(() => { if (!controller.signal.aborted) setError(true); });
    return () => controller.abort();
  }, [revision]);

  function refresh() {
    setConfig(null);
    setError(false);
    setRevision((value) => value + 1);
  }

  const price = config ? new Intl.NumberFormat(locale, {
    style: "currency", currency: config.pro.currency, currencyDisplay: "code",
  }).format(config.pro.price_minor / 100) : null;
  const freeReturn = `${locale === "en" ? "" : `/${locale}`}/transcribe`;
  const needsSignIn = config?.usage_enabled && !signedIn;

  return <>
    <h1 className="font-display text-3xl font-bold leading-tight sm:text-4xl">{t("pricingTitle")}</h1>
    <p className="mt-4 max-w-2xl text-base leading-7 text-[#61716c]">{t("pricingSummary")}</p>
    {locale !== "en" && locale !== "zh" && <p className="mt-5 border-l-2 border-[#9a7031] pl-4 text-sm leading-6 text-[#765527]" lang="en">{t("localeFallback")}</p>}

    {!config ? <div className={`${SURFACE} mt-8`}>
      <p role={error ? "alert" : "status"} className="text-sm leading-6 text-[#52635f]">{t(error ? "loadError" : "loading")}</p>
      {error && <button type="button" onClick={refresh} className={`${SECONDARY} mt-4`} title={t("refresh")}><RefreshCw size={16} aria-hidden="true" />{t("refresh")}</button>}
    </div> : <>
      <div className="mt-8 flex gap-3 border-l-2 border-[#147d70] pl-4 text-sm leading-6 text-[#52635f]">
        <Info size={18} className="mt-1 shrink-0 text-[#147d70]" aria-hidden="true" />
        <div>
          <p>{t(config.checkout_enabled ? "testNotice" : "proposalNotice")}</p>
          {!config.usage_enabled && <p className="mt-2">{t("meterOff")}</p>}
        </div>
      </div>

      <div className={`${SURFACE} mt-7 grid md:grid-cols-2`}>
        <section aria-labelledby="free-plan" className="flex min-w-0 flex-col border-b border-[#dce3dc] pb-8 md:border-b-0 md:border-r md:pb-0 md:pr-8">
          <h2 id="free-plan" className="text-lg font-bold">{t("freeName")}</h2>
          <p className="mt-3 text-3xl font-semibold leading-tight">{t("freePrice")}</p>
          {!config.usage_enabled && <p className="mt-2 text-xs font-semibold text-[#765527]">{t("proposedAllowance")}</p>}
          <dl className="mt-7 space-y-5 text-sm leading-6">
            <div><dt className="font-semibold">{t("allowanceLabel")}</dt><dd className="mt-1 text-[#52635f]">{t("freeAllowance", { count: config.free.monthly_jobs })}</dd></div>
            <div><dt className="font-semibold">{t("excerptLabel")}</dt><dd className="mt-1 text-[#52635f]">{t("clipLimit", { seconds: config.free.max_clip_seconds })}</dd></div>
            <div><dt className="font-semibold">{t("rulesLabel")}</dt><dd className="mt-1 text-[#52635f]">{t("freeRules", { count: config.free.monthly_jobs, seconds: config.free.max_clip_seconds })}</dd></div>
          </dl>
          <div className="mt-7 pt-2 md:mt-auto md:pt-8">
            <Link href={needsSignIn ? `/login?return_to=${encodeURIComponent(freeReturn)}` : "/transcribe"} className={PRIMARY}><ArrowRight size={17} aria-hidden="true" />{t(needsSignIn ? "signIn" : "transcribe")}</Link>
          </div>
        </section>

        <section aria-labelledby="pro-plan" className="flex min-w-0 flex-col pt-8 md:pl-8 md:pt-0">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1"><h2 id="pro-plan" className="text-lg font-bold">{t("proName")}</h2><span className="text-xs font-semibold text-[#765527]">{t(config.checkout_enabled ? "testMode" : "proposal")}</span></div>
          <p className="mt-3 text-3xl font-semibold leading-tight">{t("monthlyPrice", { price: price ?? "" })}</p>
          <dl className="mt-7 space-y-5 text-sm leading-6">
            <div><dt className="font-semibold">{t("allowanceLabel")}</dt><dd className="mt-1 text-[#52635f]">{t("paidMinutes", { minutes: config.pro.seconds / 60 })}</dd></div>
            <div><dt className="font-semibold">{t("excerptLabel")}</dt><dd className="mt-1 text-[#52635f]">{t("clipLimit", { seconds: config.pro.max_clip_seconds })}</dd></div>
            <div><dt className="font-semibold">{t("rulesLabel")}</dt><dd className="mt-1 text-[#52635f]">{t("paidRules", { minutes: config.pro.seconds / 60, seconds: config.pro.max_clip_seconds, min: config.pro.min_charge_seconds })}</dd></div>
          </dl>
          <p className="mt-5 text-sm leading-6 text-[#52635f]">{t(config.checkout_enabled ? "testRenewal" : "proposalRenewal")}</p>
          <div className="mt-7 pt-2 md:mt-auto md:pt-8"><CheckoutButton config={config} /></div>
        </section>
      </div>

      <p className="mt-5 text-sm leading-6 text-[#52635f]">{config.usage_enabled ? t("guestRules", { seconds: config.guest.max_clip_seconds }) : t("legacyNotice")}</p>
      {config.guest_usage_enabled && <p className="mt-2 text-sm leading-6 text-[#52635f]">{t("guestTrial", { count: 1 })} {t("guestDayRule")}</p>}
      <section aria-labelledby="purchase-disclosure" className="mt-10 border-t border-[#dce3dc] pt-7">
        <h2 id="purchase-disclosure" className="text-lg font-bold">{t("disclosureTitle")}</h2>
        <div className="mt-4 grid gap-4 text-sm leading-7 text-[#52635f] md:grid-cols-2 md:gap-8">
          <div className="space-y-3"><p>{t("partialFormats")}</p><p>{t("qualityNotice")}</p></div>
          <div className="space-y-3"><p>{t("retention", { hours: config.retention_hours })}</p><p>{t("billingRetention")}</p><p>{t("cancelNote")}</p></div>
        </div>
        <nav className="mt-6 flex flex-wrap gap-x-6 gap-y-3 text-sm font-semibold text-[#075e55]" aria-label={t("disclosureTitle")}>
          <Link href="/account" className="underline underline-offset-4">{t("accountLink")}</Link>
          <Link href="/refund" className="underline underline-offset-4">{t("refundLink")}</Link>
          <Link href="/contact" className="underline underline-offset-4">{t("contactSupport")}</Link>
          <Link href="/privacy" className="underline underline-offset-4">{t("privacyLink")}</Link>
        </nav>
      </section>
    </>}
  </>;
}
