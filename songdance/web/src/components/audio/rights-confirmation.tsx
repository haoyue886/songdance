"use client";

import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";

type RightsConfirmationProps = {
  checked: boolean;
  disabled?: boolean;
  onChange: (checked: boolean) => void;
};

export function RightsConfirmation({ checked, disabled, onChange }: RightsConfirmationProps) {
  const t = useTranslations("audio");
  return (
    <label className="flex cursor-pointer items-start gap-3 rounded-2xl border border-[#dce4de] bg-[#f7f9f5] p-4 text-sm leading-6 text-[#52635f]">
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.currentTarget.checked)}
        className="mt-1 size-4 accent-[#147d70]"
      />
      <span>
        {t("rightsText")} {t("rightsPrivacyPrefix")}{" "}
        <Link className="font-bold text-[#075e55] underline underline-offset-2" href="/privacy">
          {t("privacy")}
        </Link>
        {t("and")}
        <Link className="font-bold text-[#075e55] underline underline-offset-2" href="/terms">
          {t("terms")}
        </Link>
        .
      </span>
    </label>
  );
}
