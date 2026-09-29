import argparse
import json
from pathlib import Path

from scripts.piano_comparison_cases import file_sha256


def build(annotation_dir: Path, evidence_json: Path, output: Path) -> dict:
    manifest = json.loads((annotation_dir / "manifest.json").read_text())
    labels = json.loads((annotation_dir / "labels.json").read_text())
    audit = json.loads(evidence_json.read_text())
    if labels.get("manifest_sha256") != file_sha256(annotation_dir / "manifest.json"):
        raise ValueError("annotation manifest binding changed")
    by_index = {r["input_index"]: r for r in audit["events"]}
    suggestions = []
    for label in labels["labels"]:
        item = next(r for r in manifest["candidates"] if r["id"] == label["id"])
        m = by_index[item["input_index"]]["measurement"]
        suggestion = "no_restrike" if m["continuous_hypothesis"] else "uncertain"
        reason = (
            "多条可分离泛音均呈连续衰减"
            if suggestion == "no_restrike"
            else "现有真人录音证据不足，不能安全判断"
        )
        suggestions.append(
            {
                **label,
                "judgment": "pending",
                "ai_suggestion": suggestion,
                "ai_reason": reason,
                "ai_evidence_status": m["status"],
                "ai_generated": True,
            }
        )
    report = {
        "schema_version": 1,
        "production_eligible": False,
        "deletion_authorized": False,
        "human_review_required": True,
        "source_manifest_sha256": file_sha256(annotation_dir / "manifest.json"),
        "evidence_sha256": file_sha256(evidence_json),
        "suggestions": suggestions,
        "counts": {
            "total": len(suggestions),
            "uncertain": sum(x["ai_suggestion"] == "uncertain" for x in suggestions),
            "no_restrike": sum(x["ai_suggestion"] == "no_restrike" for x in suggestions),
        },
    }
    output.mkdir(parents=True, exist_ok=False)
    (output / "ai-prelabels.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    (output / "README.md").write_text(
        """# 机器辅助重复音预标注

`judgment` 保持 `pending`，`ai_suggestion` 不是人工结论。
不得直接用于删除音符或修改曲谱。
"""
    )
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("annotation_dir", type=Path)
    p.add_argument("evidence_json", type=Path)
    p.add_argument("output", type=Path)
    a = p.parse_args()
    print(json.dumps(build(a.annotation_dir, a.evidence_json, a.output)["counts"]))
