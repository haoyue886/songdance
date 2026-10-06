"use client";

import { useEffect, useState } from "react";
import { accessSession, authEnabled } from "@/lib/auth/client";
import { getBillingConfig, getBillingSummary, type BillingConfig, type BillingSummary } from "@/lib/api/billing";
import { guestSession, type GuestSession } from "@/lib/api/guest";

export function useUploadBilling() {
  const [data, setData] = useState<{ config: BillingConfig; summary: BillingSummary | null; guest?: GuestSession } | null>(null);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    void (async () => {
      const config = await getBillingConfig(controller.signal);
      const access = authEnabled ? await accessSession() : null;
      const summary = access && config.usage_enabled ? await getBillingSummary(controller.signal) : null;
      const guest = !access && config.guest_usage_enabled ? await guestSession() : undefined;
      if (active) { setData({ config, summary, guest }); setFailed(false); }
    })().catch(() => { if (active) { setData(null); setFailed(true); } });
    return () => { active = false; controller.abort(); };
  }, [version]);
  return { data, failed, pending: !data && !failed,
    refresh: () => setVersion((value) => value + 1),
    maxSeconds: data?.config.usage_enabled ? data.summary?.max_clip_seconds ?? data.config.guest.max_clip_seconds : 90 };
}
