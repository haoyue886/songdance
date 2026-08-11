import en from "../../messages/en.json";
import zhCN from "../../messages/zh-CN.json";
import type { AppLocale } from "./routing";

export type AppMessages = typeof en;

export function getAppMessages(locale: AppLocale): AppMessages {
  return locale === "zh-CN" ? zhCN : en;
}

export function formatMessage(
  template: string,
  values: Record<string, string | number>,
): string {
  return Object.entries(values).reduce(
    (message, [key, value]) => message.replaceAll(`{${key}}`, String(value)),
    template,
  );
}
