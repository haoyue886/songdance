import { describe, expect, it } from "vitest";
import en from "../../messages/en.json";
import zhCn from "../../messages/zh-CN.json";
import de from "../../messages/de.json";
import es from "../../messages/es.json";
import fr from "../../messages/fr.json";
import ja from "../../messages/ja.json";
import ko from "../../messages/ko.json";
import ptBR from "../../messages/pt-BR.json";
import { getAppMessages } from "./messages";
import { routing } from "./routing";

function leafKeys(value: unknown, prefix = ""): string[] {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return [prefix];
  return Object.entries(value).flatMap(([key, child]) =>
    leafKeys(child, prefix ? `${prefix}.${key}` : key));
}

describe("locale messages", () => {
  it("keeps every supported locale message tree aligned", () => {
    const expected = leafKeys(en).sort();
    for (const messages of [de, es, fr, ja, ko, ptBR, zhCn]) {
      expect(leafKeys(messages).sort()).toEqual(expected);
    }
    for (const locale of routing.locales) {
      expect(leafKeys(getAppMessages(locale)).sort()).toEqual(expected);
    }
  });

  it("does not ship blank user-facing messages", () => {
    for (const messages of [en, de, es, fr, ja, ko, ptBR, zhCn]) {
      const blanks = leafKeys(messages).filter((key) => {
        const value = key.split(".").reduce<unknown>((current, part) =>
          typeof current === "object" && current !== null
            ? (current as Record<string, unknown>)[part]
            : undefined, messages);
        return typeof value !== "string" || value.trim() === "";
      });
      expect(blanks).toEqual([]);
    }
  });
});
