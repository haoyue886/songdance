"use client";

import { useEffect, useState, useSyncExternalStore } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useRouter, Link } from "@/i18n/navigation";
import { accessSession, authEnabled, authPost, AuthClientError, guestToken, subscribeGuest } from "@/lib/auth/client";
import { claimJob, getAccount, type Account } from "@/lib/api/jobs";
import { safeReturnPath } from "@/lib/auth/return-path";
import { AccountUsage } from "@/components/billing/account-usage";
import { AccountDeletion } from "./account-deletion";

const INPUT = "mt-2 w-full rounded-xl border border-[#c8d8d2] bg-white px-4 py-3 text-[#15332f]";
const BUTTON = "w-full rounded-full bg-[#147d70] px-5 py-3 font-bold text-white hover:bg-[#075e55] disabled:opacity-50";

export function AuthPanel({ mode, returnTo, initialError = false }: { mode: "login" | "account"; returnTo?: string; initialError?: boolean }) {
  const t = useTranslations("auth");
  const locale = useLocale();
  const prefix = locale === "en" ? "" : `/${locale}`;
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState(initialError ? t("invalid") : "");
  const [resendAt, setResendAt] = useState(0);
  const [now, setNow] = useState(0);
  const [user, setUser] = useState<Account | null>(null);
  const [accountVersion, setAccountVersion] = useState(0);
  const [blockedOwner, setBlockedOwner] = useState<string | null>(null);
  const [loading, setLoading] = useState(mode === "account");
  const target = safeReturnPath(returnTo ?? `${prefix}/account`);
  const jobId = target.match(/\/jobs\/([A-Za-z0-9_-]+)/)?.[1];
  const claimable = useSyncExternalStore(subscribeGuest, () => Boolean(jobId && guestToken(jobId)), () => false);
  useEffect(() => {
    if (!sent) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [sent]);
  const waitSeconds = Math.max(0, Math.ceil((resendAt - now) / 1000));
  useEffect(() => {
    let active = true;
    if (mode === "account" && authEnabled) {
      void getAccount().then((account) => { if (active) setUser(account); })
        .catch(() => { if (active) setError(t("expired")); })
        .finally(() => { if (active) setLoading(false); });
    }
    return () => { active = false; };
  }, [mode, jobId, accountVersion, t]);

  const explain = (reason: unknown) => reason instanceof AuthClientError
    ? t(reason.code === "AUTH_RATE_LIMITED" ? "rateLimited" : reason.code === "AUTH_INVALID" ? "invalid" : reason.code === "AUTH_EXPIRED" ? "expired" : "error") : t("error");
  async function run(work: () => Promise<void>) {
    setBusy(true); setError(""); setNotice("");
    try { await work(); } catch (reason) { setError(explain(reason)); } finally { setBusy(false); }
  }
  async function finishLogin() {
    if (jobId && guestToken(jobId)) {
      await accessSession();
      try { await claimJob(jobId); } catch { setError(t("claimError")); return; }
    }
    window.location.assign(target);
  }
  if (!authEnabled) return <p role="status" className="mt-6">{t("unavailable")}</p>;
  const deletionBlocked = Boolean(user && (user.deletion || blockedOwner === user.id));
  return <section className={mode === "account" ? "mt-8 max-w-2xl" : "mt-8 max-w-lg rounded-lg border border-[#dce3dc] bg-white/85 p-6 shadow-sm sm:p-8"}>
    {mode === "account" ? <>
      {loading ? <p role="status">{t("loading")}</p> : user ? <>
        <p className="break-all font-semibold">{user.email ?? t("deletionCompletedAccount")}</p>
        {!deletionBlocked && <>
          <p className="mt-3 text-sm leading-6 text-[#64736f]">{t("accountBody")}</p>
          <AccountUsage key={user.id} ownerId={user.id} />
        </>}
        <div className="mt-6 flex flex-wrap gap-4">
          {!deletionBlocked && <Link href="/transcribe" className="font-bold text-[#075e55] underline">{t("upload")}</Link>}
          <button disabled={busy} onClick={() => void run(async () => { await authPost("logout"); router.replace("/login"); router.refresh(); })} className="font-semibold underline disabled:opacity-50">{busy ? t("working") : t("signOut")}</button>
        </div>
        {!deletionBlocked && claimable && jobId && <button className={`${BUTTON} mt-5`} disabled={busy} onClick={() => void run(async () => { await claimJob(jobId); setNotice(t("claimed")); })}>{t("claim")}</button>}
        {!deletionBlocked && jobId && <Link href={target} className="mt-4 inline-block underline">{t("back")}</Link>}
        <AccountDeletion key={user.id} ownerId={user.id} initial={{ enabled: user.account_deletion_enabled === true, deletion: user.deletion ?? null }}
          onSnapshot={(snapshot) => setUser((current) => current?.id === user.id ? { ...current, email: snapshot.deletion?.status === "completed" ? null : current.email, deletion: snapshot.deletion, account_deletion_enabled: snapshot.enabled } : current)}
          onBlocked={(blocked) => setBlockedOwner(blocked ? user.id : null)}
          onIdentityChanged={() => { setUser(null); setBlockedOwner(null); setNotice(""); setError(""); setLoading(true); setAccountVersion((value) => value + 1); }} />
      </> : <Link href={`/login?return_to=${encodeURIComponent(target)}`} className="font-bold underline">{t("signIn")}</Link>}
    </> : <>
      <button className={BUTTON} disabled={busy} onClick={() => void run(async () => {
        const result = await authPost("google/start", { return_to: jobId && claimable ? `${prefix}/account?return_to=${encodeURIComponent(target)}` : target });
        window.location.assign(result.url);
      })}>{t("google")}</button>
      <form className="mt-6 space-y-5" onSubmit={(event) => {
        event.preventDefault();
        void run(async () => {
          if (sent) { await authPost("email/verify", { email, token: code, return_to: target }); await finishLogin(); }
          else { await authPost("email/start", { email }); const stamp = Date.now(); setNow(stamp); setResendAt(stamp + 60_000); setSent(true); setNotice(t("sent")); }
        });
      }}>
        <label className="block text-sm font-semibold">{t("email")}<input className={INPUT} type="email" autoComplete="email" required maxLength={254} value={email} disabled={busy || sent} onChange={(event) => setEmail(event.target.value)} /></label>
        {sent && <label className="block text-sm font-semibold">{t("code")}<input className={INPUT} required inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} value={code} disabled={busy} onChange={(event) => setCode(event.target.value)} /></label>}
        <button className={BUTTON} disabled={busy} type="submit">{busy ? t("working") : sent ? t("verify") : t("sendCode")}</button>
        {sent && <button type="button" disabled={busy || waitSeconds > 0} onClick={() => void run(async () => { await authPost("email/start", { email }); const stamp = Date.now(); setNow(stamp); setResendAt(stamp + 60_000); setNotice(t("sent")); })} className="text-sm underline disabled:opacity-50">{t("resend")}{waitSeconds > 0 ? ` (${waitSeconds}s)` : ""}</button>}
      </form>
      <p className="mt-5 text-sm leading-6 text-[#64736f]">{t("fileHint")}</p>
    </>}
    {notice && <p role="status" className="mt-5 rounded-xl bg-[#d9efe7] p-3 text-sm">{notice}</p>}
    {error && <p role="alert" className="mt-5 rounded-xl bg-[#fff1ef] p-3 text-sm text-[#9a493f]">{error}</p>}
  </section>;
}
