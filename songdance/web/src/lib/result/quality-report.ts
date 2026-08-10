import type { QualityReportEnvelope } from "@/lib/api/jobs";

export type TranscriptionQualityReport = {
  schemaVersion: number;
  reportVersion: string;
  postprocessVersion: string;
  rawNoteCount: number;
  cleanedNoteCount: number | null;
  cleanup: {
    status: string;
    version: string;
    removedNoteCount: number;
    clippedNoteCount: number;
    mergedNoteCount: number;
    fallbackUsed: boolean;
    errorCode: string | null;
  };
  analysis: {
    status: string;
    version: string;
    bpm: number | null;
    bpmConfidence: number | null;
    timeSignature: string | null;
    timeSignatureConfidence: number | null;
    timeSignatureSource: string | null;
    keySignature: string | null;
    keyConfidence: number | null;
    keySignatureSource: string | null;
    reasonCodes: string[];
  };
  noteConfidenceMean: number | null;
  modelVersion: string;
  reconstruction: {
    status: string;
    fallbackUsed: boolean;
    errorCode: string | null;
  };
  musicXmlStatus: string;
  structureErrors: string[];
};

export function parseQualityReport(
  envelope: QualityReportEnvelope | null | undefined,
): TranscriptionQualityReport | null {
  if (!envelope || typeof envelope.summary !== "string") return null;
  try {
    const input: unknown = JSON.parse(envelope.summary);
    if (!isRecord(input)) return null;
    const cleanup = record(input.cleanup);
    const analysis = record(input.analysis);
    const confidence = record(input.confidence);
    const model = record(input.model);
    const reconstruction = record(input.reconstruction);
    const musicXml = record(input.musicxml_parse);
    if (!cleanup || !analysis || !confidence || !model || !reconstruction || !musicXml) {
      return null;
    }
    const rawNoteCount = nonNegativeInteger(input.raw_note_count);
    const schemaVersion = nonNegativeInteger(input.schema_version);
    if (
      rawNoteCount === null ||
      schemaVersion === null ||
      typeof input.quality_report_version !== "string" ||
      typeof input.postprocess_version !== "string" ||
      typeof cleanup.status !== "string" ||
      typeof cleanup.version !== "string" ||
      typeof analysis.status !== "string" ||
      typeof analysis.version !== "string" ||
      typeof model.version !== "string" ||
      typeof reconstruction.status !== "string" ||
      typeof musicXml.status !== "string"
    ) {
      return null;
    }
    const reasonCodes = stringArray(analysis.reason_codes);
    const structureErrors = stringArray(input.structure_errors);
    if (!reasonCodes || !structureErrors) return null;

    return {
      schemaVersion,
      reportVersion: input.quality_report_version,
      postprocessVersion: input.postprocess_version,
      rawNoteCount,
      cleanedNoteCount: nullableNonNegativeInteger(input.cleaned_note_count),
      cleanup: {
        status: cleanup.status,
        version: cleanup.version,
        removedNoteCount: nonNegativeInteger(cleanup.removed_note_count) ?? 0,
        clippedNoteCount: nonNegativeInteger(cleanup.clipped_note_count) ?? 0,
        mergedNoteCount: nonNegativeInteger(cleanup.merged_note_count) ?? 0,
        fallbackUsed: cleanup.fallback_used === true,
        errorCode: nullableString(cleanup.error_code),
      },
      analysis: {
        status: analysis.status,
        version: analysis.version,
        bpm: nullableNumber(analysis.bpm),
        bpmConfidence: confidenceValue(analysis.bpm_confidence),
        timeSignature: nullableString(analysis.time_signature),
        timeSignatureConfidence: confidenceValue(analysis.time_signature_confidence),
        timeSignatureSource: nullableString(analysis.time_signature_source),
        keySignature: nullableString(analysis.key_signature),
        keyConfidence: confidenceValue(analysis.key_confidence),
        keySignatureSource: nullableString(analysis.key_signature_source),
        reasonCodes,
      },
      noteConfidenceMean: confidenceValue(confidence.mean),
      modelVersion: model.version,
      reconstruction: {
        status: reconstruction.status,
        fallbackUsed: reconstruction.fallback_used === true,
        errorCode: nullableString(reconstruction.error_code),
      },
      musicXmlStatus: musicXml.status,
      structureErrors,
    };
  } catch {
    return null;
  }
}

export function cleanupActionCount(report: TranscriptionQualityReport): number {
  return report.cleanup.removedNoteCount
    + report.cleanup.clippedNoteCount
    + report.cleanup.mergedNoteCount;
}

function isRecord(input: unknown): input is Record<string, unknown> {
  return typeof input === "object" && input !== null;
}

function record(input: unknown): Record<string, unknown> | null {
  return isRecord(input) ? input : null;
}

function nonNegativeInteger(input: unknown): number | null {
  return Number.isInteger(input) && (input as number) >= 0 ? input as number : null;
}

function nullableNonNegativeInteger(input: unknown): number | null {
  return input === null ? null : nonNegativeInteger(input);
}

function nullableNumber(input: unknown): number | null {
  return typeof input === "number" && Number.isFinite(input) ? input : null;
}

function confidenceValue(input: unknown): number | null {
  const value = nullableNumber(input);
  return value !== null && value >= 0 && value <= 1 ? value : null;
}

function nullableString(input: unknown): string | null {
  return typeof input === "string" ? input : null;
}

function stringArray(input: unknown): string[] | null {
  return Array.isArray(input) && input.every((value) => typeof value === "string")
    ? input
    : null;
}
