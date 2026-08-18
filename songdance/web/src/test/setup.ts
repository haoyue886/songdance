import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import React from "react";
import { afterEach, vi } from "vitest";
import zhMessages from "../../messages/zh-CN.json";

type Messages = Record<string, unknown>;

function messageValue(namespace: string | undefined, key: string, values?: Record<string, unknown>): string {
  const path = [...(namespace ? namespace.split(".") : []), ...key.split(".")];
  let value: unknown = zhMessages as Messages;
  for (const part of path) value = typeof value === "object" && value ? (value as Messages)[part] : undefined;
  if (typeof value !== "string") return key;
  return Object.entries(values ?? {}).reduce((text, [name, replacement]) => text.replaceAll(`{${name}}`, String(replacement)), value);
}

const TRANSLATORS = new Map<string, (key: string, values?: Record<string, unknown>) => string>();
const translator = (namespace?: string) => {
  const cacheKey = namespace ?? "";
  const cached = TRANSLATORS.get(cacheKey);
  if (cached) return cached;
  const next = (key: string, values?: Record<string, unknown>) => messageValue(namespace, key, values);
  TRANSLATORS.set(cacheKey, next);
  return next;
};

vi.mock("next-intl", () => ({
  hasLocale: (locales: readonly string[], locale: string) => locales.includes(locale),
  NextIntlClientProvider: ({ children }: { children: React.ReactNode }) => children,
  useLocale: () => "zh",
  useMessages: () => zhMessages,
  useTranslations: translator,
}));

vi.mock("next-intl/server", () => ({
  getMessages: async () => zhMessages,
  getTranslations: async (input?: string | { namespace?: string }) => translator(typeof input === "string" ? input : input?.namespace),
  setRequestLocale: () => undefined,
}));

vi.mock("next-intl/navigation", () => ({
  createNavigation: () => ({
    Link: ({ href, children, ...props }: { href: string; children: React.ReactNode }) => React.createElement("a", { href, ...props }, children),
    redirect: vi.fn(),
    usePathname: () => "/",
    useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
    getPathname: ({ href }: { href: string }) => href,
  }),
}));

afterEach(() => cleanup());
