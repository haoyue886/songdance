import { describe, expect, it } from "vitest";
import { JobsApiError } from "@/lib/api/jobs";
import { localizeError } from "./errors";

const translate = (key: string, values?: Record<string, string | number>) =>
  `${key}:${values?.seconds ?? ""}`;

describe("localized API errors", () => {
  it("maps stable quota codes with an actionable retry delay", () => {
    expect(localizeError(
      new JobsApiError("internal API message", 429, "ACTIVE_JOB_LIMIT", 30),
      translate,
    )).toBe("activeJobLimit:30");
  });

  it("uses the safe rate-limit fallback for unknown 429 codes", () => {
    expect(localizeError(new JobsApiError("internal API message", 429, "NEW_LIMIT"), translate))
      .toBe("rateLimit:");
  });
});
