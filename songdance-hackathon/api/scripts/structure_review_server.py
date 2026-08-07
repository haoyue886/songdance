import json
from datetime import UTC, datetime
from http.server import ThreadingHTTPServer

import pretty_midi

from scripts.human_review_server import HTML as HUMAN_HTML
from scripts.human_review_server import RATINGS, ReviewHandler
from scripts.structure_quality_gate import (
    ARTIFACT_ROOT,
    MANIFEST_PATH,
    REVIEW_PATH,
    compute_structure_suite_fingerprint,
)

HTML = (
    HUMAN_HTML.replace(
        "SongDance · 10 段真实钢琴质量评审",
        "SongDance · Phase 15 结构谱面评审",
    )
    .replace(
        "逐段比较原音与转录；“少量修改”= 30 秒内不超过 10 个明显错音/漏音，且无需重建节拍网格。",
        "逐段检查节拍、和弦、声部、左右手和小节排版；至少 13/16 段需达到可直接使用或少量修改可用。",
    )
    .replace("/files/human-manifest.json", "/files/manifest.json")
    .replace("/files/human-review.json", "/files/structure-review.json")
    .replace("/files/human-generated/", "/files/generated/")
    .replace("/files/human-review-artifacts/", "/files/structure-review-artifacts/")
)


class StructureReviewHandler(ReviewHandler):
    html = HTML

    def _save_review(self, payload: dict) -> dict:
        return save_structure_review(payload)


def save_structure_review(payload: dict) -> dict:
    if payload.get("midi_daw_experience") is not True:
        raise ValueError("请由具备 MIDI/DAW 使用经验的人完成评审")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    expected = [case["id"] for case in manifest["cases"]]
    results = payload["results"]
    if len(results) != len(expected):
        raise ValueError("请完成全部 16 段评级")
    if [case.get("id") for case in results] != expected:
        raise ValueError("评审项目与固定结构集不一致")
    if any(case.get("rating") not in RATINGS for case in results):
        raise ValueError("请完成全部 16 段评级")
    review = json.loads(REVIEW_PATH.read_text(encoding="utf-8"))
    if review.get("suite_fingerprint") != compute_structure_suite_fingerprint():
        raise ValueError("结构回归产物已变化，请重新生成后再评审")
    stored_counts = {
        case["id"]: case.get("raw_midi_note_count") for case in review["results"]
    }
    stored_parsers = {
        case["id"]: case.get("parser_validation") for case in review["results"]
    }
    normalized = [
        {
            "id": case["id"],
            "raw_midi_note_count": _note_count(
                case["id"], stored_counts.get(case["id"])
            ),
            "parser_validation": stored_parsers[case["id"]],
            "rating": case["rating"],
            "notes": str(case.get("notes", ""))[:1000],
        }
        for case in results
    ]
    review["reviewer"] = {
        "midi_daw_experience": True,
        "reviewed_at": datetime.now(UTC).isoformat(),
    }
    review["results"] = normalized
    REVIEW_PATH.write_text(
        json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    usable = sum(case["rating"] != "needs_redo" for case in normalized)
    return {
        "usable_count": usable,
        "total_count": len(normalized),
        "passed": usable >= review["minimum_readable_count"],
    }


def _note_count(case_id: str, stored: object) -> int:
    if type(stored) is int and stored > 0:
        return stored
    parsed = pretty_midi.PrettyMIDI(str(ARTIFACT_ROOT / case_id / "raw.mid"))
    count = sum(len(instrument.notes) for instrument in parsed.instruments)
    if count <= 0:
        raise ValueError(f"{case_id} 的原始 MIDI 不包含音符")
    return count


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 8766), StructureReviewHandler)
    print("SongDance structure review: http://127.0.0.1:8766")
    server.serve_forever()
