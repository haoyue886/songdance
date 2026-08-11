import { describe, expect, it } from "vitest";
import en from "../../messages/en.json";
import zhCn from "../../messages/zh-CN.json";

function leafKeys(value: unknown, prefix = ""): string[] {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return [prefix];
  return Object.entries(value).flatMap(([key, child]) =>
    leafKeys(child, prefix ? `${prefix}.${key}` : key));
}

describe("locale messages", () => {
  it("keeps English and Simplified Chinese message keys aligned", () => {
    expect(leafKeys(en).sort()).toEqual(leafKeys(zhCn).sort());
  });

  it("does not ship blank user-facing messages", () => {
    for (const messages of [en, zhCn]) {
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
