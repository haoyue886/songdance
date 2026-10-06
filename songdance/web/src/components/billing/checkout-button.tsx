"use client";

import { useRef, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { CreditCard, LoaderCircle } from "lucide-react";
import { authEnabled } from "@/lib/auth/client";
import { getAccount } from "@/lib/api/jobs";
import { BillingApiError, createCheckout, type BillingConfig } from "@/lib/api/billing";
import { useRouter } from "@/i18n/navigation";
import { PRIMARY } from "./styles";

export function CheckoutButton({ config, ownerId }: { config: BillingConfig; ownerId?: string }) {
  const t = useTranslations("billing");
  const locale = useLocale();
  const router = useRouter();
  const lock = useRef(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const available = config.checkout_enabled && authEnabled;
  async function purchase() {
    if (lock.current || !available) return;
    lock.current = true; setBusy(true); setError("");
    try {
      const account = ownerId ? { id: ownerId } : await getAccount();
      const reply = await createCheckout(account.id);
      if (reply.checkout_url && reply.status === "pending") window.location.assign(reply.checkout_url);
      else if (reply.status === "failed" || reply.status === "expired") setError(t(reply.status === "failed" ? "paymentFailed" : "paymentExpired"));
      else router.push("/billing/return");
    } catch (reason) {
      const code = reason instanceof BillingApiError ? reason.code : reason && typeof reason === "object" && "status" in reason && reason.status === 401 ? "AUTH_REQUIRED" : "BILLING_UNAVAILABLE";
      if (["AUTH_REQUIRED", "AUTH_EXPIRED", "AUTH_INVALID", "AUTH_REVOKED", "AUTH_CHANGED"].includes(code)) router.push(`/login?return_to=${encodeURIComponent(`${locale === "en" ? "" : `/${locale}`}/pricing`)}`);
      else if (code === "SUBSCRIPTION_EXISTS" || code === "BILLING_REVIEW_REQUIRED") router.push("/account");
      else setError(t("checkoutError"));
    } finally { lock.current = false; setBusy(false); }
  }
  return <div>
    <button type="button" disabled={!available || busy} className={PRIMARY} onClick={() => void purchase()}>
      {busy ? <LoaderCircle size={17} className="animate-spin" aria-hidden="true" /> : <CreditCard size={17} aria-hidden="true" />}
      {busy ? t("working") : available ? t("testCheckout") : t("notAvailable")}
    </button>
    {error && <p role="alert" className="mt-3 max-w-md text-sm leading-6 text-[#9a493f]">{error}</p>}
  </div>;
}
