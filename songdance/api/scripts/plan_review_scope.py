"""Create review priorities from bound artifacts without granting ratings."""

import json
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

from scripts.compare_piano_model_outputs import read_midi
from scripts.human_quality_gate import file_sha256
from scripts.rebuild_review_isolated import SOURCE


def changes(old, new):
    pitch_counts = Counter(n["pitch"] for n in old) != Counter(n["pitch"] for n in new)
    sequence = [n["pitch"] for n in old] != [n["pitch"] for n in new]

    def values(notes, fields):
        return [
            tuple(round(n[f], 6) if isinstance(n[f], float) else n[f] for f in fields)
            for n in notes
        ]

    return {
        "old_count": len(old),
        "new_count": len(new),
        "pitch_counts_changed": pitch_counts,
        "ordered_pitch_sequence_changed": sequence,
        "timing_changed": values(old, ("start_sec", "end_sec"))
        != values(new, ("start_sec", "end_sec")),
        "velocity_changed": values(old, ("velocity",)) != values(new, ("velocity",)),
    }


def visible(path):
    root = ET.parse(path)
    return {
        tag: [ET.tostring(n, encoding="unicode").strip() for n in root.findall(f".//{tag}")]
        for tag in ("time", "key", "clef", "metronome", "sound", "pedal", "words")
    }


def run(root):
    diff_path = root / "differences.json"
    diff = json.loads(diff_path.read_text())
    rows = []
    for row in diff["cases"]:
        old = SOURCE / f"{row['suite']}-review-artifacts" / row["case_id"]
        new = root / f"{row['suite']}-review-artifacts" / row["case_id"]
        for name, hashes in row["files"].items():
            if file_sha256(old / name) != hashes["old"] or file_sha256(new / name) != hashes["new"]:
                raise ValueError("comparison inputs changed")
        result = changes(read_midi(old / "score.mid"), read_midi(new / "score.mid"))
        result["visible_metadata_changed"] = visible(old / "score.musicxml") != visible(
            new / "score.musicxml"
        )
        if result["pitch_counts_changed"] or result["ordered_pitch_sequence_changed"]:
            focus = "音符数量/顺序及完整谱面复核"
        elif result["timing_changed"] or not row["xml_note_rest_timing_equal"]:
            focus = "节奏/时值/小节对齐复核"
        elif result["velocity_changed"] or result["visible_metadata_changed"]:
            focus = "力度或可见谱面标记复核"
        else:
            focus = "已比较内容未变；检查版面与旧评审适用性"
        rows.append(
            {
                "suite": row["suite"],
                "case_id": row["case_id"],
                **result,
                "review_focus": focus,
                "rating": "pending",
                "inputs": row["files"],
            }
        )
    report = {
        "production_eligible": False,
        "difference_report_sha256": file_sha256(diff_path),
        "script_sha256": file_sha256(Path(__file__)),
        "cases": rows,
        "limitation": "review priority only; not approval or exhaustive visual equivalence",
    }
    with (root / "review-scope.json").open("x") as out:
        json.dump(report, out, ensure_ascii=False, indent=2)
    lines = [
        "# 2026-09-22 复评范围",
        "",
        "所有评级保持待确认；清单只安排复查重点，不自动迁移旧评级。",
        "",
        "| 集合 | 样本 | 音符数（旧→新） | 复查重点 |",
        "|---|---|---:|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['suite']} | {row['case_id']} | "
            f"{row['old_count']}→{row['new_count']} | {row['review_focus']} |"
        )
    lines.extend(
        [
            "",
            "06结构固定集仍为旧四音源，不是用户确认的新三音候选；07/10固定集也不自动继承隔离候选评价。",
            "真实录音的音符时序未变，也不等于音质已通过。XML排版、歌词/装饰等未做穷尽比较，不能称为仅元数据变化。",
        ]
    )
    with (root / "review-scope.md").open("x") as out:
        out.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    run(parser.parse_args().directory)
