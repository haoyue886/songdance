"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, Clock3, RefreshCw } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { BillingApiError, getBillingSummary, notifyBillingChanged, type BillingSummary } from "@/lib/api/billing";
import { PRIMARY, SECONDARY } from "./styles";

type State = "checking" | "ready" | "waiting" | "timeout" | "failed" | "expired" | "review" | "missing" | "auth" | "error";
function decide(summary: BillingSummary): State {
  if (summary.sync_state === "review_required" || summary.state === "frozen" || summary.state === "revoked") return "review";
  if (summary.checkout_status === "failed") return "failed";
  if (summary.checkout_status === "expired") return "expired";
  if (summary.plan === "pro" && summary.state === "active" && summary.sync_state === "ready") return "ready";
  if (summary.sync_state === "payment_confirming") return "waiting";
  return "missing";
}

export function PaymentReturn() {
  const t = useTranslations("billing");
  const locale = useLocale();
  const [state, setState] = useState<State>("checking");
  const [version, setVersion] = useState(0);
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const controller = new AbortController();
    const deadline = Date.now() + 60_000;
    const deadlineTimer = setTimeout(() => {
      if (active) { active = false; clearTimeout(timer); controller.abort(); setState("timeout"); }
    }, 60_000);
    async function poll() {
      try {
        const summary = await getBillingSummary(controller.signal);
        if (!active) return;
        const next = decide(summary);
        if (next !== "waiting") { clearTimeout(deadlineTimer); setState(next); if (next === "ready") notifyBillingChanged(); return; }
        if (Date.now() >= deadline) { setState("timeout"); return; }
        setState("waiting");
        timer = setTimeout(() => void poll(), Math.min(3000, deadline - Date.now()));
      } catch (reason) {
        if (active) { clearTimeout(deadlineTimer); setState(reason instanceof BillingApiError && reason.status === 401 ? "auth" : "error"); }
      }
    }
    void poll();
    return () => { active = false; controller.abort(); clearTimeout(timer); clearTimeout(deadlineTimer); };
  }, [version]);
  const key = ({ checking: "loading", ready: "paymentConfirmed", waiting: "paymentPending", timeout: "paymentTimeout", failed: "paymentFailed", expired: "paymentExpired", review: "reviewRequired", missing: "paymentMissing", auth: "authExpired", error: "paymentUnknown" } as const)[state];
  const checking = state === "checking" || state === "waiting";
  return <div className="mt-8 max-w-2xl border-y border-[#dce3dc] py-8">
    {state === "ready" ? <CheckCircle2 size={28} className="text-[#147d70]" aria-hidden="true" /> : <Clock3 size={28} className="text-[#52635f]" aria-hidden="true" />}
    <p role={state === "error" ? "alert" : "status"} className="mt-5 text-lg font-semibold leading-7">{t(key)}</p>
    <div className="mt-6 flex flex-wrap gap-3">
      {state === "auth" ? <Link className={PRIMARY} href={`/login?return_to=${encodeURIComponent(`${locale === "en" ? "" : `/${locale}`}/billing/return`)}`}>{t("signIn")}</Link> : <Link className={PRIMARY} href={state === "ready" ? "/transcribe" : "/account"}>{t(state === "ready" ? "transcribe" : "backToAccount")}</Link>}
      {!checking && state !== "ready" && state !== "auth" && <button className={SECONDARY} type="button" onClick={() => { setState("checking"); setVersion((value) => value + 1); }}><RefreshCw size={16} aria-hidden="true" />{t("refresh")}</button>}
      <Link href="/contact" className={SECONDARY}>{t("contactSupport")}</Link>
    </div>
  </div>;
}
