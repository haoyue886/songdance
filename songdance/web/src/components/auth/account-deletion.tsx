"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { LoaderCircle, LogIn, RefreshCw, Trash2, X } from "lucide-react";
import { Link, useRouter } from "@/i18n/navigation";
import { languageTag, type AppLocale } from "@/i18n/routing";
import { authPost } from "@/lib/auth/client";
import { AccountDeletionApiError, getAccountDeletion, requestAccountDeletion, type AccountDeletionSnapshot } from "@/lib/api/account-deletion";

type Props = {
  ownerId: string;
  initial: AccountDeletionSnapshot;
  onSnapshot: (snapshot: AccountDeletionSnapshot) => void;
  onBlocked: (blocked: boolean) => void;
  onIdentityChanged: () => void;
};

const COMMAND = "inline-flex min-h-11 items-center justify-center gap-2 rounded-md border border-[#9a493f] bg-white px-4 py-2 text-sm font-semibold text-[#9a493f] hover:bg-[#fff1ef] disabled:opacity-50";

export function AccountDeletion(props: Props) {
  return <AccountDeletionState key={props.ownerId} {...props} />;
}

function AccountDeletionState({ ownerId, initial, onSnapshot, onBlocked, onIdentityChanged }: Props) {
  const t = useTranslations("auth");
  const locale = useLocale() as AppLocale;
  const router = useRouter();
  const [snapshot, setSnapshot] = useState(initial);
  const [confirming, setConfirming] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [reauth, setReauth] = useState(false);
  const [unknown, setUnknown] = useState(false);
  const [pollVersion, setPollVersion] = useState(0);
  const lock = useRef(false);
  const active = useRef(true);
  const owner = useRef(ownerId);
  const callbacks = useRef({ onSnapshot, onBlocked, onIdentityChanged });
  useEffect(() => { callbacks.current = { onSnapshot, onBlocked, onIdentityChanged }; }, [onSnapshot, onBlocked, onIdentityChanged]);
  useEffect(() => {
    active.current = true;
    owner.current = ownerId;
    return () => { active.current = false; };
  }, [ownerId]);
  const current = useCallback(() => active.current && owner.current === ownerId, [ownerId]);

  const accept = useCallback((value: AccountDeletionSnapshot) => {
    if (!current()) return;
    setSnapshot(value); setUnknown(false); setError(""); setReauth(false); setConfirmed(false); setConfirming(false);
    callbacks.current.onSnapshot(value);
    callbacks.current.onBlocked(Boolean(value.deletion));
  }, [current]);
  const explain = useCallback((reason: unknown) => {
    if (!current()) return;
    if (reason instanceof AccountDeletionApiError && reason.status === 401) {
      setConfirmed(false); setConfirming(false); setError("");
      callbacks.current.onIdentityChanged();
      return;
    }
    setError(t(reason instanceof AccountDeletionApiError && reason.code === "REAUTH_REQUIRED" ? "deletionReauth" : "deletionLoadError"));
    setReauth(reason instanceof AccountDeletionApiError && reason.code === "REAUTH_REQUIRED");
    if (reason instanceof AccountDeletionApiError && reason.code === "REAUTH_REQUIRED") setConfirmed(false);
  }, [current, t]);
  const refresh = useCallback(async (signal?: AbortSignal) => {
    const value = await getAccountDeletion(ownerId, signal);
    if (!signal?.aborted) accept(value);
  }, [ownerId, accept]);

  const deletion = snapshot.deletion;
  const polling = deletion?.status === "pending" || deletion?.status === "retry";
  useEffect(() => {
    if (!polling) return;
    const controller = new AbortController();
    let count = 0;
    const timer = setInterval(() => {
      if (++count >= 8) clearInterval(timer);
      if (lock.current) return;
      lock.current = true;
      void refresh(controller.signal).catch((reason) => { if (!controller.signal.aborted) explain(reason); })
        .finally(() => { lock.current = false; });
    }, 15_000);
    return () => { controller.abort(); clearInterval(timer); };
  }, [polling, pollVersion, refresh, explain]);

  async function manualRefresh() {
    if (lock.current) return;
    lock.current = true; setBusy(true); setError("");
    try { await refresh(); if (current()) setPollVersion((value) => value + 1); }
    catch (reason) { explain(reason); }
    finally { lock.current = false; if (current()) setBusy(false); }
  }

  async function submit() {
    if (lock.current || !confirmed || snapshot.deletion || unknown || !snapshot.enabled) return;
    lock.current = true; setBusy(true); setError(""); setReauth(false);
    try {
      const result = await requestAccountDeletion(ownerId);
      if (!current()) return;
      callbacks.current.onBlocked(true);
      setConfirming(false); setConfirmed(false); setUnknown(true);
      if (result.deletion?.status !== "completed") {
        setSnapshot(result); callbacks.current.onSnapshot(result);
      }
      // Completion is displayed only after a separate authenticated status read.
      await refresh();
    } catch (reason) {
      if (!current()) return;
      if (reason instanceof AccountDeletionApiError && reason.uncertain) {
        setUnknown(true); setConfirming(false); setConfirmed(false); callbacks.current.onBlocked(true);
        try { await refresh(); } catch (readError) { explain(readError); }
      } else { explain(reason); }
    } finally { lock.current = false; if (current()) setBusy(false); }
  }

  async function signInAgain() {
    if (lock.current) return;
    lock.current = true; setBusy(true); setError(""); setConfirmed(false);
    try {
      await authPost("logout");
      if (current()) {
        const prefix = locale === "en" ? "" : `/${locale}`;
        router.replace(`/login?return_to=${encodeURIComponent(`${prefix}/account`)}`);
        router.refresh();
      }
    } catch { if (current()) setError(t("error")); }
    finally { lock.current = false; if (current()) setBusy(false); }
  }

  if (!snapshot.enabled && !deletion && !unknown) return null;
  const stateKey = deletion?.status === "completed" ? "deletionCompleted"
    : deletion?.status === "review" ? "deletionReview"
      : deletion?.status === "retry" ? deletion.phase === "billing" ? "deletionRetryBilling" : "deletionRetryCleanup"
        : deletion?.phase === "cleanup" ? "deletionCleanup" : "deletionBilling";
  return <section className="mt-8 border-t border-[#dce3dc] pt-6" aria-label={t("deletionTitle")}>
    <div className="flex items-center justify-between gap-3">
      <h2 className="text-lg font-bold">{t("deletionTitle")}</h2>
      {(deletion || unknown) && <button type="button" title={t("deletionRefresh")} aria-label={t("deletionRefresh")} disabled={busy} onClick={() => void manualRefresh()} className="grid h-10 w-10 shrink-0 place-items-center rounded-md border border-[#c8d8d2] bg-white hover:bg-[#eef5f2] disabled:opacity-50">
        <RefreshCw size={17} aria-hidden="true" className={busy ? "animate-spin" : ""} />
      </button>}
    </div>
    {deletion ? <>
      <p role="status" className="mt-4 font-semibold">{t(stateKey)}</p>
      <p className="mt-3 text-sm leading-6 text-[#64736f]">{t(deletion.status === "completed" ? "deletionCompletedBody" : "deletionProcessingBody")}</p>
      <p className="mt-3 text-sm leading-6 text-[#64736f]">{t("deletionRequestedAt", { date: new Intl.DateTimeFormat(languageTag(locale), { dateStyle: "medium", timeStyle: "short" }).format(new Date(deletion.requested_at)) })}</p>
      {deletion.error_code && <p className="mt-3 break-all text-sm text-[#9a493f]">{t("deletionErrorCode", { code: deletion.error_code })}</p>}
    </> : unknown ? <p role="status" className="mt-4 text-sm leading-6 text-[#64736f]">{t("deletionUnknown")}</p> : confirming ? <>
      <p className="mt-4 text-sm leading-6 text-[#64736f]">{t("deletionImpact")}</p>
      <label className="mt-4 flex cursor-pointer items-start gap-3 text-sm leading-6"><input type="checkbox" className="mt-1 h-4 w-4 shrink-0 accent-[#9a493f]" disabled={busy} checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />{t("deletionConfirm")}</label>
      <div className="mt-5 flex items-center gap-3">
        <button type="button" className={COMMAND} disabled={busy || !confirmed || reauth} onClick={() => void submit()}>{busy ? <LoaderCircle size={17} className="shrink-0 animate-spin" aria-hidden="true" /> : <Trash2 size={17} className="shrink-0" aria-hidden="true" />}{t("deletionSubmit")}</button>
        <button type="button" disabled={busy} title={t("deletionCancel")} aria-label={t("deletionCancel")} onClick={() => { setConfirming(false); setConfirmed(false); setError(""); setReauth(false); }} className="grid h-10 w-10 shrink-0 place-items-center rounded-md border border-[#c8d8d2] bg-white hover:bg-[#eef5f2] disabled:opacity-50"><X size={17} aria-hidden="true" /></button>
      </div>
    </> : <button type="button" className={`${COMMAND} mt-4`} disabled={busy} onClick={() => { setConfirming(true); setError(""); }}><Trash2 size={17} aria-hidden="true" />{t("deletionAction")}</button>}
    {unknown && deletion && <p role="status" className="mt-3 text-sm leading-6 text-[#64736f]">{t("deletionUnknown")}</p>}
    {error && <p role="alert" className="mt-4 text-sm leading-6 text-[#9a493f]">{error}</p>}
    {reauth && <button type="button" className={`${COMMAND} mt-4`} disabled={busy} onClick={() => void signInAgain()}>{busy ? <LoaderCircle size={17} className="shrink-0 animate-spin" aria-hidden="true" /> : <LogIn size={17} className="shrink-0" aria-hidden="true" />}{t("deletionReauthAction")}</button>}
    {(deletion || unknown) && <Link href="/contact" className="mt-4 inline-block text-sm font-semibold text-[#075e55] underline">{t("deletionSupport")}</Link>}
  </section>;
}
