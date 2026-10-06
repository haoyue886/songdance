"use client";

import { useEffect, useRef, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { ArrowUpRight, RefreshCw, LoaderCircle } from "lucide-react";
import { Link } from "@/i18n/navigation";
import { languageTag, type AppLocale } from "@/i18n/routing";
import { BillingApiError, createPortal, getBillingConfig, getBillingSummary, notifyBillingChanged, type BillingConfig, type BillingSummary } from "@/lib/api/billing";
import { CheckoutButton } from "./checkout-button";
import { PRIMARY, SECONDARY } from "./styles";

export function AccountUsage({ ownerId }: { ownerId: string }) {
  const t = useTranslations("billing");
  const locale = useLocale() as AppLocale;
  const [version, setVersion] = useState(0);
  const [data, setData] = useState<{ config: BillingConfig; summary: BillingSummary } | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [portalBusy, setPortalBusy] = useState(false);
  const portalLock = useRef(false);
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    void Promise.all([getBillingConfig(controller.signal), getBillingSummary(controller.signal)])
      .then(([config, summary]) => {
        if (summary.owner_id && summary.owner_id !== ownerId) throw new BillingApiError("AUTH_CHANGED", 401);
        if (active) { setData({ config, summary }); setError(""); notifyBillingChanged(); }
      })
      .catch((reason) => { if (active) { setData(null); setError(t(reason instanceof BillingApiError && reason.status === 401 ? "authExpired" : "loadError")); } })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; controller.abort(); };
  }, [ownerId, version, t]);

  async function openPortal() {
    if (portalLock.current) return;
    portalLock.current = true; setPortalBusy(true); setError("");
    try { window.location.assign(await createPortal(ownerId)); }
    catch { setError(t("portalError")); }
    finally { portalLock.current = false; setPortalBusy(false); }
  }
  const summary = data?.summary;
  const config = data?.config;
  const refresh = () => { setData(null); setError(""); setLoading(true); setVersion((value) => value + 1); };
  return <div className="mt-6 border-t border-[#dce3dc] pt-6">
    <div className="flex items-center justify-between gap-3">
      <h2 className="text-lg font-bold">{t("plan")}</h2>
      <button type="button" title={t("refresh")} aria-label={t("refresh")} disabled={loading} onClick={refresh} className="grid h-10 w-10 shrink-0 place-items-center rounded-md border border-[#c8d8d2] bg-white hover:bg-[#eef5f2] disabled:opacity-50">
        <RefreshCw size={17} aria-hidden="true" className={loading ? "animate-spin" : ""} />
      </button>
    </div>
    {loading && !data && <p role="status" className="mt-4 text-sm text-[#64736f]">{t("loading")}</p>}
    {error && <p role="alert" className="mt-4 text-sm leading-6 text-[#9a493f]">{error}</p>}
    {summary && config && <>
      {!summary.enabled ? <p className="mt-4 text-sm leading-6 text-[#64736f]">{t("meterOff")}</p> : <>
        <div className="mt-5 flex flex-wrap items-baseline justify-between gap-3">
          <p className="text-xl font-bold">{t(summary.plan === "pro" ? "proName" : "freeName")}</p>
          <p className="text-sm font-semibold text-[#075e55]">{summary.unit === "seconds" ? t("remainingSeconds", { seconds: summary.remaining ?? 0 }) : t("remainingJobs", { count: summary.remaining ?? 0 })}</p>
        </div>
        <progress aria-label={t("used")} max={summary.limit || 1} value={(summary.used ?? 0) + (summary.reserved ?? 0)} className="mt-4 h-2 w-full accent-[#147d70]" />
        <dl className="mt-4 grid grid-cols-2 gap-5 border-b border-[#dce3dc] pb-5 text-sm">
          <div><dt className="text-[#64736f]">{t("used")}</dt><dd className="mt-1 font-semibold">{summary.unit === "seconds" ? t("secondsValue", { seconds: summary.used ?? 0 }) : summary.used}</dd></div>
          <div><dt className="text-[#64736f]">{t("reserved")}</dt><dd className="mt-1 font-semibold">{summary.unit === "seconds" ? t("secondsValue", { seconds: summary.reserved ?? 0 }) : summary.reserved}</dd></div>
        </dl>
        <p className="mt-4 text-sm leading-6 text-[#64736f]">{t("periodEnds")} {new Intl.DateTimeFormat(languageTag(locale), { year: "numeric", month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZoneName: "short" }).format(new Date(summary.period_end!))}</p>
        <p className="mt-3 text-sm leading-6 text-[#64736f]">{summary.plan === "pro" ? t("paidRules", { minutes: (summary.limit ?? config.pro.seconds) / 60, seconds: summary.max_clip_seconds ?? config.pro.max_clip_seconds, min: config.pro.min_charge_seconds }) : t("freeRules", { count: summary.limit ?? config.free.monthly_jobs, seconds: summary.max_clip_seconds ?? config.free.max_clip_seconds })}</p>
        {(summary.remaining ?? 0) === 0 && <p role="status" className="mt-3 text-sm font-semibold text-[#9a493f]">{t("balanceEmpty")}</p>}
      </>}
      {(summary.sync_state === "review_required" || summary.state === "frozen" || summary.state === "revoked") && <p role="status" className="mt-4 border-l-2 border-[#9a493f] pl-3 text-sm leading-6 text-[#9a493f]">{t("reviewRequired")}</p>}
      {summary.sync_state === "payment_confirming" && <Link href="/billing/return" className="mt-4 inline-block text-sm font-semibold text-[#075e55] underline">{t("paymentPending")}</Link>}
      <div className="mt-6 flex flex-wrap gap-3">
        {summary.portal_available && config.checkout_enabled && <button type="button" className={PRIMARY} onClick={() => void openPortal()} disabled={portalBusy}>{portalBusy ? <LoaderCircle size={17} className="animate-spin" /> : <ArrowUpRight size={17} />}{t("manageBilling")}</button>}
        {summary.plan !== "pro" && summary.sync_state !== "review_required" && config.checkout_enabled && <CheckoutButton config={config} ownerId={ownerId} />}
        <Link className={SECONDARY} href="/pricing">{t("plans")}</Link>
        <Link className={SECONDARY} href="/contact">{t("contactSupport")}</Link>
      </div>
      {summary.portal_available && <p className="mt-4 text-sm leading-6 text-[#64736f]">{t("cancelNote")}</p>}
      <p className="mt-5 text-sm leading-6 text-[#64736f]">{t("retention", { hours: config.retention_hours })}</p>
    </>}
  </div>;
}
