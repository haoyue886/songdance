import { describe, expect, it } from "vitest";
import type { TranscriptionQualityReport } from "@/lib/result/quality-report";
import { qualityWarnings } from "./quality-summary";
import { scoreAssumptionText } from "./task-summary";

const report: TranscriptionQualityReport = {
  schemaVersion: 4,
  reportVersion: "quality-v6",
  postprocessVersion: "cleanup/analysis/score",
  rawNoteCount: 10,
  cleanedNoteCount: 8,
  cleanup: {
    status: "applied",
    version: "cleanup-v3",
    removedNoteCount: 2,
    clippedNoteCount: 0,
    mergedNoteCount: 0,
    fallbackUsed: false,
    errorCode: null,
  },
  analysis: {
    status: "analyzed",
    version: "analysis-v2",
    bpm: 120,
    bpmConfidence: 0.8,
    timeSignature: "4/4",
    timeSignatureConfidence: 0.75,
    timeSignatureSource: "detected",
    keySignature: "C major",
    keyConfidence: 0.7,
    keySignatureSource: "detected",
    reasonCodes: [],
  },
  noteConfidenceMean: 0.82,
  modelVersion: "model-v1",
  reconstruction: { status: "reconstructed", fallbackUsed: false, errorCode: null },
  musicXmlStatus: "passed",
  structureErrors: [],
};

describe("scoreAssumptionText", () => {
  it("explains score layout defaults without presenting them as transcription results", () => {
    expect(
      scoreAssumptionText(["TIME_SIGNATURE_ASSUMED_4_4", "HAND_ASSIGNMENT_MIDDLE_C"]),
    ).toBe("拍号按 4/4 排版；左右手按中央 C 划分；均为排版假设，并非原曲结构识别。");
  });

  it("does not add an explanation when no layout default was used", () => {
    expect(scoreAssumptionText([])).toBeNull();
  });

  it("explains uncertain hand placement and reconstruction fallback", () => {
    expect(
      scoreAssumptionText([
        "UNKNOWN_HAND_NOTATION_FALLBACK",
        "SCORE_RECONSTRUCTION_FALLBACK",
      ]),
    ).toBe(
      "无法确定分手的音符按音高放入谱表；复杂谱面重建失败，已生成基础谱面；均为排版假设，并非原曲结构识别。",
    );
  });
});

describe("qualityWarnings", () => {
  it("keeps a high-quality report free of synthetic warnings", () => {
    expect(qualityWarnings(report)).toEqual([]);
  });

  it("uses backend fallback semantics for low-confidence analysis", () => {
    expect(qualityWarnings({
      ...report,
      analysis: {
        ...report.analysis,
        reasonCodes: [
          "TEMPO_DEFAULTED",
          "TIME_SIGNATURE_DEFAULTED_4_4",
          "KEY_SIGNATURE_DEFAULTED_C_MAJOR",
        ],
      },
    })).toEqual([
      "BPM 置信度不足，当前速度为系统默认值。",
      "拍号置信度不足，当前按 4/4 排版。",
      "调性置信度不足，当前按 C major 排版。",
    ]);
  });

  it("reports cleanup, reconstruction and structure fallbacks", () => {
    expect(qualityWarnings({
      ...report,
      cleanup: { ...report.cleanup, fallbackUsed: true },
      reconstruction: { ...report.reconstruction, fallbackUsed: true },
      musicXmlStatus: "failed",
      structureErrors: ["MEASURE_DURATION_INVALID"],
    })).toEqual([
      "音符清洗失败，预览已回退到原始模型音符。",
      "复杂谱面重建失败，五线谱使用基础排版。",
      "五线谱结构校验未通过；请优先使用钢琴卷帘、MIDI 和原音校对。",
    ]);
  });
});
