import { describe, expect, it } from "vitest";
import { cleanupActionCount, parseQualityReport } from "./quality-report";

const summary = {
  schema_version: 4,
  quality_report_version: "quality-report-v6",
  postprocess_version: "cleanup/analysis/score",
  raw_note_count: 12,
  cleaned_note_count: 9,
  cleanup: {
    status: "applied",
    version: "cleanup-v3",
    removed_note_count: 2,
    clipped_note_count: 1,
    merged_note_count: 0,
    fallback_used: false,
    error_code: null,
  },
  analysis: {
    status: "analyzed",
    version: "analysis-v2",
    bpm: 118,
    bpm_confidence: 0.8,
    time_signature: "3/4",
    time_signature_confidence: 0.7,
    time_signature_source: "detected",
    key_signature: "G major",
    key_confidence: 0.65,
    key_signature_source: "detected",
    reason_codes: [],
  },
  confidence: { min: 0.2, max: 0.99, mean: 0.82 },
  model: { version: "basic-pitch-v1", thresholds: {} },
  reconstruction: { status: "reconstructed", fallback_used: false, error_code: null },
  musicxml_parse: { status: "passed" },
  structure_errors: [],
};

describe("quality report parser", () => {
  it("parses the persisted report and counts cleanup actions", () => {
    const report = parseQualityReport({
      report_version: "quality-report-v6",
      summary: JSON.stringify(summary),
    });

    expect(report?.analysis.keySignature).toBe("G major");
    expect(report?.analysis.timeSignatureConfidence).toBe(0.7);
    expect(report && cleanupActionCount(report)).toBe(3);
  });

  it.each([
    null,
    { report_version: "v", summary: "not-json" },
    { report_version: "v", summary: JSON.stringify({ ...summary, analysis: null }) },
    { report_version: "v", summary: JSON.stringify({ ...summary, raw_note_count: -1 }) },
  ])("returns an empty state for missing or malformed reports", (input) => {
    expect(parseQualityReport(input)).toBeNull();
  });
});
