"use client";

import { useLocale, useMessages } from "next-intl";
import type { AppMessages } from "./messages";
import type { AppLocale } from "./routing";

export function useAppMessages(): AppMessages {
  return useMessages() as AppMessages;
}

export function useAppLocale(): AppLocale {
  return useLocale() as AppLocale;
}
