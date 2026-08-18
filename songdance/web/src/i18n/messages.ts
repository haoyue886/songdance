import en from "../../messages/en.json";
import zhCN from "../../messages/zh-CN.json";
import de from "../../messages/de.json";
import es from "../../messages/es.json";
import fr from "../../messages/fr.json";
import ja from "../../messages/ja.json";
import ko from "../../messages/ko.json";
import ptBR from "../../messages/pt-BR.json";
import type { AppLocale } from "./routing";

export type AppMessages = typeof en;

const BASE_MESSAGES: Record<Exclude<AppLocale, "en" | "zh">, AppMessages> = {
  ja,
  ko,
  es,
  "pt-br": ptBR,
  fr,
  de,
};

export function getAppMessages(locale: AppLocale): AppMessages {
  if (locale === "zh") return zhCN;
  if (locale === "en") return en;
  return BASE_MESSAGES[locale];
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
